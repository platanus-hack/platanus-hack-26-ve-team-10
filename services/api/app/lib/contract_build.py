"""Arma la oferta y el comercio del contrato. Lo usan todas las fuentes que puntúan su canal.

Vive aparte de search.py porque la web abierta no pasa por el registro de fuentes y search.py ya
la importa: si el armador viviera ahí, el import sería circular. El puntaje lo trae cada fuente;
aquí solo se le pone forma, y el precio, la tasa y la conversión salen de lo que ya calculó quien
llama, que es el único lugar donde viven.
"""

import re
from typing import Any

from app.lib.contracts import (
    CanonicalProduct,
    Condition,
    Location,
    MerchantLink,
    Money,
    Offer,
    RateRef,
    TrustScore,
)
from app.lib.contracts import Merchant as ContractMerchant
from app.lib.sources.firecrawl import plain
from app.lib.trust import entity_id_for
from app.lib.types import ExchangeRate
from app.lib.types import Money as PriceMoney

_USED = re.compile(r"\b(usado|usada|second\s*hand|de\s+uso|pre\s*-?\s*owned|preowned|seminuevo)\b")
_REFURBISHED = re.compile(r"\b(reacondicionado|refurbished|renewed)\b")
# El canal cuyo id de comercio es un handle o un dominio: sirve para unir al mismo vendedor.
_LINK_OF: dict[str, str] = {
    "instagram": "instagram",
    "tiktok": "tiktok",
    "facebook": "facebook",
    "web": "dominio",
}


def product_key(text: str) -> str:
    """Agrupa las ofertas comparables para la mediana. Todas las fuentes buscan el mismo texto."""
    return "-".join(plain(text).split()) or "sin-producto"


def condition_of(declared: Condition | None, *texts: str) -> Condition:
    """Lo que diga la fuente manda: ella vio la publicación entera, aquí llega solo el título."""
    if declared is not None:
        return declared
    joined = plain(" ".join(texts))
    if _REFURBISHED.search(joined):
        return "reacondicionado"
    if _USED.search(joined):
        return "usado"
    return "nuevo"


def build(
    *,
    merchant_id: str,
    name: str,
    channel: str,
    merchant_url: str,
    zone: str | None,
    delivers: bool | None,
    title: str,
    url: str,
    seen_at: str,
    price: PriceMoney | None,
    price_usd: float | None,
    rate: ExchangeRate,
    product: str,
    trust: TrustScore,
    condition: Condition | None = None,
    link_value: str | None = None,
) -> tuple[Offer, ContractMerchant]:
    """La oferta y el comercio del contrato, con el puntaje parcial que puso la fuente."""
    evidence = entity_id_for(url)
    kind = _LINK_OF.get(channel)
    value = link_value or merchant_id.split(":", 1)[-1]
    merchant = ContractMerchant(
        id=merchant_id,
        name=name,
        channel=channel,
        url=merchant_url,
        location=Location(city=zone) if zone else None,
        delivers=delivers,
        links=[MerchantLink(kind=kind, value=value)] if kind else [],
    )
    priced = price is not None
    offer = Offer(
        id=evidence,
        merchant_id=merchant_id,
        product=CanonicalProduct(key=product_key(product), label=product),
        condition=condition_of(condition, title, product),
        title=title,
        url=url,
        seen_at=seen_at,
        evidence_ids=[evidence],
        trust=trust,
        price=Money(amount=price.amount, currency=price.currency) if priced else None,
        price_kind="publicado" if priced else "al_dm",
        price_usd=price_usd,
        rate_used=(
            RateRef(source=rate.source, usd_to_ves=rate.usd_to_ves, observed_at=rate.observed_at)
            if priced and price.currency == "VES"
            else None
        ),
    )
    return offer, merchant


def as_card(offer: Offer, merchant: ContractMerchant) -> dict[str, Any]:
    """Las dos claves que close_listings busca en cada listado."""
    return {
        "contractOffer": offer.model_dump(mode="json", by_alias=True),
        "contractMerchant": merchant.model_dump(mode="json", by_alias=True),
    }
