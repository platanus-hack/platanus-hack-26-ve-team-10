"""El MCP es transporte: la búsqueda y la confianza son las del agente. Sin red.

Correr desde services/api: .venv/bin/python -m unittest discover -s tests
"""

import unittest
from unittest import mock

from app.agents import specialists
from app.agents.orchestrator import TRUST_SKILL, root_agent
from app.lib.trust import to_stars
from app.lib.types import ExchangeRate, SearchQuery
from app.routes import mcp


def _offer(url: str, channel: str, usd: float) -> dict:
    return {
        "title": "iPhone 14 Pro 128 GB",
        "url": url,
        "price": f"USD {usd:g}",
        "priceUsd": usd,
        "seenAt": "2026-10-25T12:00:00Z",
        "source": channel,
        "merchant": {"name": f"Tienda {channel}", "channel": channel, "zone": "Caracas", "trust": 70},
    }


class FindAllListingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.registry_calls = 0

        async def open_web(product, budget_s):
            self.assertEqual(budget_s, 25)
            return {"offers": [_offer("https://tienda.example/1", "web", 690)], "failedSources": ["firecrawl:caida.example"]}

        async def registry(query):
            self.registry_calls += 1
            return {
                "offers": [
                    _offer("https://ig.example/1", "instagram", 700),
                    _offer("https://ml.example/1", "mercadolibre", 705),
                    _offer("https://web.example/ejemplo", "web", 1),
                ],
                "failedSources": ["apify-tiktok"],
            }

        async def imported(product):
            card = {"title": product, "seller": "Amazon", "channel": "importacion", "url": "https://amazon.com/x",
                    "price": "USD 812", "price_usd": 812, "price_kind": "estimado"}
            return {"source": "importacion", "product": product, "listings": [card]}

        async def no_review(product, offers):
            return None

        for name, fake in (("search_open_web", open_web), ("search_offers", registry),
                           ("quote_import", imported), ("review_offers", no_review)):
            patcher = mock.patch.object(specialists, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_runs_every_source_the_agent_runs_and_the_registry_once(self):
        found = await specialists.find_all_listings(SearchQuery(text="iPhone 14 Pro"), 25)
        channels = sorted(card["channel"] for card in found["listings"])
        self.assertEqual(channels, ["importacion", "instagram", "mercadolibre", "web"])
        self.assertEqual(self.registry_calls, 1)
        self.assertEqual(found["failedSources"], ["apify-tiktok", "firecrawl:caida.example"])

    async def test_a_registry_offer_on_a_channel_without_a_tool_is_left_out(self):
        found = await specialists.find_all_listings(SearchQuery(text="iPhone 14 Pro"), 25)
        self.assertNotIn("https://web.example/ejemplo", [card["url"] for card in found["listings"]])

    async def test_search_prices_answers_with_those_cards(self):
        async def rate():
            return ExchangeRate(source="BCV", usd_to_ves=216.4, observed_at="2026-10-25")

        with mock.patch.object(mcp, "get_rate", rate):
            result = await mcp.search_prices("iPhone 14 Pro")
        offers = result.structured_content["offers"]
        self.assertEqual([offer["priceUsd"] for offer in offers], [690, 700, 705, 812])
        imported = offers[-1]
        self.assertEqual(imported["priceKind"], "estimado")
        self.assertEqual(imported["merchant"]["channel"], "importacion")
        instagram = offers[1]
        self.assertEqual(instagram["merchant"]["zone"], "Caracas")
        self.assertEqual(instagram["merchant"]["stars"], to_stars(70))
        self.assertIn("estimated landed price", result.content[0].text)


class OfferMappingTests(unittest.TestCase):
    def test_a_closed_score_brings_its_verdict_and_stars(self):
        card = {"title": "x", "seller": "s", "channel": "web", "url": "https://s.example", "price": "USD 1",
                "price_usd": 1, "trust": {"score": 0, "verdict": "riesgosa"}, "trustStars": 0}
        merchant = mcp._offer(card).merchant
        self.assertEqual((merchant.trust, merchant.stars, merchant.verdict), (0, 0, "riesgosa"))


class SkillTests(unittest.TestCase):
    def test_mcp_and_whatsapp_share_the_trust_skill(self):
        self.assertIn(TRUST_SKILL, mcp.INSTRUCTIONS)
        self.assertIn(TRUST_SKILL, root_agent.instruction)
        self.assertNotIn("{trust_skill}", mcp.INSTRUCTIONS)
        self.assertNotIn("trust_review", TRUST_SKILL)


if __name__ == "__main__":
    unittest.main()
