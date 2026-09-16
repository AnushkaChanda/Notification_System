from __future__ import annotations

from typing import Optional

from app.models import Category, Channel, Status


RETRYABLE_MARKERS = ("timeout", "unavailable", "503", "429", "temporary", "connection")


def is_retryable(error: str) -> bool:
    lower = error.lower()
    if any(code in lower for code in ("400", "401", "403", "404", "invalid", "permanent")):
        if "429" in lower:
            return True
        return False
    return True


def skip_otp_opt_out(category: Category) -> bool:
    return category == Category.otp


def terminal_status(status: Status) -> bool:
    return status in {Status.sent, Status.skipped, Status.failed}


def channel_destination_ok(
    channel: Channel, email: Optional[str], phone: Optional[str], token: Optional[str]
) -> Optional[str]:
    if channel == Channel.email and not email:
        return "missing_email"
    if channel == Channel.sms and not phone:
        return "missing_phone"
    if channel == Channel.push and not token:
        return "missing_push_token"
    return None
