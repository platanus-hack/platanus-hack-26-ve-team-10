from dataclasses import dataclass
from typing import Literal, Protocol

Currency = Literal["USD", "VES"]
Channel = Literal["instagram", "tiktok", "web", "mercadolibre", "facebook", "amazon"]


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
class Offer:
    merchant_id: str
    title: str  # como lo publica la fuente
    url: str
    price: Money | None  # None cuando la fuente no publica el precio ("precio al DM")
    seen_at: str  # ISO 8601


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


class Source(Protocol):
    id: str  # "firecrawl", "apify-instagram", "mercadolibre"…
    enabled: bool  # normalmente: si su API key está en el entorno

    # La búsqueda le da 8 s (asyncio.wait_for): si tarda más se cancela y sigue sin esta fuente.
    async def search(self, query: SearchQuery) -> SourceResult: ...
