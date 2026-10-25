"""Mercado Libre Venezuela, por un actor de Apify.

La API oficial responde 403 hasta en el endpoint más básico: hay que registrar una app. El sitio
tampoco se puede leer directo, porque manda a su verificación anti-bots. Así que por ahora el canal
entra por `sourabhbgp/mercadolibre-scraper`, que acepta `country: "VE"` y devuelve avisos reales
de MLV con su precio en dólares.

**Esto es un puente, no el destino.** La API oficial es la vía sancionada por Mercado Libre, es más
rápida (JSON, entra en los 8 s de la búsqueda, cosa que un actor no) y trae tres señales que aquí
faltan: antigüedad de la cuenta, calificaciones negativas y el volumen real del vendedor. Cuando
exista el token, esta fuente se reemplaza y `score_mercadolibre` no cambia: ya lee la forma de la
API, y aquí se le traduce la del actor.

La relevancia de Mercado Libre es floja —buscando "iPhone 15" devuelve Xiaomi Redmi—, así que el
filtro por producto no es opcional.
"""

from datetime import UTC, datetime
from typing import Any

from app.lib.sources.apify import ApifySource, count_of, seen_at_of
from app.lib.sources.firecrawl import matches_product
from app.lib.trust import score_mercadolibre
from app.lib.types import Condition, Merchant, Money, Offer, SourceResult

ACTOR = "sourabhbgp/mercadolibre-scraper"
SITE = "VE"
# Cada ficha abierta cuesta aparte: 15 resultados con detalle salieron por unos 3 céntimos.
RESULTS = 15

_CONDITION: dict[str, Condition] = {
    "newcondition": "nuevo",
    "new": "nuevo",
    "usedcondition": "usado",
    "used": "usado",
    "refurbished": "reacondicionado",
    "refurbishedcondition": "reacondicionado",
}


def entries(product: str) -> list[tuple[str, dict[str, Any]]]:
    return [
        (
            ACTOR,
            {
                "mode": "search",
                "country": SITE,
                "searchQuery": product,
                "maxItems": RESULTS,
                # Abre cada ficha: sin esto no vienen la reputación del vendedor ni la garantía,
                # y el puntaje se quedaría bajo el 40 % de cobertura.
                "scrapeProductDetails": True,
                "sortBy": "relevance",
            },
        )
    ]


def _condition(item: dict[str, Any]) -> Condition | None:
    return _CONDITION.get(str(item.get("condition") or "").lower().replace(" ", ""))


def _price(item: dict[str, Any]) -> Money | None:
    amount, currency = item.get("price"), str(item.get("currency") or "").upper()
    if isinstance(amount, (int, float)) and amount > 0 and currency in {"USD", "VES"}:
        return Money(float(amount), currency)
    return None


def _as_api_shape(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """El aviso y el vendedor con los nombres de la API oficial, que es lo que lee el puntaje.

    Lo que el actor no trae —antigüedad, calificaciones negativas, transacciones del vendedor,
    estado de la cuenta— se queda fuera a propósito: `score_mercadolibre` deja esas señales en
    `None`, no cuentan y su peso se reparte. Inventarlas sería peor que no medirlas.
    """
    api_item = {
        "id": item.get("itemId"),
        "title": item.get("title"),
        "pictures": item.get("images") or [],
        "warranty": item.get("warranty"),
        "description": item.get("description") or "",
    }
    reputation: dict[str, Any] = {}
    if isinstance(item.get("sellerReputation"), str):
        reputation["level_id"] = item["sellerReputation"]
    if isinstance(item.get("sellerPowerStatus"), str):
        reputation["power_seller_status"] = item["sellerPowerStatus"]
    return api_item, {"seller_reputation": reputation} if reputation else {}


def read(items: list[dict[str, Any]], product: str, now: str) -> SourceResult:
    offers, merchants, trust, seen = [], {}, {}, set()
    moment = datetime.now(UTC)
    for item in items:
        title = str(item.get("title") or "")
        url = str(item.get("listingUrl") or item.get("url") or "")
        price = _price(item)
        if not url or not price or not matches_product(product, title):
            continue
        if url in seen:
            continue
        seen.add(url)
        seller_id = str(item.get("sellerId") or item.get("sellerName") or "mlv").strip()
        merchant_id = f"ml:{seller_id}"
        if merchant_id not in merchants:
            name = item.get("officialStoreName") or item.get("sellerName") or "Vendedor de Mercado Libre"
            merchants[merchant_id] = Merchant(
                id=merchant_id,
                name=str(name),
                channel="mercadolibre",
                url=f"https://www.mercadolibre.com.ve/perfil/{seller_id}",
                zone="Venezuela",
                delivers=bool(item.get("freeShipping")),
                comments=count_of(item.get("reviewCount") or item.get("ratingCount")),
            )
            api_item, api_seller = _as_api_shape(item)
            trust[merchant_id] = score_mercadolibre(api_item, api_seller, now=moment)
        offers.append(
            Offer(
                merchant_id,
                title,
                url,
                price,
                seen_at_of(item.get("scrapedAt"), now),
                condition=_condition(item),
            )
        )
    return SourceResult(offers=offers, merchants=list(merchants.values()), trust=trust)


mercadolibre_source = ApifySource("mercadolibre", "mercadolibre", ACTOR, entries, read)
