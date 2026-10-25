"""Facebook Marketplace con avisos falsos, copiados de la forma de una corrida real."""

import unittest
from datetime import UTC, datetime, timedelta

from app.lib.sources import facebook

PRODUCT = "iPhone 15"
NOW = "2026-10-25T00:00:00-04:00"
OLD_SELLER = "2010-10-18T17:39:43.000Z"


def listing(**extra):
    seller = {
        "id": "100001",
        "name": "Betty Rumbos",
        "url": "https://www.facebook.com/marketplace/profile/100001/",
        "joined_at": OLD_SELLER,
        "rating_avg": None,
        "rating_count": 0,
    }
    seller.update(extra.pop("seller", {}))
    base = {
        "marketplace_listing_title": "iPhone 15",
        "redacted_description": {"text": "iPhone 15 todo original 128gb, nunca destapado."},
        "listingUrl": "https://www.facebook.com/marketplace/item/1234567890/",
        # Facebook etiqueta los avisos venezolanos con una moneda que no existe desde 2018.
        "listing_price": {"amount": "440.00", "currency": "VEF"},
        "location_text": {"text": "Caracas, DF"},
        "listing_photos": [1, 2, 3, 4, 5],
        "creation_time": "2026-10-20T10:00:00Z",
        "marketplace_listing_seller": seller,
        "commerce_badges_info": {"badges": []},
    }
    return {**base, **extra}


def read(items, product=PRODUCT):
    return facebook.read(items, product, NOW)


def trust_of(item):
    return next(iter(read([item]).trust.values()))


class InputTest(unittest.TestCase):
    def test_it_searches_the_three_big_cities(self):
        found = facebook.entries(PRODUCT)
        self.assertEqual(len(found), len(facebook.CITIES))
        actors = {actor for actor, _ in found}
        self.assertEqual(actors, {facebook.ACTOR})
        self.assertEqual(found[0][1]["searchKeyword"], PRODUCT)
        self.assertIn("Caracas", found[0][1]["location"])


class PriceTest(unittest.TestCase):
    def test_a_vef_label_is_read_as_dollars(self):
        # Nadie pone precios en una moneda muerta: el aviso está en dólares.
        price = facebook._price(listing())
        self.assertEqual((price.amount, price.currency), (440, "USD"))

    def test_what_the_seller_writes_wins_over_the_label(self):
        item = listing(
            listing_price={"amount": "5000.00", "currency": "VEF"},
            redacted_description={"text": "iPhone 15 en Bs. 5.000,00"},
        )
        price = facebook._price(item)
        self.assertEqual((price.amount, price.currency), (5000, "VES"))

    def test_a_listing_without_a_price_is_left_out(self):
        self.assertIsNone(facebook._price(listing(listing_price={"amount": "0.00", "currency": "VEF"})))
        self.assertIsNone(facebook._price(listing(listing_price={})))

    def test_an_unknown_currency_is_not_guessed(self):
        self.assertIsNone(facebook._price(listing(listing_price={"amount": "440.00", "currency": "COP"})))


class ReadTest(unittest.TestCase):
    def test_a_listing_becomes_an_offer(self):
        result = read([listing()])
        offer, merchant = result.offers[0], result.merchants[0]
        self.assertEqual(offer.price.amount, 440)
        self.assertEqual((merchant.id, merchant.channel, merchant.zone), ("fb:100001", "facebook", "Caracas, DF"))

    def test_another_product_is_left_out(self):
        self.assertEqual(read([listing(marketplace_listing_title="Funda para iPhone 15")], "iPhone 15 128 GB").offers, [])

    def test_the_same_link_is_one_offer(self):
        self.assertEqual(len(read([listing(), listing()]).offers), 1)


class TrustTest(unittest.TestCase):
    def test_an_old_profile_measures_its_age(self):
        trust = trust_of(listing())
        age = next(signal for signal in trust.signals if signal.key == "fb_age")
        self.assertGreater(age.value, 0.6)
        self.assertIn("2010", age.reason)
        self.assertEqual(trust.formula, "fb-v1")
        self.assertEqual(trust.stage, "parcial")

    def test_a_profile_from_last_week_is_a_red_flag(self):
        recent = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        self.assertIn(facebook.NEW_PROFILE_FLAG, trust_of(listing(seller={"joined_at": recent})).red_flags)

    def test_a_bad_rating_with_enough_votes_is_a_red_flag(self):
        trust = trust_of(listing(seller={"rating_avg": 2.1, "rating_count": 12}))
        self.assertIn(facebook.LOW_RATING_FLAG, trust.red_flags)

    def test_a_few_bad_votes_are_not_enough_to_flag(self):
        # En Marketplace casi nadie califica: dos votos no condenan a un vendedor.
        trust = trust_of(listing(seller={"rating_avg": 2.1, "rating_count": 2}))
        self.assertEqual(trust.red_flags, [])

    def test_a_listing_with_few_photos_measures_worse(self):
        poor = trust_of(listing(listing_photos=[1], redacted_description={"text": "iPhone 15"}))
        rich = trust_of(listing())
        value = next(signal.value for signal in poor.signals if signal.key == "completeness")
        self.assertLess(value, next(signal.value for signal in rich.signals if signal.key == "completeness"))

    def test_the_photo_and_price_signals_wait_for_the_aggregator(self):
        pending = {signal.key for signal in trust_of(listing()).signals if signal.value == "pending"}
        self.assertEqual(pending, {"price_anomaly", "photos_original"})

    def test_the_history_needs_another_run_so_it_stays_null(self):
        history = next(signal for signal in trust_of(listing()).signals if signal.key == "history")
        self.assertIsNone(history.value)


if __name__ == "__main__":
    unittest.main()
