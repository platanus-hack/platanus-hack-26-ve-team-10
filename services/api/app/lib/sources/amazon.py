"""Producto de Amazon por el actor público de Apify, no por la página a mano.

El actor es `junglee/Amazon-crawler`. El input usa los campos de su schema:
categoría o búsqueda en `categoryOrProductUrls`, detalle del producto y el
vendedor de la oferta principal. `useCaptchaSolver` queda apagado: Amazon
esconde peso y atributos cuando la página sale de un captcha, y no saltamos
ese bloqueo.

No está en el registro de `search_offers`. Esa búsqueda corta a los 8 s y
mostraría el precio de Amazon sin el flete. Lo llama la tool de importación.
Sin `APIFY_TOKEN` no corre.
"""

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote_plus

from apify_client import ApifyClientAsync

from app.lib.sources.firecrawl import _matching_title

log = logging.getLogger("prais.amazon")

AMAZON_ACTOR = "junglee/Amazon-crawler"
MAX_ITEMS = 5
# La tool espera la cotización. El actor tarda más que los 8 s de search_offers.
AMAZON_WAIT_S = 35
CACHE_S = 6 * 60 * 60
EMPTY_CACHE_S = 15 * 60

Fulfillment = Literal["amazon", "fba", "merchant"]
Runner = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]

_cache: dict[str, tuple[float, list["AmazonListing"]]] = {}
_runs: dict[str, asyncio.Task[None]] = {}


@dataclass(frozen=True)
class AmazonListing:
    asin: str
    title: str
    url: str
    price_usd: float
    seller_id: str | None
    seller_name: str
    seller_url: str
    fulfillment: Fulfillment | None
    image_url: str | None
    rows: tuple[tuple[str, str], ...]


def amazon_enabled() -> bool:
    return bool(os.environ.get("APIFY_TOKEN"))


def amazon_input(product: str) -> dict[str, Any]:
    """Búsqueda en amazon.com. El tope bajo es para no pagar de más por resultado."""
    query = quote_plus(" ".join(product.split()))
    return {
        "categoryOrProductUrls": [{"url": f"https://www.amazon.com/s?k={query}"}],
        "maxItemsPerStartUrl": MAX_ITEMS,
        "maxSearchPagesPerStartUrl": 1,
        "maxOffers": 0,
        "scrapeSellers": True,
        "scrapeProductDetails": True,
        "useCaptchaSolver": False,
    }


async def run_amazon_actor(actor: str, run_input: dict[str, Any]) -> list[dict[str, Any]]:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        return []
    client = ApifyClientAsync(token)
    run = await client.actor(actor).call(run_input=run_input, max_items=MAX_ITEMS, logger=None)
    if run is None:
        return []
    page = await client.dataset(run.default_dataset_id).list_items(clean=True)
    return [item for item in page.items if isinstance(item, dict)]


def read_listing(item: dict[str, Any], product: str) -> AmazonListing | None:
    """Un resultado del actor, o None si no es el producto o no trae precio en dólares."""
    if item.get("error") or not item.get("asin"):
        return None
    title = str(item.get("title") or "").strip()
    priced = _matching_title(product, title, str(item.get("brand") or "") or None)
    price = _usd(item.get("price"))
    if not priced or price is None or price <= 0:
        return None
    seller = item.get("seller") if isinstance(item.get("seller"), dict) else {}
    asin = str(item["asin"])
    url = item.get("url") if isinstance(item.get("url"), str) and item["url"].startswith("https://") else ""
    if not url:
        url = f"https://www.amazon.com/dp/{asin}"
    image = item.get("thumbnailImage")
    image_url = image if isinstance(image, str) and image.startswith("https://") else None
    seller_id = seller.get("id")
    seller_id = str(seller_id) if seller_id else None
    return AmazonListing(
        asin=asin,
        title=priced,
        url=url,
        price_usd=price,
        seller_id=seller_id,
        seller_name=str(seller.get("name") or "Amazon").strip() or "Amazon",
        seller_url=_seller_url(seller, asin, url),
        fulfillment=_fulfillment(seller),
        image_url=image_url,
        rows=tuple(_rows(item)),
    )


def choose_listing(listings: list[AmazonListing]) -> AmazonListing | None:
    """El que vende Amazon, si no el más barato. Uno solo: el ranking compara productos."""
    if not listings:
        return None
    rank = {"amazon": 0, "fba": 1, "merchant": 2, None: 3}
    return min(listings, key=lambda item: (rank[item.fulfillment], item.price_usd, item.asin))


def asin_median(listings: list[AmazonListing], asin: str) -> float | None:
    """Mediana del mismo ASIN. Con un solo precio no hay mediana: null, no el precio mismo."""
    prices = sorted(item.price_usd for item in listings if item.asin == asin)
    if len(prices) < 2:
        return None
    mid = len(prices) // 2
    if len(prices) % 2:
        return prices[mid]
    return (prices[mid - 1] + prices[mid]) / 2


async def search_amazon(product: str, runner: Runner | None = None) -> list[AmazonListing]:
    key = " ".join(product.lower().split())
    hit = _cache.get(key)
    if hit and time.monotonic() < hit[0]:
        return hit[1]
    task = _runs.get(key)
    if task is None or task.done():
        task = asyncio.create_task(_fill(key, product, runner or run_amazon_actor))
        _runs[key] = task
    await asyncio.wait([task], timeout=AMAZON_WAIT_S)
    hit = _cache.get(key)
    return hit[1] if hit else []


async def _fill(key: str, product: str, runner: Runner) -> None:
    started = time.monotonic()
    items: list[dict[str, Any]] = []
    detail = None
    run_input = amazon_input(product)
    try:
        items = await runner(AMAZON_ACTOR, run_input)
    except Exception as error:  # noqa: BLE001  una fuente que falla no tumba la cotización
        detail = f"{type(error).__name__}: {error}"
    listings = [row for item in items if (row := read_listing(item, product))]
    _cache[key] = (time.monotonic() + (CACHE_S if listings else EMPTY_CACHE_S), listings)
    _runs.pop(key, None)
    log.info(
        "amazon %s",
        {"query": product, "seconds": round(time.monotonic() - started, 2), "items": len(items),
         "listings": len(listings), **({"detail": detail} if detail else {})},
    )


def _usd(price: Any) -> float | None:
    if isinstance(price, dict):
        currency = str(price.get("currency") or "$").strip().upper()
        raw = price.get("value")
    else:
        currency, raw = "$", price
    if currency not in {"$", "USD", "US$"}:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _fulfillment(seller: dict[str, Any]) -> Fulfillment | None:
    name = str(seller.get("name") or "").strip().lower()
    url = str(seller.get("url") or "")
    if not name and not url:
        return None
    if name.startswith("amazon"):
        return "amazon"
    if "isamazonfulfilled=1" in url.lower():
        return "fba"
    if name:
        return "merchant"
    return None


def _seller_url(seller: dict[str, Any], asin: str, product_url: str) -> str:
    raw = str(seller.get("url") or "")
    if raw.startswith("https://"):
        return raw
    if raw.startswith("/"):
        return "https://www.amazon.com" + raw
    if seller.get("id"):
        return f"https://www.amazon.com/sp?seller={seller['id']}"
    return product_url or f"https://www.amazon.com/dp/{asin}"


def _rows(item: dict[str, Any]) -> list[tuple[str, str]]:
    """Peso y medidas salen de attributes, productOverview o manufacturerAttributes."""
    found: list[tuple[str, str]] = []
    for key in ("attributes", "productOverview", "manufacturerAttributes"):
        raw = item.get(key)
        if isinstance(raw, dict):
            found.extend((str(name), str(value)) for name, value in raw.items() if value is not None)
        elif isinstance(raw, list):
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("key") or entry.get("name") or entry.get("label")
                value = entry.get("value")
                if name and value is not None:
                    found.append((str(name), str(value)))
    return found
