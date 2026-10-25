"""Una tool por fuente. Devuelve el listado ya armado: ningún modelo lo reescribe."""

import asyncio
from typing import Any

from app.agents.listing import cards_from_offers
from app.agents.open_web_trust import review_offers
from app.lib.importacion.cotizar import quote_import
from app.lib.search import search_offers
from app.lib.sources.firecrawl import BUDGET_S, search_open_web
from app.lib.trust import close_listings
from app.lib.types import Channel, SearchQuery

ORCHESTRATOR_NAME = "root_agent"


def _listings_tool(source: str, channel: Channel | None):
    slug = channel or "meta_ad_library"

    async def find_listings(product: str) -> dict[str, Any]:
        """Return this source's listings for one product. Call once.

        Args:
            product: Product or service the orchestrator is comparing.
        """
        if channel is None:
            return {"source": source, "product": product, "listings": [], "notice": "This source is not connected."}
        found = await search_offers(SearchQuery(text=product))
        offers = [offer for offer in found["offers"] if offer["merchant"]["channel"] == channel]
        return {
            "source": source,
            "product": product,
            "listings": cards_from_offers(offers),
            "notice": found.get("notice"),
        }

    find_listings.__name__ = f"find_listings_{slug}"
    find_listings.__doc__ = (
        f"Return {source} listings for one product. Each listing uses the shared card fields. Call once.\n\n"
        "Args:\n"
        "    product: Product or service the orchestrator is comparing."
    )
    return find_listings


async def _open_web(product: str, budget_s: float = BUDGET_S) -> dict[str, Any]:
    found = await search_open_web(product, budget_s)
    offers = found.get("offers") or []
    # El puntaje va en la oferta, que es la que trae el precio crudo; la tarjeta solo lo arrastra.
    await review_offers(product, offers)
    found["listings"] = cards_from_offers(offers)
    return found


async def find_listings_open_web(product: str) -> dict[str, Any]:
    """Return open-web listings from Firecrawl for one product. Call once.

    Args:
        product: Product or service the orchestrator is comparing.
    """
    return await _open_web(product)


# Apagadas hasta conectar cada fuente de verdad. El código queda; no se le ofrecen al orquestador.
PAUSED_TOOLS = [
    _listings_tool("the Meta Ad Library", None),
]


async def find_listings_importacion(product: str) -> dict[str, Any]:
    """Quote buying one product on Amazon and bringing it with a Miami courier. Call once.

    The tool decides if the product can be imported. Declined calls return no listings.

    Args:
        product: Product the orchestrator is comparing. Pass it unchanged.
    """
    return await quote_import(product)


# Los canales del registro de search_offers que el orquestador consulta, una tool por canal.
REGISTRY_CHANNELS: list[tuple[str, Channel]] = [
    ("Mercado Libre", "mercadolibre"),
    ("Facebook Marketplace", "facebook"),
    ("Instagram", "instagram"),
    ("TikTok", "tiktok"),
]

# La web abierta (Firecrawl), las redes (Apify) y traerlo de USA. Instagram, TikTok y Amazon
# responden vacío mientras no haya APIFY_TOKEN. El actor de Amazon tarda más que el plazo
# de search_offers: esta tool lo espera aparte y, si no alcanza, la siguiente búsqueda lo lee.
SOURCE_TOOLS = [
    find_listings_open_web,
    *(_listings_tool(source, channel) for source, channel in REGISTRY_CHANNELS),
    find_listings_importacion,
]


async def find_all_listings(query: SearchQuery, open_web_budget_s: float = BUDGET_S) -> dict[str, Any]:
    """Lo que juntan las tools del orquestador en un turno, sin el modelo y con la confianza cerrada.

    Es la búsqueda del MCP: quien pregunta ya es un asistente de IA y no necesita al orquestador,
    pero sí las mismas fuentes y el mismo puntaje que ve la persona en WhatsApp. El registro corre
    una sola vez y se reparte por los mismos canales que filtran las tools.

    La zona solo filtra el registro: casi ninguna tienda web dice su ciudad. Si falla toda la web
    abierta, failedSources dice firecrawl; si falla una tienda, firecrawl:<dominio>.
    """
    web, registry, imported = await asyncio.gather(
        _open_web(query.text, open_web_budget_s), search_offers(query), quote_import(query.text)
    )
    channels = {channel for _source, channel in REGISTRY_CHANNELS}
    offers = [offer for offer in registry["offers"] if offer["merchant"]["channel"] in channels]
    listings = web["listings"] + cards_from_offers(offers) + (imported.get("listings") or [])

    failed = registry["failedSources"] + (["firecrawl"] if web.get("failed") else web.get("failedSources", []))
    notices = [registry.get("notice"), web.get("notice") if web.get("offers") else None]
    response: dict[str, Any] = {"query": query.text, "listings": close_listings(listings), "failedSources": failed}
    if any(notices):
        response["notice"] = " ".join(notice for notice in notices if notice)
    return response
