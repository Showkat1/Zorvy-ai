from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import (
    AppError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.core.rate_limit import rate_limit
from app.models.subscription import Plan, Subscription, SubscriptionStatus
from app.models.user import User
from app.schemas.billing import (
    CheckoutRequest,
    CheckoutResponse,
    PaymentVerification,
    PlansResponse,
    SubscriptionState,
)
from app.services import razorpay
from app.services.billing import (
    effective_plan,
    get_subscription,
    plan_catalog,
    plan_limits,
    subscription_state,
    sync_from_provider,
    timestamp_from_epoch,
)

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.get("/plans", response_model=PlansResponse)
async def list_plans() -> PlansResponse:
    return PlansResponse(
        billing_enabled=settings.billing_configured,
        currency=settings.billing_currency,
        plans=[plan_limits(spec) for spec in plan_catalog().values()],
    )


@router.get("/subscription", response_model=SubscriptionState)
async def read_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionState:
    return await subscription_state(db, user)


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    dependencies=[Depends(rate_limit("billing", limit=10))],
)
async def create_checkout(
    payload: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    if not settings.billing_configured:
        raise AppError(
            "Billing is not configured on this deployment yet.",
            status_code=503,
            code="billing_not_configured",
        )

    plan = Plan(payload.plan)
    existing = await get_subscription(db, user.id)
    if (
        existing is not None
        and existing.status == SubscriptionStatus.ACTIVE
        and effective_plan(existing) is not Plan.FREE
        and existing.provider_subscription_id
    ):
        raise ConflictError(
            "You already have an active subscription. Cancel it before switching plans."
        )

    spec = plan_catalog()[plan]
    plan_id = (
        settings.razorpay_plan_pro if plan is Plan.PRO else settings.razorpay_plan_standard
    )

    try:
        customer_id = existing.provider_customer_id if existing else None
        if not customer_id:
            customer = await razorpay.create_customer(
                name=user.full_name,
                email=user.email,
                user_id=str(user.id),
            )
            customer_id = customer["id"]

        remote = await razorpay.create_subscription(
            plan_id=plan_id,
            customer_id=customer_id,
            user_id=str(user.id),
            email=user.email,
            plan=plan.value,
        )
    except razorpay.RazorpayError as exc:
        raise AppError(
            f"Could not start checkout: {exc}",
            status_code=502,
            code="billing_provider_error",
        ) from exc

    subscription = existing or Subscription(user_id=user.id, provider="razorpay")
    subscription.plan = plan
    subscription.status = SubscriptionStatus.PENDING
    subscription.provider = "razorpay"
    subscription.provider_customer_id = customer_id
    subscription.provider_subscription_id = remote["id"]
    subscription.cancel_at_period_end = False
    db.add(subscription)
    await db.commit()

    return CheckoutResponse(
        subscription_id=remote["id"],
        key_id=settings.razorpay_key_id,
        short_url=remote.get("short_url"),
        name=f"Zorvy {spec.name}",
        description=f"Zorvy {spec.name} â€” monthly subscription",
    )


@router.post("/verify", response_model=SubscriptionState)
async def verify_payment(
    payload: PaymentVerification,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionState:
    if not settings.billing_configured:
        raise AppError(
            "Billing is not configured on this deployment yet.",
            status_code=503,
            code="billing_not_configured",
        )

    valid = razorpay.verify_payment_signature(
        payment_id=payload.razorpay_payment_id,
        subscription_id=payload.razorpay_subscription_id,
        signature=payload.razorpay_signature,
    )
    if not valid:
        raise ValidationError("The payment signature did not verify")

    try:
        remote = await razorpay.fetch_subscription(payload.razorpay_subscription_id)
    except razorpay.RazorpayError as exc:
        raise AppError(
            f"Could not confirm the subscription: {exc}",
            status_code=502,
            code="billing_provider_error",
        ) from exc

    subscription = await sync_from_provider(db, remote, event="subscription.charged")
    if subscription is None or subscription.user_id != user.id:
        raise NotFoundError("Subscription not found")

    return await subscription_state(db, user)


@router.post(
    "/cancel",
    response_model=SubscriptionState,
    dependencies=[Depends(rate_limit("billing", limit=10))],
)
async def cancel_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionState:
    if not settings.billing_configured:
        raise AppError(
            "Billing is not configured on this deployment yet.",
            status_code=503,
            code="billing_not_configured",
        )

    subscription = await get_subscription(db, user.id)
    if (
        subscription is None
        or not subscription.provider_subscription_id
        or effective_plan(subscription) is Plan.FREE
    ):
        raise ConflictError("You do not have an active paid subscription")

    try:
        remote = await razorpay.cancel_subscription(subscription.provider_subscription_id)
    except razorpay.RazorpayError as exc:
        raise AppError(
            f"Could not cancel the subscription: {exc}",
            status_code=502,
            code="billing_provider_error",
        ) from exc

    await sync_from_provider(db, remote)
    return await subscription_state(db, user)


@router.post("/webhook", include_in_schema=False)
async def razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")
    if not razorpay.verify_webhook_signature(body, signature):
        raise UnauthorizedError("Invalid webhook signature")

    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise ValidationError("Invalid webhook payload") from exc

    event = str(payload.get("event", ""))
    entity = (
        (payload.get("payload") or {}).get("subscription", {}).get("entity") or {}
    )
    if not entity:
        return {"status": "ignored"}

    subscription = await sync_from_provider(
        db,
        entity,
        event=event,
        event_at=timestamp_from_epoch(payload.get("created_at")),
    )
    return {"status": "ok" if subscription else "ignored"}
