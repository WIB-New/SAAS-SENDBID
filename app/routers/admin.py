"""
StorageHub — Admin router (master key uniquement)
Accès réservé au propriétaire du service (utilise la master API key du .env).
Permet de voir tous les clients, leur usage, les fichiers globaux, les incidents.

GET  /v1/admin/overview      Vue d'ensemble du service
GET  /v1/admin/clients       Liste tous les clients inscrits
GET  /v1/admin/clients/{id}  Détail d'un client
GET  /v1/admin/files         Tous les fichiers (paginé)
GET  /v1/admin/logs          Derniers logs d'audit
POST /v1/admin/clients/{id}/suspend    Suspendre un compte
POST /v1/admin/clients/{id}/activate   Réactiver un compte
"""
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.config import PLANS, get_plan, settings
from app.database import get_db
from app.utils.storage import get_disk_usage_by_category

router = APIRouter(prefix="/v1/admin", tags=["admin"])

_start_time = time.time()


async def _require_master_key(db: AsyncSession = Depends(get_db)):
    """
    Ce router ne passe pas par le système de clés client —
    il est monté en second dans main.py avec la dépendance master key.
    Cette fonction est appelée depuis les dépendances de chaque endpoint.
    """
    pass  # L'auth est vérifiée dans main.py via _admin_auth_dep


# ──────────────────────────────────────────────
#  GET /v1/admin/overview
# ──────────────────────────────────────────────
@router.get("/overview", summary="Vue d'ensemble globale du service")
async def admin_overview(db: AsyncSession = Depends(get_db)):
    """
    Dashboard admin : tous les clients, fichiers, stockage total, revenus estimés.
    Accès réservé à la master API key.
    """
    # Clients
    client_result = await db.execute(select(func.count(models.Client.id)))
    total_clients = client_result.scalar() or 0

    active_result = await db.execute(
        select(func.count(models.Client.id)).where(models.Client.is_active == True)
    )
    active_clients = active_result.scalar() or 0

    # Fichiers
    files_result = await db.execute(
        select(
            func.count(models.StoredFile.id),
            func.coalesce(func.sum(models.StoredFile.size_bytes), 0),
        ).where(models.StoredFile.is_deleted == False)
    )
    files_row = files_result.one()
    total_files = files_row[0]
    total_bytes = files_row[1]

    # Fichiers supprimés (en attente de purge)
    del_result = await db.execute(
        select(func.count(models.StoredFile.id)).where(models.StoredFile.is_deleted == True)
    )
    deleted_pending = del_result.scalar() or 0

    # Répartition par plan
    plan_result = await db.execute(
        select(models.Client.plan, func.count(models.Client.id))
        .group_by(models.Client.plan)
    )
    plan_distribution = {r[0]: r[1] for r in plan_result.all()}

    # Revenu mensuel estimé
    mrr = sum(
        PLANS.get(plan_id, {}).get("price_monthly", 0) * count
        for plan_id, count in plan_distribution.items()
    )

    # Activité récente (24h)
    recent_result = await db.execute(
        text("SELECT COUNT(*) FROM stored_files WHERE created_at >= datetime('now','-1 day')")
    )
    uploads_24h = recent_result.scalar() or 0

    # Webhooks
    wh_result = await db.execute(
        select(func.count(models.Webhook.id)).where(models.Webhook.is_active == True)
    )
    active_webhooks = wh_result.scalar() or 0

    # Disque
    disk = get_disk_usage_by_category()
    disk_info = disk.get("_disk", {})

    return {
        "service":  "StorageHub",
        "version":  "2.0.0",
        "uptime_hours": round((time.time() - _start_time) / 3600, 2),
        "timestamp": datetime.utcnow().isoformat() + "Z",

        "clients": {
            "total":    total_clients,
            "active":   active_clients,
            "inactive": total_clients - active_clients,
            "by_plan":  plan_distribution,
        },

        "storage": {
            "total_files":       total_files,
            "total_size_bytes":  total_bytes,
            "total_size_label":  _fmt_bytes(total_bytes),
            "deleted_pending_purge": deleted_pending,
            "disk_total":        disk_info.get("total_gb", "N/A"),
            "disk_used_pct":     disk_info.get("percent", "N/A"),
            "disk_alert":        disk_info.get("alert", False),
        },

        "activity": {
            "uploads_last_24h":  uploads_24h,
            "active_webhooks":   active_webhooks,
        },

        "revenue": {
            "mrr_eur":          mrr,
            "mrr_label":        f"{mrr}€/mois (estimé)",
            "note":             "Basé sur les plans actifs — sans passerelle de paiement",
        },
    }


# ──────────────────────────────────────────────
#  GET /v1/admin/clients
# ──────────────────────────────────────────────
@router.get("/clients", summary="Liste tous les clients inscrits")
async def list_clients(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    plan: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(models.Client)
    if plan:
        query = query.where(models.Client.plan == plan)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(
        query.order_by(models.Client.created_at.desc())
        .offset((page - 1) * limit).limit(limit)
    )
    clients = result.scalars().all()

    items = []
    for c in clients:
        # Usage par client
        usage_r = await db.execute(
            select(
                func.count(models.StoredFile.id),
                func.coalesce(func.sum(models.StoredFile.size_bytes), 0),
            ).where(
                models.StoredFile.client_id == c.id,
                models.StoredFile.is_deleted == False,
            )
        )
        ur = usage_r.one()
        plan_info = get_plan(c.plan)
        quota = plan_info["storage_mb"] * 1024 * 1024
        items.append({
            "id":            c.id,
            "email":         c.email,
            "company_name":  c.company_name,
            "plan":          c.plan,
            "plan_name":     plan_info["name"],
            "is_active":     c.is_active,
            "created_at":    c.created_at,
            "files":         ur[0],
            "bytes_used":    ur[1],
            "bytes_label":   _fmt_bytes(ur[1]),
            "quota_pct":     round(ur[1] / quota * 100, 1) if quota else 0,
        })

    return {
        "items":  items,
        "total":  total,
        "page":   page,
        "limit":  limit,
        "pages":  max(1, (total + limit - 1) // limit),
    }


# ──────────────────────────────────────────────
#  GET /v1/admin/clients/{id}
# ──────────────────────────────────────────────
@router.get("/clients/{client_id}", summary="Détail d'un client")
async def get_client(client_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.Client).where(models.Client.id == client_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Clés API
    keys_r = await db.execute(
        select(models.ApiKey).where(models.ApiKey.client_id == client_id)
    )
    keys = keys_r.scalars().all()

    # Fichiers par catégorie
    files_r = await db.execute(
        select(
            models.StoredFile.category,
            func.count(models.StoredFile.id),
            func.coalesce(func.sum(models.StoredFile.size_bytes), 0),
        )
        .where(
            models.StoredFile.client_id == client_id,
            models.StoredFile.is_deleted == False,
        )
        .group_by(models.StoredFile.category)
    )
    by_cat = {r[0]: {"files": r[1], "bytes": r[2], "label": _fmt_bytes(r[2])} for r in files_r.all()}

    # Webhooks
    wh_r = await db.execute(
        select(models.Webhook).where(models.Webhook.client_id == client_id)
    )
    webhooks = [{
        "id": w.id, "url": w.url, "events": w.events, "is_active": w.is_active
    } for w in wh_r.scalars().all()]

    plan_info = get_plan(client.plan)
    quota = plan_info["storage_mb"] * 1024 * 1024
    total_bytes = sum(v["bytes"] for v in by_cat.values())

    return {
        "id":            client.id,
        "email":         client.email,
        "company_name":  client.company_name,
        "plan":          client.plan,
        "plan_details":  plan_info,
        "is_active":     client.is_active,
        "created_at":    client.created_at,
        "storage": {
            "used_bytes":    total_bytes,
            "used_label":    _fmt_bytes(total_bytes),
            "quota_bytes":   quota,
            "quota_label":   _fmt_bytes(quota),
            "quota_pct":     round(total_bytes / quota * 100, 1) if quota else 0,
            "by_category":   by_cat,
        },
        "api_keys": [{
            "id":         k.id,
            "name":       k.name,
            "key_prefix": k.api_key[:10] + "…",
            "revoked":    k.revoked,
            "created_at": k.created_at,
            "last_used":  k.last_used_at,
        } for k in keys],
        "webhooks": webhooks,
    }


# ──────────────────────────────────────────────
#  GET /v1/admin/files
# ──────────────────────────────────────────────
@router.get("/files", summary="Tous les fichiers stockés (paginé)")
async def list_all_files(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    client_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(models.StoredFile).where(models.StoredFile.is_deleted == False)
    if category:
        query = query.where(models.StoredFile.category == category)
    if client_id:
        query = query.where(models.StoredFile.client_id == client_id)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(
        query.order_by(models.StoredFile.created_at.desc())
        .offset((page - 1) * limit).limit(limit)
    )
    files = result.scalars().all()

    return {
        "items": [{
            "file_id":    f.id,
            "client_id":  f.client_id,
            "owner":      f.owner_user_id,
            "category":   f.category,
            "mime_type":  f.mime_type,
            "size":       _fmt_bytes(f.size_bytes),
            "size_bytes": f.size_bytes,
            "encrypted":  f.is_encrypted,
            "has_thumb":  bool(f.thumbnail_path),
            "tags":       f.tags,
            "version":    f.version,
            "created_at": f.created_at,
        } for f in files],
        "total":  total,
        "page":   page,
        "limit":  limit,
        "pages":  max(1, (total + limit - 1) // limit),
    }


# ──────────────────────────────────────────────
#  GET /v1/admin/logs
# ──────────────────────────────────────────────
@router.get("/logs", summary="Derniers logs d'audit")
async def audit_logs(
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.AuditLog)
        .order_by(models.AuditLog.timestamp.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return [{
        "id":        l.id,
        "file_id":   l.file_id,
        "user":      l.requester_user_id,
        "role":      l.requester_role,
        "action":    l.action,
        "ip":        l.ip_address,
        "timestamp": l.timestamp,
        "success":   l.success,
    } for l in logs]


# ──────────────────────────────────────────────
#  POST /v1/admin/clients/{id}/suspend
# ──────────────────────────────────────────────
@router.post("/clients/{client_id}/suspend", summary="Suspendre un compte client")
async def suspend_client(client_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Client).where(models.Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    client.is_active = False
    await db.commit()
    return {"id": client_id, "is_active": False, "message": "Account suspended"}


# ──────────────────────────────────────────────
#  POST /v1/admin/clients/{id}/activate
# ──────────────────────────────────────────────
@router.post("/clients/{client_id}/activate", summary="Réactiver un compte client")
async def activate_client(client_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Client).where(models.Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    client.is_active = True
    await db.commit()
    return {"id": client_id, "is_active": True, "message": "Account activated"}


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────
def _fmt_bytes(b: int) -> str:
    if b >= 1024 ** 3: return f"{b / 1024**3:.2f} GB"
    if b >= 1024 ** 2: return f"{b / 1024**2:.2f} MB"
    if b >= 1024:      return f"{b / 1024:.1f} KB"
    return f"{b} B"
