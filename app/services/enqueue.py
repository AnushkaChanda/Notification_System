from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import metrics
from app.models import Notification, Status, Template, User
from app.queue import publish
from app.redis_client import get_redis
from app.schemas import NotificationCreate


async def enqueue(session: AsyncSession, body: NotificationCreate) -> tuple[Notification, bool]:
    redis = await get_redis()
    lock_key = f"idemp:{body.idempotency_key}"
    acquired = await redis.set(lock_key, "1", nx=True, ex=172800)

    existing = await session.scalar(
        select(Notification).where(Notification.idempotency_key == body.idempotency_key)
    )
    if existing is not None:
        return existing, True

    user = await session.get(User, body.user_id)
    if user is None:
        if acquired:
            await redis.delete(lock_key)
        raise ValueError("user_not_found")

    template = await session.scalar(
        select(Template).where(Template.code == body.template_code, Template.channel == body.channel)
    )
    if template is None:
        if acquired:
            await redis.delete(lock_key)
        raise ValueError("template_not_found")

    notification = Notification(
        id=uuid4(),
        idempotency_key=body.idempotency_key,
        user_id=body.user_id,
        category=body.category,
        priority=body.priority,
        channel=body.channel,
        template_code=body.template_code,
        payload=body.payload,
        status=Status.queued,
        scheduled_at=body.scheduled_at,
        next_attempt_at=body.scheduled_at,
    )
    session.add(notification)
    try:
        await session.commit()
        await session.refresh(notification)
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(Notification).where(Notification.idempotency_key == body.idempotency_key)
        )
        assert existing is not None
        return existing, True

    if body.scheduled_at is None:
        await publish(notification.id, notification.priority)
        metrics.inc("enqueued")
    else:
        metrics.inc("scheduled")
    return notification, False


async def enqueue_batch(session: AsyncSession, items: list[NotificationCreate]) -> list[tuple[Notification, bool]]:
    results = []
    for item in items:
        results.append(await enqueue(session, item))
    return results


async def get_notification(session: AsyncSession, notification_id: UUID) -> Optional[Notification]:
    return await session.get(Notification, notification_id)
