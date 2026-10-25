"""Pregunta una elección que cambia el precio antes de buscar. Sin red.

Correr desde apps/api: .venv/bin/python -m unittest discover -s tests
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

    async def test_text_answers_then_search_that_product(self):
        with self._runner(), self._no_network():
            first = await ask_prais("wa-text", "iPhone 14")
            self.assertEqual(self.searches, [])
            self.assertIn("iPhone 14 Pro Max", first.choices)

            pro = await ask_prais("wa-text", "el pro")
            self.assertEqual(self.searches, [])
            self.assertEqual(pro.list_section, "Estado")
            self.assertNotIn("iPhone 14 Pro Max", pro.choices)

            storage = await ask_prais("wa-text", "nuevo")
            self.assertEqual(self.searches, [])
            self.assertIn("128 GB", storage.choices)
            self.assertIn("1 TB", storage.choices)

            done = await ask_prais("wa-text", "256")
        self.assertEqual(done.choices, [])
        self.assertEqual(self.searches, ["iPhone 14 Pro nuevo 256 GB"])

    async def test_one_reply_can_close_the_remaining_choices(self):
        with self._runner(), self._no_network():
            await ask_prais("wa-once", "quiero un iPhone 14")
            done = await ask_prais("wa-once", "el pro de 256 nuevo")
        self.assertEqual(done.choices, [])
        self.assertEqual(self.searches, ["quiero un iPhone 14 Pro nuevo 256 GB"])

    async def test_pro_max_does_not_match_plain_pro(self):
        with self._runner(), self._no_network():
            await ask_prais("wa-max", "iPhone 14")
            condition = await ask_prais("wa-max", "pro max")
            self.assertEqual(condition.list_section, "Estado")
            await ask_prais("wa-max", "nuevo")
            done = await ask_prais("wa-max", "Me da igual")
        self.assertEqual(done.choices, [])
        self.assertEqual(self.searches, ["iPhone 14 Pro Max nuevo"])

    async def test_me_da_igual_closes_only_that_question(self):
        with self._runner(), self._no_network():
            await ask_prais("wa-any", "iPhone 14 nuevo")
            answer = await ask_prais("wa-any", "me da igual")
        self.assertEqual(self.searches, [])
        self.assertEqual(answer.list_section, "Capacidad")
        self.assertNotIn("1 TB", answer.choices)

    async def test_regular_model_then_storage_without_one_terabyte(self):
        with self._runner(), self._no_network():
            await ask_prais("wa-base", "iPhone 14")
            condition = await ask_prais("wa-base", "el regular")
            self.assertEqual(condition.list_section, "Estado")
            storage = await ask_prais("wa-base", "Usado")
        self.assertIn("512 GB", storage.choices)
        self.assertNotIn("1 TB", storage.choices)
        self.assertEqual(self.searches, [])

    async def test_one_message_with_every_choice_searches_immediately(self):
        with self._runner(), self._no_network():
            answer = await ask_prais("wa-full", "iPhone 14 Pro Max 256 GB usado")
        self.assertEqual(answer.choices, [])
        self.assertEqual(self.searches, ["iPhone 14 Pro Max 256 GB usado"])

    async def test_console_stops_after_model_and_condition(self):
        with self._runner(), self._no_network():
            await ask_prais("wa-ps", "PlayStation 5")
            condition = await ask_prais("wa-ps", "Slim")
            self.assertEqual(condition.list_section, "Estado")
            done = await ask_prais("wa-ps", "nuevo")
        self.assertEqual(done.choices, [])
        self.assertEqual(self.searches, ["PlayStation 5 Slim nuevo"])

    async def test_blocked_tool_does_not_search(self):
        tool = SimpleNamespace(name="find_listings_open_web")
        blocked = _before_search(
            tool,
            {"product": "iPhone 14"},
            SimpleNamespace(invocation_id="block-1", session=SimpleNamespace(user_id="nobody")),
        )
        assert blocked is not None
        self.assertEqual(blocked["listings"], [])
        self.assertEqual(blocked["notice"], "Ask this one question and stop. Do not search.")
        self.assertIn("iPhone 14 Pro", blocked["ask"]["choices"])

        allowed = _before_search(
            tool,
            {"product": "iPhone 14 Pro Max 256 GB usado"},
            SimpleNamespace(invocation_id="allow-1", session=SimpleNamespace(user_id="nobody")),
        )
        self.assertIsNone(allowed)

    async def test_waived_product_may_be_searched(self):
        with self._runner(), self._no_network():
            await ask_prais("wa-waive", "iPhone 14")
            await ask_prais("wa-waive", "Me da igual")
            await ask_prais("wa-waive", "Me da igual")
            done = await ask_prais("wa-waive", "Me da igual")
        self.assertEqual(done.choices, [])
        self.assertEqual(self.searches, ["iPhone 14"])
        tool = SimpleNamespace(name="find_listings_open_web")
        allowed = _before_search(
            tool,
            {"product": "iPhone 14"},
            SimpleNamespace(invocation_id="waive-1", session=SimpleNamespace(user_id="wa-waive")),
        )
        self.assertIsNone(allowed)


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

        async def run_async(**kwargs):
            self.sent = kwargs["new_message"].parts[0].text
            yield _Final("Listo.")

        async def explode(*_args, **_kwargs):
            raise AssertionError("search_open_web was called")

        with (
            mock.patch("app.routes.whatsapp._post_message", capture),
            mock.patch("app.agent.runner.run_async", run_async),
            mock.patch("app.agents.specialists.search_open_web", explode),
        ):
            await _reply(_text_event("5800", "iPhone 14"))
            await _reply(_list_reply("5800", "iPhone 14 Pro", "iphone-14-pro"))
            await _reply(_text_event("5800", "nuevo"))
            self.assertFalse(hasattr(self, "sent"))
            await _reply(_text_event("5800", "128 GB"))

        self.assertEqual(posted[0]["type"], "interactive")
        self.assertEqual(posted[0]["interactive"]["type"], "list")
        titles = [row["title"] for row in posted[0]["interactive"]["action"]["sections"][0]["rows"]]
        self.assertEqual(
            titles,
            ["iPhone 14", "iPhone 14 Plus", "iPhone 14 Pro", "iPhone 14 Pro Max", "Me da igual"],
        )
        second = [row["title"] for row in posted[1]["interactive"]["action"]["sections"][0]["rows"]]
        self.assertEqual(second, ["Nuevo", "Usado", "Me da igual"])
        third = [row["title"] for row in posted[2]["interactive"]["action"]["sections"][0]["rows"]]
        self.assertIn("128 GB", third)
        self.assertEqual(posted[3]["type"], "text")
        self.assertEqual(self.sent, "iPhone 14 Pro nuevo 128 GB")
