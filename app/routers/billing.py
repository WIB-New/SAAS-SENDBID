"""
StorageHub — Billing router (Stripe, optionnel)
POST /v1/billing/checkout   Créer une session Stripe Checkout (JWT client)
POST /v1/billing/webhook    Réception Stripe (signature vérifiée) → plan

Inactif tant que STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET / STRIPE_PRICE_*
ne sont pas configurés — les endpoints répondent alors 503.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.auth import get_current_client
from app.config import settings
from app.database import get_db

router = APIRouter(prefix="/v1/billing", tags=["billing"])
logger = logging.getLogger("storagehub.billing")

_PLAN_PRICES = {
    "starter":  "stripe_price_starter",
    "pro":      "stripe_price_pro",
    "business": "stripe_price_business",
}


def _stripe():
    """Import paresseux — stripe est une dépendance optionnelle."""
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Billing is not configured on this server")
    try:
        import stripe
    except ImportError:
        raise HTTPException(status_code=503, detail="Stripe package not installed")
    stripe.api_key = settings.stripe_secret_key
    return stripe


class CheckoutRequest(BaseModel):
    plan: str


@router.post("/checkout", summary="Créer une session Stripe Checkout")
async def create_checkout(
    body: CheckoutRequest,
    client: models.Client = Depends(get_current_client),
):
    stripe = _stripe()

    if body.plan not in _PLAN_PRICES:
        raise HTTPException(status_code=400, detail=f"Invalid plan '{body.plan}'")
    price_id = getattr(settings, _PLAN_PRICES[body.plan], "")
    if not price_id:
        raise HTTPException(status_code=400, detail=f"No Stripe price configured for plan '{body.plan}'")

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            client_reference_id=client.id,
            customer_email=client.email,
            metadata={"client_id": client.id, "plan": body.plan},
            # Propagé sur la Subscription → retrouvable à l'annulation
            subscription_data={"metadata": {"client_id": client.id}},
            success_url=f"{settings.base_url}/ui/dashboard.html?billing=success",
            cancel_url=f"{settings.base_url}/ui/dashboard.html?billing=cancel",
        )
    except Exception as exc:
        logger.error(f"Stripe checkout failed for client {client.id}: {exc}")
        raise HTTPException(status_code=502, detail="Payment provider error")

    return {"checkout_url": session.url, "session_id": session.id, "plan": body.plan}


@router.post("/webhook", summary="Webhook Stripe — provisionne le plan payé",
             include_in_schema=False)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    stripe = _stripe()
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        client_id = session_obj.get("metadata", {}).get("client_id")
        plan = session_obj.get("metadata", {}).get("plan")
        if client_id and plan in _PLAN_PRICES:
            await _apply_plan(db, client_id, plan)
            logger.info(f"Client {client_id} upgraded to '{plan}' via Stripe")

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        client_id = sub.get("metadata", {}).get("client_id")
        if client_id:
            await _apply_plan(db, client_id, "free")
            logger.info(f"Client {client_id} downgraded to 'free' (subscription cancelled)")

    return {"received": True}


async def _apply_plan(db: AsyncSession, client_id: str, plan: str):
    """Assigne un plan et resynchronise le snapshot des clés actives."""
    result = await db.execute(
        select(models.Client).where(models.Client.id == client_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        return
    client.plan = plan
    keys = await db.execute(
        select(models.ApiKey).where(
            models.ApiKey.client_id == client.id,
            models.ApiKey.revoked == False,
        )
    )
    for k in keys.scalars().all():
        k.plan = plan
    await db.commit()
