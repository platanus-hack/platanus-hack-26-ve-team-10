"""El agente recibe el mensaje tal como lo escribió la persona. Sin red.

Correr desde services/api: .venv/bin/python -m unittest discover -s tests
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from app.agent import ask_prais, track_product
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

    async def test_a_link_is_compared_by_the_product_on_the_page(self):
        async def name(_url: str) -> str:
            return "iPhone 15 128 GB"

        with self._runner(), self._no_network(), mock.patch("app.agent.product_name_at", name):
            await ask_prais("link-person", "mira https://tienda.example/iphone")
        self.assertIn("iPhone 15 128 GB", self.heard[0])
        self.assertIn("No preguntes cuál modelo es", self.heard[0])

    async def test_the_same_question_is_not_asked_twice(self):
        searched: list[str] = []

        async def run_async(**_kwargs):
            yield _Final("¿Cuál iPhone buscas?")

        async def search(product: str, budget_s: float = 45):
            searched.append(product)
            return {"offers": []}

        with mock.patch("app.agent.runner.run_async", run_async), mock.patch("app.agent.search_open_web", search):
            first = await ask_prais("twice", "un iphone")
            second = await ask_prais("twice", "el normal")
        self.assertEqual(first.text, "¿Cuál iPhone buscas?")
        self.assertEqual(second.text, "Dime el nombre y lo busco.")
        self.assertEqual(searched, [])

    async def test_latest_model_does_not_ask_which_model(self):
        searched: list[str] = []

        async def run_async(**_kwargs):
            yield _Final("¿Cuál modelo de iPhone buscas?")

        async def search(product: str, budget_s: float = 45):
            searched.append(product)
            return {"offers": []}

        with mock.patch("app.agent.runner.run_async", run_async), mock.patch("app.agent.search_open_web", search):
            answer = await ask_prais("known-18", "Hola! Quiero un iphone 18\nel ultimo modelo que salio")
        self.assertEqual(answer.text, "Busco iphone 18.")
        self.assertEqual(searched, ["iphone 18"])

    async def test_a_failed_summary_still_returns_the_listings(self):
        class _Response:
            def __init__(self):
                self.function_call = None
                self.function_response = SimpleNamespace(
                    response={"listings": [{"url": "https://tienda.example/p", "title": "iPhone 17"}]}
                )
                self.text = None

        class _ToolEvent:
            def __init__(self):
                self.content = SimpleNamespace(parts=[_Response()])

            def is_final_response(self) -> bool:
                return False

        async def run_async(**_kwargs):
            yield _ToolEvent()
            raise RuntimeError("429")

        with mock.patch("app.agent.runner.run_async", run_async), self._no_network():
            answer = await ask_prais("quota", "iphone 17")
        self.assertIn("Encontré opciones", answer.text)
        self.assertEqual(answer.listings[0]["url"], "https://tienda.example/p")


class ProductMemoryTests(unittest.TestCase):
    def test_the_latest_model_keeps_the_phone_already_named(self):
        named = track_product(None, "Hola! Quiero un iphone 18")
        self.assertEqual(named, "iphone 18")
        self.assertEqual(track_product(named, "el ultimo modelo que salio"), "iphone 18")

    def test_latest_without_a_name_is_not_a_search_phrase(self):
        self.assertIsNone(track_product(None, "el ultimo modelo por favor"))
        self.assertIsNone(track_product(None, "el 17 o el 18 no me acuerdo cual es"))
        self.assertIsNone(track_product("iphone 17", "el 17 o el 18 no me acuerdo cual es"))


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

    def test_an_unresolved_phrase_is_not_searched_and_does_not_use_the_turn(self):
        tool = SimpleNamespace(name="find_listings_open_web")
        context = SimpleNamespace(invocation_id="vague", session=SimpleNamespace(user_id="somebody"))
        blocked = _before_search(tool, {"product": "el último iPhone"}, context)
        assert blocked is not None
        self.assertEqual(blocked["listings"], [])
        self.assertIn("not a product name", blocked["notice"])
        concrete = _before_search(tool, {"product": "iPhone 17"}, context)
        self.assertIsNone(concrete)


class WhatsAppTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._quiet = mock.patch("app.routes.whatsapp.QUIET_S", 0)
        self._quiet.start()

    def tearDown(self):
        self._quiet.stop()

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

        self.assertIn("comprar un iphone 17pro", heard[0])
        self.assertNotIn("Producto ya fijado", heard[0])
        self.assertEqual(heard[1], "toyota corolla en valencia")
        self.assertIn("iPhone 17 Pro", heard[2])
        self.assertEqual([item["type"] for item in posted], ["text", "text", "text"])
        # Aquí no corrió ninguna fuente, así que tampoco se encabeza con un producto:
        # eso solo pasa cuando hubo búsqueda. El cuerpo es el texto del agente.
        self.assertEqual(posted[0]["text"]["body"], "Listo.")
