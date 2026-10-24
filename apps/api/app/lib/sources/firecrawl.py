"""Web abierta con Firecrawl. La usan el especialista open_web y la tool search_prices del MCP.

No está en el registro de sources: search_offers cancela a los 8 s y cada
especialista la llamaría. Una búsqueda de Firecrawl tarda más y cobra por uso.
"""

import asyncio
import os
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from firecrawl import AsyncFirecrawl

from app.lib.prices import format_money, to_usd
from app.lib.rate import get_rate
from app.lib.types import Money

SEARCH_LIMIT = 5
SCRAPE_LIMIT = 3
SEARCH_TIMEOUT_MS = 20_000
SCRAPE_TIMEOUT_MS = 15_000
BUDGET_S = 45
# Cada búsqueda cobra créditos: el mismo producto no se vuelve a buscar en una hora. Un resultado
# sin ofertas dura menos, y uno que falló no se guarda.
CACHE_S = 60 * 60
EMPTY_CACHE_S = 10 * 60

_cache: dict[str, tuple[float, dict[str, Any]]] = {}

# Esas tiendas las cubren otros especialistas. La web abierta no las repite.
_SKIP_HOSTS = (
    "instagram.com",
    "tiktok.com",
    "facebook.com",
    "fb.com",
    "mercadolibre.",
    "google.",
    "youtube.com",
    "youtu.be",
)

def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _usable(url: str) -> bool:
    host = _host(url)
    return url.startswith("http") and host and not any(part in host for part in _SKIP_HOSTS)


def _web_hits(result: Any) -> list[Any]:
    web = getattr(result, "web", None)
    if web is None and isinstance(result, dict):
        web = result.get("web") or result.get("data")
    return list(web or [])


def _hit_url(hit: Any) -> str:
    if isinstance(hit, dict):
        return str(hit.get("url") or "")
    return str(getattr(hit, "url", "") or "")


def _hit_title(hit: Any) -> str | None:
    if isinstance(hit, dict):
        return hit.get("title")
    return getattr(hit, "title", None)


def _currency(value: str | None) -> str | None:
    token = (value or "").upper().replace(".", "")
    if token in ("USD", "US$", "$"):
        return "USD"
    if token in ("VES", "VEF", "BS", "BSS"):
        return "VES"
    return None


def _from_product(document: Any) -> tuple[str | None, str | None, Money | None]:
    product = getattr(document, "product", None)
    if product is None and isinstance(document, dict):
        product = document.get("product")
    if product is None:
        return None, None, None
    title = getattr(product, "title", None)
    seller = getattr(product, "brand", None)
    variants = getattr(product, "variants", None) or []
    price = None
    if variants and getattr(variants[0], "price", None):
        amount = variants[0].price.amount
        currency = _currency(variants[0].price.currency)
        if isinstance(amount, (int, float)) and currency:
            price = Money(float(amount), currency)
    return title, seller, price


async def _scrape_price(client: AsyncFirecrawl, url: str) -> tuple[str | None, str | None, Money | None]:
    document = await client.scrape(
        url,
        formats=["product"],
        only_main_content=True,
        timeout=SCRAPE_TIMEOUT_MS,
    )
    return _from_product(document)


async def search_open_web(product: str, budget_s: float = BUDGET_S) -> dict[str, Any]:
    """Busca el producto en la web de Venezuela y lee el precio publicado de hasta 3 páginas."""
    if not os.environ.get("FIRECRAWL_API_KEY"):
        return {
            "source": "the open web",
            "product": product,
            "offers": [],
            "notice": "Firecrawl is not configured.",
        }

    key = " ".join(product.lower().split())
    hit = _cache.get(key)
    if hit and time.monotonic() < hit[0]:
        return hit[1]

    async def _run() -> dict[str, Any]:
        client = AsyncFirecrawl(api_key=os.environ["FIRECRAWL_API_KEY"])
        found = await client.search(
            f"{product} precio Venezuela",
            limit=SEARCH_LIMIT,
            location="Caracas,Venezuela",
            country="VE",
            timeout=SEARCH_TIMEOUT_MS,
        )
        urls: list[str] = []
        titles: dict[str, str | None] = {}
        for hit in _web_hits(found):
            url = _hit_url(hit)
            if not _usable(url) or url in titles:
                continue
            titles[url] = _hit_title(hit)
            urls.append(url)
            if len(urls) == SCRAPE_LIMIT:
                break

        pages = await asyncio.gather(*(_scrape_price(client, url) for url in urls), return_exceptions=True)
        rate = await get_rate()
        seen_at = datetime.now(UTC).isoformat()
        offers = []
        for url, page in zip(urls, pages):
            title, seller, price = page if isinstance(page, tuple) else (None, None, None)
            offers.append(
                {
                    "title": title or titles.get(url) or product,
                    "url": url,
                    "price": format_money(price) if price else None,
                    "priceUsd": to_usd(price, rate) if price else None,
                    "rate": (
                        f"{rate.usd_to_ves:g} Bs/USD ({rate.source}, {rate.observed_at})"
                        if price and price.currency == "VES"
                        else None
                    ),
                    "seenAt": seen_at,
                    "source": "firecrawl",
                    "example": False,
                    "merchant": {
                        "name": seller or _host(url),
                        "channel": "web",
                        "zone": "Venezuela",
                        "delivers": None,
                        "trust": None,
                    },
                }
            )
        return {
            "source": "the open web",
            "product": product,
            "offers": offers,
            "notice": "Open-web shops have no seller trust score yet. Prices come only from the scraped page.",
        }

    try:
        result = await asyncio.wait_for(_run(), budget_s)
    except Exception as error:  # noqa: BLE001  la web abierta no tumba al orquestador
        return {
            "source": "the open web",
            "product": product,
            "offers": [],
            "failed": True,
            "notice": f"Firecrawl search failed: {type(error).__name__}",
        }
    _cache[key] = (time.monotonic() + (CACHE_S if result["offers"] else EMPTY_CACHE_S), result)
    return result
