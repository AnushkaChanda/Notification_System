from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import metrics
from app.config import get_settings
from app.db import get_session
from app.models import Channel, Notification
from app.queue import queue_depths
from app.schemas import (
    BatchCreate,
    EnqueueResult,
    NotificationCreate,
    NotificationOut,
    PreferencePatch,
)
from app.services.enqueue import enqueue, enqueue_batch, get_notification
from app.services.preferences import set_preference
from app.services.send import replay_from_dlq

router = APIRouter()


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if x_api_key != get_settings().api_key:
        raise HTTPException(status_code=401, detail="invalid_api_key")


@router.post("/v1/notifications", response_model=EnqueueResult, status_code=202)
async def create_notification(
    body: NotificationCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_api_key),
):
    try:
        notification, duplicate = await enqueue(session, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EnqueueResult(notification_id=notification.id, status=notification.status, duplicate=duplicate)


@router.post("/v1/notifications/batch", status_code=202)
async def create_batch(
    body: BatchCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_api_key),
):
    try:
        results = await enqueue_batch(session, body.notifications)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "items": [
            EnqueueResult(notification_id=n.id, status=n.status, duplicate=dup).model_dump()
            for n, dup in results
        ]
    }


@router.get("/v1/notifications/{notification_id}", response_model=NotificationOut)
async def read_notification(
    notification_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_api_key),
):
    notification = await get_notification(session, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="not_found")
    return notification


@router.get("/v1/activity", response_model=list[NotificationOut])
async def activity(
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_api_key),
    limit: int = Query(default=20, le=50),
    user_id: Optional[str] = None,
):
    stmt = select(Notification).order_by(Notification.created_at.desc()).limit(limit)
    if user_id:
        stmt = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
    rows = await session.scalars(stmt)
    return list(rows)


@router.get("/v1/users/{user_id}/notifications", response_model=list[NotificationOut])
async def user_inbox(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_api_key),
    limit: int = Query(default=50, le=200),
):
    rows = await session.scalars(
        select(Notification)
        .where(Notification.user_id == user_id, Notification.channel == Channel.inapp)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    return list(rows)


@router.patch("/v1/users/{user_id}/preferences")
async def patch_preferences(
    user_id: str,
    body: PreferencePatch,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_api_key),
):
    try:
        row = await set_preference(session, user_id, body.category, body.channel, body.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"user_id": row.user_id, "category": row.category, "channel": row.channel, "enabled": row.enabled}


@router.post("/v1/admin/dlq/{notification_id}/replay", response_model=NotificationOut)
async def replay(
    notification_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_api_key),
):
    try:
        return await replay_from_dlq(session, notification_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/metrics")
async def read_metrics():
    return {"mode": get_settings().mode, "counters": dict(metrics.metrics), "queue_depth": await queue_depths()}
