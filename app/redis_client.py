from __future__ import annotations

import time
from typing import Any, Dict, Optional

from app.config import get_settings

_redis: Any = None


class MemoryKV:
    """In-process stand-in for Redis (idempotency, cache, rate limits)."""

    def __init__(self) -> None:
        self._data: Dict[str, str] = {}
        self._expires: Dict[str, float] = {}

    def _alive(self, key: str) -> bool:
        exp = self._expires.get(key)
        if exp is not None and exp < time.time():
            self._data.pop(key, None)
            self._expires.pop(key, None)
            return False
        return key in self._data

    async def set(self, key: str, value: str, nx: bool = False, ex: Optional[int] = None) -> bool:
        if nx and self._alive(key):
            return False
        self._data[key] = value
        if ex is not None:
            self._expires[key] = time.time() + ex
        return True

    async def get(self, key: str) -> Optional[str]:
        if not self._alive(key):
            return None
        return self._data.get(key)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._expires.pop(key, None)

    async def incr(self, key: str) -> int:
        if not self._alive(key):
            self._data[key] = "0"
        n = int(self._data.get(key, "0")) + 1
        self._data[key] = str(n)
        return n

    async def expire(self, key: str, seconds: int) -> None:
        if key in self._data:
            self._expires[key] = time.time() + seconds


async def get_redis() -> Any:
    global _redis
    if _redis is not None:
        return _redis
    settings = get_settings()
    if settings.is_local:
        _redis = MemoryKV()
        return _redis
    from redis.asyncio import Redis

    _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis
