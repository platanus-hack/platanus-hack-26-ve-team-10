"""Un mensaje de WhatsApp se responde una sola vez, aunque la cola reintente.

La fila queda en pending mientras el agente corre. Si ese intento muere, otro
puede tomarla pasado el plazo o en el último reintento. Cuando el envío ya
salió, un reintento reenvía el mismo payload y no vuelve a llamar al agente.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import Column, Float, MetaData, String, Table, insert, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

LEASE_SECONDS = 120

_metadata = MetaData()
_replies = Table(
    "whatsapp_replies",
    _metadata,
    Column("message_id", String, primary_key=True),
    Column("status", String, nullable=False),
    Column("payload", String, nullable=True),
    Column("started_at", Float, nullable=False),
)


class ReplyInProgress(Exception):
    """Otro intento de este mensaje sigue dentro del plazo. La cola debe esperar."""


@dataclass(frozen=True)
class Claim:
    kind: str
    payload: dict[str, Any] | None = None


class ReplyStore(Protocol):
    async def ensure_schema(self) -> None: ...

    async def claim(self, message_id: str, *, takeover: bool) -> Claim: ...

    async def complete(self, message_id: str, payload: dict[str, Any]) -> None: ...


def _fresh(started_at: float, now: float) -> bool:
    return now - started_at < LEASE_SECONDS


class MemoryReplyStore:
    def __init__(self) -> None:
        self._rows: dict[str, tuple[str, float, dict[str, Any] | None]] = {}
        self._lock = asyncio.Lock()

    async def ensure_schema(self) -> None:
        return None

    async def claim(self, message_id: str, *, takeover: bool) -> Claim:
        async with self._lock:
            return self._claim(message_id, takeover=takeover, now=time.time())

    def _claim(self, message_id: str, *, takeover: bool, now: float) -> Claim:
        row = self._rows.get(message_id)
        if row and row[0] == "done" and row[2] is not None:
            return Claim("done", row[2])
        if row and row[0] == "pending" and not takeover and _fresh(row[1], now):
            return Claim("in_progress")
        self._rows[message_id] = ("pending", now, None)
        return Claim("started")

    async def complete(self, message_id: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            started = time.time()
            current = self._rows.get(message_id)
            if current:
                started = current[1]
            self._rows[message_id] = ("done", started, payload)


class SqlReplyStore:
    def __init__(self, db: AsyncEngine) -> None:
        self._engine = db
        self._ready = False

    async def ensure_schema(self) -> None:
        if self._ready:
            return
        async with self._engine.begin() as conn:
            await conn.run_sync(_metadata.create_all)
        self._ready = True

    async def claim(self, message_id: str, *, takeover: bool) -> Claim:
        await self.ensure_schema()
        now = time.time()
        async with self._engine.begin() as conn:
            found = await conn.execute(_replies.select().where(_replies.c.message_id == message_id))
            row = found.mappings().first()
            if row and row["status"] == "done" and row["payload"]:
                return Claim("done", json.loads(row["payload"]))
            pending = row and row["status"] == "pending" and not takeover and _fresh(row["started_at"], now)
            if pending:
                return Claim("in_progress")
            if row is None:
                try:
                    async with conn.begin_nested():
                        await conn.execute(
                            insert(_replies).values(
                                message_id=message_id, status="pending", payload=None, started_at=now
                            )
                        )
                except IntegrityError:
                    return Claim("in_progress")
                return Claim("started")
            await conn.execute(
                update(_replies)
                .where(_replies.c.message_id == message_id)
                .values(status="pending", payload=None, started_at=now)
            )
            return Claim("started")

    async def complete(self, message_id: str, payload: dict[str, Any]) -> None:
        await self.ensure_schema()
        body = json.dumps(payload)
        async with self._engine.begin() as conn:
            result = await conn.execute(
                update(_replies).where(_replies.c.message_id == message_id).values(status="done", payload=body)
            )
            if result.rowcount == 0:
                await conn.execute(
                    insert(_replies).values(
                        message_id=message_id, status="done", payload=body, started_at=time.time()
                    )
                )


_store: ReplyStore | None = None


def build_reply_store() -> ReplyStore:
    from app.runtime import engine

    db = engine()
    if db is None:
        return MemoryReplyStore()
    return SqlReplyStore(db)


def set_store(store: ReplyStore) -> None:
    global _store
    _store = store


def _current() -> ReplyStore:
    global _store
    if _store is None:
        _store = build_reply_store()
    return _store


async def ensure_schema() -> None:
    await _current().ensure_schema()


async def claim(message_id: str, *, takeover: bool) -> Claim:
    return await _current().claim(message_id, takeover=takeover)


async def complete(message_id: str, payload: dict[str, Any]) -> None:
    await _current().complete(message_id, payload)
