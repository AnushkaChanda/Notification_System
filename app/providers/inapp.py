from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification
from app.providers.base import BaseProvider


class InAppProvider(BaseProvider):
    channel = "inapp"

    def __init__(self, session: AsyncSession):
        self.session = session

    async def send(self, *, to: str, subject: str, body: str, payload: dict) -> str:
        # Inbox is the notifications table itself (channel=inapp, status=sent).
        _ = (to, subject, body, payload, self.session)
        return f"inapp_{uuid4().hex[:12]}"
