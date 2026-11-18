"""Add subscriptions.

Revision ID: 0003_subscriptions
Revises: 0002_device_scans
Create Date: 2026-11-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_subscriptions"
down_revision: str | None = "0002_device_scans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("plan", sa.String(length=16), nullable=False, server_default="free"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="razorpay"),
        sa.Column("provider_customer_id", sa.String(length=64), nullable=True),
        sa.Column("provider_subscription_id", sa.String(length=64), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("last_payment_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subscriptions_user_id"), "subscriptions", ["user_id"], unique=True)
    op.create_index(
        op.f("ix_subscriptions_provider_subscription_id"),
        "subscriptions",
        ["provider_subscription_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
