"""Instagram y TikTok con un actor falso: sin red ni créditos.

Correr desde services/api: .venv/bin/python -m unittest discover -s tests
"""

import asyncio
import os
import unittest
from unittest import mock

from app.lib.sources import apify
from app.lib.types import SearchQuery

PRODUCT = "iPhone 15 128 GB"


def ig_post(caption, user="tiendave", url="https://www.instagram.com/p/A1/", comments=12):
    return {
        "caption": caption,
        "ownerUsername": user,
        "ownerFullName": "Tienda VE",
        "url": url,
        "commentsCount": comments,
        "timestamp": "2026-10-20T14:00:00.000Z",
    }


def tt_video(text, user="ofertasve", url="https://www.tiktok.com/@ofertasve/video/1"):
    return {
        "text": text,
        "webVideoUrl": url,
        "commentCount": 30,
        "createTimeISO": "2026-10-21T10:00:00.000Z",
        "authorMeta": {"name": user, "nickName": "Ofertas VE", "profileUrl": f"https://www.tiktok.com/@{user}",
                       "fans": 52000},
    }  # fmt: skip


class FakeActor:
    """Devuelve las publicaciones que le den, o lo que tarde o falle la corrida."""

    def __init__(self, items, seconds=0):
        self.items = items
        self.seconds = seconds
        self.inputs = []

    async def __call__(self, actor, run_input):
        self.inputs.append((actor, run_input))
        if self.seconds:
            await asyncio.sleep(self.seconds)
        if isinstance(self.items, Exception):
            raise self.items
        return self.items


class ApifyTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        apify._cache.clear()
        apify._runs.clear()
        patcher = mock.patch.dict(os.environ, {"APIFY_TOKEN": "fake"})
        patcher.start()
        self.addCleanup(patcher.stop)

    async def search(self, source, actor, product=PRODUCT):
        with mock.patch.object(apify, "run_actor", actor):
            return await source.search(SearchQuery(text=product))

    # ── Hashtag ────────────────────────────────────────────────────────────────────────────

    def test_the_hashtag_drops_the_presentation(self):
        self.assertEqual(apify._hashtag("Harina PAN 1 kg"), "harinapan")
        self.assertEqual(apify._hashtag("iPhone 15 128 GB"), "iphone15")
        self.assertEqual(apify._hashtag("Smart TV 32 pulgadas"), "smarttv")
        self.assertEqual(apify._hashtag(""), "")

    # ── Precio ─────────────────────────────────────────────────────────────────────────────

    def test_the_dollar_price_wins_over_the_bolivar_one(self):
        price = apify._price("iPhone 15 128GB nuevo $680 o Bs. 136.000")
        self.assertEqual((price.amount, price.currency), (680, "USD"))

    def test_a_post_with_two_products_leaves_no_price(self):
        self.assertIsNone(apify._price("iPhone 14 $500 y iPhone 15 $680"))

    def test_a_phone_number_is_not_a_price(self):
        self.assertIsNone(apify._price("iPhone 15 128GB disponible, 0414 1234567"))

    # ── Instagram ──────────────────────────────────────────────────────────────────────────

    async def test_instagram_posts_become_offers(self):
        actor = FakeActor([ig_post("iPhone 15 128 GB nuevo sellado $680\nEnvíos a todo el país #iphone15")])
        result = await self.search(apify.instagram_source, actor)
        offer, merchant = result.offers[0], result.merchants[0]
        self.assertEqual((offer.price.amount, offer.price.currency), (680, "USD"))
        self.assertEqual(offer.title, "iPhone 15 128 GB nuevo sellado $680")
        self.assertEqual(offer.seen_at, "2026-10-20T14:00:00.000Z")
        self.assertEqual((merchant.id, merchant.channel, merchant.delivers), ("ig:tiendave", "instagram", True))
        self.assertEqual(merchant.comments, 12)
        self.assertEqual(actor.inputs[0][1]["directUrls"], ["https://www.instagram.com/explore/tags/iphone15/"])

    async def test_a_post_about_another_product_is_left_out(self):
        actor = FakeActor([ig_post("iPhone 14 Pro Max 256 GB $900")])
        self.assertEqual((await self.search(apify.instagram_source, actor)).offers, [])

    async def test_price_in_the_dm_keeps_the_offer_without_a_price(self):
        actor = FakeActor([ig_post("iPhone 15 128 GB disponible, precio por DM")])
        offer = (await self.search(apify.instagram_source, actor)).offers[0]
        self.assertIsNone(offer.price)

    async def test_a_post_without_a_price_or_a_dm_is_left_out(self):
        actor = FakeActor([ig_post("iPhone 15 128 GB ya disponible en tienda")])
        self.assertEqual((await self.search(apify.instagram_source, actor)).offers, [])

    # ── TikTok ─────────────────────────────────────────────────────────────────────────────

    async def test_tiktok_videos_become_offers(self):
        actor = FakeActor([tt_video("iPhone 15 128GB en Bs. 136.000, delivery incluido")])
        result = await self.search(apify.tiktok_source, actor)
        offer, merchant = result.offers[0], result.merchants[0]
        self.assertEqual((offer.price.amount, offer.price.currency), (136000, "VES"))
        self.assertEqual((merchant.id, merchant.followers, merchant.delivers), ("tt:ofertasve", 52000, True))
        self.assertEqual(actor.inputs[0][1]["proxyCountryCode"], "VE")

    # ── Plazo y caché ──────────────────────────────────────────────────────────────────────

    async def test_a_slow_run_leaves_the_search_empty_and_fills_the_cache(self):
        actor = FakeActor([ig_post("iPhone 15 128 GB $680")], seconds=0.2)
        with mock.patch.object(apify, "LIVE_WAIT_S", 0.01):
            self.assertEqual((await self.search(apify.instagram_source, actor)).offers, [])
        await asyncio.sleep(0.3)  # la corrida sigue aunque la búsqueda ya no la espere
        self.assertEqual(len((await self.search(apify.instagram_source, actor)).offers), 1)
        self.assertEqual(len(actor.inputs), 1)  # la segunda búsqueda sale de la caché

    async def test_a_failed_run_does_not_break_the_search(self):
        actor = FakeActor(RuntimeError("apify caído"))
        self.assertEqual((await self.search(apify.instagram_source, actor)).offers, [])

    async def test_without_a_token_the_source_is_off(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(apify.ApifySource(
                "x", "instagram", "a", apify._instagram_input, apify._instagram_offers, apify._instagram_profiles
            ).enabled)


if __name__ == "__main__":
    unittest.main()
