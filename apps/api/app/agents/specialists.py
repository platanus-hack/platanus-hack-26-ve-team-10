"""Un especialista por fuente de la pizarra. Cada uno habla solo con el orquestador."""

import os
from typing import Any

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

from app.lib.search import search_offers
from app.lib.sources.firecrawl import search_open_web
from app.lib.types import Channel, SearchQuery

# El nombre del agente tiene que ser un identificador de Python. En el texto,
# los especialistas llaman al orquestador "root-agent", como en la plantilla.
ORCHESTRATOR_NAME = "root_agent"


class ProductInput(BaseModel):
    product: str = Field(
        description="Product or service the user wants to compare, decided by the orchestrator.",
    )


def _brief(source: str) -> str:
    return (
        f"You are a helpful assistant that helps source offer information from {source} "
        "and helps evaluate the fidelity of the seller, including the seller trust score. "
        'You report your findings only to the orchestrator "root-agent". '
        "Please find listing data for the product or service in the product field of your input. "
        "Call your listings tool with that product. Use only what the tool returns. "
        "merchant.trust is the seller trust score, from 0 to 100. If it is null, say the seller trust is not scored. "
        "Do not mention a trust score for the price. "
        "Do not invent listings, prices, sellers, scores, or reasons. "
        "If example is true, or the seller name contains 'ejemplo', say the listing is sample data. "
        "Reply only to the orchestrator, in at most 5 short lines. No greeting. "
        "One line per listing: title, price, seller, seller trust. "
        "If there are no listings, one line that says so."
    )


def _listings_tool(source: str, channel: Channel | None):
    slug = channel or "meta_ad_library"

    async def find_listings(product: str) -> dict[str, Any]:
        """Find listing data for the product on this source only.

        Args:
            product: Product or service the orchestrator is comparing.
        """
        if channel is None:
            return {
                "source": source,
                "product": product,
                "offers": [],
                "notice": "This source is not connected, so there are no listings.",
            }
        found = await search_offers(SearchQuery(text=product))
        offers = [offer for offer in found["offers"] if offer["merchant"]["channel"] == channel]
        return {
            "source": source,
            "product": product,
            "offers": offers,
            "notice": found.get("notice"),
        }

    find_listings.__name__ = f"find_listings_{slug}"
    return find_listings


async def find_listings_open_web(product: str) -> dict[str, Any]:
    """Search the open web in Venezuela with Firecrawl.

    Args:
        product: Product or service the orchestrator is comparing.
    """
    return await search_open_web(product)


def _specialist(name: str, source: str, channel: Channel | None, tool: Any = None) -> LlmAgent:
    brief = _brief(source)
    return LlmAgent(
        name=name,
        model=os.environ.get("PRAIS_MODEL", "gemini-flash-latest"),
        description=brief,
        instruction=brief,
        input_schema=ProductInput,
        include_contents="none",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        tools=[tool or _listings_tool(source, channel)],
    )


# La web abierta busca con Firecrawl. Meta Ads no tiene canal: la pizarra la dibuja
# y la fuente todavía no está conectada.
SPECIALISTS: list[LlmAgent] = [
    _specialist("open_web", "the open web", None, tool=find_listings_open_web),
    _specialist("meta_ad_library", "the Meta Ad Library", None),
    _specialist("mercado_libre", "Mercado Libre", "mercadolibre"),
    _specialist("facebook_marketplace", "Facebook Marketplace", "facebook"),
    _specialist("instagram", "Instagram", "instagram"),
    _specialist("tiktok", "TikTok", "tiktok"),
]
