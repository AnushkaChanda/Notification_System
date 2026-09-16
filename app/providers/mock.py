import random
import uuid

from app.config import get_settings
from app.providers.base import BaseProvider, ProviderError


class MockProvider(BaseProvider):
    def __init__(self, channel: str):
        self.channel = channel

    async def send(self, *, to: str, subject: str, body: str, payload: dict) -> str:
        if payload.get("force_fail"):
            raise ProviderError("temporary provider failure", retryable=True)
        if payload.get("invalid_destination"):
            raise ProviderError("invalid destination 400", retryable=False)
        if to.endswith("-invalid"):
            raise ProviderError("invalid destination 400", retryable=False)
        if random.random() < get_settings().provider_fail_rate:
            raise ProviderError("temporary provider failure", retryable=True)
        return f"{self.channel}_{uuid.uuid4().hex[:12]}"
