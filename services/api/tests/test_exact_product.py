"""Pregunta una elección que cambia el precio antes de buscar. Sin red.

Correr desde services/api: .venv/bin/python -m unittest discover -s tests
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from app.agent import ask_prais, clear_product_dialog
from app.agents.clarify import next_question
from app.agents.listing import list_message
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


class QuestionTests(unittest.TestCase):
    def test_iphone_14_asks_only_the_model(self):
        question = next_question("iPhone 14", frozenset())
        assert question is not None
        self.assertEqual(question.dimension, "model")
        self.assertEqual(question.text, "¿Cuál iPhone 14 buscas?")
        self.assertEqual(
            question.choices,
            ("iPhone 14", "iPhone 14 Plus", "iPhone 14 Pro", "iPhone 14 Pro Max", "Me da igual"),
        )

    def test_exact_phone_is_ready_to_search(self):
        self.assertIsNone(next_question("iPhone 14 Pro Max 256 GB usado", frozenset()))

    def test_named_pro_asks_condition_not_another_model(self):
        question = next_question("iPhone 14 Pro", frozenset())
        assert question is not None
        self.assertEqual(question.dimension, "condition")
        self.assertEqual(question.choices, ("Nuevo", "Usado", "Me da igual"))

    def test_accessory_does_not_ask(self):
        self.assertIsNone(next_question("funda para iPhone 14", frozenset()))

    def test_playstation_asks_the_model_and_not_storage(self):
        question = next_question("PlayStation 5", frozenset())
        assert question is not None
        self.assertEqual(question.dimension, "model")
        self.assertEqual(
            question.choices,
            ("PlayStation 5", "PlayStation 5 Pro", "PlayStation 5 Slim", "Me da igual"),
        )


class SearchGateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_product_dialog()
        self.searches: list[str] = []

    def _runner(self):
        searches = self.searches

        async def run_async(**kwargs):
            searches.append(kwargs["new_message"].parts[0].text)
            yield _Final("Listo.")

        return mock.patch("app.agent.runner.run_async", run_async)

    def _no_network(self):
        async def explode(*_args, **_kwargs):
            raise AssertionError("search_open_web was called")

        return mock.patch("app.agents.specialists.search_open_web", explode)

    async def test_iphone_17pro_reaches_the_agent_unchanged(self):
        with self._runner():
            answer = await ask_prais("wa-17", "comprar un iphone 17pro")
        self.assertEqual(answer.choices, [])
        self.assertEqual(self.searches, ["comprar un iphone 17pro"])

    async def test_a_non_phone_is_not_rewritten(self):
        with self._runner():
            await ask_prais("wa-car", "Toyota Corolla")
        self.assertEqual(self.searches, ["Toyota Corolla"])

    async def test_a_vague_name_does_not_block_the_tool(self):
        tool = SimpleNamespace(name="find_listings_open_web")
        context = SimpleNamespace(invocation_id="once-1", session=SimpleNamespace(user_id="nobody"))
        first = _before_search(tool, {"product": "iPhone 14"}, context)
        self.assertIsNone(first)
        again = _before_search(tool, {"product": "iPhone 14"}, context)
        self.assertEqual(again["notice"], "This search already ran for this message. Use those listings.")


class WhatsAppListTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_product_dialog()

    def test_list_payload_matches_kapso(self):
        payload = list_message(
            "584120000000",
            "¿Cuál iPhone 14 buscas?",
            ["iPhone 14", "iPhone 14 Plus", "iPhone 14 Pro", "iPhone 14 Pro Max", "Me da igual"],
            section="Modelos",
        )
        self.assertEqual(
            payload,
            {
                "messaging_product": "whatsapp",
                "to": "584120000000",
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": "¿Cuál iPhone 14 buscas?"},
                    "action": {
                        "button": "Ver opciones",
                        "sections": [
                            {
                                "title": "Modelos",
                                "rows": [
                                    {"id": "iphone-14", "title": "iPhone 14"},
                                    {"id": "iphone-14-plus", "title": "iPhone 14 Plus"},
                                    {"id": "iphone-14-pro", "title": "iPhone 14 Pro"},
                                    {"id": "iphone-14-pro-max", "title": "iPhone 14 Pro Max"},
                                    {"id": "me-da-igual", "title": "Me da igual"},
                                ],
                            }
                        ],
                    },
                },
            },
        )

    def test_text_and_list_reply_both_count(self):
        self.assertEqual(_inbound_text(_text_event("5800", "el pro")), ("99", "5800", "el pro"))
        tapped = _inbound_text(_list_reply("5800", "iPhone 14 Pro", "iphone-14-pro"))
        self.assertEqual(tapped, ("99", "5800", "iPhone 14 Pro"))
        reaction = {
            "phone_number_id": "99",
            "message": {"type": "reaction", "from": "5800", "reaction": {"emoji": "👍"}},
        }
        self.assertIsNone(_inbound_text(reaction))

    async def test_whatsapp_sends_a_list_and_accepts_a_tap_or_text(self):
        posted: list[dict] = []

        async def capture(_phone_number_id, payload):
            posted.append(payload)

        sent: list[str] = []

        async def run_async(**kwargs):
            sent.append(kwargs["new_message"].parts[0].text)
            yield _Final("Listo.")

        async def explode(*_args, **_kwargs):
            raise AssertionError("search_open_web was called")

        with (
            mock.patch("app.routes.whatsapp._post_message", capture),
            mock.patch("app.agent.runner.run_async", run_async),
            mock.patch("app.agents.specialists.search_open_web", explode),
        ):
            await _reply(_text_event("5800", "comprar un iphone 17pro"))
            await _reply(_list_reply("5800", "iPhone 14 Pro", "iphone-14-pro"))

        self.assertEqual([item["type"] for item in posted], ["text", "text"])
        self.assertEqual(sent, ["comprar un iphone 17pro", "iPhone 14 Pro"])
