from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()
connect_args = {}
kwargs = {"echo": False}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    kwargs["pool_size"] = 10
    kwargs["max_overflow"] = 20

engine = create_async_engine(settings.database_url, connect_args=connect_args, **kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
