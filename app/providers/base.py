class ProviderError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class BaseProvider:
    channel: str

    async def send(self, *, to: str, subject: str, body: str, payload: dict) -> str:
        raise NotImplementedError
