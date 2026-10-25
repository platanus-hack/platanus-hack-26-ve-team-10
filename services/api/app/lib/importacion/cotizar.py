"""Flujo de la tool: Amazon, filtros, couriers y una sola oferta.

El orquestador solo decide si llama. Si llama de más, esto declina sin cotizar.
`price_usd` es el total puesto en Venezuela, no el precio de Amazon.
"""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from app.agents.listing import ListingCard
from app.lib.contracts import CanonicalProduct
from app.lib.contracts import Landed as ContractLanded
from app.lib.contracts import Merchant as ContractMerchant
from app.lib.contracts import Money as ContractMoney
from app.lib.contracts import Offer as ContractOffer
from app.lib.importacion.couriers import quote_couriers
from app.lib.importacion.couriers.client import Shipment
from app.lib.importacion.factibilidad import (
    MAX_LB,
    blocked,
    coarse_estimate,
    worth_quoting,
)
from app.lib.importacion.landed import compose, quote_total
from app.lib.importacion.peso import billable
from app.lib.prices import format_money
from app.lib.sources.amazon import (
    amazon_enabled,
    asin_median,
    choose_listing,
    search_amazon,
)
from app.lib.sources.firecrawl import plain
from app.lib.trust import score_import
from app.lib.types import Money

_NOT_CONNECTED = "Amazon no está conectado."
_NO_PRODUCT = "Amazon no trajo ese producto."
_NO_COURIER = "Ningún courier cotizó."
_TOO_HEAVY = "No se cotiza: no entra en un casillero aéreo."
_NOT_WORTH = "Traerlo no se acerca al mejor precio local, así que no se cotiza."
_QUOTED = (
    "Estimado para comprarlo en Amazon y traerlo con un casillero en Miami. Hace falta tarjeta internacional."
)


async def quote_import(
    product: str,
    *,
    runner=None,
    client=None,
    best_local_usd: float | None = None,
) -> dict[str, Any]:
    reason = blocked(product)
    if reason:
        return _empty(product, reason)
    if runner is None and not amazon_enabled():
        return _empty(product, _NOT_CONNECTED)

    listings = await search_amazon(product, runner)
    allowed = []
    blocked_title = None
    for listing in listings:
        why = blocked(listing.title)
        if why:
            blocked_title = why
            continue
        allowed.append(listing)
    chosen = choose_listing(allowed)
    if chosen is None:
        return _empty(product, blocked_title or _NO_PRODUCT)

    weight = billable(f"{product} {chosen.title}", chosen.rows)
    if weight.lb > MAX_LB:
        return _empty(product, _TOO_HEAVY)
    estimate = coarse_estimate(chosen.price_usd, weight.lb)
    if not worth_quoting(estimate, best_local_usd):
        return _empty(product, _NOT_WORTH)

    quotes = await quote_couriers(Shipment(weight.lb, chosen.price_usd), client)
    landed = compose(
        chosen.price_usd,
        weight.lb,
        weight.source,
        quotes,
        chosen.asin,
        asin_median(allowed, chosen.asin),
    )
    if landed is None:
        return _empty(product, _NO_COURIER)

    best = min(quotes, key=lambda quote: (quote_total(quote), quote.courier_id))
    trust = score_import(
        amazon_score=95 if chosen.fulfillment == "amazon" else None,
        weight_source=weight.source,
        tax_source=landed.tax_source,
        eta_days_min=landed.eta_days_min,
        eta_days_max=landed.eta_days_max,
    )
    merchant_id = f"amz:{chosen.seller_id or 'amazon'}"
    moment = datetime.now(UTC)
    contract = ContractOffer(
        id=f"import:{chosen.asin}:{best.courier_id}",
        merchant_id=merchant_id,
        fulfiller_id=best.courier_id,
        product=CanonicalProduct(key=plain(product)[:120] or "producto", label=product),
        condition=_condition(chosen.title),
        title=chosen.title,
        url=chosen.url,
        seen_at=moment,
        evidence_ids=[f"amazon:{chosen.asin}", f"courier:{best.courier_id}"],
        trust=trust,
        image_url=chosen.image_url,
        price=ContractMoney(amount=landed.total_usd, currency="USD"),
        price_kind="estimado",
        price_usd=landed.total_usd,
        landed=ContractLanded.model_validate(asdict(landed)),
    )
    merchant = ContractMerchant(
        id=merchant_id,
        name=chosen.seller_name,
        channel="amazon",
        url=chosen.seller_url,
        delivers=False,
    )
    card = ListingCard(
        title=chosen.title,
        seller=best.courier_name,
        channel="importacion",
        url=chosen.url,
        price=format_money(Money(landed.total_usd, "USD")),
        image_url=chosen.image_url,
        ships=True,
        price_usd=landed.total_usd if not float(landed.total_usd).is_integer() else int(landed.total_usd),
        price_kind="estimado",
        fulfiller=best.courier_name,
        landed=asdict(landed),
    ).model_dump()
    card["contractOffer"] = contract.model_dump(mode="json")
    card["contractMerchant"] = merchant.model_dump(mode="json")
    return {"source": "importacion", "product": product, "listings": [card], "notice": _QUOTED}


def _empty(product: str, notice: str) -> dict[str, Any]:
    return {"source": "importacion", "product": product, "listings": [], "notice": notice}


def _condition(title: str) -> str:
    folded = plain(title)
    if "reacondicion" in folded or "renewed" in folded:
        return "reacondicionado"
    if "usado" in folded or "used" in folded:
        return "usado"
    return "nuevo"
