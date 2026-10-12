"""
StorageHub — Health & monitoring endpoints
GET /health        — readiness probe (DB + disk)
GET /v1/ping       — liveness probe (défini dans main.py)
GET /v1/metrics    — métriques format Prometheus
GET /v1/info       — informations de service pour intégration
"""
import time
from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.schemas import HealthResponse
from app.utils.storage import get_disk_usage_by_category

router = APIRouter(tags=["monitoring"])
_start_time = time.time()


@router.get("/health", response_model=HealthResponse, summary="Readiness probe — état complet du service")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Vérifie la disponibilité du service, de la base de données et de l'espace disque.
    Utilisé par les load-balancers et les systèmes de monitoring.

    - **status: ok** → service pleinement opérationnel
    - **status: degraded** → service partiellement dégradé (DB down ou espace disque critique)
    """
    checks = {}

    # ── Check DB
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok", "latency_ms": None}
        db_status = "ok"
    except Exception as e:
        checks["database"] = {"status": "error", "detail": str(e)}
        db_status = f"error: {e}"

    # ── Check disk
    disk_data = get_disk_usage_by_category()
    disk_info = disk_data.pop("_disk", {})
    checks["disk"] = {
        "status": "alert" if disk_info.get("alert") else "ok",
        "percent": disk_info.get("percent"),
    }

    # ── Check storage dirs
    upload_root = settings.upload_path
    for cat in ["avatars", "kyc", "receipts"]:
        cat_path = upload_root / cat
        checks[f"dir_{cat}"] = {"status": "ok" if cat_path.exists() else "missing"}

    overall = "ok"
    if db_status != "ok":
        overall = "degraded"
    elif disk_info.get("alert"):
        overall = "degraded"

    return HealthResponse(
        status=overall,
        version="1.0.0",
        env=settings.app_env,
        uptime_seconds=round(time.time() - _start_time, 1),
        db=db_status,
        disk_usage=disk_info,
        categories=disk_data,
        checks=checks,
    )


@router.get(
    "/v1/metrics",
    response_class=PlainTextResponse,
    summary="Métriques format Prometheus",
    tags=["monitoring"],
)
async def metrics():
    """Métriques compatibles Prometheus/Grafana."""
    disk_data = get_disk_usage_by_category()
    disk_info = disk_data.pop("_disk", {})

    lines = [
        "# HELP storagehub_disk_used_gb Disk space used in GB",
        "# TYPE storagehub_disk_used_gb gauge",
        f"storagehub_disk_used_gb {disk_info.get('used_gb', 0)}",
        "# HELP storagehub_disk_free_gb Disk space free in GB",
        "# TYPE storagehub_disk_free_gb gauge",
        f"storagehub_disk_free_gb {disk_info.get('free_gb', 0)}",
        "# HELP storagehub_disk_percent_used Disk usage percentage",
        "# TYPE storagehub_disk_percent_used gauge",
        f"storagehub_disk_percent_used {disk_info.get('percent', 0)}",
        "# HELP storagehub_uptime_seconds Service uptime in seconds",
        "# TYPE storagehub_uptime_seconds counter",
        f"storagehub_uptime_seconds {round(time.time() - _start_time, 1)}",
    ]
    for cat, info in disk_data.items():
        lines += [
            f'# HELP storagehub_category_size_mb Size in MB for category {cat}',
            f'# TYPE storagehub_category_size_mb gauge',
            f'storagehub_category_size_mb{{category="{cat}"}} {info.get("size_mb", 0)}',
            f'# HELP storagehub_category_file_count File count for category {cat}',
            f'# TYPE storagehub_category_file_count gauge',
            f'storagehub_category_file_count{{category="{cat}"}} {info.get("file_count", 0)}',
        ]
    return "\n".join(lines)


@router.get("/v1/info", tags=["monitoring"], summary="Informations de service pour intégration")
async def service_info():
    """
    Retourne les informations statiques du service utiles à l'intégration :
    catégories acceptées, limites de taille, types MIME autorisés, TTL des URLs signées.
    """
    return {
        "service":  "storagehub",
        "version":  "1.0.0",
        "env":      settings.app_env,
        "categories": {
            cat: {
                "public":       cat == "avatars",
                "max_size_mb":  settings.max_sizes_bytes[cat] // (1024 * 1024),
                "allowed_mimes": settings.allowed_mimes[cat],
            }
            for cat in ["avatars", "kyc", "receipts"]
        },
        "signed_url_default_ttl_seconds": settings.signed_url_ttl,
        "cdn_base_url": settings.cdn_base_url,
        "auth": {
            "required_header":    "X-API-Key",
            "hmac_header":        "X-Signature",
            "timestamp_header":   "X-Timestamp",
            "user_id_header":     "X-User-Id",
            "user_role_header":   "X-User-Role",
            "hmac_required_in_production": True,
        },
        "response_envelope": {
            "success_shape": {"success": True, "request_id": "uuid", "data": "..."},
            "error_shape":   {"success": False, "request_id": "uuid", "error": "message", "code": "ERROR_CODE"},
        },
    }
