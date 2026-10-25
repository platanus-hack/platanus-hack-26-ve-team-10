import asyncio
import base64
from pathlib import Path
from typing import Annotated

from mcp.server.apps import Apps, ResourceCsp
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, Icon, TextContent, ToolAnnotations
from pydantic import AliasChoices, BaseModel, Field

from app.lib.rate import get_rate
from app.lib.search import search_all
from app.lib.types import SearchQuery

# Open-web budget inside one MCP call. The agent allows 45s. A listing is now one
# Firecrawl read, so 25s still covers the search plus that read. The client is
# another assistant waiting live, so this stays below the agent's 45s.
OPEN_WEB_BUDGET_S = 25

# Widget de ofertas (MCP Apps): Claude y ChatGPT lo muestran dentro del chat. Los assets son copias
# de docs/design-system/assets, porque la imagen de la API solo lleva apps/api/app.
UI_DIR = Path(__file__).resolve().parent.parent / "ui"
OFERTAS_URI = "ui://usaprais/ofertas.html"
SUMMARY_OFFERS = 10


def _data_uri(name: str, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode((UI_DIR / name).read_bytes()).decode()}"


def _widget_html() -> str:
    html = (UI_DIR / "ofertas.html").read_text(encoding="utf-8")
    for state in ("pensando", "ganga"):
        svg = (UI_DIR / f"prais-{state}-circulo.svg").read_text(encoding="utf-8")
        html = html.replace(f"__PRAIS_{state.upper()}__", svg)
    return html


ICONS = [
    Icon(src=_data_uri("usaprais.png", "image/png"), mime_type="image/png", sizes=["128x128"]),
    Icon(src=_data_uri("usaprais.svg", "image/svg+xml"), mime_type="image/svg+xml", sizes=["any"]),
]

INSTRUCTIONS = """usaprais finds where a product is cheapest in Venezuela, across online shops and the main sales channels.

- Use search_prices for any question about the price of a product sold in Venezuela.
- Before searching, make sure you know the product with its brand and model or size. If the request is vague ("un carro", "un teléfono"), ask one short question first.
- Answer in the user's language (usually Spanish, with "tú").
- Lead with the verdict: the cheapest price in USD and the shop that sells it. Then at most two alternatives.
- Every price you mention goes with its shop and when it was seen. If it was converted from bolívares, also the rate used.
- Never invent or estimate prices, shops, rates or trust scores: use only what search_prices returns. Offers with example: true are demo data; say so.
- An offer without a price is "precio al DM". If the cheapest shop has low trust or no score, say so and suggest how to stay safe.
- When the offers widget is shown in the chat, do not repeat the whole list: give the verdict in one or two sentences."""


# Salida estructurada: el cliente recibe este schema como outputSchema y el widget la pinta. Los
# nombres van en camelCase, igual que la respuesta de search_offers (docs/contracts.md).
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
    imageUrl: str | None = Field(
        default=None, validation_alias=AliasChoices("imageUrl", "image_url"), description="Product photo, if any"
    )
    reviews: str | None = Field(default=None, description="Recent comments on the merchant, if known")
    merchant: Merchant


class ExchangeRate(BaseModel):
    source: str = Field(description="Where the rate comes from")
    usdToVes: float = Field(description="Bolívares per US dollar")
    observedAt: str = Field(description="When the rate was observed (ISO 8601)")


class PriceSearch(BaseModel):
    query: str
    offers: list[Offer] = Field(description="Cheapest first; offers without a price go last")
    failedSources: list[str] = Field(
        default=[],
        description="Sources that failed or ran out of time. firecrawl:<domain> is an open-web shop whose pages "
        "were blocked, failed or timed out and gave no offers (listed once; dead links are not listed)",
    )
    notice: str | None = Field(default=None, description="Caveats to show the user")
    exchangeRate: ExchangeRate | None = Field(default=None, description="Rate used to show prices in bolívares")


def _summary(result: PriceSearch) -> str:
    """Texto para el modelo y para los clientes sin widget: el veredicto y las ofertas, con fuente y fecha."""
    priced = [o for o in result.offers if o.priceUsd is not None]
    unpriced = len(result.offers) - len(priced)
    if not result.offers:
        lines = [f'"{result.query}": no offers found. Suggest searching with the exact brand and model.']
    elif priced:
        cheapest, priciest = priced[0].priceUsd, priced[-1].priceUsd
        lines = [f'"{result.query}": {len(priced)} offers with a price, from USD {cheapest:g} to USD {priciest:g}.']
    else:
        lines = [f'"{result.query}": {len(result.offers)} offers, none publishes a price.']
    for i, o in enumerate(priced[:SUMMARY_OFFERS], 1):
        flags = [o.merchant.channel]
        if o.merchant.zone and o.merchant.zone != "Venezuela":
            flags.append(o.merchant.zone)
        flags.append(f"trust {o.merchant.trust}" if o.merchant.trust is not None else "no trust score")
        if o.example:
            flags.append("EXAMPLE DATA")
        price = f"USD {o.priceUsd:g}" + (f" (published {o.price}, rate {o.rate})" if o.rate else "")
        lines.append(f"{i}. {price} · {o.merchant.name} ({', '.join(flags)}) · {o.title} · seen {o.seenAt} · {o.url}")
    if len(priced) > SUMMARY_OFFERS:
        lines.append(f"…and {len(priced) - SUMMARY_OFFERS} more with a price.")
    if unpriced:
        lines.append(f"{unpriced} offers without a published price (ask by DM).")
    if result.failedSources:
        lines.append(f"Did not respond: {', '.join(result.failedSources)}.")
    if result.notice:
        lines.append(f"Notice: {result.notice}")
    return "\n".join(lines)


apps = Apps()


# Las tools llaman directo a la búsqueda, sin el agente: quien pregunta ya es un asistente de IA.
@apps.tool(
    resource_uri=OFERTAS_URI,
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
    icons=ICONS,
    structured_output=True,
)
async def search_prices(
    query: Annotated[str, Field(description="Product with brand and size or model, e.g. 'Harina PAN 1 kg'")],
    zone: Annotated[str | None, Field(description="City or area in Venezuela")] = None,
    needs_delivery: bool | None = None,
) -> Annotated[CallToolResult, PriceSearch]:
    found, rate = await asyncio.gather(
        search_all(SearchQuery(text=query, zone=zone, needs_delivery=needs_delivery), OPEN_WEB_BUDGET_S),
        get_rate(),
    )
    result = PriceSearch.model_validate(
        found
        | {"exchangeRate": {"source": rate.source, "usdToVes": rate.usd_to_ves, "observedAt": rate.observed_at}}
    )
    return CallToolResult(
        content=[TextContent(type="text", text=_summary(result))],
        structured_content=result.model_dump(mode="json"),
    )


apps.add_html_resource(
    OFERTAS_URI,
    _widget_html(),
    name="ofertas",
    title="Ofertas de usaprais",
    description="Ranking de ofertas de search_prices, del precio más bajo al más alto",
    # Solo las fuentes de Google Fonts: las fotos de las tiendas vienen de dominios que no se conocen
    # de antemano, así que el widget las muestra solo si el host las deja cargar.
    csp=ResourceCsp(resource_domains=["https://fonts.googleapis.com", "https://fonts.gstatic.com"]),
    prefers_border=False,
)

mcp_server = MCPServer(
    "usaprais",
    title="usaprais",
    description="Compara precios en Venezuela y dice dónde está el más barato.",
    instructions=INSTRUCTIONS,
    website_url="https://usaprais.com",
    icons=ICONS,
    version="0.3.0",
    extensions=[apps],
)


# Sin sesiones (cada request es independiente) y respuesta JSON, como el servidor de Fastify.
# La app se monta en la raíz de main.py, y la ruta del endpoint es /mcp. Cloud Run pone su propio
# Host, así que se apaga la protección contra DNS rebinding, pensada para servidores locales.
mcp_app = mcp_server.streamable_http_app(
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
