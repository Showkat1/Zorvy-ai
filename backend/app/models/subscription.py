from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Plan(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    STANDARD = "standard"


class SubscriptionStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    HALTED = "halted"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Subscription(UUIDMixin, TimestampMixin, Base):
    """A user's paid plan state, mirrored from the payment provider.

    Free users have no row; the absence of an active paid subscription is what
    the quota service treats as the Free plan. Keeping only paid state in this
    table means a webhook is the single source of truth for entitlement.
    """

    __tablename__ = "subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    plan: Mapped[Plan] = mapped_column(
        Enum(Plan, native_enum=False, length=16),
        default=Plan.FREE,
        nullable=False,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, native_enum=False, length=16),
        default=SubscriptionStatus.PENDING,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), default="razorpay", nullable=False)
    provider_customer_id: Mapped[str | None] = mapped_column(String(64))
    provider_subscription_id: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        index=True,
    )
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_payment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship("User", back_populates="subscription")  # noqa: F821
