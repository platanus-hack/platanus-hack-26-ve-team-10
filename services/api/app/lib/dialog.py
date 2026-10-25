"""Lo que la conversación dejó a medias: la pregunta abierta y los botones ofrecidos.

Cloud Run corre hasta cuatro copias de prais-api (infra/config.sh), así que esto no
puede vivir en un dict del proceso: la pregunta sale de una copia y el toque entra
por otra. Un botón vuelve como su propio título, sin el producto, así que sin este
estado "Solo nuevos" se buscaría como si fuera un producto.

Va en la misma base que las sesiones y la deduplicación de WhatsApp, con el mismo
trato: sin SESSION_DATABASE_URL (el caso local) queda en memoria y se pierde al
reiniciar, que para la demo basta.
"""

import asyncio
import json
import time
from typing import Any, Protocol

from sqlalchemy import Column, Float, MetaData, String, Table, delete, insert, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

# WhatsApp solo deja contestar libre 24 horas. Un diálogo más viejo que eso ya no
# existe para la persona: un toque rezagado no revive el producto de anteayer.
TTL_SECONDS = 24 * 60 * 60

_metadata = MetaData()
_dialogs = Table(
    "dialogs",
    _metadata,
    Column("user_id", String, primary_key=True),
    Column("state", String, nullable=False),
    Column("updated_at", Float, nullable=False),
)


class DialogStore(Protocol):
    async def ensure_schema(self) -> None: ...

    async def load(self, user_id: str) -> dict[str, Any]: ...

    async def save(self, user_id: str, state: dict[str, Any]) -> None: ...

    async def drop(self, user_id: str) -> None: ...

    async def clear(self) -> None: ...


def _alive(updated_at: float, now: float) -> bool:
    return now - updated_at < TTL_SECONDS


class MemoryDialogStore:
    def __init__(self) -> None:
        self._rows: dict[str, tuple[dict[str, Any], float]] = {}
        self._lock = asyncio.Lock()

    async def ensure_schema(self) -> None:
        return None

    async def load(self, user_id: str) -> dict[str, Any]:
        async with self._lock:
            row = self._rows.get(user_id)
            if row is None or not _alive(row[1], time.time()):
                return {}
            return dict(row[0])

    async def save(self, user_id: str, state: dict[str, Any]) -> None:
        async with self._lock:
            self._rows[user_id] = (dict(state), time.time())

    async def drop(self, user_id: str) -> None:
        async with self._lock:
            self._rows.pop(user_id, None)

    async def clear(self) -> None:
        async with self._lock:
            self._rows.clear()


class SqlDialogStore:
    def __init__(self, db: AsyncEngine) -> None:
        self._engine = db
        self._ready = False

    async def ensure_schema(self) -> None:
        if self._ready:
            return
        async with self._engine.begin() as conn:
            await conn.run_sync(_metadata.create_all)
        self._ready = True

    async def load(self, user_id: str) -> dict[str, Any]:
        await self.ensure_schema()
        async with self._engine.begin() as conn:
            found = await conn.execute(_dialogs.select().where(_dialogs.c.user_id == user_id))
            row = found.mappings().first()
        if row is None or not _alive(row["updated_at"], time.time()):
            return {}
        state = json.loads(row["state"])
        return state if isinstance(state, dict) else {}

    async def save(self, user_id: str, state: dict[str, Any]) -> None:
        await self.ensure_schema()
        body, now = json.dumps(state), time.time()
        async with self._engine.begin() as conn:
            result = await conn.execute(
                update(_dialogs).where(_dialogs.c.user_id == user_id).values(state=body, updated_at=now)
            )
            if result.rowcount:
                return
            try:
                async with conn.begin_nested():
                    await conn.execute(insert(_dialogs).values(user_id=user_id, state=body, updated_at=now))
            except IntegrityError:
                # Otra copia guardó primero: la suya es tan buena como la nuestra.
                await conn.execute(
                    update(_dialogs).where(_dialogs.c.user_id == user_id).values(state=body, updated_at=now)
                )

    async def drop(self, user_id: str) -> None:
        await self.ensure_schema()
        async with self._engine.begin() as conn:
            await conn.execute(delete(_dialogs).where(_dialogs.c.user_id == user_id))

    async def clear(self) -> None:
        await self.ensure_schema()
        async with self._engine.begin() as conn:
            await conn.execute(delete(_dialogs))


_store: DialogStore | None = None


def build_dialog_store() -> DialogStore:
    from app.runtime import engine

    db = engine()
    if db is None:
        return MemoryDialogStore()
    return SqlDialogStore(db)


def set_store(store: DialogStore) -> None:
    global _store
    _store = store


def _current() -> DialogStore:
    global _store
    if _store is None:
        _store = build_dialog_store()
    return _store


async def ensure_schema() -> None:
    await _current().ensure_schema()


async def load(user_id: str) -> dict[str, Any]:
    return await _current().load(user_id)


async def save(user_id: str, state: dict[str, Any]) -> None:
    await _current().save(user_id, state)


async def drop(user_id: str) -> None:
    await _current().drop(user_id)


async def clear() -> None:
    await _current().clear()
