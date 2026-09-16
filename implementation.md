# Implementation Plan: Scalable Notification System

**Goal:** Design and later build a notification system that can handle **1 million notifications per day**.

**Current phase:** Planning only. No application code until this plan is reviewed.

---

## 1. Problem statement

A product needs to notify users when something happens (order placed, OTP, comment, campaign, etc.). The system must:

- Accept notification requests from other services or an API.
- Deliver them over multiple channels.
- Stay reliable when traffic spikes.
- Scale to **1,000,000 notifications / day**.

This is a **soft real-time** system: most messages should go out quickly, but it is not a stock-exchange-level latency problem.

---

## 2. Capacity math (why 1M/day is actually modest)

| Metric | Value |
|--------|--------|
| Daily volume | 1,000,000 |
| Average rate | 1,000,000 / 86,400 ≈ **12 notifications/second** |
| Peak (assume 10× average, typical product spike) | **~120 notifications/second** |
| Burst (campaign / incident, 20×) | **~240 notifications/second** |

Design for **peak**, not average. Average of 12/s would fit on a laptop. Peak + retries + provider delays is what the architecture must absorb.

**Assumed mix (adjust when real product data exists):**

| Channel | Share | Per day | Role |
|---------|--------|---------|------|
| In-app | 40% | 400k | Cheap, stored in our DB |
| Push | 30% | 300k | APNs / FCM |
| Email | 25% | 250k | SMTP / provider |
| SMS | 5% | 50k | Expensive, critical only |

**Rough storage (90 days of history):**

- ~200 bytes metadata per notification → 1M × 200B × 90 ≈ **18 GB** (comfortable for PostgreSQL with indexes).
- Payload/templates live separately; do not dump huge HTML into every row.

---

## 3. Requirements to implement against

### Functional

1. **Channels:** in-app, email, push, SMS (SMS and push can start as mocked providers).
2. **Trigger types:**
   - Immediate (event-driven): “order shipped”.
   - Scheduled: “reminder at 9am”.
3. **Templates:** subject/body with placeholders (`{{user_name}}`, `{{order_id}}`).
4. **User preferences:** opt-in / opt-out per channel and per category.
5. **Priority:** `critical` (OTP, payment) vs `normal` vs `marketing`.
6. **Idempotency:** same event must not notify the user twice.
7. **Retries:** failed sends retry with backoff; poison messages go to a dead-letter queue (DLQ).
8. **Status tracking:** `queued` → `sending` → `sent` / `failed` / `skipped`.
9. **Admin / debug:** list notifications, inspect a single delivery, replay from DLQ.

### Non-functional

| Quality | Target for this assignment |
|---------|----------------------------|
| Throughput | 1M/day, peak ~200/s |
| Latency | Critical: a few seconds; marketing: minutes OK |
| Delivery | At-least-once + dedup (effective exactly-once for the user) |
| Availability | API stays up even if email provider is down (queue buffers) |
| Observability | Logs + simple metrics (queued, sent, failed, lag) |

### Out of scope (unless assignment expands)

- Real APNs/FCM production certificates.
- Multi-region active-active.
- Full marketing campaign UI.
- ML ranking of which notification to send.

---

## 4. Core design decisions

### 4.1 Do not send inside the HTTP request

The API only **validates and enqueues**. Workers send.

```
Client / other service
        │
        ▼
   Notification API  ──►  Message queue  ──►  Channel workers  ──►  Providers
        │                      │
        ▼                      ▼
   PostgreSQL              Redis (cache, rate limit, idempotency)
```

If SMTP is slow, the API still returns `202 Accepted`. That is how 1M/day stays stable.

### 4.2 Separate queues by priority (and ideally by channel)

Marketing bursts must not delay OTPs.

- Topics/queues: `notifications.critical`, `notifications.normal`, `notifications.marketing`
- Optional split later: `email`, `sms`, `push`, `inapp`

Workers for critical get more concurrency and no artificial throttle.

### 4.3 Idempotency key

Every request carries `idempotency_key` (or we derive one: `event_id + user_id + channel`).

Store processed keys in Redis (TTL 24–48h) and/or a unique DB constraint. Duplicate requests return the original result.

### 4.4 Preferences before send

Worker checks:

1. User exists and is not banned.
2. Channel enabled for that category.
3. Quiet hours (optional).
4. Per-user rate limit (e.g. max 10 marketing emails/day).

If skipped, persist `status = skipped` with reason. Do not retry skips.

### 4.5 Retry and DLQ

| Attempt | Delay |
|---------|--------|
| 1 | immediate |
| 2 | 30s |
| 3 | 2 min |
| 4 | 10 min |
| 5 | DLQ |

Do not retry **4xx** from providers (bad token, invalid email). Retry **5xx** and timeouts.

### 4.6 Provider adapters are fake-able

Each channel is an interface:

- `InAppProvider` → write to DB (real).
- `EmailProvider` → SMTP or mock that logs + random failure.
- `SmsProvider` → mock.
- `PushProvider` → mock.

This proves architecture without paying Twilio.

---

## 5. Suggested tech stack (student-implementable)

Keep one language and few moving parts.

| Layer | Choice | Why |
|-------|--------|-----|
| API + workers | Node.js (Express/Nest) **or** Python (FastAPI) | Fast to ship, async I/O |
| Database | PostgreSQL | Notifications, users, templates, preferences |
| Cache / locks | Redis | Idempotency, rate limits, preference cache |
| Queue | RabbitMQ **or** Redis Streams | Kafka is overkill for 1M/day in this assignment |
| Auth | Simple API key for producer services | Enough for a backend-to-backend API |
| Observability | Structured logs + Prometheus-style counters (or even a `/metrics` JSON) | Prove scale behavior |
| Local run | Docker Compose | API, Postgres, Redis, RabbitMQ together |

**Recommendation:** FastAPI + PostgreSQL + Redis + RabbitMQ + Docker Compose.

1M/day does not require Kafka. Use Kafka only if the course specifically asks for it.

---

## 6. Data model (logical)

### `users`

- `id`, `email`, `phone`, `push_token`, `timezone`, `created_at`

### `notification_preferences`

- `user_id`, `category` (otp, transactional, social, marketing), `channel`, `enabled`

### `templates`

- `id`, `code` (e.g. `ORDER_SHIPPED`), `channel`, `subject`, `body`, `version`

### `notifications`

- `id` (UUID)
- `idempotency_key` (unique)
- `user_id`, `category`, `priority`, `channel`
- `template_code`, `payload` (JSON)
- `status` (`queued`, `sending`, `sent`, `failed`, `skipped`)
- `attempts`, `last_error`, `provider_message_id`
- `scheduled_at`, `sent_at`, `created_at`

### `notification_events` (optional audit)

- `notification_id`, `type` (`enqueued`, `retry`, `sent`, `dlq`), `at`, `detail`

Indexes: `(user_id, created_at)`, `(status, scheduled_at)`, unique `idempotency_key`.

---

## 7. API surface (to build later)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/notifications` | Enqueue one notification (`202`) |
| `POST` | `/v1/notifications/batch` | Enqueue many (chunk internally) |
| `GET` | `/v1/notifications/{id}` | Status |
| `GET` | `/v1/users/{id}/notifications` | In-app inbox |
| `PATCH` | `/v1/users/{id}/preferences` | Opt-in/out |
| `POST` | `/v1/admin/dlq/{id}/replay` | Retry from DLQ |
| `GET` | `/health` | Liveness |
| `GET` | `/metrics` | Counts |

**Enqueue contract (sketch):**

```json
{
  "idempotency_key": "order-991-shipped-user-42-email",
  "user_id": "42",
  "channel": "email",
  "category": "transactional",
  "priority": "normal",
  "template_code": "ORDER_SHIPPED",
  "payload": { "order_id": "991", "user_name": "Anushka" },
  "scheduled_at": null
}
```

Validation happens in the API. Sending happens in workers.

---

## 8. Component flow (happy path)

1. Producer calls `POST /v1/notifications`.
2. API validates schema, user, template.
3. API inserts row `status=queued` (or skip insert if duplicate key).
4. API publishes message `{ notification_id }` to the right queue.
5. API returns `202` with `notification_id`.
6. Worker consumes message.
7. Worker loads notification + cached preferences.
8. If disabled → `skipped`, ack message.
9. Worker renders template.
10. Worker checks rate limit.
11. Worker calls provider.
12. On success → `sent`, ack.
13. On retryable failure → increment attempts, republish delayed, ack original.
14. On max attempts → `failed`, publish DLQ, ack.

**Scheduled notifications:** a small scheduler job (every 10–30s) selects `scheduled_at <= now()` and `status=queued`, then publishes like step 4.

---

## 9. Scaling plan (what we would do at higher load)

1M/day is the assignment target. The same design grows as follows:

| Bottleneck | Action |
|------------|--------|
| API CPU | Add API replicas behind a load balancer (stateless) |
| Queue lag | Add workers; split queues by channel |
| Postgres writes | Batch inserts for campaigns; partition table by date later |
| Provider 429s | Global Redis token bucket per provider |
| Preference reads | Cache in Redis (TTL 5–15 min), invalidate on PATCH |
| Campaign of 200k | Fan-out service writes to queue in chunks of 500–1000 |

**Horizontal scale rule:** API and workers are stateless. Postgres and Redis hold state. Queue is the buffer.

---

## 10. Implementation phases (when coding starts)

Do **not** start phase 1 until this document is accepted.

### Phase 0 — Repo and local infra

- Docker Compose: Postgres, Redis, RabbitMQ.
- `.env.example`, README with run commands.
- Empty API that returns `/health`.

### Phase 1 — Data and enqueue API

- Migrations for tables above.
- `POST /v1/notifications` + uniqueness on `idempotency_key`.
- Publish to one queue only (`notifications.normal`).

### Phase 2 — Worker + in-app channel (end-to-end real)

- Consumer updates status.
- In-app provider writes inbox rows.
- `GET` inbox endpoint.
- Prove: enqueue → worker → user can read notification.

### Phase 3 — Templates, preferences, skip logic

- Template renderer.
- Preference checks.
- Tests: opted-out user never gets email.

### Phase 4 — Email/SMS/push adapters (mock)

- Mock providers with configurable failure rate.
- Retry + DLQ.
- Replay endpoint.

### Phase 5 — Priority queues + rate limiting

- Three queues and three worker pools.
- Redis rate limiter per user and per provider.

### Phase 6 — Scheduling + batch

- `scheduled_at` scheduler.
- Batch enqueue with chunking.

### Phase 7 — Proof of scale

- Load script: 10k–50k enqueue requests (or 1M if machine allows).
- Record: p99 enqueue latency, queue lag, success/fail/skip counts.
- Write a short results section in README (numbers, not screenshots-only).

### Phase 8 — Hardening (if time)

- Structured logs (`notification_id` on every line).
- Metrics endpoint.
- Basic auth/API key.
- Graceful worker shutdown (finish current message).

---

## 11. Testing strategy

| Level | What to prove |
|-------|----------------|
| Unit | Template render, preference skip, retry classification (4xx vs 5xx) |
| Integration | API → DB → queue → worker → status `sent` |
| Idempotency | Same key twice → one row, one send |
| Failure | Provider down → retries → DLQ |
| Preference | Opt-out → `skipped`, no provider call |
| Load | Sustained enqueue at >120/s for a few minutes |

Do not wait for a real email inbox to call the system “working”. Mocks + DB status are the source of truth.

---

## 12. Folder structure (planned, not created yet)

```
/
  implementation.md      ← this file
  learning.md            ← concepts
  docker-compose.yml
  .env.example
  README.md
  app/
    api/                 # HTTP
    workers/             # consumers
    providers/           # inapp, email, sms, push
    services/            # enqueue, render, preferences, ratelimit
    models/
    db/
  tests/
  scripts/
    load_test.py
```

Exact names follow the language chosen in Phase 0.

---

## 13. Risks and how we avoid them

| Risk | Mitigation |
|------|------------|
| Building a giant Kafka cluster first | RabbitMQ/Redis Streams; 12/s average does not need Kafka |
| Sending email inside the request | Enqueue-only API |
| Duplicate OTPs | Idempotency key + unique index |
| Marketing blocks OTP | Separate queues |
| Infinite retries | Max attempts + DLQ |
| Scope creep (real FCM, campaign UI) | Mocks + listed out-of-scope |
| No proof it scales | Load script + metrics in Phase 7 |

---

## 14. Definition of done (assignment)

The assignment is complete when all of the following are true:

1. A request can be accepted without waiting for the provider.
2. At least **in-app + one mocked external channel** work end-to-end.
3. Duplicates are ignored.
4. Failures retry, then land in DLQ.
5. Opt-out is respected.
6. Priority is isolated (critical vs marketing).
7. A load run shows the system can absorb well above 12/s (target peak ~100+/s).
8. README explains how to run, test, and how the 1M/day number maps to architecture.

---

## 15. Next step

Review this plan. After approval, start **Phase 0** only (Compose + health endpoint), then Phase 1.

No feature code until then.
