from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:  # contracts.py importa Channel de aquí: la anotación va entre comillas
    from app.lib.contracts import TrustScore

Currency = Literal["USD", "VES"]
Channel = Literal["instagram", "tiktok", "web", "mercadolibre", "facebook", "amazon", "importacion"]
PriceKind = Literal["publicado", "al_dm", "estimado"]
WeightSource = Literal["listing", "tabla"]
TaxSource = Literal["cotizado", "tabla"]
QuoteSource = Literal["cotizador", "tabla"]


@dataclass(frozen=True)
class Money:
    amount: float
    currency: Currency


@dataclass(frozen=True)
class ExchangeRate:
    source: str  # de dónde salió la tasa: "BCV", "paralelo"...
    usd_to_ves: float
    observed_at: str  # ISO 8601


@dataclass(frozen=True)
class Merchant:
    id: str
    name: str
    channel: Channel
    url: str
    zone: str
    delivers: bool
    followers: int | None = None
    comments: int | None = None  # comentarios recientes en sus publicaciones
    response_time_min: int | None = None  # minutos en responder un mensaje


@dataclass(frozen=True)
class CourierQuote:
    """Una cotización. `source` es el flete; `tax_source` es el impuesto, que puede no coincidir."""

    courier_id: str
    courier_name: str
    freight_usd: float
    tax_usd: float
    insurance_usd: float
    includes_tax: bool
    quoted_at: str  # ISO 8601
    source: QuoteSource
    tax_source: TaxSource
    eta_days_min: int | None = None
    eta_days_max: int | None = None


@dataclass(frozen=True)
class Landed:
    """Costo puesto en Venezuela. `total_usd` es lo que compite en el ranking."""

    product_usd: float
    freight_usd: float
    tax_usd: float
    insurance_usd: float
    total_usd: float
    billable_lb: float
    weight_source: WeightSource
    tax_source: TaxSource
    asin: str
    requirements: tuple[str, ...] = ()
    quotes: tuple[CourierQuote, ...] = ()
    eta_days_min: int | None = None
    eta_days_max: int | None = None
    asin_median_usd: float | None = None


@dataclass(frozen=True)
class Offer:
    merchant_id: str
    title: str  # como lo publica la fuente
    url: str
    price: Money | None  # None cuando la fuente no publica el precio ("precio al DM")
    seen_at: str  # ISO 8601
    price_kind: PriceKind = "publicado"
    fulfiller_id: str | None = None  # el courier, solo en channel "importacion"
    landed: Landed | None = None


# ── Contrato de las fuentes ──────────────────────────────────────────────────────────────
# Cada fuente (Firecrawl, Apify, Mercado Libre…) es un archivo en sources/ con un objeto que
# cumple Source y se registra en sources/__init__.py. La búsqueda las llama en paralelo, junta
# lo que devuelven y se encarga de filtrar, convertir y ordenar: la fuente solo trae datos.


@dataclass(frozen=True)
class SearchQuery:
    text: str  # lo que busca la persona, ej. "Harina PAN 1 kg"
    zone: str | None = None
    needs_delivery: bool | None = None


@dataclass(frozen=True)
class SourceResult:
    offers: list[Offer]
    merchants: list[Merchant]  # los comercios de esas ofertas; el id va con prefijo de la fuente, ej. "ig:bodegon"
    # Puntaje de confianza por comercio, en el contrato de trust.py y siempre en etapa "parcial":
    # la fuente mide solo lo que ve su canal y el agregador cierra. Una fuente que todavía no
    # puntúa su canal lo deja vacío y su oferta sigue mostrando el entero provisional.
    trust: "dict[str, TrustScore]" = field(default_factory=dict)


class Source(Protocol):
    id: str  # "firecrawl", "apify-instagram", "mercadolibre"…
    enabled: bool  # normalmente: si su API key está en el entorno

    # La búsqueda le da 8 s (asyncio.wait_for): si tarda más se cancela y sigue sin esta fuente.
    async def search(self, query: SearchQuery) -> SourceResult: ...
