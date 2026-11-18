from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from fastapi.testclient import TestClient


def _signed(body: bytes) -> str:
    return hmac.new(
        settings.razorpay_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()


def _subscription_event(
    *,
    subscription_id: str,
    user_id: str,
    event: str = "subscription.charged",
    status: str = "active",
    plan_id: str | None = None,
    plan: str = "pro",
    created_at: int | None = None,
) -> tuple[bytes, str]:
    now = int(datetime.now(UTC).timestamp())
    payload = {
        "event": event,
        "created_at": created_at if created_at is not None else now,
        "payload": {
            "subscription": {
                "entity": {
                    "id": subscription_id,
                    "plan_id": plan_id or settings.razorpay_plan_pro,
                    "status": status,
                    "customer_id": "cust_test",
                    "current_start": now,
                    "current_end": now + 30 * 24 * 3600,
                    "cancel_at_cycle_end": 0,
                    "notes": {"user_id": user_id, "plan": plan},
                }
            }
        },
    }
    body = json.dumps(payload).encode()
    return body, _signed(body)


def _post_webhook(client: TestClient, body: bytes, signature: str) -> dict:
    response = client.post(
        "/api/v1/billing/webhook",
        content=body,
        headers={"content-type": "application/json", "x-razorpay-signature": signature},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _activate(client: TestClient, auth_user: dict, *, plan: str = "pro") -> str:
    subscription_id = f"sub_test_{uuid.uuid4().hex[:10]}"
    plan_id = (
        settings.razorpay_plan_standard if plan == "standard" else settings.razorpay_plan_pro
    )
    body, signature = _subscription_event(
        subscription_id=subscription_id,
        user_id=auth_user["id"],
        plan_id=plan_id,
        plan=plan,
    )
    _post_webhook(client, body, signature)
    return subscription_id


def test_plans_catalogue_lists_three_tiers(client: TestClient) -> None:
    response = client.get("/api/v1/billing/plans")
    assert response.status_code == 200
    body = response.json()
    assert body["billing_enabled"] is True
    plans = {plan["id"]: plan for plan in body["plans"]}
    assert set(plans) == {"free", "pro", "standard"}
    assert plans["free"]["price_inr"] == 0
    assert plans["free"]["investigations_per_month"] == 5
    assert plans["pro"]["price_inr"] == 499
    assert plans["pro"]["exports"] is True
    assert plans["standard"]["price_inr"] == 1999
    assert plans["standard"]["api_access"] is True


def test_new_account_starts_on_the_free_plan(
    client: TestClient, auth: dict[str, str]
) -> None:
    response = client.get("/api/v1/billing/subscription", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "free"
    assert body["status"] == "active"
    assert body["limits"]["investigations_per_month"] == 5
    assert body["usage"]["investigations"] == 0
    assert body["cancel_at_period_end"] is False


def test_free_plan_blocks_the_sixth_investigation(
    client: TestClient, auth: dict[str, str]
) -> None:
    for index in range(5):
        response = client.post(
            "/api/v1/investigations",
            headers=auth,
            data={
                "input_type": "message",
                "text": f"Pay PKR 5,000 verification fee immediately to keep account {index}.",
            },
        )
        assert response.status_code == 202, response.text

    blocked = client.post(
        "/api/v1/investigations",
        headers=auth,
        data={
            "input_type": "message",
            "text": "Your account will be blocked. Send your OTP immediately.",
        },
    )
    assert blocked.status_code == 402
    error = blocked.json()["error"]
    assert error["code"] == "payment_required"
    assert error["details"]["limit"] == 5
    assert error["details"]["upgrade_url"] == "/settings#billing"


def test_free_plan_cannot_export_a_report(
    client: TestClient, auth: dict[str, str]
) -> None:
    created = client.post(
        "/api/v1/investigations",
        headers=auth,
        data={
            "input_type": "message",
            "text": "Your HBL account is blocked. Verify at https://secure-hbl.example.com.",
        },
    )
    assert created.status_code == 202
    investigation_id = created.json()["id"]

    export = client.get(f"/api/v1/investigations/{investigation_id}/export", headers=auth)
    assert export.status_code == 402
    assert export.json()["error"]["code"] == "payment_required"


def test_webhook_activates_and_cancels_a_subscription(
    client: TestClient, auth: dict[str, str], auth_user: dict
) -> None:
    subscription_id = f"sub_test_{uuid.uuid4().hex[:10]}"
    body, signature = _subscription_event(
        subscription_id=subscription_id,
        user_id=auth_user["id"],
    )

    activated = client.post(
        "/api/v1/billing/webhook",
        content=body,
        headers={"content-type": "application/json", "x-razorpay-signature": signature},
    )
    assert activated.status_code == 200
    assert activated.json() == {"status": "ok"}

    state = client.get("/api/v1/billing/subscription", headers=auth)
    assert state.status_code == 200
    body = state.json()
    assert body["plan"] == "pro"
    assert body["status"] == "active"
    assert body["limits"]["investigations_per_month"] is None
    assert body["limits"]["exports"] is True
    period_end = datetime.fromisoformat(body["current_period_end"])
    if period_end.tzinfo is None:
        # SQLite drops tzinfo; treat the stored value as UTC.
        period_end = period_end.replace(tzinfo=UTC)
    assert period_end > datetime.now(UTC)

    cancel_body, cancel_signature = _subscription_event(
        subscription_id=subscription_id,
        user_id=auth_user["id"],
        event="subscription.cancelled",
        status="cancelled",
    )
    cancelled = client.post(
        "/api/v1/billing/webhook",
        content=cancel_body,
        headers={
            "content-type": "application/json",
            "x-razorpay-signature": cancel_signature,
        },
    )
    assert cancelled.status_code == 200

    downgraded = client.get("/api/v1/billing/subscription", headers=auth).json()
    assert downgraded["plan"] == "free"
    assert downgraded["status"] == "cancelled"
    assert downgraded["limits"]["investigations_per_month"] == 5


def test_webhook_rejects_an_invalid_signature(client: TestClient) -> None:
    body, _ = _subscription_event(
        subscription_id="sub_test_invalid",
        user_id=str(uuid.uuid4()),
    )
    response = client.post(
        "/api/v1/billing/webhook",
        content=body,
        headers={"content-type": "application/json", "x-razorpay-signature": "bad"},
    )
    assert response.status_code == 401


def test_webhook_ignores_an_unknown_user(client: TestClient) -> None:
    body, signature = _subscription_event(
        subscription_id="sub_test_unknown",
        user_id=str(uuid.uuid4()),
    )
    response = client.post(
        "/api/v1/billing/webhook",
        content=body,
        headers={"content-type": "application/json", "x-razorpay-signature": signature},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


def test_active_subscription_has_a_renewal_window(
    client: TestClient, auth: dict[str, str], auth_user: dict
) -> None:
    subscription_id = f"sub_test_{uuid.uuid4().hex[:10]}"
    now = datetime.now(UTC)
    payload = {
        "event": "subscription.charged",
        "payload": {
            "subscription": {
                "entity": {
                    "id": subscription_id,
                    "plan_id": settings.razorpay_plan_standard,
                    "status": "active",
                    "customer_id": "cust_test",
                    "current_start": int(now.timestamp()),
                    "current_end": int((now + timedelta(days=30)).timestamp()),
                    "notes": {"user_id": auth_user["id"], "plan": "standard"},
                }
            }
        },
    }
    body = json.dumps(payload).encode()
    response = client.post(
        "/api/v1/billing/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "x-razorpay-signature": _signed(body),
        },
    )
    assert response.status_code == 200

    state = client.get("/api/v1/billing/subscription", headers=auth).json()
    assert state["plan"] == "standard"
    assert state["limits"]["investigations_per_month"] is None
    assert state["limits"]["device_scans_per_month"] is None
    assert state["limits"]["api_access"] is True


def test_paid_plan_unlocks_export_and_drops_the_free_cap(
    client: TestClient, auth: dict[str, str], auth_user: dict
) -> None:
    _activate(client, auth_user)

    created = client.post(
        "/api/v1/investigations",
        headers=auth,
        data={
            "input_type": "message",
            "text": "Your HBL account is blocked. Verify at https://secure-hbl.example.com.",
        },
    )
    assert created.status_code == 202
    investigation_id = created.json()["id"]

    export = client.get(f"/api/v1/investigations/{investigation_id}/export", headers=auth)
    assert export.status_code == 200, export.text
    assert "attachment" in export.headers["content-disposition"]
    assert "risk" in export.json()["report"]

    # The Free plan stops the user at five; Pro must not.
    for index in range(5):
        more = client.post(
            "/api/v1/investigations",
            headers=auth,
            data={
                "input_type": "message",
                "text": f"Pay PKR 5,000 verification fee now to unlock account {index}.",
            },
        )
        assert more.status_code == 202, more.text

    state = client.get("/api/v1/billing/subscription", headers=auth).json()
    assert state["plan"] == "pro"
    assert state["usage"]["investigations"] == 6


def test_webhook_is_idempotent_for_repeated_events(
    client: TestClient, auth: dict[str, str], auth_user: dict
) -> None:
    body, signature = _subscription_event(
        subscription_id=f"sub_test_{uuid.uuid4().hex[:10]}",
        user_id=auth_user["id"],
    )
    assert _post_webhook(client, body, signature) == {"status": "ok"}
    assert _post_webhook(client, body, signature) == {"status": "ok"}

    state = client.get("/api/v1/billing/subscription", headers=auth).json()
    assert state["plan"] == "pro"
    assert state["status"] == "active"


def test_stale_webhook_cannot_revive_or_cancel_a_newer_state(
    client: TestClient, auth: dict[str, str], auth_user: dict
) -> None:
    subscription_id = f"sub_test_{uuid.uuid4().hex[:10]}"
    now = int(datetime.now(UTC).timestamp())

    activated, signature = _subscription_event(
        subscription_id=subscription_id,
        user_id=auth_user["id"],
        created_at=now,
    )
    _post_webhook(client, activated, signature)

    # A retried, older cancellation must not downgrade the plan.
    stale, stale_signature = _subscription_event(
        subscription_id=subscription_id,
        user_id=auth_user["id"],
        event="subscription.cancelled",
        status="cancelled",
        created_at=now - 600,
    )
    _post_webhook(client, stale, stale_signature)

    state = client.get("/api/v1/billing/subscription", headers=auth).json()
    assert state["plan"] == "pro"
    assert state["status"] == "active"

    # A genuinely newer cancellation still wins.
    cancel, cancel_signature = _subscription_event(
        subscription_id=subscription_id,
        user_id=auth_user["id"],
        event="subscription.cancelled",
        status="cancelled",
        created_at=now + 60,
    )
    _post_webhook(client, cancel, cancel_signature)

    downgraded = client.get("/api/v1/billing/subscription", headers=auth).json()
    assert downgraded["plan"] == "free"
    assert downgraded["status"] == "cancelled"


