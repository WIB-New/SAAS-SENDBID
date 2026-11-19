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
    await _resolve_checked(url)


async def _resolve_checked(url: str) -> tuple:
    """
    Valide l'URL et retourne (parsed, host, ips_sûres).
    Factorisé pour être réutilisé par l'épinglage d'IP.
    """
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

    safe_ips = set()
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
        safe_ips.add(ip_str)

    return parsed, host, safe_ips


async def resolve_pinned_url(url: str) -> dict:
    """
    Valide l'URL puis la réécrit sur l'IP résolue — empêche le DNS rebinding
    (TOCTOU) où l'hôte re-résoudrait vers une IP privée entre la validation
    et la connexion TCP.

    Retourne {"url": url_épinglée, "headers": {"Host": ...}, "sni_hostname": ...}
    Le Host header et le SNI conservent le vrai hostname (virtual hosting + TLS).
    """
    parsed, host, ips = await _resolve_checked(url)

    ip = sorted(ips)[0]
    # IPv6 doit être encadrée de crochets dans une URL
    netloc = f"[{ip}]" if ":" in ip else ip
    port = parsed.port
    if port and port not in (80, 443):
        netloc = f"{netloc}:{port}"

    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    host_header = host if not port or port in (80, 443) else f"{host}:{port}"
    return {
        "url": f"{parsed.scheme}://{netloc}{path}",
        "headers": {"Host": host_header},
        # SNI = vrai hostname pour la validation du certificat TLS
        "sni_hostname": host if parsed.scheme == "https" else None,
    }
