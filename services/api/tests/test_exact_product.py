"""El agente recibe el mensaje tal como lo escribió la persona. Sin red.

Correr desde services/api: .venv/bin/python -m unittest discover -s tests
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from app.agent import ask_prais
from app.agents.orchestrator import _before_search
from app.routes.whatsapp import _inbound_text, _reply


class _Part:
    def __init__(self, text: str):
        self.text = text
        self.function_call = None


class _Final:
    def __init__(self, text: str):
        self.content = SimpleNamespace(parts=[_Part(text)])

    def is_final_response(self) -> bool:
        return True


def _text_event(sender: str, body: str) -> dict:
    return {
        "phone_number_id": "99",
        "message": {"type": "text", "from": sender, "text": {"body": body}},
    }


def _list_reply(sender: str, title: str, row_id: str) -> dict:
    return {
        "phone_number_id": "99",
        "message": {
            "type": "interactive",
            "from": sender,
            "interactive": {"type": "list_reply", "list_reply": {"id": row_id, "title": title}},
        },
    }


class AgentReceivesTheMessageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.heard: list[str] = []

    def _runner(self):
        heard = self.heard

        async def run_async(**kwargs):
            heard.append(kwargs["new_message"].parts[0].text)
            yield _Final("Listo.")

        return mock.patch("app.agent.runner.run_async", run_async)

    def _no_network(self):
        async def explode(*_args, **_kwargs):
            raise AssertionError("search_open_web was called")

        return mock.patch("app.agents.specialists.search_open_web", explode)

    async def test_any_request_reaches_the_agent_unchanged(self):
        messages = (
            "comprar un iphone 17pro",
            "Estoy buscando un apartamento en Valencia de 2 habitaciones de lujo",
            "PlayStation 5",
            "hola",
        )
        with self._runner(), self._no_network():
            for message in messages:
                await ask_prais(f"person-{message}", message)
        self.assertEqual(self.heard, list(messages))


class SearchGateTests(unittest.TestCase):
    def test_the_product_name_does_not_block_the_search(self):
        tool = SimpleNamespace(name="find_listings_open_web")
        context = SimpleNamespace(invocation_id="once", session=SimpleNamespace(user_id="somebody"))
        first = _before_search(tool, {"product": "comprar un iphone 17pro"}, context)
        self.assertIsNone(first)
        again = _before_search(tool, {"product": "comprar un iphone 17pro"}, context)
        assert again is not None
        self.assertEqual(again["listings"], [])
        self.assertEqual(again["notice"], "This search already ran for this message. Use those listings.")


class WhatsAppTests(unittest.IsolatedAsyncioTestCase):
    def test_text_and_a_tapped_row_are_the_message(self):
        self.assertEqual(
            _inbound_text(_text_event("5800", "comprar un iphone 17pro")),
            ("99", "5800", "comprar un iphone 17pro"),
        )
        tapped = _inbound_text(_list_reply("5800", "iPhone 17 Pro", "iphone-17-pro"))
        self.assertEqual(tapped, ("99", "5800", "iPhone 17 Pro"))
        reaction = {
            "phone_number_id": "99",
            "message": {"type": "reaction", "from": "5800", "reaction": {"emoji": "👍"}},
        }
        self.assertIsNone(_inbound_text(reaction))

    async def test_whatsapp_sends_the_agent_reply_for_whatever_was_asked(self):
        posted: list[dict] = []
        heard: list[str] = []

        async def capture(_phone_number_id, payload):
            posted.append(payload)

        async def run_async(**kwargs):
            heard.append(kwargs["new_message"].parts[0].text)
            yield _Final("Listo.")

        async def explode(*_args, **_kwargs):
            raise AssertionError("search_open_web was called")

        with (
            mock.patch("app.routes.whatsapp._post_message", capture),
            mock.patch("app.agent.runner.run_async", run_async),
            mock.patch("app.agents.specialists.search_open_web", explode),
        ):
            await _reply(_text_event("5800", "comprar un iphone 17pro"))
            await _reply(_text_event("5800", "toyota corolla en valencia"))
            await _reply(_list_reply("5800", "iPhone 17 Pro", "iphone-17-pro"))

        self.assertEqual(
            heard,
            [
                "comprar un iphone 17pro",
                "toyota corolla en valencia",
                "iPhone 17 Pro",
            ],
        )
        self.assertEqual([item["type"] for item in posted], ["text", "text", "text"])
        self.assertEqual(posted[0]["text"]["body"], "Listo.")
