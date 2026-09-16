from __future__ import annotations

from datetime import datetime, timezone

from app.config import get_settings
from app.models import Category
from app.redis_client import get_redis


async def allow_user_marketing(user_id: str, category: Category) -> bool:
    if category != Category.marketing:
        return True
    settings = get_settings()
    redis = await get_redis()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"rl:user:{user_id}:marketing:{day}"
    n = await redis.incr(key)
    if n == 1:
        await redis.expire(key, 86400)
    return n <= settings.marketing_per_user_per_day


async def allow_provider(channel: str) -> bool:
    settings = get_settings()
    redis = await get_redis()
    key = f"rl:provider:{channel}:{int(datetime.now(timezone.utc).timestamp())}"
    n = await redis.incr(key)
    if n == 1:
        await redis.expire(key, 2)
    return n <= settings.provider_rps
