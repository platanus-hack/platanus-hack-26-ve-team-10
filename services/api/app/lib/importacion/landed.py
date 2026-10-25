"""Arma el costo puesto en Venezuela con el courier más barato.

Cada cifra que entra ya trae origen. La tabla de impuestos está en cero hasta
que se confirme (punto abierto 5): un cero de esa tabla no es un arancel inventado.
"""

import math
from typing import Literal

from app.lib.types import CourierQuote, Landed

# Tasa de la tabla cuando el courier no cotiza el impuesto. Sin confirmar, es 0.
TAX_TABLE_RATE = 0.0
_REQUIREMENTS = ("casillero en Miami", "tarjeta internacional")


def usd(value: float) -> float:
    rounded = math.floor(value * 100 + 0.5) / 100
    return int(rounded) if float(rounded).is_integer() else rounded


def compose(
    product_usd: float,
    billable_lb: float,
    weight_source: Literal["listing", "tabla"],
    quotes: list[CourierQuote],
    asin: str,
    asin_median_usd: float | None,
) -> Landed | None:
    if not quotes:
        return None
    best = min(quotes, key=lambda quote: (quote_total(quote), quote.courier_id))
    tax = 0.0 if best.includes_tax else best.tax_usd
    product = usd(product_usd)
    total = usd(product + best.freight_usd + tax + best.insurance_usd)
    return Landed(
        product_usd=product,
        freight_usd=best.freight_usd,
        tax_usd=tax,
        insurance_usd=best.insurance_usd,
        total_usd=total,
        billable_lb=billable_lb,
        weight_source=weight_source,
        tax_source=best.tax_source,
        asin=asin,
        requirements=_REQUIREMENTS,
        quotes=tuple(quotes),
        eta_days_min=best.eta_days_min,
        eta_days_max=best.eta_days_max,
        asin_median_usd=asin_median_usd,
    )


def quote_total(quote: CourierQuote) -> float:
    tax = 0.0 if quote.includes_tax else quote.tax_usd
    return quote.freight_usd + tax + quote.insurance_usd
