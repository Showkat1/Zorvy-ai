from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import PaymentRequiredError
from app.models.device import DeviceScan
from app.models.investigation import Investigation
from app.models.subscription import Plan, Subscription, SubscriptionStatus
from app.models.user import User
from app.schemas.billing import BillingUsage, PlanLimits, SubscriptionState

UPGRADE_HINT = "Upgrade in Settings to continue."


@dataclass(frozen=True)
class PlanSpec:
    plan: Plan
    name: str
    tagline: str
    price_inr: int
    investigations_per_month: int | None
    device_scans_per_month: int | None
    exports: bool
    api_access: bool


def plan_catalog() -> dict[Plan, PlanSpec]:
    return {
        Plan.FREE: PlanSpec(
            plan=Plan.FREE,
            name="Free",
            tagline="Occasional checks, no card required",
            price_inr=0,
            investigations_per_month=settings.free_investigations_per_month,
            device_scans_per_month=settings.free_device_scans_per_month,
            exports=False,
            api_access=False,
        ),
        Plan.PRO: PlanSpec(
            plan=Plan.PRO,
            name="Pro",
            tagline="For individuals who investigate often",
            price_inr=499,
            investigations_per_month=None,
            device_scans_per_month=settings.pro_device_scans_per_month,
            exports=True,
            api_access=False,
        ),
        Plan.STANDARD: PlanSpec(
            plan=Plan.STANDARD,
            name="Standard",
            tagline="For teams that need API access and unlimited scans",
            price_inr=1999,
            investigations_per_month=None,
            device_scans_per_month=None,
            exports=True,
            api_access=True,
        ),
    }


def plan_limits(spec: PlanSpec) -> PlanLimits:
    return PlanLimits(
        id=spec.plan.value,
        name=spec.name,
        tagline=spec.tagline,
        price_inr=spec.price_inr,
        investigations_per_month=spec.investigations_per_month,
        device_scans_per_month=spec.device_scans_per_month,
        exports=spec.exports,
        api_access=spec.api_access,
    )


def effective_plan(subscription: Subscription | None) -> Plan:
    """A paid plan only counts while the provider says it is active."""
    if (
        subscription is not None
        and subscription.status == SubscriptionStatus.ACTIVE
        and subscription.plan is not Plan.FREE
    ):
        return subscription.plan
    return Plan.FREE


async def get_subscription(db: AsyncSession, user_id: uuid.UUID) -> Subscription | None:
    return await db.scalar(select(Subscription).where(Subscription.user_id == user_id))


def period_bounds(subscription: Subscription | None) -> tuple[datetime, datetime]:
    if (
        subscription is not None
        and subscription.status == SubscriptionStatus.ACTIVE
        and subscription.current_period_start
        and subscription.current_period_end
    ):
        return subscription.current_period_start, subscription.current_period_end

    now = datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start + timedelta(days=32)).replace(day=1)
    return start, end


async def _count_investigations(
    db: AsyncSession,
    user_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> int:
    total = await db.scalar(
        select(func.count())
        .select_from(Investigation)
        .where(
            Investigation.user_id == user_id,
            Investigation.created_at >= start,
            Investigation.created_at < end,
        )
    )
    return int(total or 0)


async def _count_device_scans(
    db: AsyncSession,
    user_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> int:
    total = await db.scalar(
        select(func.count())
        .select_from(DeviceScan)
        .where(
            DeviceScan.user_id == user_id,
            DeviceScan.created_at >= start,
            DeviceScan.created_at < end,
        )
    )
    return int(total or 0)


async def usage_for(
    db: AsyncSession,
    user_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> BillingUsage:
    return BillingUsage(
        investigations=await _count_investigations(db, user_id, start, end),
        device_scans=await _count_device_scans(db, user_id, start, end),
        period_start=start,
        period_end=end,
    )


async def subscription_state(db: AsyncSession, user: User) -> SubscriptionState:
    subscription = await get_subscription(db, user.id)
    plan = effective_plan(subscription)
    spec = plan_catalog()[plan]
    start, end = period_bounds(subscription if plan is not Plan.FREE else None)

    return SubscriptionState(
        plan=plan.value,
        name=spec.name,
        status=subscription.status.value if subscription else "active",
        current_period_end=end,
        cancel_at_period_end=bool(subscription and subscription.cancel_at_period_end),
        billing_enabled=settings.billing_configured,
        limits=plan_limits(spec),
        usage=await usage_for(db, user.id, start, end),
    )


async def check_investigation_quota(db: AsyncSession, user: User) -> None:
    subscription = await get_subscription(db, user.id)
    plan = effective_plan(subscription)
    spec = plan_catalog()[plan]
    limit = spec.investigations_per_month
    if limit is None:
        return

    start, end = period_bounds(subscription if plan is not Plan.FREE else None)
    used = await _count_investigations(db, user.id, start, end)
    if used < limit:
        return

    raise PaymentRequiredError(
        f"You have used all {limit} investigations included in the {spec.name} plan "
        f"this month. {UPGRADE_HINT}",
        details={
            "plan": plan.value,
            "limit": limit,
            "used": used,
            "upgrade_url": "/settings#billing",
        },
    )


async def check_device_scan_quota(db: AsyncSession, user: User) -> None:
    subscription = await get_subscription(db, user.id)
    plan = effective_plan(subscription)
    spec = plan_catalog()[plan]
    limit = spec.device_scans_per_month
    if limit is None:
        return

    start, end = period_bounds(subscription if plan is not Plan.FREE else None)
    used = await _count_device_scans(db, user.id, start, end)
    if used < limit:
        return

    raise PaymentRequiredError(
        f"You have used all {limit} device scans included in the {spec.name} plan "
        f"this month. {UPGRADE_HINT}",
        details={
            "plan": plan.value,
            "limit": limit,
            "used": used,
            "upgrade_url": "/settings#billing",
        },
    )


async def check_export_access(db: AsyncSession, user: User) -> None:
    subscription = await get_subscription(db, user.id)
    spec = plan_catalog()[effective_plan(subscription)]
    if spec.exports:
        return
    raise PaymentRequiredError(
        "Report export is available on the Pro and Standard plans. " + UPGRADE_HINT,
        details={"plan": spec.plan.value, "upgrade_url": "/settings#billing"},
    )


def _plan_from_payload(entity: dict[str, Any]) -> Plan | None:
    plan_id = entity.get("plan_id")
    if plan_id and plan_id == settings.razorpay_plan_pro:
        return Plan.PRO
    if plan_id and plan_id == settings.razorpay_plan_standard:
        return Plan.STANDARD

    notes = entity.get("notes") or {}
    raw = str(notes.get("plan", "")).lower()
    if raw in {Plan.PRO.value, Plan.STANDARD.value}:
        return Plan(raw)
    return None


_STATUS_MAP = {
    "active": SubscriptionStatus.ACTIVE,
    "charged": SubscriptionStatus.ACTIVE,
    "authenticated": SubscriptionStatus.PENDING,
    "created": SubscriptionStatus.PENDING,
    "pending": SubscriptionStatus.PENDING,
    "halted": SubscriptionStatus.HALTED,
    "paused": SubscriptionStatus.HALTED,
    "cancelled": SubscriptionStatus.CANCELLED,
    "completed": SubscriptionStatus.CANCELLED,
    "expired": SubscriptionStatus.EXPIRED,
}

_EVENT_STATUS = {
    "subscription.activated": SubscriptionStatus.ACTIVE,
    "subscription.charged": SubscriptionStatus.ACTIVE,
    "subscription.resumed": SubscriptionStatus.ACTIVE,
    "subscription.halted": SubscriptionStatus.HALTED,
    "subscription.paused": SubscriptionStatus.HALTED,
    "subscription.cancelled": SubscriptionStatus.CANCELLED,
    "subscription.completed": SubscriptionStatus.CANCELLED,
    "subscription.expired": SubscriptionStatus.EXPIRED,
}


def timestamp_from_epoch(value: Any) -> datetime | None:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return datetime.fromtimestamp(seconds, tz=UTC)


async def sync_from_provider(
    db: AsyncSession,
    entity: dict[str, Any],
    *,
    event: str | None = None,
    event_at: datetime | None = None,
) -> Subscription | None:
    """Mirror a Razorpay subscription entity into local state.

    Webhooks can repeat or arrive out of order, so the function is idempotent
    and refuses to overwrite a newer subscription with a stale one.
    """

    subscription_id = entity.get("id")
    if not subscription_id:
        return None

    subscription = await db.scalar(
        select(Subscription).where(Subscription.provider_subscription_id == subscription_id)
    )

    if subscription is None:
        notes = entity.get("notes") or {}
        try:
            user_id = uuid.UUID(str(notes.get("user_id")))
        except (TypeError, ValueError):
            return None
        user = await db.get(User, user_id)
        if user is None:
            return None

        existing = await get_subscription(db, user_id)
        if existing and existing.provider_subscription_id not in (None, subscription_id):
            # A newer checkout already replaced this subscription; ignore the
            # late event instead of rolling the user back to an old plan.
            return None

        subscription = existing or Subscription(user_id=user_id, provider="razorpay")
        subscription.provider_subscription_id = subscription_id
        db.add(subscription)

    if event_at is not None:
        stored = subscription.last_event_at
        if stored is not None:
            if stored.tzinfo is None:
                # SQLite forgets tzinfo; every provider timestamp is UTC.
                stored = stored.replace(tzinfo=UTC)
            if event_at < stored:
                return subscription
        subscription.last_event_at = event_at

    plan = _plan_from_payload(entity)
    if plan is not None:
        subscription.plan = plan

    status = _STATUS_MAP.get(str(entity.get("status", "")).lower())
    if event in _EVENT_STATUS:
        status = _EVENT_STATUS[event]
    if status is not None:
        subscription.status = status

    if entity.get("customer_id"):
        subscription.provider_customer_id = str(entity["customer_id"])
    subscription.current_period_start = timestamp_from_epoch(entity.get("current_start"))
    subscription.current_period_end = timestamp_from_epoch(entity.get("current_end"))
    subscription.cancel_at_period_end = bool(entity.get("cancel_at_cycle_end") or 0)
    if event == "subscription.charged":
        subscription.last_payment_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(subscription)
    return subscription
