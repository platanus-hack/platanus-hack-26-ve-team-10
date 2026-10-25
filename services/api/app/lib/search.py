import asyncio
from typing import Any

from app.lib.prices import format_money, to_usd, trust_score
from app.lib.rate import get_rate
from app.lib.sources import sources
from app.lib.sources.firecrawl import search_open_web
from app.lib.types import Merchant, SearchQuery, Source, SourceResult

SOURCE_TIMEOUT_S = 8


def _same_zone(merchant: Merchant, zone: str | None) -> bool:
    return not zone or zone.lower() in merchant.zone.lower()


async def _run_source(source: Source, query: SearchQuery) -> SourceResult | None:
    try:
        return await asyncio.wait_for(source.search(query), SOURCE_TIMEOUT_S)
    except Exception:  # noqa: BLE001  la fuente falló o tardó demasiado: la búsqueda sigue sin ella
        return None


# Único punto de búsqueda: lo usan el agente y MCP. Llama a todas las fuentes en paralelo.
# Devuelve un dict con las claves del contrato (query, notice, failedSources, offers); cada oferta:
# title, url, price (como la publica el comercio), priceUsd, rate (si hubo conversión), seenAt,
# source y merchant {name, channel, zone, delivers, trust}. Primero las que tienen precio, de
# menor a mayor en USD.
async def search_offers(query: SearchQuery) -> dict[str, Any]:
    active = [source for source in sources if source.enabled]
    rate, *results = await asyncio.gather(get_rate(), *(_run_source(source, query) for source in active))

    failed_sources = [source.id for source, result in zip(active, results) if result is None]
    found = []
    for source, result in zip(active, results):
        if result is None:
            continue
        merchants = {merchant.id: merchant for merchant in result.merchants}
        for offer in result.offers:
            merchant = merchants.get(offer.merchant_id)
            if merchant:
                found.append((source.id, offer, merchant))

    offers = []
    for source_id, offer, merchant in found:
        # Con envío vale cualquier comercio que envíe; sin envío, solo los de la zona.
        if not (merchant.delivers if query.needs_delivery else _same_zone(merchant, query.zone)):
            continue
        offers.append(
            {
                "title": offer.title,
                "url": offer.url,
                "price": format_money(offer.price) if offer.price else None,
                "priceUsd": to_usd(offer.price, rate) if offer.price else None,
                "rate": (
                    f"{_js_number(rate.usd_to_ves)} Bs/USD ({rate.source}, {rate.observed_at})"
                    if offer.price and offer.price.currency == "VES"
                    else None
                ),
                "seenAt": offer.seen_at,
                "reviews": (
                    f"{merchant.comments} comentarios recientes" if merchant.comments is not None else None
                ),
                "image_url": None,
                "source": source_id,
                "example": source_id == "ejemplo",
                "merchant": {
                    "name": merchant.name,
                    "channel": merchant.channel,
                    "zone": merchant.zone,
                    "delivers": merchant.delivers,
                    "trust": trust_score(merchant),
                },
            }
        )
    offers.sort(key=lambda o: o["priceUsd"] if o["priceUsd"] is not None else float("inf"))

    response: dict[str, Any] = {"query": query.text, "failedSources": failed_sources, "offers": offers}
    if any(offer["example"] for offer in offers):
        response["notice"] = "Incluye datos de ejemplo: no todas las fuentes reales están conectadas."
    return response


# Para el MCP: las fuentes del registro y la web abierta (Firecrawl) a la vez, con la misma forma
# que search_offers. La web abierta no entra en search_offers porque tarda más de 8 s: aquí tiene
# su propio plazo. Sus ofertas no se filtran por zona: casi ninguna tienda web dice su ciudad, y la
# de un anuncio (merchant.zone) se muestra pero no se compara. Si falla toda la web abierta,
# failedSources dice firecrawl; si falla una tienda de la web abierta, firecrawl:<dominio>.
async def search_all(query: SearchQuery, open_web_budget_s: float) -> dict[str, Any]:
    found, web = await asyncio.gather(search_offers(query), search_open_web(query.text, open_web_budget_s))

    offers = found["offers"] + web["offers"]
    offers.sort(key=lambda o: o["priceUsd"] if o["priceUsd"] is not None else float("inf"))
    failed_sources = found["failedSources"] + (["firecrawl"] if web.get("failed") else web.get("failedSources", []))
    notices = [found.get("notice"), web.get("notice") if web["offers"] else None]

    response: dict[str, Any] = {"query": query.text, "failedSources": failed_sources, "offers": offers}
    if any(notices):
        response["notice"] = " ".join(notice for notice in notices if notice)
    return response


def _js_number(value: float) -> str:
    # 200.0 se escribe "200", como en JavaScript.
    return str(int(value)) if float(value).is_integer() else str(value)
