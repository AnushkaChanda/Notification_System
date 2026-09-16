from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Channel(str, enum.Enum):
    inapp = "inapp"
    email = "email"
    sms = "sms"
    push = "push"


class Category(str, enum.Enum):
    otp = "otp"
    transactional = "transactional"
    social = "social"
    marketing = "marketing"


class Priority(str, enum.Enum):
    critical = "critical"
    normal = "normal"
    marketing = "marketing"


class Status(str, enum.Enum):
    queued = "queued"
    sending = "sending"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"


def str_enum(enum_cls, name):
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        values_callable=lambda items: [item.value for item in items],
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    push_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", "category", "channel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    category: Mapped[Category] = mapped_column(str_enum(Category, "category"))
    channel: Mapped[Channel] = mapped_column(str_enum(Channel, "channel"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Template(Base):
    __tablename__ = "templates"
    __table_args__ = (UniqueConstraint("code", "channel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64))
    channel: Mapped[Channel] = mapped_column(str_enum(Channel, "channel"))
    subject: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_status_scheduled", "status", "scheduled_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    category: Mapped[Category] = mapped_column(str_enum(Category, "category"))
    priority: Mapped[Priority] = mapped_column(str_enum(Priority, "priority"))
    channel: Mapped[Channel] = mapped_column(str_enum(Channel, "channel"))
    template_code: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[Status] = mapped_column(str_enum(Status, "status"), default=Status.queued)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    skip_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
