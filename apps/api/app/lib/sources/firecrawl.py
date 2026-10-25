"""Web abierta con Firecrawl. La usan el especialista open_web y la tool search_prices del MCP.

No está en el registro de sources: search_offers cancela a los 8 s y cada
especialista la llamaría. Una búsqueda de Firecrawl tarda más y cobra por uso.
"""

import asyncio
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from firecrawl import AsyncFirecrawl
from pydantic import BaseModel, Field, ValidationError

from app.lib.prices import format_money, to_usd
from app.lib.rate import get_rate
from app.lib.types import Money

log = logging.getLogger("prais.firecrawl")

# 15 results bill 4 credits (2 per 10, rounded up). The extra hits replace pages
# we drop because they do not sell in Venezuela, so the 8 scrapes stay local.
SEARCH_LIMIT = 15
SCRAPE_LIMIT = 8
PRICED_TARGET = 5
PER_SHOP = 2
SEARCH_TIMEOUT_MS = 20_000
# Keep this much of the budget for page reads. A 20s search on the MCP's 25s
# budget left no time to read a listing.
SEARCH_RESERVE_MS = 10_000
# Do not start a scrape that has less than this left: it cannot return.
MIN_SCRAPE_MS = 500
# Firecrawl's timeout is milliseconds (the scrape docs use 120000). Shave a
# little off so the response arrives before we cancel the task.
SCRAPE_SLACK_MS = 200
BUDGET_S = 45
# Margin for building the response. Pages still running at the deadline are errors.
MARGIN_S = 1
# One search is cached for an hour. An empty result, or one with a page error,
# is kept for less. A page that finished is cached on its own: see _page_cache.
CACHE_S = 60 * 60
EMPTY_CACHE_S = 10 * 60
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_page_cache: dict[tuple[str, str], tuple[float, Any]] = {}

# Esas tiendas las cubren otros especialistas, o no se pueden leer. La web abierta no las repite.
_SKIP_HOSTS = (
    "instagram.com",
    "tiktok.com",
    "facebook.com",
    "fb.com",
    "mercadolibre.",
    # TuCarro es de Mercado Libre: le toca a ese especialista. Su página manda a una verificación
    # anti-bots, y no se intenta saltarla.
    "tucarro.",
    # Trovit junta anuncios de otros portales: da links de rastreo, pone Bs a precios en dólares y
    # su listado tarda unos 40 s en leerse.
    "trovit.",
    # eBay es de Estados Unidos: su categoría no vende en Venezuela y tarda más de 20 s en leerse.
    "ebay.",
    "google.",
    "youtube.com",
    "youtu.be",
)

# What Firecrawl extracts from a page that is not one product: a classifieds
# portal, a category listing, or a product page whose structured data has no
# price. JSON mode is +4 credits on the 1-credit scrape (5 total). Markdown is
# included in that same call and is not charged extra. The product format is
# the 1-credit scrape with no LLM, so a product page asks for it alone.
# https://docs.firecrawl.dev/features/scrape.md — several formats per request;
# https://docs.firecrawl.dev/billing.md — JSON is +4, product is not.
class ListedOffer(BaseModel):
    title: str = Field(description="Title of the listing or product, as shown")
    variant: str | None = Field(default=None, description="Year, version, size or condition, if shown")
    price: float | None = Field(
        default=None, description="Published price as a number, without thousands separators. Null if none is shown"
    )
    currency: str | None = Field(
        default=None, description="Currency exactly as written next to the price, e.g. USD, US$, u$s, $, Bs"
    )
    city: str | None = Field(default=None, description="City or area of the listing, if shown")
    url: str | None = Field(default=None, description="Link to this specific listing or product page")
    image: str | None = Field(default=None, description="Image URL of this listing")


class ListedOffers(BaseModel):
    offers: list[ListedOffer]


def _listing_prompt(product: str) -> str:
    return (
        f'List every item for sale on this page that matches the search "{product}", with its published '
        "price. Skip accessories, other models and related or recommended products. Never invent a price: "
        "if an item shows none, leave price null."
    )


@dataclass
class _Found:
    title: str | None
    price: Money
    url: str
    image: str | None
    seller: str
    zone: str


@dataclass
class _Page:
    url: str
    # con_ofertas, sin_ofertas, bloqueada or error. The last two go to failedSources.
    outcome: str = "sin_ofertas"
    offers: list[_Found] = field(default_factory=list)
    detail: str | None = None
    seconds: float = 0
    credits: int = 0
    # True once the scrape we needed actually returned. A listing we skipped
    # because the budget was gone is not complete and is not cached.
    complete: bool = False


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _usable(url: str) -> bool:
    host = _host(url)
    return url.startswith("http") and host and not any(part in host for part in _SKIP_HOSTS)


def _host_is(host: str, name: str) -> bool:
    return host == name or host.endswith("." + name)


# Country-code domains other than Venezuela. Longer suffixes first so .com.mx
# is decided before a shorter tail. .com stores in Venezuela are not in this list.
_FOREIGN_SUFFIXES = (
    ".com.mx", ".com.ar", ".com.br", ".com.pe", ".com.co", ".com.ec", ".com.cl",
    ".com.uy", ".com.bo", ".com.py", ".com.gt", ".com.do", ".com.sv", ".com.hn",
    ".com.ni", ".com.cr", ".com.pa", ".com.pr", ".com.es", ".com.cn", ".co.uk",
    ".mx", ".ar", ".br", ".pe", ".co", ".ec", ".cl", ".uy", ".bo", ".py",
    ".gt", ".do", ".sv", ".hn", ".ni", ".cr", ".pa", ".pr", ".es", ".cn",
    ".uk", ".de", ".fr", ".it", ".us",
)

# Brand and retailer sites that do not publish a Venezuela price. A /ve/ path
# or a .ve host is still read (apple.com/ve).
_ABROAD_BRANDS = (
    "lenovo.com",
    "nvidia.com",
    "samsung.com",
    "hp.com",
    "dell.com",
    "asus.com",
    "acer.com",
    "msi.com",
    "apple.com",
    "microsoft.com",
    "amazon.com",
    "bestbuy.com",
    "walmart.com",
    "newegg.com",
    "aliexpress.com",
    "falabella.com",
    "ripley.com",
)

# .com shops we already know sell in Venezuela. They sort ahead of other results
# so a foreign hit cannot take their scrape. .ve hosts sort next.
_VE_SHOPS = (
    "sigmatiendas.com",
    "soytechno.com",
    "tiendasdaka.com",
    "elplazas.com",
)

# Path segments of a category or search page. A product URL such as
# /apple-iphone-15/ or /producto/... is not here, so it still uses the product format.
_LISTING_SEGMENTS = frozenset({
    "collections", "collection",
    "categoria", "categorias", "category", "categories",
    "departamento", "departamentos",
    "listado", "listing", "listings",
    "product-category", "categoria-producto",
    "catalogo", "catalog",
    "laptops-gamer",
    "search", "busca", "busqueda",
})


def _foreign_host(host: str) -> bool:
    if host.endswith(".ve"):
        return False
    return any(host.endswith(suffix) for suffix in _FOREIGN_SUFFIXES)


def _venezuela_section(url: str) -> bool:
    host = _host(url)
    if host.endswith(".ve") or host.startswith("ve."):
        return True
    path = "/" + unquote(urlparse(url).path).strip("/").lower()
    return path == "/ve" or path.startswith("/ve/") or "/venezuela" in path


def _brand_abroad(url: str) -> bool:
    if _venezuela_section(url):
        return False
    host = _host(url)
    return any(_host_is(host, brand) for brand in _ABROAD_BRANDS)


def _sells_in_venezuela(url: str) -> bool:
    if not _usable(url):
        return False
    return not _foreign_host(_host(url)) and not _brand_abroad(url)


def _ve_group(url: str) -> int:
    """0 known shop, 1 other .ve host, 2 the rest. Lower is read first."""
    host = _host(url)
    if any(_host_is(host, shop) for shop in _VE_SHOPS):
        return 0
    if host.endswith(".ve"):
        return 1
    return 2


def _is_listing(url: str) -> bool:
    """A category or search page, which has no single product price."""
    if _host(url).startswith("listado."):
        return True
    segments = [_plain(segment) for segment in unquote(urlparse(url).path).split("/") if segment]
    return any(segment in _LISTING_SEGMENTS for segment in segments)


def _pick_urls(hits: list[Any]) -> list[tuple[str, str | None]]:
    """Venezuelan pages only, known shops and .ve first, at most SCRAPE_LIMIT."""
    seen: set[str] = set()
    found: list[tuple[str, str | None]] = []
    for hit in hits:
        url = _hit_url(hit)
        if not url or url in seen or not _sells_in_venezuela(url):
            continue
        seen.add(url)
        found.append((url, _hit_title(hit)))
    found.sort(key=lambda item: _ve_group(item[0]))
    return found[:SCRAPE_LIMIT]


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


def _plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _currency(value: str | None) -> str | None:
    token = re.sub(r"[\s.:]", "", _plain(value or "")).upper()
    # En Venezuela el dólar se escribe también u$s, U$S o REF (el precio de referencia, en dólares).
    if token in ("USD", "US$", "U$S", "U$D", "USD$", "$USD", "$", "REF", "DOLAR", "DOLARES"):
        return "USD"
    if token in ("VES", "VEF", "BS", "BSS", "BSD", "BSF", "BOLIVAR", "BOLIVARES"):
        return "VES"
    return None


_SYMBOL = r"u\$s|u\$d|us\s?\$|usd\$?|\$usd|\bref\b\.?|\$|\bbs\.?\s?[sdf]?\b\.?|\bves\b|d[oó]lares"
# El símbolo de después cuenta solo en la misma línea y si no abre otro monto: en "Bs. 5.200 REF 26"
# o en un título que termina en cifra ("Galaxy A15\nRef. 150"), el símbolo es del monto siguiente.
_PRICE = re.compile(
    rf"(?:(?P<before>{_SYMBOL})[\s:]*)?(?P<number>\d[\d.,]*)(?:[ \t]*(?P<after>{_SYMBOL})(?![\s:]*\d))?",
    re.IGNORECASE,
)


def _amount(raw: str) -> float | None:
    """Un monto en formato venezolano (6.000 o 1.039,96) o en inglés (1,039.96)."""
    raw = raw.rstrip(".,")
    if "." in raw and "," in raw:
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
    else:
        separator = "." if "." in raw else ","
        groups = raw.split(separator)[1:]
        # Grupos de tres cifras tras el separador son miles (6.000); si no, es el decimal (84,20).
        decimal = None if all(len(group) == 3 for group in groups) else separator
    if decimal is None:
        number = raw.replace(".", "").replace(",", "")
    else:
        number = raw.replace("," if decimal == "." else ".", "").replace(decimal, ".")
    try:
        return round(float(number), 2)
    except ValueError:
        return None


def _published_prices(text: str) -> dict[float, set[str | None]]:
    """Cada monto escrito en la página, con la moneda escrita junto a él (None si no tiene)."""
    prices: dict[float, set[str | None]] = {}
    for match in _PRICE.finditer(text):
        amount = _amount(match["number"])
        if amount is not None:
            currency = _currency(match["before"]) or _currency(match["after"])
            prices.setdefault(amount, set()).add(currency)
    return prices


# Palabras de la consulta que el título de un anuncio no tiene por qué repetir: relleno, estado,
# categorías que cada tienda nombra a su manera y unidades. Se comparan en singular.
_GENERIC = {
    "precio", "de", "del", "la", "el", "lo", "en", "con", "para", "venezuela",
    "usado", "usada", "nuevo", "nueva", "economico", "economica", "barato", "barata",
    "carro", "auto", "vehiculo", "camioneta", "moto", "celular", "telefono", "smartphone",
    "televisor", "nevera", "refrigerador", "laptop", "notebook", "portatil", "computadora",
    "zapato", "zapatilla", "audifono", "caucho", "neumatico", "harina", "aceite", "arroz",
    "pulgada", "litro", "kilo", "gramo", "unidad",
    # Marcas que el título omite cuando ya nombra el modelo (iPhone, Redmi).
    "apple", "xiaomi",
}  # fmt: skip
# Una cifra con su unidad vale por la cifra sola: "1kg" es "1 Kilo", "128gb" es "128 GB".
_UNIT = re.compile(r"^(\d+)(?:kg|kgs|g|gr|grs|ml|l|lt|lts|gb|tb|mah|w|cc|pulg)$")


def _singular(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word[-2].isdigit() else word


def _matches(product: str, title: str) -> bool:
    """El anuncio nombra la marca, el modelo y las cifras de la consulta.

    Un listado mezcla productos: sin esto, "Harina PAN" trae Harina Kaly, y
    "Redmi 15C" trae el 13C. Se compara sin espacios ni signos, como la fuente
    de ejemplo, para que "BR200" cuente como "BR 200" y "P.A.N." como "PAN".
    """
    compact = re.sub(r"[^a-z0-9]", "", _plain(title))
    required = []
    for word in re.findall(r"[a-z0-9]+", _plain(product)):
        word = _UNIT.sub(r"\1", _singular(word))
        if word not in _GENERIC and (len(word) >= 3 or any(char.isdigit() for char in word)):
            required.append(word)
    return all(word in compact for word in required)


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


def _site_name(document: Any) -> str | None:
    metadata = getattr(document, "metadata", None)
    return getattr(metadata, "og_site_name", None) if metadata else None


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


def _same_page(one: str, other: str) -> bool:
    def path(url: str) -> str:
        return unquote(urlparse(url).path).rstrip("/")

    return _host(one) == _host(other) and path(one) == path(other)


def _from_product(url: str, document: Any) -> _Found | None:
    product = getattr(document, "product", None)
    if product is None and isinstance(document, dict):
        product = document.get("product")
    # A veces el formato product lee un producto relacionado de la misma página (azúcar en la
    # ficha de un arroz). Ese no vale: la página pasa a la lista de ofertas.
    product_url = getattr(product, "url", None)
    if isinstance(product_url, str) and product_url.startswith("http") and not _same_page(product_url, url):
        return None
    variants = getattr(product, "variants", None) or []
    if not variants or not getattr(variants[0], "price", None):
        return None
    amount = variants[0].price.amount
    currency = _currency(variants[0].price.currency)
    if not isinstance(amount, (int, float)) or not currency:
        return None
    return _Found(
        title=getattr(product, "title", None),
        price=Money(float(amount), currency),
        url=url,
        image=_image_url(product, document),
        seller=shop_name(url, _site_name(document), getattr(product, "brand", None)),
        zone="Venezuela",
    )


def _listed_currency(listed: ListedOffer, published: dict[float, set[str | None]]) -> str | None:
    """La moneda del precio, solo si el monto está escrito en la página.

    La moneda escrita junto al monto manda sobre la que dijo el modelo, que a
    veces marca como Bs un precio en REF (dólares).
    """
    on_page = published.get(round(listed.price or 0, 2))
    if not on_page:
        return None
    said = _currency(listed.currency)
    written = {currency for currency in on_page if currency}
    if not written or said in written:
        return said
    return next(iter(written)) if len(written) == 1 else None


def _from_listing(url: str, document: Any, product: str) -> list[_Found]:
    """Las ofertas de la extracción JSON que son el producto pedido y cuyo precio está en la página.

    La extracción pasa por un modelo: un monto que no aparece en el markdown de
    la página se descarta, para no mostrar nunca un precio inventado.
    """
    data = getattr(document, "json", None)
    items = data.get("offers") if isinstance(data, dict) else None
    published = _published_prices(getattr(document, "markdown", None) or "")
    seller = shop_name(url, _site_name(document), None)
    found = []
    for item in items or []:
        try:
            listed = ListedOffer.model_validate(item)
        except ValidationError:
            continue
        title = listed.title
        if listed.variant and listed.variant.lower() not in title.lower():
            title = f"{title} {listed.variant}"
        currency = _listed_currency(listed, published)
        if not listed.price or listed.price <= 0 or not currency or not _matches(product, title):
            continue
        link = urljoin(url, listed.url) if listed.url else url
        found.append(
            _Found(
                title=title,
                price=Money(listed.price, currency),
                url=link if link.startswith("http") else url,
                image=_https_url(listed.image) or _image_url(None, document),
                seller=seller,
                zone=listed.city or "Venezuela",
            )
        )
    return found


def _credits(document: Any) -> int:
    metadata = getattr(document, "metadata", None)
    credits = getattr(metadata, "credits_used", None)
    return credits if isinstance(credits, int) else 0


def _block(url: str, document: Any) -> str | None:
    """bloqueada o error si la página no se pudo leer, aunque Firecrawl haya respondido.

    TuCarro, por ejemplo, responde 200 pero manda a la verificación anti-bots de
    Mercado Libre: se nota en que la URL final es de otro dominio.
    """
    metadata = getattr(document, "metadata", None)
    status = getattr(metadata, "status_code", None)
    final = str(getattr(metadata, "url", None) or url)
    if status in (401, 403, 429) or "account-verification" in final or "captcha" in final.lower():
        return "bloqueada"
    # Un link muerto no es una tienda que falló: no va a failedSources.
    if status in (404, 410):
        return "sin_ofertas"
    if status is not None and not (200 <= status < 300 or status == 304):
        return "error"
    asked, landed = _host(url), _host(final)
    if landed and not (landed.endswith(asked) or asked.endswith(landed)):
        return "bloqueada"
    return None


def _product_key(product: str) -> str:
    return " ".join(product.lower().split())


def _listing_formats(product: str) -> list[Any]:
    # Markdown is free and is how _from_listing checks the price is on the page.
    # JSON and markdown are one scrape: https://docs.firecrawl.dev/features/scrape.md
    return [{"type": "json", "schema": ListedOffers, "prompt": _listing_prompt(product)}, "markdown"]


def _timeout_ms(deadline: float) -> int | None:
    """Milliseconds left for one scrape, or None when it cannot finish in time."""
    remaining_ms = int((deadline - time.monotonic()) * 1000) - SCRAPE_SLACK_MS
    if remaining_ms < MIN_SCRAPE_MS:
        return None
    return remaining_ms


def _search_timeout_ms(deadline: float) -> int:
    """Cap the search so page reads still have time inside the same budget."""
    remaining_ms = int((deadline - time.monotonic()) * 1000)
    reserve_ms = min(SEARCH_RESERVE_MS, max(remaining_ms // 2, 0))
    return max(min(SEARCH_TIMEOUT_MS, remaining_ms - reserve_ms), 1)


def _remember(product: str, page: _Page) -> None:
    """Keep a page that was fully read. Errors and cut-off reads are retried."""
    if not page.complete or page.outcome not in ("con_ofertas", "sin_ofertas"):
        return
    ttl = CACHE_S if page.offers else EMPTY_CACHE_S
    _page_cache[(_product_key(product), page.url)] = (
        time.monotonic() + ttl,
        _Page(
            url=page.url,
            outcome=page.outcome,
            offers=list(page.offers),
            seconds=page.seconds,
            credits=page.credits,
            complete=True,
        ),
    )


def _recall(product: str, url: str) -> _Page | None:
    key = (_product_key(product), url)
    hit = _page_cache.get(key)
    if hit is None:
        return None
    expires, page = hit
    if time.monotonic() >= expires:
        _page_cache.pop(key, None)
        return None
    return _Page(
        url=page.url,
        outcome=page.outcome,
        offers=list(page.offers),
        detail="cache",
        seconds=0,
        credits=0,
        complete=True,
    )


async def _scrape(client: AsyncFirecrawl, url: str, formats: list[Any], deadline: float) -> Any | None:
    timeout = _timeout_ms(deadline)
    if timeout is None:
        return None
    return await client.scrape(url, formats=formats, only_main_content=True, timeout=timeout)


def _apply_listing(page: _Page, listing: Any, product: str) -> None:
    page.credits += _credits(listing)
    page.offers = _from_listing(page.url, listing, product)
    page.outcome = "con_ofertas" if page.offers else _block(page.url, listing) or "sin_ofertas"
    page.complete = True


async def _read_page(client: AsyncFirecrawl, page: _Page, product: str, deadline: float) -> None:
    """One scrape for a listing. A product page tries product first, then JSON if time remains.

    A category page never has a price in the product format, so the old code always
    did both reads in series (up to 35s) and the MCP's 25s budget marked it timeout.
    Listings now ask for JSON and markdown together. The timeout is whatever time
    is left, and a read that cannot finish is not started.
    """
    started = time.monotonic()
    try:
        if _is_listing(page.url):
            listing = await _scrape(client, page.url, _listing_formats(product), deadline)
            if listing is None:
                page.outcome, page.detail = "error", "timeout"
            else:
                _apply_listing(page, listing, product)
        else:
            document = await _scrape(client, page.url, ["product"], deadline)
            if document is None:
                page.outcome, page.detail = "error", "timeout"
            else:
                page.credits += _credits(document)
                found = _from_product(page.url, document)
                block = None if found else _block(page.url, document)
                if found:
                    page.offers, page.outcome, page.complete = [found], "con_ofertas", True
                elif block:
                    page.outcome, page.complete = block, True
                else:
                    listing = await _scrape(client, page.url, _listing_formats(product), deadline)
                    if listing is None:
                        # The product read finished with no price and the listing
                        # read would not return in time. Do not start it.
                        page.outcome = "sin_ofertas"
                    else:
                        _apply_listing(page, listing, product)
    except Exception as error:  # noqa: BLE001  a page that fails does not fail the search
        page.outcome, page.detail, page.complete = "error", type(error).__name__, False
    page.seconds = round(time.monotonic() - started, 2)


async def _read_pages(client: AsyncFirecrawl, urls: list[str], product: str, deadline: float) -> list[_Page]:
    """Read pages in parallel until the deadline. Unfinished ones are errors.

    Pages already read for this product are reused, including when another page
    in this search runs out of time.
    """
    started = time.monotonic()
    pages: list[_Page] = []
    pending: list[tuple[_Page, asyncio.Task[None]]] = []
    for url in urls:
        cached = _recall(product, url)
        if cached is not None:
            pages.append(cached)
            continue
        page = _Page(url)
        pages.append(page)
        pending.append((page, asyncio.create_task(_read_page(client, page, product, deadline))))
    try:
        if pending:
            await asyncio.wait([task for _, task in pending], timeout=max(deadline - time.monotonic(), 0))
    finally:
        for page, task in pending:
            if not task.done():
                task.cancel()
                page.outcome, page.offers, page.detail = "error", [], "timeout"
                page.seconds = round(time.monotonic() - started, 2)
                page.complete = False
            elif page.complete and page.outcome in ("con_ofertas", "sin_ofertas"):
                _remember(product, page)
        for _, task in pending:
            if task.cancelled() or not task.done():
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    return pages


def _choose(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Las 5 más baratas, con un link una sola vez y hasta 2 por tienda.

    Un listado puede traer muchas ofertas de un mismo sitio. Si no hay otras
    tiendas para llenar las 5, se completa con las que quedaron fuera.
    """
    links: set[str] = set()
    picked, extra, per_shop = [], [], {}
    for offer in sorted(offers, key=lambda offer: offer["priceUsd"]):
        if offer["url"] in links:
            continue
        links.add(offer["url"])
        shop = _host(offer["url"])
        if per_shop.get(shop, 0) < PER_SHOP:
            per_shop[shop] = per_shop.get(shop, 0) + 1
            picked.append(offer)
        else:
            extra.append(offer)
    chosen = (picked + extra)[:PRICED_TARGET]
    return sorted(chosen, key=lambda offer: offer["priceUsd"])


def _log(product: str, pages: list[_Page], seconds: float) -> None:
    log.info(
        "firecrawl %s",
        json.dumps(
            {
                "query": product,
                "seconds": round(seconds, 2),
                # Los de las páginas: la búsqueda cobra aparte (2 créditos por 10 resultados).
                "credits": sum(page.credits for page in pages),
                "pages": [
                    {
                        "host": _host(page.url),
                        "outcome": page.outcome,
                        "offers": len(page.offers),
                        "seconds": page.seconds,
                        "credits": page.credits,
                        **({"detail": page.detail} if page.detail else {}),
                    }
                    for page in pages
                ],
            },
            ensure_ascii=False,
        ),
    )


async def search_open_web(product: str, budget_s: float = BUDGET_S) -> dict[str, Any]:
    """Busca el producto en Venezuela y se queda con hasta 5 ofertas que traen precio."""
    if not os.environ.get("FIRECRAWL_API_KEY"):
        return {
            "source": "the open web",
            "product": product,
            "offers": [],
            "notice": "Firecrawl is not configured.",
        }
    key = _product_key(product)
    hit = _cache.get(key)
    if hit and time.monotonic() < hit[0]:
        return hit[1]
    started = time.monotonic()
    deadline = started + budget_s - MARGIN_S

    async def _run() -> tuple[dict[str, Any], list[_Page]]:
        client = AsyncFirecrawl(api_key=os.environ["FIRECRAWL_API_KEY"])
        rate, found = await asyncio.gather(
            get_rate(),
            client.search(
                f"{product} precio Venezuela",
                limit=SEARCH_LIMIT,
                location="Caracas,Venezuela",
                country="VE",
                timeout=_search_timeout_ms(deadline),
            ),
        )
        picked = _pick_urls(_web_hits(found))
        urls = [url for url, _title in picked]
        titles = dict(picked)

        pages = await _read_pages(client, urls, product, deadline)
        _log(product, pages, time.monotonic() - started)
        seen_at = datetime.now(UTC).isoformat()
        offers = []
        # De qué página salió cada oferta, para saber qué tiendas quedaron en la respuesta.
        shop_of: dict[int, str] = {}
        for page in pages:
            for found_offer in page.offers:
                price = found_offer.price
                offers.append(
                    {
                        "title": found_offer.title or titles.get(page.url) or product,
                        "image_url": found_offer.image,
                        "url": found_offer.url,
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
                            "name": found_offer.seller,
                            "channel": "web",
                            "zone": found_offer.zone,
                            "delivers": None,
                            "trust": None,
                        },
                    }
                )
                shop_of[id(offers[-1])] = _host(page.url)
        offers = _choose(offers)
        notice = "Open-web shops have no seller trust score yet. Prices come only from the scraped page."
        if len(offers) < PRICED_TARGET:
            notice += " No hubo 5 ofertas con precio publicado."
        # Una tienda con ofertas en la respuesta no se reporta como caída por otra de sus páginas.
        with_offers = {shop_of[id(offer)] for offer in offers}
        failed = [
            f"firecrawl:{_host(page.url)}"
            for page in pages
            if page.outcome in ("bloqueada", "error") and _host(page.url) not in with_offers
        ]
        result = {
            "source": "the open web",
            "product": product,
            "offers": offers,
            "failedSources": list(dict.fromkeys(failed)),
            "notice": notice,
        }
        return result, pages

    try:
        result, pages = await asyncio.wait_for(_run(), budget_s)
    except Exception as error:  # noqa: BLE001  la web abierta no tumba al orquestador
        return {
            "source": "the open web",
            "product": product,
            "offers": [],
            "failed": True,
            "notice": f"Firecrawl search failed: {type(error).__name__}",
        }
    # Do not cache a result the deadline cut short: the MCP has 25s and the agent
    # 45s. Pages that did finish stay in _page_cache. A transient error with
    # offers is kept briefly; an empty error is not stored. A product page we
    # could not follow with a listing read is not finished, so it is retried.
    errors = any(page.outcome == "error" for page in pages)
    finished = all(page.complete for page in pages)
    if finished and (result["offers"] or not errors):
        ttl = CACHE_S if result["offers"] and not errors else EMPTY_CACHE_S
        _cache[key] = (time.monotonic() + ttl, result)
    return result
