"""Shared URL validation and display redaction."""
import re
from urllib.parse import urlsplit, urlunsplit


def validate_url(url):
    if not isinstance(url, str) or len(url) > 8192 or any(ord(c) < 32 for c in url):
        raise ValueError("Invalid or excessively long URL")
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ValueError("Only HTTP(S) URLs are supported")
    if len(parts.hostname) > 253 or parts.username is not None or parts.password is not None:
        raise ValueError("Invalid hostname or credentials in URL")
    if parts.port not in (None, 80, 443):
        raise ValueError("Only standard web ports are supported")
    return parts


def redact_url(url):
    try:
        parts = urlsplit(url.strip())
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return "[invalid URL]"
        host = parts.hostname
        host = f"[{host}]" if ":" in host else host
        if parts.port:
            host += f":{parts.port}"
        # Remove path parameters too; they are often session identifiers.
        path = "/".join(segment.split(";", 1)[0] for segment in parts.path.split("/"))
        return urlunsplit((parts.scheme, host, path, "", ""))
    except (ValueError, AttributeError):
        return "[invalid URL]"


def redact_text(text):
    return re.sub(r'https?://[^\s<>"\']+', lambda match: redact_url(match[0]), str(text))
