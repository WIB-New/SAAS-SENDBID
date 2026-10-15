"""
StorageHub — Webhooks router
POST   /v1/webhooks                  Enregistrer un endpoint
GET    /v1/webhooks                  Lister ses webhooks
DELETE /v1/webhooks/{id}             Supprimer un webhook
GET    /v1/webhooks/{id}/deliveries  Historique des livraisons
"""
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.auth import get_current_client
from app.database import get_db

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])
logger = logging.getLogger("storagehub.webhooks")


# ──────────────────────────────────────────────
#  CRUD
# ──────────────────────────────────────────────
@router.post("", response_model=schemas.WebhookResponse, status_code=201,
             summary="Enregistrer un endpoint webhook")
async def create_webhook(
    body: schemas.WebhookCreate,
    client: models.Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
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
    client: models.Client = Depends(get_current_client),
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
    client: models.Client = Depends(get_current_client),
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
    client: models.Client = Depends(get_current_client),
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


async def fire_event(event: str, data: dict, client_id: Optional[str], db: AsyncSession):
    """
    Envoie l'événement à tous les webhooks actifs du client.
    Appelé de façon asynchrone depuis le router files — les erreurs sont silencieuses.
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

    payload_obj = {
        "event":      event,
        "occurred_at": datetime.utcnow().isoformat() + "Z",
        "data":       data,
    }
    payload_str = json.dumps(payload_obj)

    for wh in webhooks:
        if not wh.listens_to(event):
            continue

        headers = {
            "Content-Type":     "application/json",
            "X-StorageHub-Event": event,
            "X-Delivery-ID":    str(uuid.uuid4()),
        }
        if wh.secret:
            headers["X-StorageHub-Signature"] = f"sha256={_sign_payload(payload_str, wh.secret)}"

        status_code, error_msg, success = None, None, False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client_http:
                resp = await client_http.post(wh.url, content=payload_str, headers=headers)
                status_code = resp.status_code
                success = 200 <= status_code < 300
        except Exception as exc:
            error_msg = str(exc)[:500]

        delivery = models.WebhookDelivery(
            webhook_id=wh.id,
            event=event,
            payload=payload_str[:4000],
            response_status=status_code,
            success=success,
            error=error_msg,
        )
        db.add(delivery)

    await db.commit()
