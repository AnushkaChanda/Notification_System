# Notification system (1M/day)

The API **enqueues** work and returns `202`. Workers send in-app (database) and email/SMS/push (mocks). Duplicates are blocked by `idempotency_key`. Failures retry, then go to a DLQ.

Default is **local mode**: SQLite + an in-process queue. No Docker, Postgres, Redis, or RabbitMQ.

## Run locally (no Docker)

Python 3.9+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

If port 8000 is already in use:

```bash
uvicorn app.main:app --reload --port 8010
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

One `uvicorn` process runs the API, workers, and scheduler.

Seeded users: `42` (all on), `7` (marketing email opted out), `fail` (permanent provider errors).

```bash
curl -s http://localhost:8000/health

curl -s -X POST http://localhost:8000/v1/notifications \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-key' \
  -d '{
    "idempotency_key": "order-991-shipped-user-42-inapp",
    "user_id": "42",
    "channel": "inapp",
    "category": "transactional",
    "priority": "normal",
    "template_code": "ORDER_SHIPPED",
    "payload": {"order_id": "991", "user_name": "Anushka"}
  }'
```

## Run with Docker (optional)

Uses Postgres + Redis + RabbitMQ and separate worker processes.

```bash
docker compose up --build
```

## Tests

```bash
source .venv/bin/activate
pytest tests/test_unit.py -q
pytest tests/test_integration.py -q   # needs the API running
python scripts/load_test.py -n 500
```

## Why 1M/day works

1,000,000 / 86,400 ≈ **12/s** average. Peak target ~120/s. The API never waits on a provider.

## API

| Method | Path |
|--------|------|
| POST | `/v1/notifications` |
| POST | `/v1/notifications/batch` |
| GET | `/v1/notifications/{id}` |
| GET | `/v1/users/{id}/notifications` |
| PATCH | `/v1/users/{id}/preferences` |
| POST | `/v1/admin/dlq/{id}/replay` |
| GET | `/metrics` |

Header: `X-API-Key: dev-key`
