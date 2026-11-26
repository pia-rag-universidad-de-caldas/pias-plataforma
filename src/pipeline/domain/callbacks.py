"""Where the pipeline may POST an actor's notice (feature 040). The URL comes from whoever calls PUT /actors, so the
server must not be a way to reach what only it can reach: only the allowed hosts and, even among them, never a link
local, metadata, multicast or unspecified address. Without network: resolving a name is the notifier's."""

import ipaddress
from urllib.parse import urlsplit

from pipeline.config import CALLBACK_HOSTS

_SCHEMES = frozenset({"http", "https"})
# Cloud metadata services outside the link local range (Alibaba Cloud; AWS over IPv6).
_METADATA = frozenset({"100.100.100.200", "fd00:ec2::254"})


def allowed_hosts(extra: str | None) -> frozenset[str]:
    """The hosts of the configuration plus those of `extra` (comma separated), lowercase."""
    added = (host.strip().lower() for host in (extra or "").split(","))
    return frozenset(CALLBACK_HOSTS) | {host for host in added if host}


def address_problem(address: str) -> str | None:
    """Why no notice may go to this IP address; None if it may, or if it isn't an IP address but a name."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_loopback:
        return None
    if str(ip) in _METADATA or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return f"{address} is a forbidden address (link local, metadata, multicast or unspecified)"
    return None


def url_problem(url: str, hosts: frozenset[str]) -> str | None:
    """Why this URL can't be a callback; None if it can."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
        _ = parts.port  # a port that isn't a number only fails when it is read
    except ValueError as error:
        return f"it isn't a valid URL: {error}"
    if parts.scheme not in _SCHEMES:
        return "only http and https are allowed"
    if not host:
        return "it has no host"
    if parts.username is not None or parts.password is not None:
        return "it can't carry credentials"
    problem = address_problem(host)
    if problem is not None:
        return problem
    if host not in hosts:
        return f"the host {host} isn't allowed; allowed: {', '.join(sorted(hosts))}"
    return None
