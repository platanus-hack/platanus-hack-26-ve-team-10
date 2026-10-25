"""Mercado Libre por el actor de Apify, con avisos falsos: sin red ni créditos."""

import os
import unittest
from unittest import mock

from app.lib.sources import mercadolibre
from app.lib.sources.apify import ApifySource

PRODUCT = "iPhone 15 128 GB"
NOW = "2026-10-25T00:00:00-04:00"


def listing(**extra):
    base = {
        "itemId": "MLV770718527",
        "title": "Apple iPhone 15 128gb 6gb Ram Liberado",
        "listingUrl": "https://articulo.mercadolibre.com.ve/MLV-770718527-iphone-15-_JM",
        "price": 680,
        "currency": "USD",
        "condition": "NewCondition",
        "sellerId": "310309222",
        "sellerName": "Phone Cell Vem",
        "sellerReputation": "5_green",
        "sellerPowerStatus": "silver",
        "freeShipping": True,
        "images": ["a.jpg", "b.jpg", "c.jpg"],
        "description": "iPhone 15 nuevo, sellado.",
        "warranty": "6 meses",
        "scrapedAt": "2026-10-25T10:00:00Z",
    }
    return {**base, **extra}


def read(items, product=PRODUCT):
    return mercadolibre.read(items, product, NOW)


class InputTest(unittest.TestCase):
    def test_the_search_asks_for_venezuela_and_the_detail(self):
        actor, run_input = mercadolibre.entries(PRODUCT)[0]
        self.assertEqual(actor, mercadolibre.ACTOR)
        self.assertEqual(run_input["country"], "VE")
        self.assertEqual(run_input["searchQuery"], PRODUCT)
        # Sin el detalle no vienen reputación ni garantía, y el puntaje no llega al 40 %.
        self.assertIs(run_input["scrapeProductDetails"], True)

    def test_the_source_is_off_without_a_token(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(ApifySource("x", "mercadolibre", "a", mercadolibre.entries, mercadolibre.read).enabled)


class ReadTest(unittest.TestCase):
    def test_a_listing_becomes_an_offer(self):
        result = read([listing()])
        offer, merchant = result.offers[0], result.merchants[0]
        self.assertEqual((offer.price.amount, offer.price.currency), (680, "USD"))
        self.assertEqual(offer.condition, "nuevo")
        self.assertEqual((merchant.id, merchant.channel, merchant.delivers), ("ml:310309222", "mercadolibre", True))

    def test_mercado_libre_relevance_is_loose_so_the_product_is_checked(self):
        # Buscando "iPhone 15" el sitio devuelve Xiaomi: pasó en una corrida real.
        redmi = listing(title="Teléfono Celular Xiaomi Redmi 15c 8gb/256 Gb", itemId="MLV1")
        self.assertEqual(read([redmi]).offers, [])

    def test_the_condition_comes_from_the_listing(self):
        self.assertEqual(read([listing(condition="Refurbished")]).offers[0].condition, "reacondicionado")
        self.assertEqual(read([listing(condition="UsedCondition")]).offers[0].condition, "usado")
        self.assertIsNone(read([listing(condition="")]).offers[0].condition)

    def test_a_listing_without_a_published_price_is_left_out(self):
        self.assertEqual(read([listing(price=None)]).offers, [])
        self.assertEqual(read([listing(currency="ARS")]).offers, [])

    def test_the_same_link_is_one_offer(self):
        self.assertEqual(len(read([listing(), listing()]).offers), 1)

    def test_an_official_store_keeps_its_name(self):
        result = read([listing(isOfficialStore=True, officialStoreName="Daka")])
        self.assertEqual(result.merchants[0].name, "Daka")


class TrustTest(unittest.TestCase):
    def test_the_reputation_reaches_the_score(self):
        trust = next(iter(read([listing()]).trust.values()))
        self.assertEqual(trust.formula, "ml-v1")
        self.assertEqual(trust.stage, "parcial")
        measured = {signal.key: signal for signal in trust.signals if isinstance(signal.value, float)}
        self.assertEqual(measured["thermometer"].value, 1)
        self.assertIn("verde", measured["thermometer"].reason)
        self.assertIn("silver", measured["power_seller"].reason)

    def test_what_the_actor_cannot_give_is_not_invented(self):
        trust = next(iter(read([listing()]).trust.values()))
        missing = {signal.key for signal in trust.signals if signal.value is None}
        # Antigüedad, calificaciones negativas y volumen solo salen de la API oficial.
        self.assertEqual(missing, {"sales_volume", "negative_ratings", "account_age", "location", "reports"})

    def test_the_price_signal_waits_for_the_aggregator(self):
        trust = next(iter(read([listing()]).trust.values()))
        price = next(signal for signal in trust.signals if signal.key == "price_anomaly")
        self.assertEqual(price.value, "pending")

    def test_a_listing_without_reputation_measures_less_and_says_so(self):
        trust = next(iter(read([listing(sellerReputation=None, sellerPowerStatus=None)]).trust.values()))
        self.assertLess(trust.coverage, 0.40)
        self.assertEqual(trust.verdict, "sin_datos")


if __name__ == "__main__":
    unittest.main()
