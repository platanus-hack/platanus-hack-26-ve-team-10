import json
import os
import random
import re
import unicodedata
from pathlib import Path

from app.lib.types import Merchant, Money, Offer, SearchQuery, SourceResult

# Fuente de ejemplo: comercios y precios inventados, para probar el flujo completo mientras
# conectamos las fuentes reales. Sirve también de modelo para escribir una fuente nueva.
# Además de las ofertas fijas de abajo, responde por cada modelo del catálogo (catalogo.json) con
# ofertas generadas a partir de su precioEjemplo, siempre las mismas para el mismo modelo.

MERCHANTS = [
    Merchant(
        id="bodegon-la-esquina",
        name="Bodegón La Esquina (ejemplo)",
        channel="instagram",
        url="https://instagram.com/ejemplo_bodegon",
        zone="Caracas",
        delivers=True,
        followers=18500,
        comments=120,
        response_time_min=10,
    ),
    Merchant(
        id="mercado-express",
        name="Mercado Express (ejemplo)",
        channel="web",
        url="https://example.com/mercado-express",
        zone="Caracas",
        delivers=True,
        followers=4200,
        comments=35,
        response_time_min=60,
    ),
    Merchant(
        id="tienda-maracaibo",
        name="Tienda Maracaibo (ejemplo)",
        channel="mercadolibre",
        url="https://example.com/tienda-maracaibo",
        zone="Maracaibo",
        delivers=False,
        followers=900,
        comments=8,
    ),
    Merchant(
        id="ventas-tiktok",
        name="Ofertas VE (ejemplo)",
        channel="tiktok",
        url="https://tiktok.com/@ejemplo_ofertas",
        zone="Valencia",
        delivers=True,
        followers=52000,
        comments=400,
        response_time_min=240,
    ),
]

SEEN_AT = "2026-10-24T09:00:00-04:00"

OFFERS = [
    Offer("bodegon-la-esquina", "Harina PAN 1 kg", "https://instagram.com/p/ejemplo1", Money(1.35, "USD"), SEEN_AT),
    Offer("mercado-express", "Harina P.A.N. maíz blanco 1kg", "https://example.com/p/harina-pan", Money(250, "VES"), SEEN_AT),
    Offer("tienda-maracaibo", "Harina Pan 1 kilo", "https://example.com/ml/harina-pan", Money(1.1, "USD"), SEEN_AT),
    Offer("ventas-tiktok", "Harina PAN 1kg (bulto de 20)", "https://tiktok.com/@ejemplo_ofertas/video/1", None, SEEN_AT),
    Offer("bodegon-la-esquina", "Aceite Diana 1 litro", "https://instagram.com/p/ejemplo2", Money(3.2, "USD"), SEEN_AT),
    Offer("mercado-express", "Aceite Diana 1L", "https://example.com/p/aceite-diana", Money(610, "VES"), SEEN_AT),
    Offer("ventas-tiktok", "iPhone 15 128 GB", "https://tiktok.com/@ejemplo_ofertas/video/2", Money(690, "USD"), SEEN_AT),
    Offer("tienda-maracaibo", "iPhone 15 128GB nuevo", "https://example.com/ml/iphone-15", Money(720, "USD"), SEEN_AT),
]


CATALOG_MERCHANTS = [
    Merchant("tecnocentro", "TecnoCentro (ejemplo)", "web", "https://example.com/tecnocentro", "Caracas", True, 31000, 210, 20),
    Merchant("electrohogar", "Electro Hogar (ejemplo)", "web", "https://example.com/electrohogar", "Valencia", True, 12500, 90, 45),
    Merchant("celulares-ccs", "@celulares.ccs (ejemplo)", "instagram", "https://instagram.com/ejemplo_celulares", "Caracas", True, 68000, 520, 8),
    Merchant("ml-zulia", "Vendedor en Mercado Libre (ejemplo)", "mercadolibre", "https://example.com/ml-zulia", "Maracaibo", True, 2300, 40),
    Merchant("marketplace-lara", "Particular en Marketplace (ejemplo)", "facebook", "https://example.com/marketplace", "Barquisimeto", False),
    Merchant("ofertas-oriente", "Ofertas Oriente (ejemplo)", "tiktok", "https://tiktok.com/@ejemplo_oriente", "Puerto La Cruz", True, 9100, 75, 180),
    Merchant("andes-store", "Andes Store (ejemplo)", "web", "https://example.com/andes-store", "Mérida", True, 5400, 30, 60),
]

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "catalogo.json"


def _normalize(text: str) -> str:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", sin_tildes, flags=re.IGNORECASE).lower()


_CATALOG = {_normalize(p["busqueda"]): p for p in json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))["productos"]}


def _catalog_offers(product: dict) -> SourceResult:
    rnd = random.Random(product["id"])
    base = product["precioEjemplo"]
    merchants = rnd.sample(CATALOG_MERCHANTS, rnd.randint(3, len(CATALOG_MERCHANTS)))
    is_phone = product["categoria"] in ("telefonos", "tablets")
    offers = []
    for i, merchant in enumerate(merchants):
        variant = f" {rnd.choice(['128 GB', '256 GB'])}" if is_phone else ""
        if i > 0 and i == len(merchants) - 1 and merchant.channel in ("facebook", "instagram"):
            title, price = f"{product['nombre']}{variant} usado", Money(round(base * rnd.uniform(0.7, 0.82)), "USD")
        elif i == 1 and is_phone and len(merchants) >= 4:
            title, price = f"{product['nombre']}{variant} reacondicionado", Money(round(base * rnd.uniform(0.84, 0.9)), "USD")
        elif i > 0 and merchant.channel == "tiktok":
            title, price = f"{product['nombre']}{variant}", None  # "precio al DM"
        else:
            usd = base if i == 0 else round(base * rnd.uniform(1.02, 1.18))
            # Algunos comercios publican en bolívares, a la tasa de ejemplo (200): search_offers los convierte.
            price = Money(usd * 200, "VES") if merchant.id == "electrohogar" else Money(usd, "USD")
            title = f"{product['nombre']}{variant} nuevo"
        offers.append(Offer(merchant.id, title, f"{merchant.url}/p/{product['slug']}", price, SEEN_AT))
    return SourceResult(offers=offers, merchants=merchants)


class MockSource:
    id = "ejemplo"
    enabled = os.environ.get("USE_MOCK_SOURCE") != "false"

    async def search(self, query: SearchQuery) -> SourceResult:
        product = _CATALOG.get(_normalize(query.text))
        if product:
            return _catalog_offers(product)
        words = [word for word in re.split(r"\s+", _normalize(query.text)) if len(word) >= 3]
        found = [
            offer
            for offer in OFFERS
            if all(word in _normalize(offer.title).replace(" ", "") for word in words)
        ]
        merchants = [m for m in MERCHANTS if any(o.merchant_id == m.id for o in found)]
        return SourceResult(offers=found, merchants=merchants)


mock_source = MockSource()
