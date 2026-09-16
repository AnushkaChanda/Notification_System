from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import metrics
from app.config import get_settings
from app.models import Notification, Status, Template, User
from app.providers.inapp import InAppProvider
from app.providers.mock import MockProvider
from app.queue import publish, publish_dlq
from app.services.policy import is_retryable
from app.services.preferences import preference_enabled
from app.services.ratelimit import allow_provider, allow_user_marketing
from app.services.render import render


async def process_notification(session: AsyncSession, notification_id: UUID) -> None:
    notification = await session.get(Notification, notification_id, with_for_update=True)
    if notification is None:
        return
    if notification.status in {Status.sent, Status.skipped, Status.failed}:
        return

    user = await session.get(User, notification.user_id)
    if user is None:
        await _fail_permanent(session, notification, "user_not_found")
        return

    enabled = await preference_enabled(session, user.id, notification.category, notification.channel)
    if not enabled:
        notification.status = Status.skipped
        notification.skip_reason = "preference_disabled"
        await session.commit()
        metrics.inc("skipped")
        return

    if not await allow_user_marketing(user.id, notification.category):
        notification.status = Status.skipped
        notification.skip_reason = "user_rate_limited"
        await session.commit()
        metrics.inc("skipped")
        return

    if not await allow_provider(notification.channel.value):
        await _retry_or_dlq(session, notification, "provider_rate_limited")
        return

    template = await session.scalar(
        select(Template).where(
            Template.code == notification.template_code,
            Template.channel == notification.channel,
        )
    )
    if template is None:
        await _fail_permanent(session, notification, "template_not_found")
        return

    subject = render(template.subject, notification.payload)
    body = render(template.body, notification.payload)
    to = _destination(user, notification)

    notification.status = Status.sending
    notification.attempts += 1
    notification.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=60)
    await session.commit()

    try:
        provider = InAppProvider(session) if notification.channel.value == "inapp" else MockProvider(
            notification.channel.value
        )
        message_id = await provider.send(to=to, subject=subject, body=body, payload=notification.payload)
    except Exception as exc:
        err = str(exc)
        retryable = getattr(exc, "retryable", is_retryable(err))
        if retryable:
            await _retry_or_dlq(session, notification, err)
        else:
            await _fail_permanent(session, notification, err)
        return

    notification.status = Status.sent
    notification.provider_message_id = message_id
    notification.sent_at = datetime.now(timezone.utc)
    notification.last_error = None
    await session.commit()
    metrics.inc("sent")


def _destination(user: User, notification: Notification) -> str:
    if notification.channel.value == "email":
        return user.email
    if notification.channel.value == "sms":
        return user.phone or ""
    if notification.channel.value == "push":
        return user.push_token or ""
    return user.id


async def _retry_or_dlq(session: AsyncSession, notification: Notification, error: str) -> None:
    settings = get_settings()
    notification.last_error = error
    if notification.attempts >= settings.max_attempts:
        notification.status = Status.failed
        await session.commit()
        await publish_dlq(notification.id)
        metrics.inc("dlq")
        return
    idx = min(max(notification.attempts - 1, 0), len(settings.retry_delays) - 1)
    delay = settings.retry_delays[idx]
    notification.status = Status.queued
    notification.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
    await session.commit()
    metrics.inc("retry")


async def _fail_permanent(session: AsyncSession, notification: Notification, error: str) -> None:
    notification.status = Status.failed
    notification.last_error = error
    await session.commit()
    await publish_dlq(notification.id)
    metrics.inc("dlq")


async def replay_from_dlq(session: AsyncSession, notification_id: UUID) -> Notification:
    notification = await session.get(Notification, notification_id)
    if notification is None:
        raise ValueError("not_found")
    notification.status = Status.queued
    notification.attempts = 0
    notification.last_error = None
    notification.next_attempt_at = datetime.now(timezone.utc)
    await session.commit()
    await publish(notification.id, notification.priority)
    metrics.inc("replayed")
    return notification
