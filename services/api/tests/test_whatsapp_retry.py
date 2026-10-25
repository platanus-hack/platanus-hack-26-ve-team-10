"""Un reintento de WhatsApp reenvía la respuesta guardada y no vuelve a preguntar al agente."""

import asyncio
import unittest
from unittest import mock

from app.agent import PraisAnswer
from app.lib import replies
from app.lib.replies import MemoryReplyStore, ReplyInProgress
from app.routes import whatsapp


def _event(message_id: str, text: str = "iphone 15") -> dict:
    return {
        "phone_number_id": "99",
        "message": {"id": message_id, "from": "584121112233", "type": "text", "text": {"body": text}},
    }


class WhatsappRetryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        whatsapp._running.clear()
        whatsapp._inbox.clear()
        self.store = MemoryReplyStore()
        replies.set_store(self.store)
        self.asked: list[str] = []
        self.sent: list[dict] = []

        async def ask(_user_id: str, message: str) -> PraisAnswer:
            self.asked.append(message)
            return PraisAnswer(text="abre la tienda ejemplo", listings=[])

        async def post(_phone_number_id: str, payload: dict) -> None:
            self.sent.append(payload)

        self._ask = mock.patch.object(whatsapp, "ask_prais", ask)
        self._post = mock.patch.object(whatsapp, "_post_message", post)
        self._cards = mock.patch.object(whatsapp, "shopping_message", mock.AsyncMock(return_value=None))
        self._ask.start()
        self._post.start()
        self._cards.start()

    async def asyncTearDown(self) -> None:
        self._ask.stop()
        self._post.stop()
        self._cards.stop()
        replies.set_store(MemoryReplyStore())
        whatsapp._running.clear()
        whatsapp._inbox.clear()

    async def test_retry_resends_without_calling_the_agent(self) -> None:
        await whatsapp._reply(_event("m1"))
        await whatsapp._reply(_event("m1"))
        self.assertEqual(self.asked, ["iphone 15"])
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.sent[0], self.sent[1])

    async def test_pending_does_not_start_a_second_search(self) -> None:
        await self.store.claim("m2", takeover=False)
        with self.assertRaises(ReplyInProgress):
            await whatsapp._reply(_event("m2"))
        self.assertEqual(self.asked, [])

    async def test_last_attempt_takes_over_a_pending_message(self) -> None:
        await self.store.claim("m3", takeover=False)
        await whatsapp._reply(_event("m3"), takeover=True)
        self.assertEqual(self.asked, ["iphone 15"])

    async def test_a_message_that_arrives_while_replying_is_the_only_answer(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def ask(_user_id: str, message: str) -> PraisAnswer:
            self.asked.append(message)
            if message == "17":
                started.set()
                await release.wait()
            return PraisAnswer(text=message, listings=[])

        self._ask.stop()
        self._ask = mock.patch.object(whatsapp, "ask_prais", ask)
        self._ask.start()
        first = asyncio.create_task(whatsapp._reply(_event("a", "17")))
        await started.wait()
        await whatsapp._reply(_event("b", "el ultimo modelo"))
        release.set()
        await first
        self.assertEqual(self.asked, ["17", "17\nel ultimo modelo"])
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]["text"]["body"], "17 el ultimo modelo")
