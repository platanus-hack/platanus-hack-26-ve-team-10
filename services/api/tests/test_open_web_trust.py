"""La llamada de confianza de la web abierta. Sin red.

Correr desde services/api: .venv/bin/python -m unittest discover -s tests
"""

import unittest

from app.agents.open_web_trust import review_listings, review_one


def _card(title: str, url: str, price: float | None) -> dict:
    return {"title": title, "url": url, "price_usd": price}


class OpenWebTrustTests(unittest.TestCase):
    def test_a_price_far_below_the_others_is_not_recommended(self):
        review = review_one("iPhone 15", _card("iPhone 15", "https://tienda.com/p", 100), [400, 420])
        self.assertEqual(review["verdict"], "riesgosa")
        self.assertIn("50%", review["reasons"][0])

    def test_a_case_is_not_the_phone(self):
        review = review_one(
            "iPhone 15",
            _card("Funda de silicona para iPhone 15", "https://tienda.com/funda", 15),
            [],
        )
        self.assertEqual(review["verdict"], "riesgosa")
        self.assertIn("funda", review["reasons"][0])

    def test_a_brand_in_the_domain_is_impersonation(self):
        review = review_one(
            "iPhone 15",
            _card("iPhone 15 128 GB", "https://iphone-oferta-ve.com/p", 700),
            [720],
        )
        self.assertEqual(review["verdict"], "riesgosa")
        self.assertIn("Apple", review["reasons"][0])

    def test_the_real_brand_domain_is_not_impersonation(self):
        review = review_one(
            "iPhone 15",
            _card("iPhone 15", "https://www.apple.com/ve/iphone-15/", 800),
            [790],
        )
        self.assertEqual(review["verdict"], "sin_datos")

    def test_http_is_a_caution_and_an_unmeasured_shop_is_not_called_safe(self):
        caution = review_one("Harina PAN 1 kg", _card("Harina PAN 1 kg", "http://tienda.com/pan", 2), [2.1])
        self.assertEqual(caution["verdict"], "precaucion")
        unknown = review_one("Harina PAN 1 kg", _card("Harina PAN 1 kg", "https://tienda.com/pan", 2), [2.1])
        self.assertEqual(unknown["verdict"], "sin_datos")
        self.assertNotEqual(unknown["verdict"], "confiable")

    def test_reviews_are_written_on_the_listings(self):
        listings = [
            _card("iPhone 15", "https://a.com/p", 100),
            _card("iPhone 15", "https://b.com/p", 400),
        ]
        review_listings("iPhone 15", listings)
        self.assertEqual(listings[0]["trust_review"]["verdict"], "riesgosa")
        self.assertEqual(listings[1]["trust_review"]["verdict"], "sin_datos")
