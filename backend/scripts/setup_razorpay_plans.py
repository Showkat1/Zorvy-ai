"""Create the Razorpay plans Zorvy sells and print their IDs.

Run once per Razorpay account, then copy the printed IDs into
``ZORVY_RAZORPAY_PLAN_PRO`` and ``ZORVY_RAZORPAY_PLAN_STANDARD``.

    cd backend
    ZORVY_RAZORPAY_KEY_ID=rzp_live_... \
    ZORVY_RAZORPAY_KEY_SECRET=... \
    uv run python scripts/setup_razorpay_plans.py

Use ``--dry-run`` to see what would be created without calling the API. Plans
in Razorpay are immutable, so re-running reuses a plan that already carries the
matching ``zorvy_plan`` note instead of creating a duplicate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402

API_BASE = "https://api.razorpay.com/v1"

#: Amounts are in paise (INR * 100), monthly interval.
PLANS: list[dict[str, Any]] = [
    {"key": "pro", "name": "Zorvy Pro", "amount": 499_00, "description": "Unlimited investigations, 30 device scans, export"},
    {"key": "standard", "name": "Zorvy Standard", "amount": 1999_00, "description": "Unlimited investigations and scans, export, API access"},
]


def _auth() -> tuple[str, str]:
    key_id = settings.razorpay_key_id.strip()
    secret = settings.razorpay_key_secret.strip()
    if not key_id or not secret:
        raise SystemExit(
            "Set ZORVY_RAZORPAY_KEY_ID and ZORVY_RAZORPAY_KEY_SECRET before running this script."
        )
    return key_id, secret


def _existing_plans(client: httpx.Client) -> dict[str, str]:
    response = client.get(f"{API_BASE}/plans", params={"count": 100})
    response.raise_for_status()
    found: dict[str, str] = {}
    for plan in response.json().get("items", []):
        key = str((plan.get("notes") or {}).get("zorvy_plan", ""))
        if key and key not in found:
            found[key] = plan["id"]
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the plan payloads only")
    args = parser.parse_args()

    payloads = [
        {
            "period": "monthly",
            "interval": 1,
            "item": {
                "name": plan["name"],
                "amount": plan["amount"],
                "currency": settings.billing_currency,
                "description": plan["description"],
            },
            "notes": {"zorvy_plan": plan["key"]},
        }
        for plan in PLANS
    ]

    if args.dry_run:
        for payload in payloads:
            print(payload)
        return 0

    key_id, secret = _auth()
    with httpx.Client(auth=(key_id, secret), timeout=20.0) as client:
        existing = _existing_plans(client)
        created: dict[str, str] = {}
        for payload in payloads:
            key = payload["notes"]["zorvy_plan"]
            if key in existing:
                created[key] = existing[key]
                print(f"reused {key}: {existing[key]}")
                continue
            response = client.post(f"{API_BASE}/plans", json=payload)
            if response.status_code >= 400:
                print(f"failed to create {key}: {response.text}", file=sys.stderr)
                return 1
            created[key] = response.json()["id"]
            print(f"created {key}: {created[key]}")

    print("\nAdd these to the API environment (Railway / .env) and redeploy:")
    print(f"ZORVY_RAZORPAY_PLAN_PRO={created['pro']}")
    print(f"ZORVY_RAZORPAY_PLAN_STANDARD={created['standard']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
