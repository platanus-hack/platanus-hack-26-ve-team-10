import json
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field

from app.lib.search import search_offers
from app.lib.types import SearchQuery

mcp_server = MCPServer("prais", version="0.1.0")


# Las tools llaman directo a la búsqueda, sin el agente: quien pregunta ya es un asistente de IA.
@mcp_server.tool(
    name="search_prices",
    title="Search prices in Venezuela",
    description=(
        "Find where a product is cheapest in Venezuela across the main sales channels. Returns offers sorted "
        "by USD price, with the original price, the exchange rate used, when the price was seen and a 0-100 "
        "trust score for each merchant."
    ),
    annotations=ToolAnnotations(read_only_hint=True),
    structured_output=False,
)
async def search_prices(
    query: Annotated[str, Field(description="Product with brand and size or model, e.g. 'Harina PAN 1 kg'")],
    zone: Annotated[str | None, Field(description="City or area in Venezuela")] = None,
    needs_delivery: bool | None = None,
) -> str:
    result = await search_offers(SearchQuery(text=query, zone=zone, needs_delivery=needs_delivery))
    return json.dumps(result, indent=2, ensure_ascii=False)


# Sin sesiones (cada request es independiente) y respuesta JSON, como el servidor de Fastify.
# La app se monta en la raíz de main.py, y la ruta del endpoint es /mcp. Cloud Run pone su propio
# Host, así que se apaga la protección contra DNS rebinding, pensada para servidores locales.
mcp_app = mcp_server.streamable_http_app(
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
