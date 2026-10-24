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

SEARCH_LIMIT = 8
SCRAPE_LIMIT = 8
PRICED_TARGET = 5
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


def _https_url(value: Any) -> str | None:
    if isinstance(value, str) and value.startswith("https://"):
        return value
    return None


def shop_name(url: str, site_name: str | None, brand: str | None) -> str:
    """El vendedor es la tienda del link. La marca del producto no lo es.

    Firecrawl pone en `brand` al fabricante (Apple) aunque la página sea de
    un revendedor. El nombre del sitio solo se usa si una palabra suya está
    en el dominio y no es únicamente esa marca.
    """
    host = _host(url)
    site = " ".join((site_name or "").split())
    labels = [part for part in host.split(".") if len(part) > 2]
    site_words = [word.lower() for word in site.split() if len(word) > 2]
    matches_host = any(word in label or label in word for word in site_words for label in labels)
    brand_only = site.lower() == (brand or "").strip().lower()
    brand_on_host = any(label in (brand or "").lower() for label in labels)
    if site and matches_host and (not brand_only or brand_on_host):
        return site
    return host


def _image_url(product: Any, document: Any) -> str | None:
    for variant in getattr(product, "variants", None) or []:
        for image in getattr(variant, "images", None) or []:
            url = _https_url(getattr(image, "url", None))
            if url:
                return url
    for raw in getattr(document, "images", None) or []:
        url = _https_url(raw)
        if url:
            return url
    metadata = getattr(document, "metadata", None)
    return _https_url(getattr(metadata, "og_image", None) if metadata else None)


def _from_product(document: Any) -> tuple[str | None, str | None, str | None, Money | None, str | None]:
    product = getattr(document, "product", None)
    if product is None and isinstance(document, dict):
        product = document.get("product")
    metadata = getattr(document, "metadata", None)
    site = getattr(metadata, "og_site_name", None) if metadata else None
    if product is None:
        return None, None, site, None, _image_url(None, document)
    title = getattr(product, "title", None)
    brand = getattr(product, "brand", None)
    variants = getattr(product, "variants", None) or []
    price = None
    if variants and getattr(variants[0], "price", None):
        amount = variants[0].price.amount
        currency = _currency(variants[0].price.currency)
        if isinstance(amount, (int, float)) and currency:
            price = Money(float(amount), currency)
    return title, brand, site, price, _image_url(product, document)


async def _scrape_price(
    client: AsyncFirecrawl, url: str
) -> tuple[str | None, str | None, str | None, Money | None, str | None]:
    document = await client.scrape(
        url,
        formats=["product"],
        only_main_content=True,
        timeout=SCRAPE_TIMEOUT_MS,
    )
    return _from_product(document)


async def search_open_web(product: str, budget_s: float = BUDGET_S) -> dict[str, Any]:
    """Busca el producto en Venezuela y se queda con hasta 5 páginas que traen precio."""
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
            title, brand, site, price, image = page if isinstance(page, tuple) else (None, None, None, None, None)
            if not price:
                continue
            offers.append(
                {
                    "title": title or titles.get(url) or product,
                    "image_url": image,
                    "url": url,
                    "price": format_money(price),
                    "priceUsd": to_usd(price, rate),
                    "rate": (
                        f"{rate.usd_to_ves:g} Bs/USD ({rate.source}, {rate.observed_at})"
                        if price.currency == "VES"
                        else None
                    ),
                    "seenAt": seen_at,
                    "source": "firecrawl",
                    "example": False,
                    "merchant": {
                        "name": shop_name(url, site, brand),
                        "channel": "web",
                        "zone": "Venezuela",
                        "delivers": None,
                        "trust": None,
                    },
                }
            )
        offers.sort(key=lambda offer: offer["priceUsd"] if offer["priceUsd"] is not None else float("inf"))
        notice = "Open-web shops have no seller trust score yet. Prices come only from the scraped page."
        if len(offers) < PRICED_TARGET:
            notice += " No hubo 5 páginas con precio publicado."
        result = {
            "source": "the open web",
            "product": product,
            "offers": offers[:PRICED_TARGET],
            "notice": notice,
        }
        return result

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
