# Learning Notes: Concepts Used in the Notification System

This file is the study companion to `implementation.md`. It explains **what** each idea is, **why** it appears in a 1M notifications/day system, and **how** we will use it. No code yet.

---

## 1. What a notification system is

A notification system tells a user that something happened. It is a **fan-out** service: one business event (order shipped) may become several deliveries (in-app + email).

It is usually **asynchronous**. The order service should not wait for Gmail before confirming the order.

Main jobs:

1. Ingest events.
2. Decide *whether* to notify (preferences, rate limits).
3. Decide *how* (channel, template).
4. Deliver via providers.
5. Record what happened.

---

## 2. Scale: 1 million per day

**Throughput** = work per unit time.

```
1,000,000 / 86,400 seconds ≈ 12 events/second average
```

Products are not flat. Lunch-time and launches create **peaks**. A common planning rule is **10× average** → ~120/s.

Concepts:

- **Average vs peak vs burst** — provision for peak; use a queue for burst.
- **Capacity planning** — convert a business number (“1M/day”) into QPS, storage, and worker count.
- **Back-of-the-envelope math** — required in system design; do it before picking Kafka vs a single Redis list.

Takeaway: 1M/day is **not** huge. The interesting problems are **spikes, retries, duplicates, and slow third parties**, not raw QPS.

---

## 3. Functional vs non-functional requirements

- **Functional:** what the system does (send email, respect opt-out).
- **Non-functional:** how well (latency, availability, durability).

For notifications:

| Term | Meaning here |
|------|----------------|
| Latency | Time from event to user seeing it |
| Throughput | Notifications processed per second |
| Availability | API still accepts work when SMS is down |
| Durability | A queued notification is not lost on crash |
| Reliability | We retry and do not silently drop |

---

## 4. Synchronous vs asynchronous processing

**Synchronous:** API talks to SMTP, then returns. Simple. Breaks when SMTP takes 2 seconds × 120 requests.

**Asynchronous:** API writes to a queue and returns `202 Accepted`. Workers send later.

This is the single most important design choice for scale.

Related HTTP idea: **`202 Accepted`** means “we took the job,” not “the email arrived.”

---

## 5. Decoupling and backpressure

**Decoupling:** producers (API) and consumers (workers) do not share a process or a lock-step timeline.

**Buffer:** the queue holds work when workers or providers are slower than producers.

**Backpressure:** when the system is overloaded, it slows intake instead of crashing.

- Queue lag growing = backpressure visible as delay.
- Rate limiting the API or the worker = active backpressure.

Without a buffer, a slow Twilio outage becomes an API outage.

---

## 6. Message queues

A **message queue** stores jobs until a worker can process them.

Ideas to know:

| Concept | Meaning |
|---------|---------|
| Producer | Publishes a message |
| Consumer / worker | Pulls and processes |
| Broker | The queue server (RabbitMQ, Kafka, Redis) |
| Ack (acknowledgement) | “I finished; you may delete this message” |
| Nack / retry | “I failed; give it to me later or to another worker” |
| Consumer group | Several workers sharing the same stream of work |
| Prefetch / QoS | How many unacked messages a worker may hold |

**At-least-once delivery:** the queue may deliver a message more than once if a worker crashes after send but before ack. That is why we need **idempotency**.

**Exactly-once** in distributed systems is hard. Practical approach: **at-least-once + idempotent processing**.

### RabbitMQ vs Kafka vs Redis Streams (for this assignment)

| Tool | Strength | For 1M/day |
|------|----------|------------|
| RabbitMQ | Simple queues, delayed messages, good teaching model | Excellent fit |
| Redis Streams | Already have Redis | Fine |
| Kafka | Huge retention, replay, many partitions | Optional; overkill unless required |

**Partitioning:** split a stream by key (e.g. `user_id`) so one user’s notifications stay ordered and work parallelizes across users.

---

## 7. Priority queues

If OTP and a 200,000-email campaign share one queue, OTPs wait behind the campaign (**head-of-line blocking**).

Fix: **separate queues** (critical / normal / marketing) with **separate worker pools**.

Priority *inside* one queue is weaker: a huge batch still occupies consumers.

---

## 8. Dead-letter queue (DLQ) and retries

**Transient errors:** timeout, 503, network blip → retry.

**Permanent errors:** invalid email, revoked push token → do not retry forever.

**Exponential backoff:** wait 30s, 2m, 10m… so we do not hammer a dying provider (**retry storm**).

**DLQ:** after N failures, move the message aside. Humans or an admin API can inspect and replay.

**Poison message:** a payload that always fails (bad JSON). DLQ isolates it so the rest of the queue proceeds.

---

## 9. Idempotency

**Idempotent** operation: doing it twice has the same effect as doing it once.

Network retries and at-least-once queues cause duplicates. Users must not get two OTPs.

Mechanism:

- Client sends `idempotency_key`.
- Server stores the key (Redis SET NX, or unique SQL column).
- Second request with the same key returns the first result and does not enqueue again.

Related: **deduplication window** (keep keys 24–48 hours, not forever).

---

## 10. Consistency and delivery semantics

- **At-most-once:** send once or not at all (can lose messages). Bad for OTP.
- **At-least-once:** may duplicate. Good if combined with idempotency.
- **Outbox pattern:** write DB row and “to-queue” flag in one transaction, then a publisher pushes to the queue. Avoids “DB saved but queue publish failed.”

For the assignment, a pragmatic version is: insert notification row, then publish; if publish fails, a sweeper republishes `queued` rows older than N seconds.

---

## 11. Multi-channel delivery

| Channel | Typical provider | Cost / traits |
|---------|------------------|---------------|
| In-app | Our database | Cheap, needs inbox API |
| Push | FCM, APNs | Needs device tokens |
| Email | SES, SendGrid, SMTP | Templates, bounce handling |
| SMS | Twilio, MSG91 | Expensive; use for critical |

**Adapter pattern:** workers depend on an interface (`send(to, body)`), not on Twilio. Mocks in tests and local dev.

**Template engine:** store `Hello {{name}}`, render with payload JSON. Keep logic out of templates.

---

## 12. User preferences and quiet hours

Legal and product requirement: users can opt out of marketing; OTPs usually cannot be opted out.

Concepts:

- **Category** vs **channel** matrix (marketing × email = off).
- **Quiet hours** / timezone (don’t push at 3am).
- **Preference cache** in Redis so workers do not hit Postgres on every send.

Skipping is a **successful business outcome**, not a retryable failure. Persist `skipped` + reason.

---

## 13. Rate limiting

Protect:

1. **Users** from spam (max N marketing mails/day).
2. **Providers** from 429s (max M requests/second globally).

Algorithms:

| Algorithm | Idea |
|-----------|------|
| Token bucket | Tokens refill over time; a send costs one token |
| Leaky bucket | Smooths bursts to a constant drain rate |
| Fixed window | Count in the current minute (simple, burst at edges) |
| Sliding window | Smoother than fixed window |

Redis is the usual store because all worker replicas must share one counter.

**429 Too Many Requests** from a provider should slow workers, not crash them.

---

## 14. Horizontal vs vertical scaling

- **Vertical:** bigger machine. Hits a ceiling.
- **Horizontal:** more copies of stateless services.

Stateless API + more workers = the scale path. Stateful pieces (Postgres, Redis, queue) scale separately (replicas, partitions).

**Single point of failure (SPOF):** one notification process that does API + DB + SMTP. We split those roles so one crash is not a total outage.

**Load balancer:** distributes HTTP across API replicas.

---

## 15. Caching

**Cache:** fast copy of data that is expensive to read.

Use Redis for:

- Preferences
- Rendered template metadata
- Idempotency keys
- Rate-limit counters

Concepts:

- **TTL** (time to live)
- **Cache invalidation** on preference update
- **Stampede:** many workers miss cache at once — not a big issue at 12/s; know the term

---

## 16. Database concepts we will use

- **Relational model:** users, preferences, notifications as tables with foreign keys.
- **UUID** primary keys: safer for distributed enqueue than auto-increment under load.
- **Unique constraint:** enforces idempotency in the DB, not only in Redis.
- **Indexes:** `(user_id, created_at)` for inbox; `(status, scheduled_at)` for the scheduler.
- **JSON payload column:** flexible event data without a new table per event type.
- **Status state machine:** `queued → sending → sent | failed | skipped`. Invalid jumps should be rejected.
- **Connection pooling:** workers and API share a pool, not a new TCP connection per notification.

Later (not required for 1M/day): **table partitioning** by month if history grows.

---

## 17. Scheduling

**Cron / periodic worker:** every few seconds, select due rows (`scheduled_at <= now()`).

Avoid scheduling 1M individual OS cron jobs. Store “when” in the database (or a delay queue) and have one scheduler publish due work.

**Delay queues:** RabbitMQ TTL + DLX, or Redis `ZADD` with timestamp scores.

---

## 18. Batching and fan-out

**Fan-out:** one campaign → N user notifications.

Never insert 500k rows in one HTTP request. **Chunk** (500–1000) and enqueue chunks.

**Batching to providers:** some APIs accept 100 emails per call. Fewer round trips, better throughput.

---

## 19. Observability

If you cannot see queue lag, you cannot claim the system is healthy.

| Signal | Example |
|--------|---------|
| Logs | `notification_id`, `user_id`, `attempt` |
| Metrics | sent, failed, skipped, enqueue_latency, queue_depth |
| Tracing | one request-id across API and worker |

**Golden signals:** latency, traffic, errors, saturation (queue depth is saturation).

---

## 20. Reliability patterns (short glossary)

| Pattern | In this project |
|---------|-----------------|
| Circuit breaker | Stop calling a provider that is 100% failing; fail fast to retry/DLQ |
| Timeout | Never wait forever on SMTP |
| Bulkhead | Isolated worker pools so email failures don’t starve SMS |
| Graceful shutdown | Finish current message, then exit (so deploys don’t lose work) |
| Health check | `/health` for orchestrators |
| Sweeper / reconciler | Republish stuck `queued` rows |

---

## 21. Security and privacy (minimum bar)

- Producer **API keys** (other services, not end users, call enqueue).
- Do not log full SMS OTP codes.
- Respect **unsubscribe** for marketing (CAN-SPAM / DPDP-style thinking).
- Secrets in environment variables, not in git.

---

## 22. Testing concepts

- **Unit test:** pure functions (render, backoff delay).
- **Integration test:** API + DB + queue + worker.
- **Contract of mocks:** mock provider records calls so we assert “opt-out ⇒ zero sends.”
- **Load test:** generate many enqueues; watch lag and error rate.
- **Idempotency test:** parallel double-submit of the same key.

---

## 23. HTTP and API design used here

- `POST` create/enqueue (not idempotent unless we add a key).
- `GET` read status / inbox.
- `PATCH` preferences.
- `202 Accepted` vs `200 OK` vs `409 Conflict` (duplicate key, if you choose to surface it).
- **Pagination** for inbox (`limit`, `cursor` or `offset`).
- **Version prefix** `/v1` so the contract can evolve.

---

## 24. Docker Compose as a development platform

Local “production-shaped” stack:

- App process
- PostgreSQL
- Redis
- RabbitMQ

**Why:** the architecture depends on real brokers, not in-memory fake queues, so retry/ack behavior is honest.

---

## 25. How the concepts map to 1M/day

```
1M/day
  → 12/s average, ~120/s peak     (capacity planning)
  → API must not call SMTP inline (async + queue)
  → peaks sit in the broker       (buffer, backpressure)
  → many workers share work       (horizontal scale, consumer groups)
  → providers fail                (retry, backoff, DLQ)
  → queues redeliver              (idempotency)
  → users hate spam               (preferences, rate limits)
  → OTP cannot wait on marketing  (priority isolation)
  → we must prove it              (metrics, load test)
```

That chain is the assignment: not a single giant server that “sends email in a for-loop.”

---

## 26. Suggested study order

1. Async vs sync, `202 Accepted`
2. Queue ack / at-least-once
3. Idempotency
4. Retry + DLQ
5. Rate limiting
6. Horizontal scaling and SPOF
7. Preferences and templates
8. Observability

Read `implementation.md` for *what we will build*. Use this file for *why each piece exists*.
