import ipaddress
import socket
from urllib.parse import urlparse

DISALLOWED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # AWS/GCP/Azure link-local metadata
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("224.0.0.0/4"),     # Multicast
    ipaddress.ip_network("240.0.0.0/4"),     # Reserved
    ipaddress.ip_network("::1/128"),         # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),        # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),       # IPv6 link-local
]


def is_ip_disallowed(ip_str: str) -> bool:
    """Checks whether an IP address belongs to private/loopback/metadata blocks."""
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        return any(ip_obj in network for network in DISALLOWED_NETWORKS)
    except ValueError:
        return True


def validate_safe_url(url: str) -> str:
    """
    Validates that a URL is safe against SSRF attacks.
    Returns normalized clean URL or raises ValueError.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string.")

    parsed = urlparse(url.strip())

    # 1. Scheme validation
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Disallowed scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted.")

    # 2. Host validation
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL does not contain a valid hostname.")

    # Disallow embedded credentials
    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded user credentials are not permitted.")

    # 3. Port validation
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    if port not in (80, 443, 8080, 8443):
        raise ValueError(f"Port {port} is not allowed for career page inspection.")

    # 4. Resolve IP & Check Blacklisted Subnets
    try:
        addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        for _, _, _, _, sockaddr in addr_info:
            ip_addr = sockaddr[0]
            if is_ip_disallowed(ip_addr):
                raise ValueError(f"Target host '{hostname}' resolves to private/disallowed IP: {ip_addr}")
    except socket.gaierror as e:
        raise ValueError(f"Failed to resolve hostname '{hostname}': {str(e)}")

    return url.strip()
