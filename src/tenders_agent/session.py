from functools import lru_cache

from google.adk.runners import Runner  # pyright: ignore[reportMissingImports]
from google.adk.sessions.database_session_service import (  # pyright: ignore[reportMissingImports]
    DatabaseSessionService,
)

from .agent import root_agent
from .config import settings


@lru_cache
def get_session_service() -> DatabaseSessionService:
    """Return the Postgres-backed ADK session service."""
    if not settings.postgres_url:
        raise RuntimeError(
            "POSTGRES_URL must be set to use Postgres-backed ADK session state."
        )

    return DatabaseSessionService(settings.postgres_url)


@lru_cache
def get_runner() -> Runner:
    """Return the ADK runner wired to persistent Postgres session state."""
    return Runner(
        app_name=settings.adk_app_name,
        agent=root_agent,
        session_service=get_session_service(),
        auto_create_session=True,
    )
