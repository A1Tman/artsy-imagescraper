from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from config import ScraperConfig
from downloads import download_groups
from image_selection import ImageGroup
from network import connect_public, public_addresses
from resources import ResourceManager
from security import redact_text, redact_url, validate_url


def answer(ip, port=443):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))


class NetworkPolicyTests(unittest.TestCase):
    def test_private_loopback_linklocal_multicast_and_mixed_dns_are_denied(self):
        for addresses in (["127.0.0.1"], ["10.0.0.1"], ["169.254.169.254"], ["::1"],
                          ["fc00::1"], ["100.64.0.1"], ["224.0.0.1"],
                          ["93.184.216.34", "192.168.1.1"]):
            with self.subTest(addresses=addresses), patch("network.socket.getaddrinfo", return_value=[answer(ip) for ip in addresses]):
                with self.assertRaises(ValueError):
                    public_addresses("untrusted.example", 443)

    def test_connection_is_pinned_to_checked_ip_not_resolved_twice(self):
        with patch("network.socket.getaddrinfo", return_value=[answer("93.184.216.34")]) as resolve, patch("network.socket.socket") as factory:
            connected = connect_public("example.com", 443)
            self.assertIs(connected, factory.return_value)
            factory.return_value.connect.assert_called_once_with(("93.184.216.34", 443))
            resolve.assert_called_once()

    def test_session_cannot_use_ambient_credentials_or_bypass_proxy(self):
        manager = ResourceManager(ScraperConfig())
        self.addCleanup(manager.close_all)
        with manager.get_session() as session:
            self.assertFalse(session.trust_env)
            self.assertEqual(session.proxies["http"], session.proxies["https"])
            self.assertTrue(session.proxies["http"].startswith("http://127.0.0.1:"))

    def test_browser_uses_proxy_even_for_loopback_and_disables_udp_bypass(self):
        manager = ResourceManager(ScraperConfig())
        self.addCleanup(manager.close_all)
        with patch("resources.ChromeDriverManager") as installer, patch("resources.webdriver.Chrome") as chrome:
            installer.return_value.install.return_value = "driver.exe"
            with manager.get_driver():
                options = chrome.call_args.kwargs["options"]
                self.assertIn("--proxy-bypass-list=<-loopback>", options.arguments)
                self.assertIn("--disable-quic", options.arguments)
                self.assertTrue(any(v.startswith("--proxy-server=") for v in options.arguments))

    def test_public_to_private_redirect_is_blocked_before_second_connection(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                seen.append(self.path)
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1/private.png")
                self.send_header("Content-Length", "0")
                self.end_headers()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        original_resolver = socket.getaddrinfo
        def resolver(host, port, *args, **kwargs):
            if host == "public.example":
                return [answer("93.184.216.34", port)]
            return original_resolver(host, port, *args, **kwargs)
        def fixture_connector(host, port, timeout=10):
            public_addresses(host, port)  # Real policy; only public.example maps to fixture.
            self.assertEqual(host, "public.example")
            return socket.create_connection(server.server_address, timeout)
        config = ScraperConfig(min_image_size=1)
        manager = ResourceManager(config)
        try:
            with tempfile.TemporaryDirectory() as directory, patch("network.socket.getaddrinfo", side_effect=resolver), patch("network.connect_public", side_effect=fixture_connector):
                count = download_groups([ImageGroup(["http://public.example/start"])], directory, "work", config, manager)
                self.assertEqual(count, 0)
                self.assertEqual(seen, ["/start"])
                self.assertEqual(list(Path(directory).iterdir()), [])
        finally:
            manager.close_all()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class DisplaySafetyTests(unittest.TestCase):
    def test_userinfo_tokens_and_path_parameters_are_redacted(self):
        url = "https://user:password@example.com/art;session=secret?token=secret#secret"
        self.assertEqual(redact_url(url), "https://example.com/art")
        self.assertEqual(redact_text("Loading " + url), "Loading https://example.com/art")

    def test_malformed_or_credential_urls_cannot_start_network_requests(self):
        for url in ("file:///c:/private", "https://user:pass@example.com", "https://example.com:8080", "https://" + "a" * 254 + ".com", "https://example.com/\n"):
            with self.subTest(url=url), self.assertRaises(ValueError): validate_url(url)

    def test_gui_displays_untrusted_markup_as_literal_text(self):
        code = '''
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from PyQt5.QtWidgets import QApplication, QPlainTextEdit
from types import SimpleNamespace
from gui import ImageScraperApp
app=QApplication([])
widget=QPlainTextEdit()
payload='<b>Title</b><img src="file:///DUMMY.png">'
ImageScraperApp.add_log_message(SimpleNamespace(log_output=widget),payload)
assert payload in widget.toPlainText()
'''
        subprocess.run([sys.executable, "-c", code], check=True, timeout=15, capture_output=True)


if __name__ == "__main__":
    unittest.main()
