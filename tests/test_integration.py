import os
import time
import uuid

import httpx
import pytest

BASE = os.getenv("NOTIFY_BASE_URL", "http://localhost:8000")
HEADERS = {"X-API-Key": os.getenv("API_KEY", "dev-key")}


def live() -> bool:
    try:
        r = httpx.get(f"{BASE}/health", timeout=1)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not live(), reason="API not running on localhost:8000")


def wait_status(notification_id: str, wanted: set[str], timeout: float = 20) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        r = httpx.get(f"{BASE}/v1/notifications/{notification_id}", headers=HEADERS, timeout=5)
        assert r.status_code == 200
        last = r.json()
        if last["status"] in wanted:
            return last
        time.sleep(0.3)
    raise AssertionError(f"timed out waiting for {wanted}, last={last}")


def test_health():
    assert httpx.get(f"{BASE}/health").json()["status"] == "ok"


def test_enqueue_inapp_and_inbox():
    key = f"order-{uuid.uuid4()}-inapp"
    r = httpx.post(
        f"{BASE}/v1/notifications",
        headers=HEADERS,
        json={
            "idempotency_key": key,
            "user_id": "42",
            "channel": "inapp",
            "category": "transactional",
            "priority": "normal",
            "template_code": "ORDER_SHIPPED",
            "payload": {"order_id": "991", "user_name": "Anushka"},
        },
        timeout=5,
    )
    assert r.status_code == 202
    nid = r.json()["notification_id"]
    row = wait_status(nid, {"sent"})
    assert row["status"] == "sent"
    inbox = httpx.get(f"{BASE}/v1/users/42/notifications", headers=HEADERS, timeout=5)
    assert inbox.status_code == 200
    assert any(item["id"] == nid for item in inbox.json())


def test_idempotency():
    key = f"otp-{uuid.uuid4()}"
    body = {
        "idempotency_key": key,
        "user_id": "42",
        "channel": "sms",
        "category": "otp",
        "priority": "critical",
        "template_code": "OTP",
        "payload": {"code": "123456"},
    }
    a = httpx.post(f"{BASE}/v1/notifications", headers=HEADERS, json=body, timeout=5)
    b = httpx.post(f"{BASE}/v1/notifications", headers=HEADERS, json=body, timeout=5)
    assert a.status_code == 202
    assert b.status_code == 202
    assert a.json()["notification_id"] == b.json()["notification_id"]
    assert b.json()["duplicate"] is True


def test_marketing_opt_out_skipped():
    key = f"promo-{uuid.uuid4()}"
    r = httpx.post(
        f"{BASE}/v1/notifications",
        headers=HEADERS,
        json={
            "idempotency_key": key,
            "user_id": "7",
            "channel": "email",
            "category": "marketing",
            "priority": "marketing",
            "template_code": "PROMO",
            "payload": {"user_name": "Sam", "headline": "Sale"},
        },
        timeout=5,
    )
    assert r.status_code == 202
    row = wait_status(r.json()["notification_id"], {"skipped"})
    assert row["skip_reason"] == "preference_disabled"


def test_permanent_failure_dlq():
    key = f"fail-{uuid.uuid4()}"
    r = httpx.post(
        f"{BASE}/v1/notifications",
        headers=HEADERS,
        json={
            "idempotency_key": key,
            "user_id": "fail",
            "channel": "email",
            "category": "transactional",
            "priority": "normal",
            "template_code": "ORDER_SHIPPED",
            "payload": {"order_id": "1", "user_name": "X", "invalid_destination": True},
        },
        timeout=5,
    )
    assert r.status_code == 202
    row = wait_status(r.json()["notification_id"], {"failed"})
    assert row["status"] == "failed"
