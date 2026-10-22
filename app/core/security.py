import ipaddress
import logging
import re
import socket
from typing import Any, Dict, List, Set
from urllib.parse import urlparse

from app.core.errors import SecurityViolationError

logger = logging.getLogger(__name__)

SENSITIVE_KEYS: Set[str] = {
    "api_key",
    "apikey",
    "api-key",
    "secret",
    "secret_key",
    "password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "auth",
    "credentials",
    "private_key",
}

FORBIDDEN_HOSTNAMES: Set[str] = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "169.254.169.254",
    "instance-data",
    "metadata.google.internal",
}


def is_ip_private_or_local(ip_str: str) -> bool:
    """Check if an IP address string belongs to private, loopback, or link-local ranges."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        return False


def validate_destination_url(url: str, allow_local: bool = False) -> str:
    """Validate that a destination URL is safe and not an SSRF attempt against internal services.
    
    Rejects private IP ranges, loopback addresses, and cloud metadata endpoints
    unless `allow_local` is explicitly enabled for controlled local testing.
    """
    if not url or not isinstance(url, str):
        raise SecurityViolationError("Destination URL must be a non-empty string")

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise SecurityViolationError(
            f"Unsupported URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted."
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise SecurityViolationError("Destination URL must contain a valid hostname")

    # If local test instances are permitted, skip local IP rejection
    if allow_local:
        return url.strip()

    # Check known forbidden hostnames
    if hostname in FORBIDDEN_HOSTNAMES or hostname.endswith(".localhost"):
        raise SecurityViolationError(
            f"Destination host '{hostname}' is a local or internal address and is not permitted."
        )

    # Check literal IP address
    if is_ip_private_or_local(hostname):
        raise SecurityViolationError(
            f"Destination IP '{hostname}' belongs to a private or restricted network range."
        )

    # Try resolving hostname to verify underlying IP
    try:
        resolved_ips = socket.getaddrinfo(hostname, None)
        for entry in resolved_ips:
            sockaddr = entry[4]
            ip_str = sockaddr[0]
            if is_ip_private_or_local(ip_str):
                raise SecurityViolationError(
                    f"Destination hostname '{hostname}' resolves to restricted IP '{ip_str}'."
                )
    except socket.gaierror:
        # Host resolution failure during offline or unit test execution
        logger.debug("Could not resolve hostname '%s' during SSRF validation", hostname)

    return url.strip()


def redact_sensitive_data(data: Any) -> Any:
    """Recursively scrub credentials, secrets, and auth tokens from dictionaries or lists.
    
    Returns a sanitized copy safe for logging and error reporting.
    """
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            key_lower = str(key).lower()
            if isinstance(value, (dict, list)):
                sanitized[key] = redact_sensitive_data(value)
            elif any(k in key_lower for k in SENSITIVE_KEYS):
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = value
        return sanitized
    elif isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]
    return data


class RedactingFilter(logging.Filter):
    """Logging filter ensuring API keys and authorization headers are never logged."""

    PATTERNS = [
        re.compile(r"(Api-Key[:=]\s*)([^\s,]+)", re.IGNORECASE),
        re.compile(r"(api_key[:=]\s*)([^\s,]+)", re.IGNORECASE),
        re.compile(r"(Bearer\s+)([^\s,]+)", re.IGNORECASE),
        re.compile(r"(password[:=]\s*)([^\s,]+)", re.IGNORECASE),
        re.compile(r"(secret[:=]\s*)([^\s,]+)", re.IGNORECASE),
        re.compile(r"(token[:=]\s*)([^\s,]+)", re.IGNORECASE),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            for pattern in self.PATTERNS:
                msg = pattern.sub(r"\1***REDACTED***", msg)
            record.msg = msg
        return True
