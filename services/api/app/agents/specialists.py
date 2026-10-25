"""Una tool por fuente. Devuelve el listado ya armado: ningún modelo lo reescribe."""

from typing import Any

from app.agents.listing import cards_from_offers
from app.agents.open_web_trust import review_listings
from app.lib.importacion.cotizar import quote_import
from app.lib.search import search_offers
from app.lib.sources.firecrawl import search_open_web
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


async def find_listings_open_web(product: str) -> dict[str, Any]:
    """Return open-web listings from Firecrawl for one product. Call once.

    Args:
        product: Product or service the orchestrator is comparing.
    """
    found = await search_open_web(product)
    listings = cards_from_offers(found.get("offers") or [])
    review_listings(product, listings)
    found["listings"] = listings
    return found


# Apagadas hasta conectar cada fuente de verdad. El código queda; no se le ofrecen al orquestador.
PAUSED_TOOLS = [
    _listings_tool("the Meta Ad Library", None),
    _listings_tool("Mercado Libre", "mercadolibre"),
    # Facebook Marketplace necesita un actor de pago y proxy residencial: ver docs/sources.md.
    _listings_tool("Facebook Marketplace", "facebook"),
]


async def find_listings_importacion(product: str) -> dict[str, Any]:
    """Quote buying one product on Amazon and bringing it with a Miami courier. Call once.

    The tool decides if the product can be imported. Declined calls return no listings.

    Args:
        product: Product the orchestrator is comparing. Pass it unchanged.
    """
    return await quote_import(product)


# La web abierta (Firecrawl), las redes (Apify) y traerlo de USA. Instagram, TikTok y Amazon
# responden vacío mientras no haya APIFY_TOKEN. El actor de Amazon tarda más que el plazo
# de search_offers: esta tool lo espera aparte y, si no alcanza, la siguiente búsqueda lo lee.
SOURCE_TOOLS = [
    find_listings_open_web,
    _listings_tool("Instagram", "instagram"),
    _listings_tool("TikTok", "tiktok"),
    find_listings_importacion,
]
