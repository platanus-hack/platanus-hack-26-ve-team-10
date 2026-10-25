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

SEARCH_LIMIT = 8
SCRAPE_LIMIT = 8
PRICED_TARGET = 5
PER_SHOP = 2
SEARCH_TIMEOUT_MS = 20_000
SCRAPE_TIMEOUT_MS = 15_000
LISTING_TIMEOUT_MS = 20_000
BUDGET_S = 45
# Margen para armar la respuesta: las páginas que no terminen antes del plazo quedan como error.
MARGIN_S = 1
# Cada búsqueda cobra créditos: el mismo producto no se vuelve a buscar en una hora. Un resultado
# sin ofertas, o con alguna página en error, dura menos. Las reglas completas, en search_open_web.
CACHE_S = 60 * 60
EMPTY_CACHE_S = 10 * 60
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

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

# Lo que Firecrawl extrae de una página que no es la ficha de un producto: un portal de anuncios,
# un listado o una ficha sin precio en sus datos estructurados. Cobra 5 créditos por página,
# contra 1 del formato product, así que solo se pide cuando product no trajo precio.
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
    # con_ofertas, sin_ofertas, bloqueada o error. Las dos últimas van a failedSources.
    outcome: str = "sin_ofertas"
    offers: list[_Found] = field(default_factory=list)
    detail: str | None = None
    seconds: float = 0
    credits: int = 0


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


# plain, published_prices y matches_product también los usa apify.py: leer un precio escrito y
# decidir si un anuncio es el producto pedido es lo mismo en una página que en un caption.
def plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _currency(value: str | None) -> str | None:
    token = re.sub(r"[\s.:]", "", plain(value or "")).upper()
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


def published_prices(text: str) -> dict[float, set[str | None]]:
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


def matches_product(product: str, title: str) -> bool:
    """El anuncio nombra la marca, el modelo y las cifras de la consulta.

    Un listado mezcla productos: sin esto, "Harina PAN" trae Harina Kaly, y
    "Redmi 15C" trae el 13C. Se compara sin espacios ni signos, como la fuente
    de ejemplo, para que "BR200" cuente como "BR 200" y "P.A.N." como "PAN".
    """
    compact = re.sub(r"[^a-z0-9]", "", plain(title))
    required = []
    for word in re.findall(r"[a-z0-9]+", plain(product)):
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
    published = published_prices(getattr(document, "markdown", None) or "")
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
        if not listed.price or listed.price <= 0 or not currency or not matches_product(product, title):
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


async def _read_page(client: AsyncFirecrawl, page: _Page, product: str) -> None:
    """Primero el formato product (1 crédito). Si no trae precio, la lista de ofertas (5 créditos)."""
    url = page.url
    started = time.monotonic()
    try:
        document = await client.scrape(url, formats=["product"], only_main_content=True, timeout=SCRAPE_TIMEOUT_MS)
        page.credits += _credits(document)
        found = _from_product(url, document)
        block = None if found else _block(url, document)
        if found:
            page.offers, page.outcome = [found], "con_ofertas"
        elif block:
            page.outcome = block
        else:
            listing = await client.scrape(
                url,
                # El markdown no cobra aparte: sirve para comprobar que cada precio está en la página.
                formats=[{"type": "json", "schema": ListedOffers, "prompt": _listing_prompt(product)}, "markdown"],
                only_main_content=True,
                timeout=LISTING_TIMEOUT_MS,
            )
            page.credits += _credits(listing)
            page.offers = _from_listing(url, listing, product)
            page.outcome = "con_ofertas" if page.offers else _block(url, listing) or "sin_ofertas"
    except Exception as error:  # noqa: BLE001  una página que falla no tumba la búsqueda
        page.outcome, page.detail = "error", type(error).__name__
    page.seconds = round(time.monotonic() - started, 2)


async def _read_pages(client: AsyncFirecrawl, urls: list[str], product: str, deadline: float) -> list[_Page]:
    """Lee las páginas en paralelo hasta el plazo. Las que no terminan quedan como error, con lo
    que ya hayan gastado."""
    started = time.monotonic()
    pages = [_Page(url) for url in urls]
    tasks = [asyncio.create_task(_read_page(client, page, product)) for page in pages]
    try:
        if tasks:
            await asyncio.wait(tasks, timeout=max(deadline - time.monotonic(), 0))
    finally:
        for page, task in zip(pages, tasks):
            if not task.done():
                task.cancel()
                page.outcome, page.offers, page.detail = "error", [], "timeout"
                page.seconds = round(time.monotonic() - started, 2)
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
    key = " ".join(product.lower().split())
    hit = _cache.get(key)
    if hit and time.monotonic() < hit[0]:
        return hit[1]
    started = time.monotonic()

    async def _run() -> tuple[dict[str, Any], list[_Page]]:
        client = AsyncFirecrawl(api_key=os.environ["FIRECRAWL_API_KEY"])
        rate, found = await asyncio.gather(
            get_rate(),
            client.search(
                f"{product} precio Venezuela",
                limit=SEARCH_LIMIT,
                location="Caracas,Venezuela",
                country="VE",
                timeout=SEARCH_TIMEOUT_MS,
            ),
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

        pages = await _read_pages(client, urls, product, started + budget_s - MARGIN_S)
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
    # No se guarda un resultado cortado por el plazo: el MCP tiene 25 s y el agente 45 s. Con errores
    # pasajeros, uno con ofertas dura poco y uno vacío no se guarda.
    errors = any(page.outcome == "error" for page in pages)
    if not any(page.detail == "timeout" for page in pages) and (result["offers"] or not errors):
        ttl = CACHE_S if result["offers"] and not errors else EMPTY_CACHE_S
        _cache[key] = (time.monotonic() + ttl, result)
    return result
