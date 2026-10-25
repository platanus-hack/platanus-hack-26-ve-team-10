"""Hasta cinco ofertas con precio publicado. Sin red.

Correr desde services/api: .venv/bin/python -m unittest discover -s tests
"""

import unittest
from unittest import mock

from app.agent import PraisAnswer
from app.agents.listing import (
    TARGET_OPTIONS,
    card_text,
    carousel_message,
    choose_options,
    shopping_message,
)
from app.agents.orchestrator import root_agent
from app.routes.mcp import INSTRUCTIONS, Merchant, Offer, PriceSearch, _summary
from app.routes.whatsapp import _reply


def _row(
    url: str,
    price: str | None,
    usd: float | None,
    *,
    example: bool = False,
    seller: str = "Tienda",
    image: bool = True,
) -> dict:
    row = {
        "title": "Harina PAN 1 kg",
        "seller": seller,
        "channel": "web",
        "url": url,
        "price": price,
        "example": example,
        "price_usd": usd,
        "trust": 70,
    }
    if image:
        row["image_url"] = "https://images.example/pan.jpg"
    return row


class ChooseTests(unittest.TestCase):
    def test_five_cheapest_real_prices_skip_blanks_and_examples(self):
        rows = [
            _row("https://a.example/blank", None, None),
            _row("https://a.example/space", "   ", 0.1),
            _row("https://a.example/sample", "USD 0,40", 0.4, example=True, seller="Demo"),
            _row("http://a.example/cheap", "USD 0,20", 0.2),
            _row("https://a.example/8", "USD 8,00", 8),
            _row("https://a.example/1", "USD 1,00", 1),
            _row("https://a.example/4", "USD 4,00", 4),
            _row("https://a.example/3", "USD 3,00", 3),
            _row("https://a.example/2", "USD 2,00", 2),
            _row("https://a.example/5", "USD 5,00", 5),
        ]
        chosen = choose_options(rows)
        self.assertEqual([item["price_usd"] for item in chosen], [1, 2, 3, 4, 5])
        self.assertEqual(len(chosen), TARGET_OPTIONS)
        self.assertTrue(all(not item["example"] for item in chosen))

    def test_fewer_real_prices_come_back_without_example_padding(self):
        chosen = choose_options(
            [
                _row("https://a.example/real", "USD 3,00", 3),
                _row("https://a.example/dm", None, None),
                _row("https://a.example/sample", "USD 1,00", 1, example=True),
            ]
        )
        self.assertEqual([item["url"] for item in chosen], ["https://a.example/real"])

    def test_examples_only_when_no_real_price_exists(self):
        chosen = choose_options(
            [
                _row("https://a.example/high", "USD 4,00", 4, example=True, seller="Tienda Norte"),
                _row("https://a.example/low", "USD 2,00", 2, example=True, seller="Bodegón (ejemplo)"),
                _row("https://a.example/dm", None, None, example=True),
            ]
        )
        self.assertEqual([item["price_usd"] for item in chosen], [2, 4])
        self.assertIn("ejemplo", card_text(chosen[0]).lower())
        self.assertIn("ejemplo", card_text(chosen[1]).lower())

    def test_no_priced_rows_returns_empty(self):
        self.assertEqual(choose_options([]), [])
        self.assertEqual(choose_options([_row("https://a.example/dm", None, None)]), [])


class CarouselTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_priced_cards_still_make_a_carousel(self):
        async def boom(_title: str) -> str:
            raise AssertionError("network")

        rows = [_row(f"https://a.example/{n}", f"USD {n},00", float(n)) for n in (3, 1, 2)]
        with mock.patch("app.agents.listing.marked_product_image", boom):
            payload = await carousel_message("5800", rows, "El más barato está primero.")
        assert payload is not None
        cards = payload["interactive"]["action"]["cards"]
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[0]["action"]["parameters"]["url"], "https://a.example/1")

    async def test_one_priced_card_does_not_raise(self):
        async def boom(_title: str) -> str:
            raise AssertionError("network")

        rows = [_row("https://a.example/1", "USD 2,00", 2)]
        with mock.patch("app.agents.listing.marked_product_image", boom):
            self.assertIsNone(await carousel_message("5800", rows, "Solo hay un precio."))

    async def test_one_priced_offer_is_still_a_card(self):
        async def boom(_title: str) -> str:
            raise AssertionError("network")

        rows = [_row("https://a.example/1", "USD 2,00", 2)]
        with mock.patch("app.agents.listing.marked_product_image", boom):
            payload = await shopping_message("5800", rows, "Solo hay un precio.")
        assert payload is not None
        self.assertEqual(payload["interactive"]["type"], "cta_url")
        self.assertEqual(payload["interactive"]["action"]["parameters"]["url"], "https://a.example/1")
        self.assertEqual(payload["interactive"]["action"]["parameters"]["display_text"], "Ver oferta")


def _offer(
    url: str,
    usd: float | None,
    *,
    price: str | None = "USD 1,00",
    example: bool = False,
    name: str = "Tienda",
) -> Offer:
    return Offer(
        title="Harina PAN 1 kg",
        url=url,
        price=price,
        priceUsd=usd,
        seenAt="2026-10-24T12:00:00Z",
        source="ejemplo" if example else "firecrawl",
        example=example,
        merchant=Merchant(name=name, channel="web"),
    )


class SummaryTests(unittest.TestCase):
    def test_summary_names_five_real_prices(self):
        offers = [_offer(f"https://shop.example/{n}", float(n), price=f"USD {n},00") for n in range(1, 7)]
        offers.append(_offer("https://demo.example/1", 0.5, price="USD 0,50", example=True, name="Demo"))
        offers.append(_offer("https://shop.example/dm", None, price=None, name="DM"))
        text = _summary(PriceSearch(query="Harina PAN 1 kg", offers=offers))
        self.assertIn("5 priced options, from USD 1 to USD 5.", text)
        self.assertNotIn("EXAMPLE DATA", text)
        self.assertNotIn("demo.example", text)
        self.assertIn("…and 1 more with a price.", text)
        self.assertIn("1 offer without a published price", text)

    def test_summary_uses_labeled_examples_only_without_real_prices(self):
        offers = [
            _offer("https://demo.example/1", 2, price="USD 2,00", example=True, name="Demo"),
            _offer("https://demo.example/2", 4, price="USD 4,00", example=True, name="Otra"),
        ]
        text = _summary(PriceSearch(query="Harina", offers=offers))
        self.assertIn("2 priced options", text)
        self.assertEqual(text.count("EXAMPLE DATA"), 2)

    def test_instructions_ask_for_five(self):
        self.assertIn("up to five", INSTRUCTIONS)
        self.assertNotIn("two alternatives", INSTRUCTIONS)
        self.assertIn("cinco", root_agent.instruction)


class ReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_whatsapp_sends_five_cards_and_still_replies_with_one(self):
        posted: list[dict] = []

        async def capture(_phone: str, payload: dict) -> None:
            posted.append(payload)

        answers = [
            PraisAnswer(
                text="Cinco precios.",
                listings=[_row(f"https://a.example/{n}", f"USD {n},00", float(n)) for n in range(1, 8)]
                + [_row("https://demo.example/x", "USD 0,20", 0.2, example=True)],
            ),
            PraisAnswer(
                text="Solo hay un precio publicado.",
                listings=[_row("https://a.example/1", "USD 2,00", 2)],
            ),
        ]

        async def fake(_user: str, _message: str) -> PraisAnswer:
            return answers.pop(0)

        async def boom(_title: str) -> str:
            raise AssertionError("network")

        event = {
            "phone_number_id": "99",
            "message": {"type": "text", "from": "5801", "text": {"body": "harina pan"}},
        }
        with (
            mock.patch("app.routes.whatsapp.ask_prais", fake),
            mock.patch("app.routes.whatsapp._post_message", capture),
            mock.patch("app.agents.listing.marked_product_image", boom),
        ):
            await _reply(event)
            await _reply(event)

        cards = posted[0]["interactive"]["action"]["cards"]
        self.assertEqual(posted[0]["interactive"]["type"], "carousel")
        self.assertEqual(len(cards), 5)
        self.assertEqual(cards[0]["action"]["parameters"]["url"], "https://a.example/1")
        self.assertNotIn("demo.example", str(cards))
        self.assertEqual(posted[1]["interactive"]["type"], "cta_url")
        self.assertEqual(posted[1]["interactive"]["action"]["parameters"]["url"], "https://a.example/1")
        self.assertIn("Solo hay un precio", posted[1]["interactive"]["body"]["text"])
