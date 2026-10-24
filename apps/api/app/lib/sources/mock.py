import os
import re
import unicodedata

from app.lib.types import Merchant, Money, Offer, SearchQuery, SourceResult

# Fuente de ejemplo: comercios y precios inventados, para probar el flujo completo mientras
# conectamos las fuentes reales. Sirve también de modelo para escribir una fuente nueva.

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


def _normalize(text: str) -> str:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", sin_tildes, flags=re.IGNORECASE).lower()


class MockSource:
    id = "ejemplo"
    enabled = os.environ.get("USE_MOCK_SOURCE") != "false"

    async def search(self, query: SearchQuery) -> SourceResult:
        words = [word for word in re.split(r"\s+", _normalize(query.text)) if len(word) >= 3]
        found = [
            offer
            for offer in OFFERS
            if all(word in _normalize(offer.title).replace(" ", "") for word in words)
        ]
        merchants = [m for m in MERCHANTS if any(o.merchant_id == m.id for o in found)]
        return SourceResult(offers=found, merchants=merchants)


mock_source = MockSource()
