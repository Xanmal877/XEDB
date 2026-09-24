"""SSRF guard for MusicCog playback URLs."""

import ipaddress
import urllib.parse


def is_blocked_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname
    if not host:
        return True
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local or ip.is_multicast or ip.is_unspecified

