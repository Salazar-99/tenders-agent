import hashlib

import asyncpg  # pyright: ignore[reportMissingImports]
from fastapi import HTTPException, status  # pyright: ignore[reportMissingImports]

from .config import settings


class ApiKeyValidator:
    """Validate QueryTenders API keys against the backend Postgres schema."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    async def start(self) -> None:
        connect_kwargs = settings.api_key_postgres_connect_kwargs()
        if not connect_kwargs:
            raise RuntimeError(
                "API key validation requires API_KEY_POSTGRES_URL, "
                "POSTGRES_ENDPOINT, or POSTGRES_URL."
            )

        self._pool = await asyncpg.create_pool(**connect_kwargs)

    async def stop(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def validate(self, api_key: str | None) -> None:
        if not api_key or not api_key.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-API-Key header.",
            )
        if not self._pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API key validator is not initialized.",
            )

        key_hash = hashlib.sha256(api_key.strip().encode("utf-8")).hexdigest()
        row = await self._pool.fetchrow(
            """
            SELECT tenant_id, created_by_user_id
            FROM api_keys
            WHERE key_hash = $1
              AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > NOW())
            """,
            key_hash,
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key.",
            )


api_key_validator = ApiKeyValidator()
