"""Best-effort outbound URL policy for project-controlled HTTP clients."""

from __future__ import annotations

import asyncio
import fnmatch
import ipaddress
import os
import socket
import time
import urllib.request
from collections import deque
from urllib.parse import SplitResult, urlsplit


class NetworkPolicyError(ValueError):
    pass


_REQUEST_TIMES: deque[float] = deque()


def configured_allowed_hosts() -> tuple[str, ...]:
    return tuple(
        item.strip().lower().rstrip(".")
        for item in os.getenv("CUTAWAY_PROJECT_NETWORK_HOSTS", "").split(",")
        if item.strip()
    )


def _host_allowed(host: str, patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return False
    return any(pattern == "*" or fnmatch.fnmatch(host, pattern) for pattern in patterns)


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _normalize_ip(address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    parsed = ipaddress.ip_address(address.split("%", 1)[0])
    mapped = getattr(parsed, "ipv4_mapped", None)
    if mapped is not None:
        return mapped
    return parsed


def _is_dangerous(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Loopback and link-local stay forbidden: they reach the local machine and metadata."""
    return bool(
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    )


def _resolved_ips(host: str, port: int) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise NetworkPolicyError("Outbound host could not be resolved.") from exc
    if not addresses:
        raise NetworkPolicyError("Outbound host resolved to no addresses.")
    return [_normalize_ip(address) for address in addresses]


def _prefer_ipv4(
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address],
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    for address in addresses:
        if isinstance(address, ipaddress.IPv4Address):
            return address
    return addresses[0]


def preferred_outbound_ip(host: str, port: int, *, allow_private: bool) -> str:
    """Pick one address to connect to.

    An allowlisted name on this platform can resolve to an internal address as
    well as a public one. A public address is preferred. An internal address is
    used only when the name has no public address. Loopback and link-local
    addresses are never used. An IP literal still has to be public unless
    private destinations were explicitly allowed.
    """
    addresses = _resolved_ips(host, port)
    if allow_private:
        return str(_prefer_ipv4(addresses))
    usable = [address for address in addresses if not _is_dangerous(address)]
    public = [address for address in usable if address.is_global]
    if public:
        return str(_prefer_ipv4(public))
    if usable and not _is_ip_literal(host):
        return str(_prefer_ipv4(usable))
    raise NetworkPolicyError("Private or special-purpose destinations are forbidden.")


def _enforce_rate() -> None:
    maximum = int(os.getenv("CUTAWAY_PROJECT_NETWORK_RPM", "0"))
    if maximum <= 0:
        return
    now = time.monotonic()
    while _REQUEST_TIMES and _REQUEST_TIMES[0] < now - 60:
        _REQUEST_TIMES.popleft()
    if len(_REQUEST_TIMES) >= maximum:
        raise NetworkPolicyError("Outbound request budget exceeded.")
    _REQUEST_TIMES.append(now)


def validate_outbound_url(
    raw_url: str,
    *,
    allowed_hosts: tuple[str, ...] | None = None,
    allow_private: bool | None = None,
    resolve_dns: bool = True,
) -> SplitResult:
    """Validate scheme, destination and resolved addresses immediately before use."""
    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError as exc:
        raise NetworkPolicyError("Malformed outbound URL.") from exc
    if parsed.scheme not in {"http", "https"}:
        raise NetworkPolicyError("Only HTTP and HTTPS outbound URLs are allowed.")
    if parsed.username is not None or parsed.password is not None:
        raise NetworkPolicyError("Credentials in outbound URLs are forbidden.")
    host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
    if not host:
        raise NetworkPolicyError("Outbound URL has no host.")
    if port is not None and port not in {80, 443, 8080}:
        raise NetworkPolicyError("Outbound port is not allowed.")

    patterns = allowed_hosts if allowed_hosts is not None else configured_allowed_hosts()
    patterns = tuple(pattern.lower().rstrip(".") for pattern in patterns)
    if not _host_allowed(host, patterns):
        raise NetworkPolicyError("Outbound host is not allowed for this project.")

    private_allowed = (
        allow_private
        if allow_private is not None
        else os.getenv("CUTAWAY_PROJECT_ALLOW_PRIVATE_NETWORK", "0") == "1"
    )
    if resolve_dns:
        preferred_outbound_ip(
            host,
            port or (443 if parsed.scheme == "https" else 80),
            allow_private=private_allowed,
        )

    _enforce_rate()
    return parsed


async def validate_outbound_url_async(
    raw_url: str,
    *,
    allowed_hosts: tuple[str, ...] | None = None,
    allow_private: bool | None = None,
) -> SplitResult:
    return await asyncio.to_thread(
        validate_outbound_url,
        raw_url,
        allowed_hosts=allowed_hosts,
        allow_private=allow_private,
    )


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-apply the project policy to every urllib redirect."""

    def __init__(
        self,
        *,
        allowed_hosts: tuple[str, ...] | None = None,
        allow_private: bool | None = None,
    ):
        super().__init__()
        self.allowed_hosts = allowed_hosts
        self.allow_private = allow_private

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_outbound_url(
            newurl,
            allowed_hosts=self.allowed_hosts,
            allow_private=self.allow_private,
        )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_urlopen(
    request: str | urllib.request.Request,
    *,
    timeout: float,
    allowed_hosts: tuple[str, ...] | None = None,
    max_bytes: int | None = None,
) -> bytes:
    url = request.full_url if isinstance(request, urllib.request.Request) else request
    validate_outbound_url(url, allowed_hosts=allowed_hosts)
    opener = urllib.request.build_opener(SafeRedirectHandler(allowed_hosts=allowed_hosts))
    with opener.open(request, timeout=timeout) as response:
        declared = response.headers.get("Content-Length")
        if max_bytes is not None and declared and declared.isdigit() and int(declared) > max_bytes:
            raise NetworkPolicyError("Outbound response exceeds the size limit.")
        payload = response.read(None if max_bytes is None else max_bytes + 1)
    if max_bytes is not None and len(payload) > max_bytes:
        raise NetworkPolicyError("Outbound response exceeds the size limit.")
    return payload
