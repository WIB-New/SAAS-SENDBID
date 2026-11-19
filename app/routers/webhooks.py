"""
StorageHub — Webhooks router
POST   /v1/webhooks                  Enregistrer un endpoint
GET    /v1/webhooks                  Lister ses webhooks
DELETE /v1/webhooks/{id}             Supprimer un webhook
GET    /v1/webhooks/{id}/deliveries  Historique des livraisons
"""
import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime
from app.utils.time import utcnow
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.auth import get_client_from_api_key
from app.config import get_plan
from app.database import get_db
from app.utils.url_safety import resolve_pinned_url

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])
logger = logging.getLogger("storagehub.webhooks")

# Références fortes sur les tâches de livraison — asyncio.create_task()
# sans référence peut être garbage-collecté avant son exécution.
_background_tasks: set = set()


def _spawn(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _validate_webhook_url(url: str):
    """
    Anti-SSRF : un webhook doit pointer vers un endpoint public.
    L'épinglage d'IP à la livraison reste la barrière effective — ici on
    rejette dès l'enregistrement les formats invalides et les IPs privées
    quand le DNS est joignable (fail-open si le DNS est indisponible).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Webhook URL must be a valid http(s):// URL")
    try:
        await resolve_pinned_url(url)
    except HTTPException as exc:
        # Fail-open uniquement si le DNS est INJOIGNABLE ("Cannot resolve
        # remote host") — une IP privée/réservée doit rejeter même à
        # l'enregistrement. La livraison re-vérifiera de toute façon.
        if "cannot resolve" in str(exc.detail).lower():
            return
        raise


# ──────────────────────────────────────────────
#  CRUD
# ──────────────────────────────────────────────
@router.post("", response_model=schemas.WebhookResponse, status_code=201,
             summary="Enregistrer un endpoint webhook")
async def create_webhook(
    body: schemas.WebhookCreate,
    client: models.Client = Depends(get_client_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    if not get_plan(client.plan).get("webhooks", False):
        raise HTTPException(
            status_code=403,
            detail="Webhooks require the Starter plan or higher.",
        )
    await _validate_webhook_url(body.url)
    wh = models.Webhook(
        id=str(uuid.uuid4()),
        client_id=client.id,
        url=body.url,
        secret=body.secret,
        events=body.events,
    )
    db.add(wh)
    await db.commit()
    await db.refresh(wh)
    return wh


@router.get("", response_model=list[schemas.WebhookResponse],
            summary="Lister les webhooks du client")
async def list_webhooks(
    client: models.Client = Depends(get_client_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.Webhook)
        .where(models.Webhook.client_id == client.id)
        .order_by(models.Webhook.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/{webhook_id}", summary="Supprimer un webhook")
async def delete_webhook(
    webhook_id: str,
    client: models.Client = Depends(get_client_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.Webhook).where(
            models.Webhook.id == webhook_id,
            models.Webhook.client_id == client.id,
        )
    )
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(wh)
    await db.commit()
    return {"id": webhook_id, "deleted": True}


@router.get("/{webhook_id}/deliveries", response_model=list[schemas.WebhookDeliveryResponse],
            summary="Historique des livraisons d'un webhook")
async def webhook_deliveries(
    webhook_id: str,
    client: models.Client = Depends(get_client_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    # Vérifier que le webhook appartient au client
    result = await db.execute(
        select(models.Webhook).where(
            models.Webhook.id == webhook_id,
            models.Webhook.client_id == client.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Webhook not found")

    result = await db.execute(
        select(models.WebhookDelivery)
        .where(models.WebhookDelivery.webhook_id == webhook_id)
        .order_by(models.WebhookDelivery.attempted_at.desc())
        .limit(50)
    )
    return result.scalars().all()


# ──────────────────────────────────────────────
#  Utilitaire de livraison (appelé depuis le router files)
# ──────────────────────────────────────────────
def _sign_payload(payload: str, secret: str) -> str:
    """HMAC-SHA256 du payload avec le secret configuré."""
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


# Backoff (secondes) entre les tentatives de livraison
_DELIVERY_BACKOFF = [0, 2, 10, 30]


async def _deliver_webhook(wh_id: str, wh_url: str, wh_secret: Optional[str],
                           event: str, payload_str: str):
    """
    Livraison en tâche de fond avec retries exponentiels — n'ajoute plus
    de latence à la requête d'upload. Utilise sa propre session DB.
    """
    from app.database import AsyncSessionLocal

    headers = {
        "Content-Type":       "application/json",
        "X-StorageHub-Event": event,
        "X-Delivery-ID":      str(uuid.uuid4()),
    }
    if wh_secret:
        headers["X-StorageHub-Signature"] = f"sha256={_sign_payload(payload_str, wh_secret)}"

    status_code, error_msg, success, attempts = None, None, False, 0
    async with httpx.AsyncClient(timeout=5.0) as client_http:
        for i, delay in enumerate(_DELIVERY_BACKOFF):
            if delay:
                await asyncio.sleep(delay)
            attempts = i + 1
            try:
                # Épinglage d'IP à CHAQUE tentative : l'hôte est re-résolu et
                # re-validé — un rebinding DNS vers une IP privée entre
                # l'enregistrement et la livraison est bloqué.
                pinned = await resolve_pinned_url(wh_url)
                req_headers = dict(headers)
                req_headers["Host"] = pinned["headers"]["Host"]
                kwargs = {"extensions": {"sni_hostname": pinned["sni_hostname"]}} \
                    if pinned["sni_hostname"] else {}
                resp = await client_http.post(
                    pinned["url"], content=payload_str,
                    headers=req_headers, **kwargs,
                )
                status_code = resp.status_code
                success = 200 <= status_code < 300
                if success:
                    break
            except HTTPException as exc:
                error_msg = str(exc.detail)[:500]
            except Exception as exc:
                error_msg = str(exc)[:500]

    try:
        async with AsyncSessionLocal() as session:
            session.add(models.WebhookDelivery(
                webhook_id=wh_id,
                event=event,
                payload=payload_str[:4000],
                response_status=status_code,
                attempts=attempts,
                success=success,
                error=error_msg,
            ))
            await session.commit()
    except Exception as exc:
        logger.error(f"Failed to record webhook delivery {wh_id}: {exc}")

    if not success:
        logger.warning(f"Webhook {wh_id} delivery failed after {attempts} attempts: {error_msg or status_code}")


async def fire_event(event: str, data: dict, client_id: Optional[str], db: AsyncSession):
    """
    Envoie l'événement à tous les webhooks actifs du client en arrière-plan.
    Retourne immédiatement — la livraison (avec retries) se fait en tâche de fond.
    """
    if not client_id:
        return

    result = await db.execute(
        select(models.Webhook).where(
            models.Webhook.client_id == client_id,
            models.Webhook.is_active == True,
        )
    )
    webhooks = result.scalars().all()

    if not webhooks:
        return

    payload_str = json.dumps({
        "event":       event,
        "occurred_at": utcnow().isoformat() + "Z",
        "data":        data,
    })

    for wh in webhooks:
        if wh.listens_to(event):
            _spawn(_deliver_webhook(wh.id, wh.url, wh.secret, event, payload_str))
