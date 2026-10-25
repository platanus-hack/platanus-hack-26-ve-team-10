import asyncio
import re
from typing import Any

from app.lib import contract_build
from app.lib.contracts import Merchant as ContractMerchant
from app.lib.contracts import Offer as ContractOffer
from app.lib.contracts import (
    TrustScore,
)
from app.lib.prices import format_money, to_usd, trust_score
from app.lib.rate import get_rate
from app.lib.sources import sources
from app.lib.types import (
    ExchangeRate,
    Merchant,
    Offer,
    SearchQuery,
    Source,
    SourceResult,
)

SOURCE_TIMEOUT_S = 8


def _same_zone(merchant: Merchant, zone: str | None) -> bool:
    return not zone or zone.lower() in merchant.zone.lower()


async def _run_source(source: Source, query: SearchQuery) -> SourceResult | None:
    try:
        return await asyncio.wait_for(source.search(query), SOURCE_TIMEOUT_S)
    except Exception:  # noqa: BLE001  la fuente falló o tardó demasiado: la búsqueda sigue sin ella
        return None


_USED = re.compile(r"\b(usado|usada|second\s*hand|de\s+uso)\b")
_REFURBISHED = re.compile(r"\b(reacondicionado|refurbished|renewed)\b")
_HANDLE_OF: dict[str, str] = {"instagram": "instagram", "tiktok": "tiktok", "facebook": "facebook"}




def _contract(
    card: dict[str, Any],
    offer: Offer,
    merchant: Merchant,
    trust: TrustScore,
    rate: ExchangeRate,
    product: str,
) -> tuple[ContractOffer, ContractMerchant]:
    """Lo mismo que arma la web abierta: el armador vive en un solo sitio."""
    return contract_build.build(
        merchant_id=merchant.id,
        name=merchant.name,
        channel=merchant.channel,
        merchant_url=merchant.url,
        zone=merchant.zone,
        delivers=merchant.delivers,
        title=offer.title,
        url=offer.url,
        seen_at=offer.seen_at,
        price=offer.price,
        price_usd=card["priceUsd"],
        rate=rate,
        product=product,
        trust=trust,
        condition=offer.condition,
    )


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
                found.append((source.id, offer, merchant, result.trust.get(offer.merchant_id)))

    offers = []
    for source_id, offer, merchant, trust in found:
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
        # La fuente que puntúa su canal manda además el contrato. close_listings (en el agente)
        # cierra esos puntajes con la mediana de todas las fuentes; el resto sigue con el entero.
        if trust is not None:
            contract_offer, contract_merchant = _contract(offers[-1], offer, merchant, trust, rate, query.text)
            offers[-1]["contractOffer"] = contract_offer.model_dump(mode="json", by_alias=True)
            offers[-1]["contractMerchant"] = contract_merchant.model_dump(mode="json", by_alias=True)
    offers.sort(key=lambda o: o["priceUsd"] if o["priceUsd"] is not None else float("inf"))

    response: dict[str, Any] = {"query": query.text, "failedSources": failed_sources, "offers": offers}
    if any(offer["example"] for offer in offers):
        response["notice"] = "Incluye datos de ejemplo: no todas las fuentes reales están conectadas."
    return response


def _js_number(value: float) -> str:
    # 200.0 se escribe "200", como en JavaScript.
    return str(int(value)) if float(value).is_integer() else str(value)
