from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx

from app.core.config import settings

API_BASE = "https://api.razorpay.com/v1"


class RazorpayError(Exception):
    """Raised when the payment provider cannot complete a request."""


def _auth() -> tuple[str, str]:
    return settings.razorpay_key_id.strip(), settings.razorpay_key_secret.strip()


async def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(
                method,
                f"{API_BASE}{path}",
                auth=_auth(),
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise RazorpayError("The payment provider could not be reached") from exc

    if response.status_code >= 400:
        detail = "The payment provider rejected the request"
        try:
            body = response.json()
            description = body.get("error", {}).get("description")
            if description:
                detail = str(description)
        except ValueError:
            pass
        raise RazorpayError(detail)

    try:
        return response.json()
    except ValueError as exc:
        raise RazorpayError("The payment provider returned an invalid response") from exc


async def create_customer(*, name: str, email: str, user_id: str) -> dict[str, Any]:
    return await _request(
        "POST",
        "/customers",
        {
            "name": name,
            "email": email,
            "notes": {"user_id": user_id},
        },
    )


async def create_subscription(
    *,
    plan_id: str,
    customer_id: str,
    user_id: str,
    email: str,
    plan: str,
) -> dict[str, Any]:
    return await _request(
        "POST",
        "/subscriptions",
        {
            "plan_id": plan_id,
            "customer_id": customer_id,
            "total_count": settings.billing_total_count,
            "quantity": 1,
            "customer_notify": 1,
            "notes": {
                "user_id": user_id,
                "email": email,
                "plan": plan,
            },
        },
    )


async def fetch_subscription(subscription_id: str) -> dict[str, Any]:
    return await _request("GET", f"/subscriptions/{subscription_id}")


async def cancel_subscription(subscription_id: str) -> dict[str, Any]:
    return await _request(
        "POST",
        f"/subscriptions/{subscription_id}/cancel",
        {"cancel_at_cycle_end": 1},
    )


def verify_payment_signature(
    *, payment_id: str, subscription_id: str, signature: str
) -> bool:
    secret = settings.razorpay_key_secret.strip()
    if not secret or not signature:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{payment_id}|{subscription_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    secret = settings.razorpay_webhook_secret.strip()
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
