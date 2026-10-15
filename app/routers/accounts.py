"""
StorageHub — Client accounts router (SaaS self-service)
POST   /v1/accounts/register        Créer un compte → credentials API
POST   /v1/accounts/login           Session JWT dashboard
GET    /v1/accounts/me              Profil + usage + clés
POST   /v1/accounts/keys            Générer une nouvelle clé API
GET    /v1/accounts/keys            Lister les clés
DELETE /v1/accounts/keys/{id}       Révoquer une clé
POST   /v1/accounts/plan            Changer de plan
GET    /v1/plans                    Catalogue public des plans
"""
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.auth import get_current_client, get_client_from_api_key
from app.config import PLANS, get_plan
from app.database import get_db
from app.utils.security import (
    create_session_token,
    generate_api_credentials,
    hash_password,
    verify_password,
)

router = APIRouter(tags=["accounts"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── Schemas ──
class RegisterIn(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    company_name: Optional[str] = Field(None, max_length=255)
    plan: Optional[str] = Field("free", description="Plan d'abonnement: free|starter|pro|business")


class LoginIn(BaseModel):
    email: str
    password: str


class KeyCreateIn(BaseModel):
    name: str = Field("API key", max_length=120)


class PlanIn(BaseModel):
    plan: str


# ── Helpers ──
async def _usage(db: AsyncSession, client_id: str) -> dict:
    """Storage usage for a client (bytes + count, per category)."""
    result = await db.execute(
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
    rows = result.all()
    per_cat = {r[0]: {"files": r[1], "bytes": r[2]} for r in rows}
    return {
        "total_bytes": sum(r[2] for r in rows),
        "total_files": sum(r[1] for r in rows),
        "by_category": per_cat,
    }


def _key_out(k: models.ApiKey, reveal: bool = False) -> dict:
    return {
        "id": k.id,
        "name": k.name,
        "api_key": k.api_key if reveal else k.api_key[:10] + "…" + k.api_key[-4:],
        "hmac_secret": k.hmac_secret if reveal else "••••••••",
        "plan": k.plan,
        "revoked": k.revoked,
        "created_at": k.created_at,
        "last_used_at": k.last_used_at,
    }


def _client_out(c: models.Client, usage: dict) -> dict:
    plan = get_plan(c.plan)
    return {
        "id": c.id,
        "email": c.email,
        "company_name": c.company_name,
        "plan": c.plan,
        "plan_details": plan,
        "created_at": c.created_at,
        "usage": {
            **usage,
            "storage_limit_bytes": plan["storage_mb"] * 1024 * 1024,
            "storage_used_percent": round(
                usage["total_bytes"] / (plan["storage_mb"] * 1024 * 1024) * 100, 2
            ),
        },
    }


# ── Public: plans catalogue ──
@router.get("/v1/plans", summary="Catalogue des plans d'abonnement")
async def list_plans():
    return {
        pid: {
            "name": p["name"],
            "price_monthly_eur": p["price_monthly"],
            "storage_mb": p["storage_mb"],
            "max_keys": p["max_keys"],
            "signed_url_max_ttl": p["signed_url_max_ttl"],
            "support": p["support"],
        }
        for pid, p in PLANS.items()
    }


# ── Register ──
@router.post(
    "/v1/accounts/register",
    status_code=201,
    summary="Créer un compte — retourne les credentials API (affichés une seule fois)",
)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    result = await db.execute(
        select(models.Client).where(models.Client.email == email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    plan_id = body.plan if body.plan in PLANS else "free"
    client = models.Client(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password(body.password),
        company_name=body.company_name,
        plan=plan_id,
    )
    db.add(client)

    api_key, hmac_secret = generate_api_credentials()
    key = models.ApiKey(
        id=str(uuid.uuid4()),
        client_id=client.id,
        name="Clé principale",
        api_key=api_key,
        hmac_secret=hmac_secret,
        plan=plan_id,
    )
    db.add(key)
    await db.commit()

    token = create_session_token(client.id)
    return {
        "client_id":   client.id,
        "email":       client.email,
        "plan":        client.plan,
        "plan_details": get_plan(client.plan),
        "api_key":     api_key,
        "hmac_secret": hmac_secret,
        "access_token": token,
        "token_type":  "bearer",
        "storage_quota": f"{get_plan(client.plan)['storage_mb']} MB",
        "warning": "Conservez ces credentials en lieu sûr — le secret ne sera plus affiché.",
    }


# ── Login ──
@router.post("/v1/accounts/login", summary="Connexion dashboard — retourne un JWT")
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.Client).where(
            models.Client.email == body.email.strip().lower()
        )
    )
    client = result.scalar_one_or_none()
    if not client or not verify_password(body.password, client.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not client.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    return {
        "access_token": create_session_token(client.id),
        "token_type": "bearer",
        "client": {"id": client.id, "email": client.email, "plan": client.plan},
    }


# ── Me (profile + usage) ──
@router.get("/v1/accounts/me", summary="Profil + statistiques d'usage")
async def me(
    client: models.Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    usage = await _usage(db, client.id)
    result = await db.execute(
        select(models.ApiKey).where(models.ApiKey.client_id == client.id)
    )
    keys = result.scalars().all()
    out = _client_out(client, usage)
    out["api_keys"] = [_key_out(k) for k in keys]
    return out


# ── API keys management ──
@router.post("/v1/accounts/keys", status_code=201, summary="Générer une nouvelle clé API")
async def create_key(
    body: KeyCreateIn,
    client: models.Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    plan = get_plan(client.plan)
    result = await db.execute(
        select(func.count(models.ApiKey.id)).where(
            models.ApiKey.client_id == client.id,
            models.ApiKey.revoked == False,
        )
    )
    active_keys = result.scalar() or 0
    if active_keys >= plan["max_keys"]:
        raise HTTPException(
            status_code=403,
            detail=f"Plan '{plan['name']}': maximum {plan['max_keys']} clé(s) active(s). Passez à un plan supérieur.",
        )

    api_key, hmac_secret = generate_api_credentials()
    key = models.ApiKey(
        id=str(uuid.uuid4()),
        client_id=client.id,
        name=body.name.strip() or "API key",
        api_key=api_key,
        hmac_secret=hmac_secret,
        plan=client.plan,
    )
    db.add(key)
    await db.commit()
    return {
        **_key_out(key, reveal=True),
        "warning": "Le hmac_secret n'est affiché qu'une seule fois.",
    }


@router.delete("/v1/accounts/keys/{key_id}", summary="Révoquer une clé API")
async def revoke_key(
    key_id: str,
    client: models.Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.ApiKey).where(
            models.ApiKey.id == key_id,
            models.ApiKey.client_id == client.id,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    key.revoked = True
    await db.commit()
    return {"id": key_id, "revoked": True}


# ── Plan change (self-serve, no payment gateway) ──
@router.post("/v1/accounts/plan", summary="Changer de plan d'abonnement")
async def change_plan(
    body: PlanIn,
    client: models.Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    if body.plan not in PLANS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan. Must be one of: {', '.join(PLANS)}",
        )
    client.plan = body.plan
    await db.commit()
    return {"plan": client.plan, "plan_details": get_plan(client.plan)}


# ── Stats analytiques ──────────────────────────────────────────────────────────
@router.get("/v1/accounts/stats", summary="Statistiques d'usage analytiques")
async def get_stats(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client: models.Client = Depends(get_client_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne des statistiques détaillées : total fichiers, taille, uploads par jour,
    répartition par catégorie, fichiers chiffrés, thumbnails générés.
    """
    from sqlalchemy import cast, Date, and_
    from datetime import date

    base_q = select(models.StoredFile).where(
        models.StoredFile.client_id == client.id,
    )

    # Fichiers actifs
    active_result = await db.execute(
        select(
            models.StoredFile.category,
            func.count(models.StoredFile.id),
            func.coalesce(func.sum(models.StoredFile.size_bytes), 0),
        )
        .where(
            models.StoredFile.client_id == client.id,
            models.StoredFile.is_deleted == False,
        )
        .group_by(models.StoredFile.category)
    )
    rows = active_result.all()
    by_category = {
        r[0]: {"count": r[1], "size_bytes": r[2]}
        for r in rows
    }
    total_active = sum(r[1] for r in rows)
    total_size = sum(r[2] for r in rows)

    # Fichiers supprimés
    del_result = await db.execute(
        select(func.count(models.StoredFile.id)).where(
            models.StoredFile.client_id == client.id,
            models.StoredFile.is_deleted == True,
        )
    )
    total_deleted = del_result.scalar() or 0

    # Fichiers chiffrés
    enc_result = await db.execute(
        select(func.count(models.StoredFile.id)).where(
            models.StoredFile.client_id == client.id,
            models.StoredFile.is_encrypted == True,
            models.StoredFile.is_deleted == False,
        )
    )
    encrypted_count = enc_result.scalar() or 0

    # Thumbnails générés
    thumb_result = await db.execute(
        select(func.count(models.StoredFile.id)).where(
            models.StoredFile.client_id == client.id,
            models.StoredFile.thumbnail_path.isnot(None),
            models.StoredFile.is_deleted == False,
        )
    )
    thumb_count = thumb_result.scalar() or 0

    # Uploads par jour (30 derniers jours)
    from sqlalchemy import text as sa_text
    daily_result = await db.execute(
        sa_text(
            "SELECT date(created_at) as day, COUNT(*) as cnt, COALESCE(SUM(size_bytes),0) as sz "
            "FROM stored_files "
            "WHERE client_id = :cid AND is_deleted = 0 "
            "GROUP BY day ORDER BY day DESC LIMIT 30"
        ),
        {"cid": client.id},
    )
    uploads_by_day = [
        {"date": str(r[0]), "count": r[1], "size_bytes": r[2]}
        for r in daily_result.all()
    ]

    return {
        "total_files":      total_active + total_deleted,
        "active_files":     total_active,
        "deleted_files":    total_deleted,
        "total_size_bytes": total_size,
        "by_category":      by_category,
        "uploads_by_day":   uploads_by_day,
        "encrypted_files":  encrypted_count,
        "thumbnail_count":  thumb_count,
        "plan":             client.plan,
        "plan_details":     get_plan(client.plan),
    }


# ── Usage temps réel (quota) ──────────────────────────────────────────────────
@router.get("/v1/accounts/usage", summary="Quota et usage temps réel")
async def get_usage(
    client: models.Client = Depends(get_client_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne l'état du quota en temps réel avec alertes.
    Idéal pour intégrer une barre de progression dans votre application.
    """
    result = await db.execute(
        select(
            func.count(models.StoredFile.id),
            func.coalesce(func.sum(models.StoredFile.size_bytes), 0),
        ).where(
            models.StoredFile.client_id == client.id,
            models.StoredFile.is_deleted == False,
        )
    )
    row = result.one()
    total_files = row[0]
    total_bytes = row[1]

    plan = get_plan(client.plan)
    quota_bytes = plan["storage_mb"] * 1024 * 1024
    used_pct = round(total_bytes / quota_bytes * 100, 2) if quota_bytes > 0 else 0
    free_bytes = max(0, quota_bytes - total_bytes)

    # Prochains paliers
    plan_ids = list(PLANS.keys())
    current_idx = plan_ids.index(client.plan) if client.plan in plan_ids else 0
    next_plan = PLANS.get(plan_ids[current_idx + 1]) if current_idx + 1 < len(plan_ids) else None

    return {
        "plan":            client.plan,
        "plan_name":       plan["name"],
        "price_monthly":   f"{plan['price_monthly']}€/mois",

        "storage": {
            "used_bytes":   total_bytes,
            "used_label":   _fmt_bytes(total_bytes),
            "quota_bytes":  quota_bytes,
            "quota_label":  _fmt_bytes(quota_bytes),
            "free_bytes":   free_bytes,
            "free_label":   _fmt_bytes(free_bytes),
            "used_percent": used_pct,
        },

        "files":          total_files,
        "max_file_size":  f"{plan['max_file_size_mb']} MB",
        "max_api_keys":   plan["max_keys"],
        "webhooks":       plan["webhooks"],
        "encryption":     plan["encryption"],
        "bulk_upload":    plan["bulk_upload"],

        "alerts": {
            "quota_warning": used_pct >= 80,
            "quota_critical": used_pct >= 95,
            "quota_full":    total_bytes >= quota_bytes,
            "message": (
                f"Stockage plein — passez au plan {next_plan['name'] if next_plan else 'supérieur'}."
                if total_bytes >= quota_bytes else
                f"Attention : {used_pct:.0f}% du quota utilisé."
                if used_pct >= 80 else None
            ),
        },

        "upgrade": {
            "available": next_plan is not None,
            "next_plan":   next_plan["name"] if next_plan else None,
            "next_price":  f"{next_plan['price_monthly']}€/mois" if next_plan else None,
            "next_quota":  _fmt_bytes(next_plan["storage_mb"] * 1024 * 1024) if next_plan else None,
            "upgrade_url": "POST /v1/accounts/plan",
        },
    }


def _fmt_bytes(b: int) -> str:
    if b >= 1024 ** 3: return f"{b / 1024**3:.2f} GB"
    if b >= 1024 ** 2: return f"{b / 1024**2:.2f} MB"
    if b >= 1024:      return f"{b / 1024:.1f} KB"
    return f"{b} B"
