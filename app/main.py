from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.routes import router
from app.config import get_settings
from app.db import SessionLocal, engine
from app.models import Base
from app.queue import get_channel
from app.seed import seed

logging.basicConfig(level=get_settings().log_level)
log = logging.getLogger("notify")


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await seed(session)
    settings = get_settings()
    if settings.is_local:
        from app.runtime import start_background

        start_background()
        log.info("api ready (local mode: sqlite + in-process workers)")
    else:
        await get_channel()
        log.info("api ready (broker mode)")
    yield


app = FastAPI(title="Notification System", version="1.0.0", lifespan=lifespan)
app.include_router(router)

INDEX = Path(__file__).parent / "static" / "index.html"


@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(INDEX)
