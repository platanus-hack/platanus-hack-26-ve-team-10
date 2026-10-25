"""La confianza de la web abierta, ahora dentro del contrato. Sin red: los dominios van dados."""

import unittest
from datetime import UTC, datetime
from unittest import mock

from app.agents import open_web_trust
from app.lib.sources.web_trust import (
    ACCESSORY_FLAG,
    Domain,
    impersonated_brand,
    web_trust,
)
from app.lib.trust import close_listings
from app.lib.types import ExchangeRate

NOW = datetime(2026, 10, 25, tzinfo=UTC)
OLD = Domain(registered_at=datetime(2015, 3, 1, tzinfo=UTC), has_mx=True)
RATE = ExchangeRate(source="tasa de prueba", usd_to_ves=200, observed_at="2026-10-24T08:00:00-04:00")
PRODUCT = "iPhone 15 128 GB"


def score(url, title, domain=OLD, product=PRODUCT):
    return web_trust(url, title, product, domain, now=NOW)


class WebSignalsTest(unittest.TestCase):
    def test_the_specialist_leaves_the_score_open(self):
        trust = score("https://tiendasdaka.com/ve/p/iphone-15", PRODUCT)
        self.assertEqual(trust.stage, "parcial")
        self.assertIsNone(trust.score)
        self.assertEqual(trust.formula, "web-v1")

    def test_a_reviewed_chain_counts_as_verifiable_contact(self):
        trust = score("https://tiendasdaka.com/ve/p/iphone-15", PRODUCT)
        contact = next(signal for signal in trust.signals if signal.key == "contact")
        self.assertEqual(contact.value, 1)
        self.assertIn("Daka", contact.reason)
        # Dominio 15 + contacto 10 + https 5 + mx 5 + lenguaje 5: alcanza el 40 % sin el agregador.
        self.assertGreaterEqual(trust.coverage, 0.40)

    def test_an_unknown_shop_measures_less_and_says_so(self):
        trust = score("https://tiendaximena.com/iphone-15", PRODUCT)
        contact = next(signal for signal in trust.signals if signal.key == "contact")
        self.assertIsNone(contact.value)  # no se mide, no se inventa
        self.assertLess(trust.coverage, 0.40)

    def test_a_young_domain_scores_low_on_age(self):
        recent = Domain(registered_at=datetime(2026, 9, 1, tzinfo=UTC), has_mx=True)
        age = next(signal for signal in score("https://nueva.com/x", PRODUCT, recent).signals if signal.key == "domain_age")
        self.assertEqual(age.value, 0)
        self.assertIn("hace poco", age.reason)

    def test_http_loses_the_https_signal(self):
        https = next(signal for signal in score("http://tienda.com/x", PRODUCT).signals if signal.key == "https")
        self.assertEqual(https.value, 0)
        self.assertEqual(https.reason, "El sitio no usa HTTPS")

    def test_a_domain_without_mail_loses_the_mx_signal(self):
        no_mail = Domain(registered_at=OLD.registered_at, has_mx=False)
        mx = next(signal for signal in score("https://tienda.com/x", PRODUCT, no_mail).signals if signal.key == "mx")
        self.assertEqual(mx.value, 0)

    def test_what_could_not_be_looked_up_stays_null(self):
        trust = score("https://tienda.com/x", PRODUCT, Domain())
        for key in ("domain_age", "mx"):
            self.assertIsNone(next(signal for signal in trust.signals if signal.key == key).value)

    # ── Las banderas rojas que se conservan ────────────────────────────────────────────────

    def test_a_brand_in_the_domain_is_impersonation(self):
        trust = score("https://iphone-venezuela.com/p/15", PRODUCT)
        self.assertIn("El dominio imita a Apple", trust.red_flags)

    def test_the_real_brand_domain_is_not_impersonation(self):
        self.assertIsNone(impersonated_brand("apple.com", PRODUCT))
        self.assertEqual(score("https://apple.com/ve/iphone-15", PRODUCT).red_flags, [])

    def test_a_case_is_not_the_phone(self):
        trust = score("https://tienda.com/x", "Funda para iPhone 15")
        self.assertIn(ACCESSORY_FLAG, trust.red_flags)

    def test_a_case_search_is_allowed_to_find_cases(self):
        trust = score("https://tienda.com/x", "Funda para iPhone 15", product="funda iPhone 15")
        self.assertEqual(trust.red_flags, [])

    def test_the_price_rule_is_not_repeated_here(self):
        # Un precio muy bajo es price_anomaly: lo aplica el agregador, no el especialista.
        keys = {signal.key for signal in score("https://tienda.com/x", PRODUCT).signals}
        self.assertIn("price_anomaly", keys)
        price = next(signal for signal in score("https://tienda.com/x", PRODUCT).signals if signal.key == "price_anomaly")
        self.assertEqual(price.value, "pending")


class ContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_the_offer_gets_its_contract_and_the_aggregator_closes_it(self):
        offers = [
            {
                "title": "iPhone 15 128 GB",
                "url": "https://tiendasdaka.com/ve/p/iphone-15",
                "priceUsd": 680,
                "priceAmount": 680,
                "priceCurrency": "USD",
                "seenAt": "2026-10-25T09:00:00-04:00",
                "merchant": {"name": "Daka", "zone": "Venezuela", "delivers": None},
            }
        ]
        with (
            mock.patch.object(open_web_trust, "look_up", mock.AsyncMock(return_value={"tiendasdaka.com": OLD})),
            mock.patch.object(open_web_trust, "get_rate", mock.AsyncMock(return_value=RATE)),
        ):
            await open_web_trust.review_offers("iPhone 15 128 GB", offers)
        self.assertEqual(offers[0]["contractMerchant"]["id"], "web:tiendasdaka.com")
        self.assertEqual(offers[0]["contractOffer"]["price"]["amount"], 680)

        closed = close_listings([{"url": offers[0]["url"], **offers[0]}])[0]
        self.assertNotIn("trustError", closed)
        self.assertEqual(closed["trust"]["stage"], "final")
        self.assertTrue(all(signal["value"] != "pending" for signal in closed["trust"]["signals"]))
        self.assertIsInstance(closed["trustStars"], int)

    async def test_an_offer_without_a_link_is_skipped(self):
        offers = [{"title": "x", "url": ""}]
        with (
            mock.patch.object(open_web_trust, "look_up", mock.AsyncMock(return_value={})),
            mock.patch.object(open_web_trust, "get_rate", mock.AsyncMock(return_value=RATE)),
        ):
            await open_web_trust.review_offers("x", offers)
        self.assertNotIn("contractOffer", offers[0])

    async def test_no_offers_asks_nothing(self):
        with mock.patch.object(open_web_trust, "look_up", mock.AsyncMock()) as lookup:
            await open_web_trust.review_offers("x", [])
        lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
