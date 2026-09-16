from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional
from uuid import UUID

from app.config import get_settings
from app.models import Priority

QUEUES = {
    Priority.critical: "notifications.critical",
    Priority.normal: "notifications.normal",
    Priority.marketing: "notifications.marketing",
}
DLQ_NAME = "notifications.dlq"

_local_queues: Dict[str, asyncio.Queue] = {}
_connection: Any = None
_channel: Any = None


def queue_for(priority: Priority) -> str:
    return QUEUES[priority]


def local_queue(name: str) -> asyncio.Queue:
    if name not in _local_queues:
        _local_queues[name] = asyncio.Queue()
    return _local_queues[name]


async def get_channel() -> Any:
    global _connection, _channel
    if get_settings().is_local:
        return None
    import aio_pika

    if _channel is None or _channel.is_closed:
        _connection = await aio_pika.connect_robust(get_settings().rabbitmq_url)
        _channel = await _connection.channel()
        await declare_queues(_channel)
    return _channel


async def declare_queues(channel: Any) -> None:
    for name in list(QUEUES.values()) + [DLQ_NAME]:
        await channel.declare_queue(name, durable=True)


async def publish(notification_id: UUID, priority: Priority) -> None:
    if get_settings().is_local:
        await local_queue(queue_for(priority)).put(str(notification_id))
        return
    import aio_pika
    from aio_pika import Message

    channel = await get_channel()
    body = json.dumps({"notification_id": str(notification_id)}).encode()
    await channel.default_exchange.publish(
        Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
        routing_key=queue_for(priority),
    )


async def publish_dlq(notification_id: UUID) -> None:
    if get_settings().is_local:
        await local_queue(DLQ_NAME).put(str(notification_id))
        return
    import aio_pika
    from aio_pika import Message

    channel = await get_channel()
    body = json.dumps({"notification_id": str(notification_id)}).encode()
    await channel.default_exchange.publish(
        Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
        routing_key=DLQ_NAME,
    )


async def queue_depths() -> Dict[str, int]:
    if get_settings().is_local:
        return {name: local_queue(name).qsize() for name in list(QUEUES.values()) + [DLQ_NAME]}
    channel = await get_channel()
    depths = {}
    for name in list(QUEUES.values()) + [DLQ_NAME]:
        q = await channel.declare_queue(name, durable=True)
        depths[name] = q.declaration_result.message_count
    return depths
