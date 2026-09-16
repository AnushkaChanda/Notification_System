from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

import aio_pika

from app.config import get_settings
from app.db import SessionLocal, engine
from app.models import Base
from app.queue import QUEUES, get_channel
from app.seed import seed
from app.services.send import process_notification

logging.basicConfig(level=get_settings().log_level)
log = logging.getLogger("worker")


async def handle_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process():
        payload = json.loads(message.body.decode())
        notification_id = UUID(payload["notification_id"])
        async with SessionLocal() as session:
            await process_notification(session, notification_id)
        log.info("processed %s", notification_id)


async def consume() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await seed(session)

    channel = await get_channel()
    await channel.set_qos(prefetch_count=32)
    for name in QUEUES.values():
        queue = await channel.declare_queue(name, durable=True)
        await queue.consume(handle_message)
        log.info("consuming %s", name)
    await asyncio.Future()


def main() -> None:
    asyncio.run(consume())


if __name__ == "__main__":
    main()
