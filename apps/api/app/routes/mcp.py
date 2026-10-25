from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from app.lib.search import search_all
from app.lib.types import SearchQuery

mcp_server = MCPServer("prais", version="0.2.0")

# Plazo de la web abierta (Firecrawl) dentro de una llamada al MCP. El agente le da 45 s; aquí
# se responde antes con lo que haya, porque el cliente es otro asistente que espera en vivo.
OPEN_WEB_BUDGET_S = 25


# Salida estructurada: el cliente recibe este schema como outputSchema. Los nombres van en
# camelCase, igual que la respuesta de search_offers (agents/contracts.md).
class Merchant(BaseModel):
    name: str
    channel: str = Field(description="web, mercadolibre, instagram, tiktok or facebook")
    zone: str | None = Field(default=None, description="City or area the merchant reports")
    delivers: bool | None = None
    trust: int | None = Field(default=None, description="0-100 seller trust score; null when not scored yet")


class Offer(BaseModel):
    title: str
    url: str
    price: str | None = Field(default=None, description="Price as the merchant published it; null means 'ask by DM'")
    priceUsd: float | None = Field(default=None, description="Price converted to USD")
    rate: str | None = Field(default=None, description="Exchange rate used, with its source and date, if converted")
    seenAt: str = Field(description="When the price was seen (ISO 8601)")
    source: str = Field(description="Where the offer came from: firecrawl, ejemplo…")
    example: bool = Field(default=False, description="True for made-up demo data: never present it as real")
    merchant: Merchant


class PriceSearch(BaseModel):
    query: str
    offers: list[Offer] = Field(description="Cheapest first; offers without a price go last")
    failedSources: list[str] = Field(
        default=[],
        description="Sources that failed or ran out of time. firecrawl:<domain> is an open-web shop whose pages "
        "were blocked, failed or timed out and gave no offers (listed once; dead links are not listed)",
    )
    notice: str | None = Field(default=None, description="Caveats to show the user")


# Las tools llaman directo a la búsqueda, sin el agente: quien pregunta ya es un asistente de IA.
@mcp_server.tool(
    name="search_prices",
    title="Search prices in Venezuela",
    description=(
        "Find where a product is cheapest in Venezuela across online shops and the main sales channels. "
        "Returns offers sorted by USD price, each with the price as published, the exchange rate used, when "
        "it was seen, its source and the merchant's 0-100 trust score. The zone filter does not apply to "
        "open-web offers (source firecrawl): their merchant.zone is the listing's city when the page shows "
        "one, otherwise 'Venezuela'. Takes up to ~30 seconds. Never invent prices: use only "
        "what this tool returns, and say so when an offer is example data."
    ),
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    structured_output=True,
)
async def search_prices(
    query: Annotated[str, Field(description="Product with brand and size or model, e.g. 'Harina PAN 1 kg'")],
    zone: Annotated[str | None, Field(description="City or area in Venezuela")] = None,
    needs_delivery: bool | None = None,
) -> PriceSearch:
    result = await search_all(SearchQuery(text=query, zone=zone, needs_delivery=needs_delivery), OPEN_WEB_BUDGET_S)
    return PriceSearch.model_validate(result)


# Sin sesiones (cada request es independiente) y respuesta JSON, como el servidor de Fastify.
# La app se monta en la raíz de main.py, y la ruta del endpoint es /mcp. Cloud Run pone su propio
# Host, así que se apaga la protección contra DNS rebinding, pensada para servidores locales.
mcp_app = mcp_server.streamable_http_app(
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
