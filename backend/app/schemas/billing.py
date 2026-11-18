from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PlanLimits(BaseModel):
    id: str
    name: str
    tagline: str
    price_inr: int
    investigations_per_month: int | None
    device_scans_per_month: int | None
    exports: bool
    api_access: bool


class PlansResponse(BaseModel):
    billing_enabled: bool
    currency: str
    plans: list[PlanLimits]


class BillingUsage(BaseModel):
    investigations: int
    device_scans: int
    period_start: datetime
    period_end: datetime


class SubscriptionState(BaseModel):
    plan: str
    name: str
    status: str
    current_period_end: datetime | None
    cancel_at_period_end: bool
    billing_enabled: bool
    limits: PlanLimits
    usage: BillingUsage


class CheckoutRequest(BaseModel):
    plan: Literal["pro", "standard"]


class CheckoutResponse(BaseModel):
    subscription_id: str
    key_id: str
    short_url: str | None = None
    name: str
    description: str


class PaymentVerification(BaseModel):
    razorpay_payment_id: str = Field(min_length=1)
    razorpay_subscription_id: str = Field(min_length=1)
    razorpay_signature: str = Field(min_length=1)
