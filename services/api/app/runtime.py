"""Sesión del agente y el motor de base de datos que la guarda.

Sin SESSION_DATABASE_URL (el caso local) la conversación vive en memoria y se
pierde al reiniciar el proceso. Con la URL, cualquier copia de prais-api lee
la misma conversación desde Postgres.
"""

import os

from google.adk.sessions import DatabaseSessionService, InMemorySessionService
from google.adk.sessions.base_session_service import BaseSessionService
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

_engine: AsyncEngine | None = None


def database_url() -> str | None:
    url = os.environ.get("SESSION_DATABASE_URL", "").strip()
    return url or None


def engine() -> AsyncEngine | None:
    global _engine
    url = database_url()
    if url is None:
        return None
    if _engine is None:
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs = {
                "poolclass": StaticPool,
                "connect_args": {"check_same_thread": False},
            }
        _engine = create_async_engine(url, **kwargs)
    return _engine


def session_service() -> BaseSessionService:
    db = engine()
    if db is None:
        return InMemorySessionService()
    return DatabaseSessionService(db_engine=db)


def reset() -> None:
    """Suelta el motor cacheado. Lo usan las pruebas al cambiar la URL."""
    global _engine
    _engine = None
