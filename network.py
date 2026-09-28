"""Loopback forward proxy enforcing public destinations for Chrome and Requests.

HTTPS uses CONNECT without interception: certificates are still verified by the
client. DNS answers are checked and the connection uses the checked numeric IP,
so a second DNS lookup cannot rebind the connection to a private destination.
"""
import ipaddress
import select
import socket
import socketserver
import threading
import time
from urllib.parse import urlsplit
from security import validate_url


def public_addresses(host, port):
    if len(host) > 253 or port not in (80, 443):
        raise ValueError("Destination is not a supported public web endpoint")
    answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not answers:
        raise ValueError("No destination addresses")
    for _, _, _, _, endpoint in answers:
        ip = ipaddress.ip_address(endpoint[0].split("%", 1)[0])
        if not ip.is_global or ip.is_multicast or ip.is_reserved:
            raise ValueError("Private and special-use destinations are blocked")
    return answers


def connect_public(host, port, timeout=10):
    last_error = None
    for family, kind, proto, _, endpoint in public_addresses(host, port):
        sock = socket.socket(family, kind, proto)
        sock.settimeout(timeout)
        try:
            sock.connect(endpoint)  # checked IP, not hostname
            return sock
        except OSError as exc:
            sock.close()
            last_error = exc
    raise OSError("Unable to connect to public destination") from last_error


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        upstream = None
        connected = False
        try:
            self.request.settimeout(10)
            header = bytearray()
            expires = time.monotonic() + 10
            # Avoid buffered reads which can consume TLS bytes after CONNECT.
            while not header.endswith(b"\r\n\r\n"):
                if len(header) > 65536 or time.monotonic() > expires:
                    raise ValueError("Proxy request headers exceeded limits")
                chunk = self.request.recv(1)
                if not chunk:
                    return
                header.extend(chunk)
            lines = header.decode("iso-8859-1").split("\r\n")
            method, target, version = lines[0].split(" ", 2)
            if method == "CONNECT":
                parts = validate_url("https://" + target)
                upstream = connect_public(parts.hostname, parts.port or 443)
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            else:
                parts = validate_url(target)
                if parts.scheme != "http" or method not in ("GET", "HEAD", "POST", "OPTIONS", "PUT", "DELETE", "PATCH"):
                    raise ValueError("Unsupported proxy request")
                upstream = connect_public(parts.hostname, parts.port or 80)
                path = parts.path or "/"
                if parts.query:
                    path += "?" + parts.query
                forwarded = [f"{method} {path} HTTP/1.1", f"Host: {parts.netloc}"]
                for line in lines[1:]:
                    if line and line.split(":", 1)[0].lower() not in ("host", "connection", "proxy-connection", "proxy-authorization"):
                        forwarded.append(line)
                forwarded.append("Connection: close")
                upstream.sendall(("\r\n".join(forwarded) + "\r\n\r\n").encode("iso-8859-1"))
            connected = True
            sockets = [self.request, upstream]
            last_data = time.monotonic()
            started = last_data
            while (not self.server.stopping.is_set()
                   and not self.server.cancel_event.is_set()
                   and time.monotonic() - started < self.server.connection_deadline
                   and time.monotonic() - last_data < 90):
                readable, _, _ = select.select(sockets, [], [], 0.2)
                for source in readable:
                    chunk = source.recv(65536)
                    if not chunk:
                        return
                    target_socket = upstream if source is self.request else self.request
                    target_socket.sendall(chunk)
                    last_data = time.monotonic()
        except (OSError, ValueError):
            if not connected:
                try:
                    self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                except OSError:
                    pass
        finally:
            if upstream:
                upstream.close()


class PublicNetworkProxy:
    def __init__(self, cancel_event=None, connection_deadline=90):
        self.server = _Server(("127.0.0.1", 0), _Handler)
        self.server.stopping = threading.Event()
        self.server.cancel_event = cancel_event if cancel_event is not None else threading.Event()
        self.server.connection_deadline = connection_deadline
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.stopping.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
