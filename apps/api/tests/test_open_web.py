"""La web abierta con un cliente falso de Firecrawl: sin red ni créditos.

Correr desde apps/api: .venv/bin/python -m unittest discover -s tests
"""

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from app.lib import search
from app.lib.sources import firecrawl
from app.lib.sources.mock import mock_source
from app.lib.types import ExchangeRate, SearchQuery

RATE = ExchangeRate(source="tasa de prueba", usd_to_ves=200, observed_at="2026-10-24T08:00:00-04:00")


def _metadata(url, final=None, status=200, credits=1):
    return SimpleNamespace(url=final or url, status_code=status, og_site_name=None, og_image=None, credits_used=credits)


def product_page(url, amount, currency="USD", title="iPhone 15 128 GB", product_url=None):
    price = SimpleNamespace(amount=amount, currency=currency)
    product = SimpleNamespace(
        title=title, brand="Apple", url=product_url or url, variants=[SimpleNamespace(price=price, images=[])]
    )
    return {"product": SimpleNamespace(product=product, metadata=_metadata(url), images=None)}


def listing_page(url, offers, markdown):
    return {
        "product": SimpleNamespace(product=None, metadata=_metadata(url), images=None),
        "json": SimpleNamespace(
            json={"offers": offers}, markdown=markdown, metadata=_metadata(url, credits=5), images=None
        ),
    }


def blocked_page(url):
    final = "https://www.mercadolibre.com.ve/gz/account-verification?go=x"
    return {"product": SimpleNamespace(product=None, metadata=_metadata(url, final), images=None)}


def dead_page(url):
    return {"product": SimpleNamespace(product=None, metadata=_metadata(url, status=404), images=None)}


class FakeFirecrawl:
    """Responde con las páginas que le den. Una página puede ser una excepción o tardar.

    Rechaza cualquier pedido con otra forma que la que acepta la API de verdad:
    con el SDK 4.54.0, el formato JSON como objeto JsonFormat responde 400.
    """

    def __init__(self, pages, slow=()):
        self.pages = pages
        self.slow = set(slow)
        self.scraped = []

    async def search(self, query, **_):
        return SimpleNamespace(web=[SimpleNamespace(url=url, title=f"Título de {url}") for url in self.pages])

    async def scrape(self, url, *, formats, only_main_content, timeout):
        assert only_main_content is True and timeout > 0
        if formats == ["product"]:
            kind = "product"
        else:
            listing, markdown = formats
            assert markdown == "markdown"
            assert isinstance(listing, dict) and listing["type"] == "json", listing
            assert listing["schema"] is firecrawl.ListedOffers and isinstance(listing["prompt"], str)
            kind = "json"
        self.scraped.append((url, kind))
        if url in self.slow:
            await asyncio.sleep(5)
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return page[kind]


class OpenWebTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        firecrawl._cache.clear()
        for patcher in (
            mock.patch.dict(os.environ, {"FIRECRAWL_API_KEY": "fake"}),
            mock.patch.object(firecrawl, "get_rate", mock.AsyncMock(return_value=RATE)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def run_search(self, client, budget_s=firecrawl.BUDGET_S, product="Chevrolet Aveo usado"):
        with mock.patch.object(firecrawl, "AsyncFirecrawl", lambda api_key: client):
            return await firecrawl.search_open_web(product, budget_s)

    async def test_listing_offers_with_u_s_prices(self):
        url = "https://www.autocosmos.com.ve/auto/usado/chevrolet/aveo"
        client = FakeFirecrawl(
            {
                url: listing_page(
                    url,
                    [
                        {"title": "Chevrolet Aveo", "variant": "2007", "price": 6600, "currency": "u$s",
                         "city": "Libertador", "url": "/auto/usado/chevrolet/aveo/16l-aut/db4f"},
                        {"title": "Chevrolet Aveo", "variant": "2008", "price": 6000, "currency": "U$S",
                         "url": "https://www.autocosmos.com.ve/auto/usado/chevrolet/aveo/x/175596"},
                        {"title": "Chevrolet Aveo", "price": None, "currency": "Consultar precio"},
                    ],
                    "Chevrolet Aveo 2007 u$s6.600 Libertador. Chevrolet Aveo 2008 u$s6.000 San Diego.",
                )
            }
        )
        result = await self.run_search(client)
        offers = result["offers"]
        self.assertEqual([offer["priceUsd"] for offer in offers], [6000, 6600])
        self.assertEqual(offers[1]["title"], "Chevrolet Aveo 2007")
        self.assertEqual(offers[1]["url"], "https://www.autocosmos.com.ve/auto/usado/chevrolet/aveo/16l-aut/db4f")
        self.assertEqual(offers[1]["merchant"]["zone"], "Libertador")
        self.assertEqual(offers[0]["merchant"]["zone"], "Venezuela")
        self.assertEqual(result["failedSources"], [])

    async def test_product_page_skips_the_listing_extraction(self):
        url = "https://soytechno.com/apple-iphone-15/"
        client = FakeFirecrawl({url: product_page(url, 789.0)})
        result = await self.run_search(client, product="iPhone 15 128 GB")
        self.assertEqual(result["offers"][0]["priceUsd"], 789)
        self.assertEqual(client.scraped, [(url, "product")])

    async def test_related_product_falls_through_to_the_listing(self):
        url = "https://www.farmadon.com.ve/producto/mary-arroz-superior-tipo-i-900gr/"
        page = product_page(url, 1.56, title="Konfit Azúcar Blanco 1Kg", product_url=url.replace("mary-arroz", "konfit"))
        page["json"] = listing_page(
            url, [{"title": "Mary Arroz Superior Tipo I 900gr", "price": 0.81, "currency": "Bs."}], "REF 0,81"
        )["json"]
        client = FakeFirecrawl({url: page})
        result = await self.run_search(client, product="Arroz Mary 900 g")
        self.assertEqual(client.scraped, [(url, "product"), (url, "json")])
        offer = result["offers"][0]
        # El modelo dijo Bs., pero la página escribe REF: manda la página.
        self.assertEqual((offer["title"], offer["priceUsd"], offer["rate"]), ("Mary Arroz Superior Tipo I 900gr", 0.81, None))

    async def test_price_missing_from_the_page_is_dropped(self):
        url = "https://autos.example.com.ve/aveo"
        client = FakeFirecrawl(
            {url: listing_page(url, [{"title": "Chevrolet Aveo", "price": 4500, "currency": "USD"}], "Aveo $ 5.200")}
        )
        result = await self.run_search(client)
        self.assertEqual(result["offers"], [])
        self.assertEqual(result["failedSources"], [])

    async def test_other_brands_and_models_on_a_listing_are_dropped(self):
        url = "https://vallearriba.elplazas.com/harina-de-maiz.html"
        client = FakeFirecrawl(
            {
                url: listing_page(
                    url,
                    [
                        {"title": "HARINA P.A.N. MAIZ BLANCO 1 KG", "price": 1.12, "currency": "$"},
                        {"title": "HARINA KALY BLANCO 1KG", "price": 0.89, "currency": "$"},
                        {"title": "HARINA JUANA CLASICA 1KG", "price": 1.05, "currency": "$"},
                    ],
                    "$1,12 $0,89 $1,05",
                )
            }
        )
        result = await self.run_search(client, product="Harina PAN 1 kg")
        self.assertEqual([offer["title"] for offer in result["offers"]], ["HARINA P.A.N. MAIZ BLANCO 1 KG"])

    async def test_blocked_and_failing_pages_go_to_failed_sources(self):
        good = "https://www.autocosmos.com.ve/aveo"
        blocked = "https://autos.example.com.ve/aveo"
        broken = "https://broken.example.com/aveo"
        slow = "https://slow.example.com/aveo"
        client = FakeFirecrawl(
            {
                good: listing_page(good, [{"title": "Chevrolet Aveo", "price": 7000, "currency": "u$s"}], "u$s7.000"),
                blocked: blocked_page(blocked),
                broken: RuntimeError("boom"),
                slow: product_page(slow, 6500.0),
            },
            slow=[slow],
        )
        result = await self.run_search(client, budget_s=2)
        self.assertEqual([offer["priceUsd"] for offer in result["offers"]], [7000])
        self.assertEqual(
            result["failedSources"],
            ["firecrawl:autos.example.com.ve", "firecrawl:broken.example.com", "firecrawl:slow.example.com"],
        )
        # Una página bloqueada no paga la extracción de ofertas.
        self.assertNotIn((blocked, "json"), client.scraped)

    async def test_result_cut_by_the_deadline_is_not_cached(self):
        good = "https://www.autocosmos.com.ve/aveo"
        slow = "https://slow.example.com/aveo"
        client = FakeFirecrawl(
            {
                good: listing_page(good, [{"title": "Chevrolet Aveo", "price": 7000, "currency": "u$s"}], "u$s7.000"),
                slow: product_page(slow, 6500.0),
            },
            slow=[slow],
        )
        await self.run_search(client, budget_s=2)
        self.assertNotIn("chevrolet aveo usado", firecrawl._cache)

    async def test_dead_link_is_not_a_failed_shop(self):
        url = "https://www.apple.com/ve/iphone-15/"
        client = FakeFirecrawl({url: dead_page(url)})
        result = await self.run_search(client, product="iPhone 15 128 GB")
        self.assertEqual(result["failedSources"], [])
        self.assertEqual(client.scraped, [(url, "product")])

    async def test_shop_with_offers_is_not_reported_as_failed(self):
        good = "https://soytechno.com/apple-iphone-15/"
        broken = "https://soytechno.com/apple-iphone-15-pro/"
        client = FakeFirecrawl({good: product_page(good, 789.0), broken: RuntimeError("boom")})
        result = await self.run_search(client, product="iPhone 15 128 GB")
        self.assertEqual(len(result["offers"]), 1)
        self.assertEqual(result["failedSources"], [])

    async def test_other_shops_get_a_slot_before_a_listing_backfills(self):
        portal = "https://www.autocosmos.com.ve/aveo"
        shop = "https://usaditoscars.com/"
        cars = [{"title": "Chevrolet Aveo", "variant": str(2000 + n), "price": 5000 + n * 100, "currency": "u$s",
                 "url": f"{portal}/{n}"} for n in range(6)]
        client = FakeFirecrawl(
            {
                portal: listing_page(portal, cars, " ".join(f"u$s{5000 + n * 100}" for n in range(6))),
                shop: listing_page(shop, [{"title": "Chevrolet Aveo 2009", "price": 7900, "currency": "$"}], "$7.900"),
            }
        )
        result = await self.run_search(client)
        self.assertEqual([offer["priceUsd"] for offer in result["offers"]], [5000, 5100, 5200, 5300, 7900])

        firecrawl._cache.clear()
        alone = await self.run_search(FakeFirecrawl({portal: listing_page(portal, cars, "u$s5.000 u$s5.100 u$s5.200 u$s5.300 u$s5.400")}))
        self.assertEqual(len(alone["offers"]), 5)

    async def test_shop_whose_offers_were_all_cut_is_reported(self):
        shops = [f"https://s{n}.example.com/aveo" for n in range(5)]
        pages = {
            url: listing_page(url, [{"title": "Chevrolet Aveo", "price": 5000 + n, "currency": "$"}], f"${5000 + n}")
            for n, url in enumerate(shops)
        }
        expensive, broken = "https://big.example.com/a", "https://big.example.com/b"
        pages[expensive] = listing_page(expensive, [{"title": "Chevrolet Aveo", "price": 9999, "currency": "$"}], "$9999")
        pages[broken] = RuntimeError("boom")
        result = await self.run_search(FakeFirecrawl(pages))
        self.assertNotIn(9999, [offer["priceUsd"] for offer in result["offers"]])
        self.assertEqual(result["failedSources"], ["firecrawl:big.example.com"])

    async def test_tucarro_trovit_and_ebay_are_not_scraped(self):
        tucarro = "https://carros.tucarro.com.ve/chevrolet/aveo"
        trovit = "https://carros.trovit.co.ve/carros-usados/chevrolet-aveo"
        ebay = "https://ve.ebay.com/b/Apple-iPhone-15/9355/bn_7121790163"
        client = FakeFirecrawl({url: blocked_page(url) for url in (tucarro, trovit, ebay)})
        result = await self.run_search(client)
        self.assertEqual(client.scraped, [])
        self.assertEqual(result["failedSources"], [])

    async def test_bolivares_are_converted_with_the_rate(self):
        url = "https://www.locatel.com.ve/harina-pan"
        client = FakeFirecrawl(
            {url: listing_page(url, [{"title": "Harina PAN 1kg", "price": 1039.96, "currency": "Bs."}], "Bs. 1.039,96")}
        )
        result = await self.run_search(client, product="Harina PAN 1 kg")
        offer = result["offers"][0]
        self.assertEqual(offer["price"], "Bs.S\xa01.039,96")
        self.assertEqual(offer["priceUsd"], 5.2)
        self.assertEqual(offer["rate"], "200 Bs/USD (tasa de prueba, 2026-10-24T08:00:00-04:00)")


class ParsingTest(unittest.TestCase):
    def test_published_prices_keep_the_currency_next_to_them(self):
        prices = firecrawl._published_prices("u$s6.600 · Bs.S 1.039,96 · $1,039.96 · REF 0,81 · 84,20 · 6.600.000 Bs")
        self.assertEqual(prices[6600], {"USD"})
        self.assertEqual(prices[1039.96], {"VES", "USD"})
        self.assertEqual(prices[0.81], {"USD"})
        self.assertEqual(prices[84.2], {None})
        self.assertEqual(prices[6600000], {"VES"})
        self.assertNotIn(6.6, prices)

    def test_a_symbol_belongs_to_the_amount_after_it(self):
        # Un título que termina en cifra, o dos precios seguidos, no se quedan con el símbolo ajeno.
        self.assertEqual(firecrawl._published_prices("### Samsung Galaxy A15\n\nRef. 150")[150], {"USD"})
        self.assertEqual(firecrawl._published_prices("Bs. 5.200,00 REF 26,00"), {5200: {"VES"}, 26: {"USD"}})
        self.assertEqual(firecrawl._published_prices("Bs. 9.125,00\n$25,00")[25], {"USD"})
        self.assertEqual(firecrawl._published_prices("179,00$-209,00$"), {179: {"USD"}, 209: {"USD"}})

    def test_currencies(self):
        labels = ("u$s", "U$S", "US$", "$", "REF", "Ref.", "USD$", "Bs.", "Bs.S", "Bs.:", "Bs.D", "EUR", "Consultar")
        self.assertEqual(
            [firecrawl._currency(label) for label in labels],
            ["USD", "USD", "USD", "USD", "USD", "USD", "USD", "VES", "VES", "VES", "VES", None, None],
        )

    def test_matches(self):
        cases = [
            ("Harina PAN 1 kg", "HARINA P.A.N. MAIZ BLANCO 1 KG", True),
            ("Harina PAN 1 kg", "HARINA KALY BLANCO 1KG", False),
            ("Xiaomi Redmi 15C", "Redmi 15C 256GB", True),
            ("Xiaomi Redmi 15C", "Xiaomi Redmi 13C 4GB 256GB", False),
            ("Moto Bera BR 200", "Bera BR200 2025", True),
            ("Caucho 175/70 R13", "Neumático Firestone 175/70R13", True),
            ("Smart TV 32 pulgadas", 'Televisor Samsung Smart 32"', True),
            ("Smart TV 32 pulgadas", "Televisor LED Damasco 32 Pulgadas", False),
            ("Chevrolet Aveo usado", "Chevrolet Aveo 1.6 2008", True),
            ("carro usado económico", "Toyota Meru 2009", True),
            ("zapatos nike air force", "Zapato Nike Air Force 1 '07", True),
            ("nevera samsung", "Refrigerador Samsung RT38", True),
            ("laptop hp 15", "Notebook HP 15-fd0010la", True),
            ("harina pan 1kg", "Harina P.A.N. Maíz Blanco 1 Kilo", True),
            ("Arroz Mary 1 kg", "Arroz Mary Tradicional 900g", False),
        ]
        for product, title, expected in cases:
            with self.subTest(product=product, title=title):
                self.assertEqual(firecrawl._matches(product, title), expected)


class SearchNoticeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        patcher = mock.patch.object(mock_source, "enabled", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_example_notice_only_with_example_offers(self):
        with_examples = await search.search_offers(SearchQuery(text="Harina PAN 1 kg"))
        without = await search.search_offers(SearchQuery(text="Chevrolet Aveo usado"))
        self.assertTrue(any(offer["example"] for offer in with_examples["offers"]))
        self.assertIn("notice", with_examples)
        self.assertEqual(without["offers"], [])
        self.assertNotIn("notice", without)

    async def test_search_all_lists_failed_pages(self):
        async def open_web(product, budget_s):
            return {"offers": [], "failedSources": ["firecrawl:autos.example.com.ve"]}

        with mock.patch.object(search, "search_open_web", open_web):
            result = await search.search_all(SearchQuery(text="Chevrolet Aveo usado"), 25)
        self.assertEqual(result["failedSources"], ["firecrawl:autos.example.com.ve"])


if __name__ == "__main__":
    unittest.main()
