"""Tests for MusicCog URL blocking (SSRF guard)."""

from Cogs.music_url import is_blocked_url


def test_blocks_private_ip():
    assert is_blocked_url("http://127.0.0.1/x")
    assert is_blocked_url("http://10.0.0.5/x")
    assert is_blocked_url("http://192.168.1.1/x")
    assert is_blocked_url("http://[::1]/x")


def test_blocks_localhost_hostname():
    assert is_blocked_url("http://localhost/x")
    assert is_blocked_url("https://localhost.localdomain:8080/x")


def test_blocks_missing_host():
    assert is_blocked_url("not-a-url")
    assert is_blocked_url("http:///nohost")


def test_allows_public_https():
    assert not is_blocked_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert not is_blocked_url("https://youtu.be/dQw4w9WgXcQ")
