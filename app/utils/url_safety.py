"""
StorageHub — Protection SSRF pour /v1/files/from-url
Bloque les URLs pointant vers des adresses privées, loopback, link-local,
réservées ou multicast (metadata cloud, réseau interne, localhost...).

À valider à chaque hop de redirection — une redirection vers 169.254.169.254
est un vecteur d'attaque classique.
"""
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import HTTPException


def _ip_forbidden(ip) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def _resolve_ips(host: str) -> set[str]:
    loop = asyncio.get_event_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return {info[4][0] for info in infos}


async def validate_remote_url(url: str) -> None:
    """Lève HTTPException(400) si l'URL est dangereuse ou invalide."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="URL must use http:// or https://")

    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="Invalid URL: missing host")

    # Hôte littéral IPv4/IPv6, ou résolution DNS du nom de domaine
    try:
        ips = {str(ipaddress.ip_address(host))}
    except ValueError:
        try:
            ips = await _resolve_ips(host)
        except Exception:
            raise HTTPException(status_code=400, detail="Cannot resolve remote host")

    for ip_str in ips:
        try:
            # Supprimer un éventuel scope ID IPv6 (fe80::1%eth0)
            ip = ipaddress.ip_address(ip_str.split("%")[0])
        except ValueError:
            continue
        if _ip_forbidden(ip):
            raise HTTPException(
                status_code=400,
                detail="URL resolves to a private, loopback or reserved address",
            )
