from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import Category, Channel, Priority, Status


class NotificationCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    user_id: str
    channel: Channel
    category: Category
    priority: Priority = Priority.normal
    template_code: str
    payload: dict = Field(default_factory=dict)
    scheduled_at: Optional[datetime] = None


class BatchCreate(BaseModel):
    notifications: list[NotificationCreate] = Field(min_length=1, max_length=1000)


class PreferencePatch(BaseModel):
    category: Category
    channel: Channel
    enabled: bool


class NotificationOut(BaseModel):
    id: UUID
    idempotency_key: str
    user_id: str
    channel: Channel
    category: Category
    priority: Priority
    template_code: str
    payload: dict
    status: Status
    attempts: int
    last_error: Optional[str]
    skip_reason: Optional[str]
    provider_message_id: Optional[str]
    scheduled_at: Optional[datetime]
    sent_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class EnqueueResult(BaseModel):
    notification_id: UUID
    status: Status
    duplicate: bool = False
