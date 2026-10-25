"""El camino completo del puntaje: la fuente mide, la búsqueda arma el contrato, el agente cierra.

Sin red ni créditos: el actor es falso.
"""

import unittest
from datetime import UTC, datetime

from app.lib.sources.apify import _tiktok_offers
from app.lib.sources.apify_trust import instagram_trust, tiktok_trust
from app.lib.trust import close_listings

NOW = datetime(2026, 10, 25, tzinfo=UTC)
# 6733984297591636998 >> 32 son los segundos: una cuenta de 2019.
OLD_ACCOUNT = "6733984297591636998"


def author(**extra):
    base = {
        "id": OLD_ACCOUNT,
        "name": "tiendave",
        "nickName": "Tienda VE",
        "profileUrl": "https://www.tiktok.com/@tiendave",
        "region": "VE",
        "fans": 20000,
        "heart": 300000,
        "signature": "Equipos Apple en Caracas",
    }
    return {**base, **extra}


def video(index, *, plays=10000, likes=600, text="iPhone 15 128 GB sellado $680", **extra):
    base = {
        "text": text,
        "webVideoUrl": f"https://www.tiktok.com/@tiendave/video/{index}",
        "createTimeISO": f"2026-10-{10 + index:02d}T10:00:00.000Z",
        "playCount": plays,
        "diggCount": likes,
        "shareCount": 40,
        "collectCount": 30,
        "commentCount": 25,
        "authorMeta": author(),
    }
    return {**base, **extra}


class SpecialistTest(unittest.TestCase):
    def test_a_real_shop_measures_enough_to_be_scored(self):
        score = tiktok_trust(author(), [video(i) for i in range(5)], now=NOW)
        self.assertEqual(score.stage, "parcial")
        self.assertIsNone(score.score)  # el especialista nunca cierra
        self.assertGreaterEqual(score.coverage, 0.40)
        measured = {signal.key for signal in score.signals if isinstance(signal.value, float)}
        self.assertEqual(
            measured,
            {"age", "region", "like_view_ratio", "ratio_consistency", "hearts_per_follower",
             "shares_saves", "posting_rhythm", "risk_language"},
        )

    def test_the_price_signal_waits_for_the_aggregator(self):
        score = tiktok_trust(author(), [video(i) for i in range(5)], now=NOW)
        price = next(signal for signal in score.signals if signal.key == "price_anomaly")
        self.assertEqual(price.value, "pending")

    def test_a_brand_new_account_is_a_red_flag(self):
        days_old = str(int(datetime.now(UTC).timestamp()) - 10 * 24 * 3600 << 32)
        score = tiktok_trust(author(id=days_old), [video(i) for i in range(5)], now=datetime.now(UTC))
        self.assertIn("Cuenta con menos de un mes", score.red_flags)

    def test_views_without_likes_lowers_the_signal(self):
        score = tiktok_trust(author(), [video(i, plays=100000, likes=50) for i in range(5)], now=NOW)
        ratio = next(signal for signal in score.signals if signal.key == "like_view_ratio")
        self.assertEqual(ratio.value, 0)
        self.assertIn("vistas compradas", ratio.reason)

    def test_risk_language_in_the_caption_counts(self):
        score = tiktok_trust(
            author(), [video(i, text="iPhone 15 128 GB, no se aceptan devoluciones") for i in range(5)], now=NOW
        )
        risk = next(signal for signal in score.signals if signal.key == "risk_language")
        self.assertLess(risk.value, 1)
        self.assertIn("devoluciones", risk.reason)

    def test_one_video_is_not_enough_to_measure_proportions(self):
        score = tiktok_trust(author(), [video(0)], now=NOW)
        self.assertLess(score.coverage, 0.40)
        self.assertEqual(score.verdict, "sin_datos")

    def test_instagram_without_a_profile_measures_only_the_caption(self):
        posts = [{"caption": "iPhone 15 $680", "likesCount": 10, "commentsCount": 2, "timestamp": "2026-10-20"}]
        score = instagram_trust({}, posts, now=NOW)
        self.assertEqual(score.formula, "ig-v1")
        measured = {signal.key for signal in score.signals if isinstance(signal.value, float)}
        self.assertEqual(measured, {"risk_language"})


class ContractTest(unittest.TestCase):
    def test_the_source_hands_a_partial_score_per_merchant(self):
        result = _tiktok_offers([video(i) for i in range(5)], "iPhone 15 128 GB", "2026-10-25T00:00:00-04:00")
        self.assertEqual(list(result.trust), ["tt:tiendave"])
        self.assertEqual(result.trust["tt:tiendave"].stage, "parcial")

    def test_the_aggregator_closes_what_the_specialist_left_open(self):
        result = _tiktok_offers([video(i) for i in range(5)], "iPhone 15 128 GB", "2026-10-25T00:00:00-04:00")
        score = result.trust["tt:tiendave"]
        listing = {
            "url": "https://www.tiktok.com/@tiendave/video/0",
            "contractOffer": {
                "id": "oferta1",
                "merchantId": "tt:tiendave",
                "product": {"key": "iphone-15-128-gb"},
                "condition": "nuevo",
                "title": "iPhone 15 128 GB",
                "url": "https://www.tiktok.com/@tiendave/video/0",
                "seenAt": "2026-10-25T00:00:00-04:00",
                "evidenceIds": ["oferta1"],
                "trust": score.model_dump(mode="json", by_alias=True),
                "price": {"amount": 680, "currency": "USD"},
                "priceKind": "publicado",
                "priceUsd": 680,
            },
            "contractMerchant": {
                "id": "tt:tiendave",
                "name": "Tienda VE",
                "channel": "tiktok",
                "url": "https://www.tiktok.com/@tiendave",
            },
        }
        closed = close_listings([listing])[0]
        self.assertNotIn("trustError", closed)
        self.assertEqual(closed["trust"]["stage"], "final")
        # Sin cinco comparables no hay mediana: price_anomaly baja a null y no queda ningún pending.
        self.assertTrue(all(signal["value"] != "pending" for signal in closed["trust"]["signals"]))
        self.assertIn(closed["trust"]["verdict"], {"confiable", "precaucion", "riesgosa"})
        self.assertIsInstance(closed["trustStars"], int)


if __name__ == "__main__":
    unittest.main()
