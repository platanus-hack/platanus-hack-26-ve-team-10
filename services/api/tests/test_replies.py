"""El registro de respuestas de WhatsApp, en memoria y en sqlite. Sin red."""

import tempfile
import unittest

from sqlalchemy.ext.asyncio import create_async_engine

from app.lib.replies import LEASE_SECONDS, MemoryReplyStore, SqlReplyStore


class MemoryReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_second_claim_returns_the_stored_payload(self) -> None:
        store = MemoryReplyStore()
        first = await store.claim("m1", takeover=False)
        self.assertEqual(first.kind, "started")
        await store.complete("m1", {"type": "text", "text": {"body": "listo"}})
        again = await store.claim("m1", takeover=False)
        self.assertEqual(again.kind, "done")
        self.assertEqual(again.payload, {"type": "text", "text": {"body": "listo"}})

    async def test_pending_blocks_until_takeover(self) -> None:
        store = MemoryReplyStore()
        await store.claim("m1", takeover=False)
        blocked = await store.claim("m1", takeover=False)
        self.assertEqual(blocked.kind, "in_progress")
        taken = await store.claim("m1", takeover=True)
        self.assertEqual(taken.kind, "started")

    async def test_stale_pending_can_be_claimed(self) -> None:
        store = MemoryReplyStore()
        await store.claim("m1", takeover=False)
        store._rows["m1"] = ("pending", store._rows["m1"][1] - LEASE_SECONDS - 1, None)
        again = await store.claim("m1", takeover=False)
        self.assertEqual(again.kind, "started")


class SqlReplyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self._tmp.name}/replies.db")
        self.store = SqlReplyStore(self.engine)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self._tmp.cleanup()

    async def test_round_trip(self) -> None:
        self.assertEqual((await self.store.claim("m1", takeover=False)).kind, "started")
        await self.store.complete("m1", {"ok": True})
        again = await self.store.claim("m1", takeover=False)
        self.assertEqual(again.kind, "done")
        self.assertEqual(again.payload, {"ok": True})
        blocked = SqlReplyStore(self.engine)
        await blocked.claim("m2", takeover=False)
        self.assertEqual((await blocked.claim("m2", takeover=False)).kind, "in_progress")
