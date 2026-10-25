"""Amazon más courier, sin red: el actor y las páginas se reemplazan."""

import os
import unittest
from unittest import mock

from app.agents.listing import card_text, choose_options
from app.lib.contracts import CanonicalProduct, Merchant, Money, Offer, TrustSignal
from app.lib.importacion.cotizar import quote_import
from app.lib.importacion.couriers.liberty import CALCULATOR_URL
from app.lib.importacion.couriers.zoom import ZOOM_URL
from app.lib.importacion.factibilidad import blocked, worth_quoting
from app.lib.importacion.peso import billable
from app.lib.sources import amazon
from app.lib.sources.amazon import amazon_input
from app.lib.trust import ASIN_RED_FLAG, close_listings, compute_trust

PRODUCT = "iphone 15 128"
ZOOM_HTML = """
<html><body>
Tarifa Básica Casillero Aéreo: Mercancía: Cada ½ Kg $6 (no hay mínimo, puedes enviar desde cualquier peso).
Servicio de Protección de Encomienda: Aéreo: Pagaras $1 adicional si el paquete es de bajo valor
(Monto factura menos de $100), si es de alto valor (Monto factura más de $100) pagaras solo el 1% del valor de tu compra.
</body></html>
"""
LIBERTY_HTML = """
<script>let localhost = 'https://api.iqpackoffice.com/';</script>
<script src="/js/calculadora/datos.js?ver=test"></script>
<script>
let los_paises = [
  {"id": 10002, "pais": "Estados Unidos", "isO2": "US", "unidadPeso": "LBS", "iata_origen_por_defecto": "US.MIA"},
  {"id": 1, "pais": "Venezuela", "isO2": "VE", "unidadPeso": "KG", "iata_origen_por_defecto": "VE.CCS"}
];
let los_fletes = [
  {"pais_origen_ISO2": "US", "pais_destino_ISO2": "VE", "termino": "PPD", "transporte": "aereo",
   "codigo_flete": "US-PPD-0008", "contenido": "paquete", "especiales": "ninguno", "unidad": "", "condicion": "", "valor": 0},
  {"pais_origen_ISO2": "US", "pais_destino_ISO2": "VE", "termino": "COL", "transporte": "aereo",
   "codigo_flete": "VE-COL-0218", "contenido": "paquete", "especiales": "ninguno", "unidad": "", "condicion": "", "valor": 0}
];
</script>
"""
LIBERTY_JS = "let data = { token: '0123456789abcdef' };"
LIBERTY_QUOTE = {
    "valorCotizado": {"bruto": 35.23, "impuesto": 0.88, "neto": 36.11},
    "resultados": [
        {
            "valorCotizado": {"bruto": 35.23, "impuesto": 0.88, "neto": 36.11},
            "productosCotizado": [
                {"nombre": "COL FLETE PAQ", "cotizado": {"bruto": 5.78}},
                {"nombre": "COL SEGURO", "cotizado": {"bruto": 29.45}},
            ],
        }
    ],
}


def amazon_item(price=589, asin="B0PHONE", title="Apple iPhone 15 128GB", seller="Amazon.com", weight="0.8 pounds"):
    item = {
        "title": title,
        "asin": asin,
        "url": f"https://www.amazon.com/dp/{asin}",
        "brand": "Apple",
        "price": {"value": price, "currency": "$"},
        "thumbnailImage": "https://m.media-amazon.com/images/I/phone.jpg",
        "seller": {"name": seller, "id": "ATVPDKIKX0DER", "url": "/gp/help/seller/at-a-glance.html?seller=ATVPDKIKX0DER"},
        "attributes": [{"key": "Item Weight", "value": weight}],
    }
    return item


class FakeRunner:
    def __init__(self, items):
        self.items = items
        self.inputs = []

    async def __call__(self, actor, run_input):
        self.inputs.append((actor, run_input))
        if isinstance(self.items, Exception):
            raise self.items
        return self.items


class FakePages:
    def __init__(self):
        self.posts = []

    async def get_text(self, url):
        if url == ZOOM_URL:
            return ZOOM_HTML
        if url == CALCULATOR_URL:
            return LIBERTY_HTML
        if url.endswith("datos.js?ver=test"):
            return LIBERTY_JS
        raise AssertionError(url)

    async def post_json(self, url, body):
        self.posts.append((url, body))
        return LIBERTY_QUOTE


class ImportacionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        amazon._cache.clear()
        amazon._runs.clear()

    def test_the_actor_input_does_not_bypass_amazon(self):
        run_input = amazon_input(PRODUCT)
        self.assertFalse(run_input["useCaptchaSolver"])
        self.assertTrue(run_input["scrapeProductDetails"])
        self.assertTrue(run_input["scrapeSellers"])
        self.assertEqual(run_input["maxOffers"], 0)
        self.assertIn("https://www.amazon.com/s?k=", run_input["categoryOrProductUrls"][0]["url"])

    def test_medicines_groceries_and_loose_batteries_are_not_quoted(self):
        for text in ("ibuprofeno 400", "harina pan 1 kg", "bateria de litio", "pollo fresco"):
            self.assertIsNotNone(blocked(text), text)
        self.assertIsNone(blocked(PRODUCT))

    async def test_a_blocked_product_never_calls_amazon(self):
        async def fail(actor, run_input):
            raise AssertionError("Amazon no debía correr")

        found = await quote_import("ibuprofeno 400", runner=fail)
        self.assertEqual(found["listings"], [])
        self.assertIn("medicamento", found["notice"])

    async def test_without_a_token_amazon_stays_off(self):
        with mock.patch.dict(os.environ, {"APIFY_TOKEN": ""}):
            found = await quote_import(PRODUCT)
        self.assertEqual(found["listings"], [])
        self.assertIn("no está conectado", found["notice"])

    async def test_a_different_product_is_dropped_and_zoom_wins(self):
        runner = FakeRunner(
            [
                amazon_item(),
                amazon_item(price=400, asin="B0OTHER", title="Samsung Galaxy S24 128GB"),
                amazon_item(price=700, asin="B0PRO", title="Apple iPhone 15 Pro 128GB"),
            ]
        )
        pages = FakePages()
        found = await quote_import(PRODUCT, runner=runner, client=pages)
        self.assertEqual(runner.inputs[0][0], "junglee/Amazon-crawler")
        self.assertEqual(len(found["listings"]), 1)
        card = found["listings"][0]
        self.assertEqual(card["channel"], "importacion")
        self.assertEqual(card["price_kind"], "estimado")
        self.assertEqual(card["seller"], "Zoom")
        self.assertEqual(card["fulfiller"], "Zoom")
        self.assertEqual(card["price_usd"], 600.89)
        self.assertEqual(card["landed"]["product_usd"], 589)
        self.assertEqual(card["landed"]["total_usd"], 600.89)
        self.assertEqual(card["landed"]["weight_source"], "listing")
        self.assertEqual(card["landed"]["tax_source"], "tabla")
        self.assertEqual(card["landed"]["asin"], "B0PHONE")
        self.assertIsNone(card["landed"]["asin_median_usd"])
        self.assertEqual({quote["courier_id"] for quote in card["landed"]["quotes"]}, {"cur:zoom", "cur:liberty"})
        self.assertEqual(pages.posts[0][1]["porCotizar"][0]["codigo"], "VE-COL-0218")
        self.assertEqual(pages.posts[0][1]["token"], "0123456789abcdef")
        text = card_text(card)
        self.assertLessEqual(len(text), 160)
        self.assertIn("estimado", text)
        self.assertIn("Traerlo de USA", text)
        closed = close_listings([card])[0]
        self.assertEqual(closed["trust"]["score"], 86)
        self.assertNotIn(ASIN_RED_FLAG, closed["trust"]["redFlags"])

    async def test_a_cheap_import_is_not_judged_against_venezuela(self):
        runner = FakeRunner([amazon_item(price=580), amazon_item(price=600, asin="B0PHONE")])
        found = await quote_import(PRODUCT, runner=runner, client=FakePages())
        card = found["listings"][0]
        self.assertEqual(card["landed"]["product_usd"], 580)
        self.assertEqual(card["landed"]["asin_median_usd"], 590)
        # Cinco precios locales. Si el total importado entrara en la mediana,
        # el de 2000 dejaría de tener desviación 0.
        locals_ = [_local(index, price) for index, price in enumerate((100, 100, 2000, 2000, 2000))]
        closed = close_listings([card, *locals_])
        imported = closed[0]["trust"]
        self.assertNotIn(ASIN_RED_FLAG, imported["redFlags"])
        self.assertGreater(imported["score"], 0)
        dear = next(item for item in closed[1:] if item["contractOffer"]["priceUsd"] == 2000)
        self.assertEqual(dear["contractOffer"]["judge"]["priceDeviation"], 0)

    async def test_half_the_asin_median_is_a_red_flag(self):
        runner = FakeRunner([amazon_item(price=100), amazon_item(price=400, asin="B0PHONE")])
        found = await quote_import(PRODUCT, runner=runner, client=FakePages())
        closed = close_listings(found["listings"])[0]
        self.assertEqual(closed["landed"]["product_usd"], 100)
        self.assertIn(ASIN_RED_FLAG, closed["trust"]["redFlags"])
        self.assertEqual(closed["trust"]["score"], 0)
        shown = card_text(closed)
        self.assertIn("Confianza 0", shown)

    def test_category_weight_is_labeled_and_volume_wins(self):
        table = billable("iphone 15 128", ())
        self.assertEqual((table.lb, table.source), (0.8, "tabla"))
        bulky = billable(
            "caja",
            (
                ("Item Weight", "1 pounds"),
                ("Product Dimensions", "10 x 10 x 10 inches"),
            ),
        )
        self.assertEqual(bulky.source, "listing")
        self.assertGreater(bulky.lb, 1)

    def test_worth_quoting_skips_when_it_cannot_beat_the_local_price(self):
        self.assertFalse(worth_quoting(700, 500))
        self.assertTrue(worth_quoting(700, None))

    async def test_the_import_option_competes_on_price(self):
        found = await quote_import(PRODUCT, runner=FakeRunner([amazon_item()]), client=FakePages())
        local = {
            "title": "iPhone 15",
            "seller": "Soytechno",
            "channel": "web",
            "url": "https://soytechno.com/iphone",
            "price": "USD 720,00",
            "price_usd": 720,
            "image_url": "https://soytechno.com/foto.jpg",
        }
        chosen = choose_options([local, found["listings"][0]])
        self.assertEqual([item["seller"] for item in chosen], ["Zoom", "Soytechno"])


def _local(index: int, price: float) -> dict:
    trust = compute_trust(
        "custom-v1",
        [
            TrustSignal(family="reputacion", key="known", weight=50, value=1),
            TrustSignal(family="precio", key="price_anomaly", weight=50, value="pending"),
        ],
        stage="parcial",
    )
    offer = Offer(
        id=f"local-{index}",
        merchant_id=f"web:{index}",
        product=CanonicalProduct(key="iphone 15 128"),
        condition="nuevo",
        title="iPhone 15 128GB",
        url=f"https://tienda.example/{index}",
        seen_at=trust.computed_at,
        evidence_ids=["price"],
        trust=trust,
        price=Money(amount=price, currency="USD"),
        price_kind="publicado",
        price_usd=price,
    )
    merchant = Merchant(id=f"web:{index}", name="Tienda", channel="web", url=f"https://tienda.example/{index}")
    return {
        "title": offer.title,
        "seller": "Tienda",
        "channel": "web",
        "url": offer.url,
        "price": f"USD {price:g}",
        "price_usd": price,
        "contractOffer": offer.model_dump(mode="json"),
        "contractMerchant": merchant.model_dump(mode="json"),
    }
