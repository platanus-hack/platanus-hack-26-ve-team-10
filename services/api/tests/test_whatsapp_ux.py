"""Lo que la persona ve en WhatsApp: presencia, tarjeta y salida. Sin red.

Correr desde services/api: .venv/bin/python -m unittest discover -s tests
"""

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from app.agent import RETRY, PraisAnswer, ask_prais
from app.agents.listing import (
    ONLY_NEW,
    ONLY_USED,
    button_message,
    card_text,
    mixed_condition,
    narrowed,
)
from app.lib import dialog, replies
from app.routes import whatsapp
from app.routes.whatsapp import _reply


def _event(body: str = "iPhone 15", message_id: str | None = "wamid.1", sender: str = "5801") -> dict:
    message: dict = {"type": "text", "from": sender, "text": {"body": body}}
    if message_id:
        message["id"] = message_id
    return {"phone_number_id": "99", "message": message}


def _card(url: str = "https://tienda.example/1", title: str = "iPhone 15 128 GB") -> dict:
    return {
        "url": url,
        "price": "USD 10,00",
        "title": title,
        "seller": "Tienda",
        "channel": "web",
        "trust": 80,
        "seen_at": "2026-10-24T08:00:00-04:00",
        "image_url": "https://tienda.example/foto.jpg",
    }


class CardTests(unittest.TestCase):
    def test_the_card_shows_stars_and_the_date_not_a_bare_number(self):
        text = card_text(_card())
        # "Confianza 80" no dice sobre qué. Y un precio sin fecha, con esta
        # inflación, no es un precio: lo pide la regla 7.
        self.assertNotIn("Confianza", text)
        self.assertIn("★★★★☆", text)
        self.assertIn("24 oct", text)

    def test_a_merchant_without_a_score_gets_no_stars(self):
        self.assertNotIn("★", card_text(_card() | {"trust": None}))

    def test_the_closed_contract_score_is_read_too(self):
        self.assertIn("★★★☆☆", card_text(_card() | {"trust": {"score": 70}}))


class FilterTests(unittest.TestCase):
    def test_filters_come_from_the_offers_not_from_a_catalog(self):
        mixed = [_card("https://a.co/1", "iPhone 15 usado"), _card("https://b.co/2", "iPhone 15")]
        self.assertTrue(mixed_condition(mixed))
        # Si todas son del mismo estado, separarlas no es una pregunta que valga.
        self.assertFalse(mixed_condition([_card("https://a.co/1", "iPhone 15")]))

    def test_broadening_only_drops_words_the_person_wrote(self):
        self.assertEqual(narrowed("iPhone 15 nuevo 128 GB"), ("Sin la capacidad", "iPhone 15 nuevo"))
        self.assertEqual(narrowed("iPhone 15 nuevo"), ("Nuevos y usados", "iPhone 15"))
        # De un Toyota no se inventa una capacidad que nadie nombró.
        self.assertIsNone(narrowed("Toyota Corolla"))

    def test_more_than_three_buttons_do_not_fit(self):
        self.assertIsNone(button_message("5801", "¿Cuál?", ["a", "b", "c", "d"]))
        payload = button_message("5801", "¿Lo afinamos?", [ONLY_NEW, ONLY_USED])
        assert payload is not None
        titles = [b["reply"]["title"] for b in payload["interactive"]["action"]["buttons"]]
        self.assertEqual(titles, [ONLY_NEW, ONLY_USED])


class PresenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await dialog.clear()
        replies.set_store(replies.MemoryReplyStore())
        whatsapp._inbox.clear()
        whatsapp._running.clear()
        self.posted: list[dict] = []
        self.typed: list[str] = []
        patcher = mock.patch.dict(os.environ, {"KAPSO_API_KEY": "fake"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _wired(self, answer: PraisAnswer, *, delay: float = 0.0):
        posted, typed = self.posted, self.typed

        async def capture(_phone_number_id, payload):
            posted.append(payload)

        async def typing(_phone_number_id, message_id):
            typed.append(message_id)

        async def fake_ask(_user, _message):
            if delay:
                await asyncio.sleep(delay)
            return answer

        async def no_image(_title):
            raise AssertionError("network")

        return [
            mock.patch("app.routes.whatsapp._post_message", capture),
            mock.patch("app.routes.whatsapp._show_typing", typing),
            mock.patch("app.routes.whatsapp.ask_prais", fake_ask),
            mock.patch("app.agents.listing.marked_product_image", no_image),
        ]

    def _start(self, patchers):
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_it_marks_read_as_soon_as_the_message_lands(self):
        self._start(self._wired(PraisAnswer(text="Listo.")))
        await _reply(_event())
        # Los ticks azules salen con el acuse, sin esperar a tener respuesta.
        self.assertEqual(self.typed[0], "wamid.1")

    async def test_the_indicator_is_re_emitted_because_it_dies_at_25_seconds(self):
        patchers = self._wired(PraisAnswer(text="Listo."), delay=0.08)
        patchers.append(mock.patch.object(whatsapp, "TYPING_EVERY_S", 0.01))
        self._start(patchers)
        await _reply(_event())
        # Una búsqueda puede pasar de 25 s: si solo se mandara una vez, la persona
        # vería el indicador apagarse y quedaría peor que sin ponerlo.
        self.assertGreater(len(self.typed), 1)

    async def test_the_result_names_the_product_it_searched(self):
        answer = PraisAnswer(
            text="La más barata es la primera.",
            listings=[_card(), _card("https://b.example/2")],
            product="iPhone 15 128 GB nuevo",
            priced=True,
        )
        self._start(self._wired(answer))
        await _reply(_event())
        body = self.posted[0]["interactive"]["body"]["text"]
        self.assertTrue(body.startswith("*iPhone 15 128 GB nuevo*\n"))
        self.assertIn("La más barata", body)

    async def test_filters_arrive_as_their_own_button_message(self):
        answer = PraisAnswer(
            text="Listo.",
            listings=[_card(), _card("https://b.example/2")],
            product="iPhone 15",
            buttons=[ONLY_NEW, ONLY_USED],
            priced=True,
        )
        self._start(self._wired(answer))
        await _reply(_event())
        self.assertEqual(self.posted[0]["interactive"]["type"], "carousel")
        # WhatsApp no deja colgar botones de un carrusel: van aparte.
        self.assertEqual(self.posted[1]["interactive"]["type"], "button")

    async def test_a_dead_end_still_offers_a_way_out(self):
        answer = PraisAnswer(
            text="No encontré ningún precio publicado para iPhone 15 nuevo 1 TB.",
            product="iPhone 15 nuevo 1 TB",
            buttons=["Sin la capacidad"],
        )
        self._start(self._wired(answer))
        await _reply(_event())
        self.assertEqual(self.posted[0]["type"], "text")
        self.assertIn("No encontré", self.posted[0]["text"]["body"])
        self.assertEqual(self.posted[1]["interactive"]["type"], "button")


class StuckTurnTests(unittest.IsolatedAsyncioTestCase):
    """Los dos finales mudos: el turno que no vuelve y el payload que Kapso rechaza."""

    async def asyncSetUp(self):
        await dialog.clear()
        replies.set_store(replies.MemoryReplyStore())
        whatsapp._inbox.clear()
        whatsapp._running.clear()
        self.posted: list[dict] = []
        patcher = mock.patch.dict(os.environ, {"KAPSO_API_KEY": "fake"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _start(self, patchers):
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_a_turn_that_never_returns_still_answers(self):
        posted = self.posted

        async def capture(_phone_number_id, payload):
            posted.append(payload)

        async def never(_user, _message):
            await asyncio.sleep(30)
            raise AssertionError("el tope tenía que cortar antes")

        self._start(
            [
                mock.patch("app.routes.whatsapp._post_message", capture),
                mock.patch("app.routes.whatsapp._show_typing", mock.AsyncMock()),
                mock.patch("app.routes.whatsapp.ask_prais", never),
                mock.patch.object(whatsapp, "TURN_TIMEOUT_S", 0.05),
            ]
        )
        await _reply(_event())
        # Cloud Run corta la request a los 300 s y la cola ya dio la tarea por hecha.
        # Sin este tope la persona se queda con el indicador encendido y sin respuesta.
        self.assertEqual(posted[0]["type"], "text")
        self.assertIn("tardando", posted[0]["text"]["body"])

    async def test_a_rejected_carousel_falls_back_to_the_verdict_in_text(self):
        posted = self.posted
        answer = PraisAnswer(
            text="La más barata es la primera.",
            listings=[_card(), _card("https://b.example/2")],
            product="iPhone 15",
            priced=True,
        )

        async def capture(_phone_number_id, payload):
            posted.append(payload)
            # Kapso contesta 400 al carrusel: un título largo, un campo de más.
            if payload.get("type") != "text":
                raise RuntimeError("400 Bad Request")

        async def fake_ask(_user, _message):
            return answer

        async def no_image(_title):
            raise AssertionError("network")

        self._start(
            [
                mock.patch("app.routes.whatsapp._post_message", capture),
                mock.patch("app.routes.whatsapp._show_typing", mock.AsyncMock()),
                mock.patch("app.routes.whatsapp.ask_prais", fake_ask),
                mock.patch("app.agents.listing.marked_product_image", no_image),
            ]
        )
        await _reply(_event())
        self.assertEqual(posted[0]["interactive"]["type"], "carousel")
        self.assertEqual(posted[1]["type"], "text")
        self.assertIn("La más barata", posted[1]["text"]["body"])
        # Y queda guardado como hecho, así el reintento de la cola reenvía el texto.
        claim = await replies.claim("wamid.1", takeover=False)
        self.assertEqual(claim.kind, "done")
        self.assertEqual(claim.payload["type"], "text")


class FollowupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await dialog.clear()
        self.heard: list[str] = []
        self.cards: list[dict] = []
        self.explode = False

    def _wired(self):
        heard, holder = self.heard, self

        async def run_async(**kwargs):
            heard.append(kwargs["new_message"].parts[0].text)
            if holder.explode:
                raise RuntimeError("se cayó")
            yield SimpleNamespace(
                content=SimpleNamespace(parts=[SimpleNamespace(text="Listo.", function_call=None)]),
                is_final_response=lambda: True,
            )

        return [
            mock.patch("app.agent.runner.run_async", run_async),
            mock.patch("app.agent._event_listings", lambda _e: list(holder.cards)),
            mock.patch("app.agent._event_searched", lambda _e: True),
        ]

    def _start(self):
        for patcher in self._wired():
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_a_tap_searches_the_filtered_product(self):
        self.cards = [_card("https://a.co/1", "iPhone 15 usado"), _card("https://b.co/2", "iPhone 15")]
        self._start()
        found = await ask_prais("wa-ref", "iPhone 15")
        self.assertTrue(found.priced)
        self.assertEqual(found.buttons, [ONLY_NEW, ONLY_USED])

        # El botón vuelve solo con su título: sin el estado guardado, "Solo nuevos"
        # se buscaría como si fuera un producto.
        await ask_prais("wa-ref", ONLY_NEW)
        self.assertIn("iphone 15 nuevo", self.heard[-1].lower())

    async def test_no_price_offers_to_broaden_by_dropping_what_was_written(self):
        self.cards = [_card("https://a.co/1") | {"price": None}]
        self._start()
        answer = await ask_prais("wa-none", "iPhone 15 128 GB")
        self.assertFalse(answer.priced)
        # La capacidad sale del mensaje, no del modelo que guardó la sesión.
        self.assertEqual(answer.buttons, ["Sin la capacidad"])

    async def test_nothing_at_all_says_so_and_names_the_product(self):
        self.cards = []
        self._start()
        answer = await ask_prais("wa-zero", "iPhone 15 128 GB")
        # Sin nada que mostrar, el texto del modelo no aporta: se dice qué no se halló.
        self.assertIn("iphone 15 128 gb", answer.text.lower())
        self.assertEqual(answer.buttons, ["Sin la capacidad"])

    async def test_a_failed_search_keeps_the_query_and_offers_a_retry(self):
        self.explode = True
        self._start()
        failed = await ask_prais("wa-boom", "iPhone 15")
        self.assertIn("iphone 15", failed.text.lower())
        self.assertEqual(failed.buttons, [RETRY])

    async def test_a_greeting_gets_no_search_buttons(self):
        self._start()
        with mock.patch("app.agent._event_searched", lambda _e: False):
            answer = await ask_prais("wa-hola", "hola")
        # Sin búsqueda no hay callejón del que salir: ofrecerlo sería ruido.
        self.assertEqual(answer.buttons, [])


if __name__ == "__main__":
    unittest.main()
