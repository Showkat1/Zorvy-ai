from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

TEST_DB = Path(__file__).resolve().parent / "test_zorvy.db"
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ.update(
    {
        "ZORVY_ENVIRONMENT": "test",
        "ZORVY_DATABASE_URL": f"sqlite+aiosqlite:///{TEST_DB.as_posix()}",
        "ZORVY_AUTO_CREATE_TABLES": "true",
        "ZORVY_SEED_KNOWLEDGE_ON_STARTUP": "true",
        "ZORVY_PIPELINE_MODE": "inline",
        "ZORVY_RATE_LIMIT_ENABLED": "false",
        "ZORVY_SECRET_KEY": "test-secret-key-not-for-production",
        "ZORVY_LLM_ENABLED": "false",
        "ZORVY_EMBEDDING_PROVIDER": "hash",
        "ZORVY_COOKIE_SECURE": "false",
        "ZORVY_LOG_LEVEL": "WARNING",
        "ZORVY_RAZORPAY_KEY_ID": "rzp_test_key",
        "ZORVY_RAZORPAY_KEY_SECRET": "test-key-secret",
        "ZORVY_RAZORPAY_WEBHOOK_SECRET": "test-webhook-secret",
        "ZORVY_RAZORPAY_PLAN_PRO": "plan_test_pro",
        "ZORVY_RAZORPAY_PLAN_STANDARD": "plan_test_standard",
    }
)

from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def user_credentials() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:10]
    return {
        "email": f"tester-{suffix}@example.com",
        "full_name": "Test Investigator",
        "password": "StrongPassword123",
    }


@pytest.fixture()
def auth(client: TestClient, user_credentials: dict[str, str]) -> dict[str, str]:
    response = client.post("/api/v1/auth/register", json=user_credentials)
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth_user(client: TestClient, auth: dict[str, str]) -> dict:
    response = client.get("/api/v1/auth/me", headers=auth)
    assert response.status_code == 200
    return response.json()
