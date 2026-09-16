from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Channel, NotificationPreference, User
from app.redis_client import get_redis

OTP_ALWAYS_ON = True


async def preference_enabled(
    session: AsyncSession, user_id: str, category: Category, channel: Channel
) -> bool:
    if category == Category.otp:
        return True
    redis = await get_redis()
    cache_key = f"pref:{user_id}:{category.value}:{channel.value}"
    cached = await redis.get(cache_key)
    if cached is not None:
        return cached == "1"

    row = await session.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.category == category,
            NotificationPreference.channel == channel,
        )
    )
    enabled = True if row is None else row.enabled
    await redis.set(cache_key, "1" if enabled else "0", ex=300)
    return enabled


async def set_preference(
    session: AsyncSession, user_id: str, category: Category, channel: Channel, enabled: bool
) -> NotificationPreference:
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError("user_not_found")
    row = await session.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.category == category,
            NotificationPreference.channel == channel,
        )
    )
    if row is None:
        row = NotificationPreference(
            user_id=user_id, category=category, channel=channel, enabled=enabled
        )
        session.add(row)
    else:
        row.enabled = enabled
    await session.commit()
    redis = await get_redis()
    await redis.set(f"pref:{user_id}:{category.value}:{channel.value}", "1" if enabled else "0", ex=300)
    return row


def in_quiet_hours(now: Optional[datetime] = None) -> bool:
    current = now or datetime.now(timezone.utc)
    return current.hour < 7
