from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI  # pyright: ignore[reportMissingImports]

from .auth import api_key_validator
from .config import settings
from .routes import router
from .session import get_runner


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize the ADK runner so Postgres session storage is ready."""
    await api_key_validator.start()
    get_runner()
    try:
        yield
    finally:
        await api_key_validator.stop()


app = FastAPI(title="Tenders Agent", lifespan=lifespan)
app.include_router(router)


@app.get("/health", tags=["health"])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    import uvicorn  # pyright: ignore[reportMissingImports]

    uvicorn.run(
        "tenders_agent.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
