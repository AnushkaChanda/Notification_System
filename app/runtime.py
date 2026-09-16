from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.db import SessionLocal
from app.queue import QUEUES, local_queue
from app.services.send import process_notification
from app.workers.scheduler import tick

log = logging.getLogger("notify.runtime")
_tasks = []


async def _consume(name: str) -> None:
    q = local_queue(name)
    while True:
        notification_id = await q.get()
        try:
            async with SessionLocal() as session:
                await process_notification(session, UUID(notification_id))
            log.info("processed %s from %s", notification_id, name)
        except Exception:
            log.exception("failed processing %s", notification_id)
        finally:
            q.task_done()


async def _schedule() -> None:
    while True:
        try:
            await tick()
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(2)


def start_background() -> None:
    loop = asyncio.get_event_loop()
    for name in QUEUES.values():
        _tasks.append(loop.create_task(_consume(name)))
    _tasks.append(loop.create_task(_schedule()))
    log.info("in-process workers started")
