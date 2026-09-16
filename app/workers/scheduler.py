from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, engine
from app.models import Base, Notification, Status
from app.queue import publish
from app.seed import seed

logging.basicConfig(level=get_settings().log_level)
log = logging.getLogger("scheduler")


async def tick() -> int:
    now = datetime.now(timezone.utc)
    published = 0
    async with SessionLocal() as session:
        stuck = (
            await session.scalars(
                select(Notification)
                .where(
                    Notification.status == Status.sending,
                    Notification.next_attempt_at <= now,
                )
                .limit(50)
            )
        ).all()
        for row in stuck:
            row.status = Status.queued
            row.next_attempt_at = now

        rows = (
            await session.scalars(
                select(Notification)
                .where(
                    Notification.status == Status.queued,
                    Notification.next_attempt_at.is_not(None),
                    Notification.next_attempt_at <= now,
                )
                .limit(200)
            )
        ).all()
        for row in rows:
            await publish(row.id, row.priority)
            row.next_attempt_at = None
            published += 1
        if stuck or rows:
            await session.commit()
    if published:
        log.info("published %s due notifications", published)
    return published


async def run() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await seed(session)
    while True:
        await tick()
        await asyncio.sleep(2)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
