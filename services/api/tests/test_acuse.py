"""El acuse: decir qué se entendió antes de buscar, no después. Sin red.

Correr desde services/api: .venv/bin/python -m unittest discover -s tests
"""

import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from app import agent
from app.agent import ask_prais, searched_name
from app.lib import dialog
from app.routes.whatsapp import _ack_text


def _call_event(product: str, tool: str = "find_listings_open_web"):
    part = SimpleNamespace(
        function_call=SimpleNamespace(name=tool, args={"product": product}),
        function_response=None,
        text=None,
    )
    return SimpleNamespace(content=SimpleNamespace(parts=[part]), is_final_response=lambda: False)


def _final_event(text: str = "Listo."):
    part = SimpleNamespace(text=text, function_call=None, function_response=None)
    return SimpleNamespace(content=SimpleNamespace(parts=[part]), is_final_response=lambda: True)


class NameTests(unittest.TestCase):
    def test_the_intent_opener_is_dropped_not_the_product(self):
        self.assertEqual(searched_name("comprar un iphone 17pro"), "iphone 17pro")
        self.assertEqual(searched_name("quiero una macbook air m5"), "macbook air m5")
        self.assertEqual(searched_name("precio de la harina pan"), "harina pan")
        self.assertEqual(searched_name("cuánto cuesta un toyota corolla"), "toyota corolla")

    def test_a_name_that_opens_with_nothing_survives_whole(self):
        # No es un catálogo: lo que no calza con un arranque de intención pasa igual.
        self.assertEqual(searched_name("iPhone 17 Pro"), "iPhone 17 Pro")
        self.assertEqual(searched_name("Chevrolet Aveo usado"), "Chevrolet Aveo usado")
        self.assertEqual(searched_name("  apartamento  en  valencia "), "apartamento en valencia")


class TextTests(unittest.TestCase):
    def test_it_promises_what_prais_does_not_what_it_will_find(self):
        said = _ack_text("iPhone 17 Pro")
        self.assertIn("*iPhone 17 Pro*", said)
        # "Te traigo lo más confiable" sería prometer un resultado que puede no existir.
        self.assertNotIn("confiab", said.lower())
        # La frase que deja corregir mientras todavía sirve de algo.
        self.assertIn("dime cuál", said)

    def test_a_link_is_not_read_out_as_a_product_name(self):
        said = _ack_text("https://tienda.example/p/123")
        self.assertNotIn("http", said)
        self.assertIn("esa página", said)


class AckTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await dialog.clear()
        self.acked: list[str] = []

        async def on_search(product: str) -> None:
            self.acked.append(product)

        self.on_search = on_search

    def _runner(self, events, *, pause: float = 0.0):
        async def run_async(**_kwargs):
            for event in events:
                yield event
                if pause:
                    await asyncio.sleep(pause)

        return mock.patch("app.agent.runner.run_async", run_async)

    async def test_the_tool_call_is_what_says_a_search_started(self):
        events = [_call_event("comprar un iphone 17pro"), _final_event()]
        with self._runner(events, pause=0.05), mock.patch.object(agent, "ACK_GRACE_S", 0.01):
            await ask_prais("wa-ack", "comprar un iphone 17pro", self.on_search)
        # El argumento de la tool es la lectura del modelo: lee cualquier producto,
        # no solo los que un catálogo tenga escritos.
        self.assertEqual(self.acked, ["iphone 17pro"])

    async def test_a_fast_answer_does_not_spend_a_message(self):
        events = [_call_event("iPhone 17 Pro"), _final_event()]
        with self._runner(events), mock.patch.object(agent, "ACK_GRACE_S", 5):
            await ask_prais("wa-fast", "iPhone 17 Pro", self.on_search)
        # Con el caché de Firecrawl la respuesta vuelve sola: el acuse se cancela.
        self.assertEqual(self.acked, [])

    async def test_a_question_gets_no_acknowledgement(self):
        with self._runner([_final_event("¿Cuál modelo buscas?")]), mock.patch.object(agent, "ACK_GRACE_S", 0.01):
            await ask_prais("wa-ask", "un teléfono", self.on_search)
        # Si el modelo pregunta en vez de buscar, su pregunta ya llega rápido.
        self.assertEqual(self.acked, [])

    async def test_only_the_first_search_is_acknowledged(self):
        events = [
            _call_event("iPhone 17 Pro"),
            _call_event("iPhone 17 Pro", tool="find_listings_instagram"),
            _final_event(),
        ]
        with self._runner(events, pause=0.03), mock.patch.object(agent, "ACK_GRACE_S", 0.01):
            await ask_prais("wa-many", "iPhone 17 Pro", self.on_search)
        # Varias fuentes corren a la vez, pero la persona recibe un solo mensaje.
        self.assertEqual(self.acked, ["iPhone 17 Pro"])

    async def test_a_failing_acknowledgement_never_takes_the_answer_down(self):
        async def boom(_product: str) -> None:
            raise RuntimeError("Kapso dijo que no")

        events = [_call_event("iPhone 17 Pro"), _final_event("Listo.")]
        with self._runner(events, pause=0.05), mock.patch.object(agent, "ACK_GRACE_S", 0.01):
            answer = await ask_prais("wa-boom", "iPhone 17 Pro", boom)
        self.assertTrue(answer.text)

    async def test_without_a_channel_callback_nothing_changes(self):
        events = [_call_event("iPhone 17 Pro"), _final_event("Listo.")]
        with self._runner(events):
            answer = await ask_prais("wa-web", "iPhone 17 Pro")
        # La web no manda acuse y no cambia nada por eso.
        self.assertEqual(answer.text, "Listo.")


if __name__ == "__main__":
    unittest.main()
