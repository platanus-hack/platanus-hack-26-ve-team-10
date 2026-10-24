import math

from app.lib.types import ExchangeRate, Merchant, Money

# Intl de es-VE escribe el código de la moneda, un espacio duro y el número con "." de miles.
_SYMBOLS = {"USD": "USD", "VES": "Bs.S"}


def _round_half_up(value: float) -> int:
    # Math.round de JavaScript redondea .5 hacia arriba; round() de Python, al par más cercano.
    return math.floor(value + 0.5)


def to_usd(price: Money, rate: ExchangeRate) -> float:
    usd = price.amount if price.currency == "USD" else price.amount / rate.usd_to_ves
    rounded = _round_half_up(usd * 100) / 100
    # 690.0 se escribe 690 en el JSON, como en JavaScript.
    return int(rounded) if rounded.is_integer() else rounded


def format_money(price: Money) -> str:
    number = f"{price.amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{_SYMBOLS[price.currency]} {number}"


# Puntaje de 0 a 100. Fórmula inicial: ajustarla cuando tengamos datos reales.
def trust_score(merchant: Merchant) -> int:
    score = 40.0
    if merchant.followers:
        score += min(25, math.log10(merchant.followers) * 6)
    if merchant.comments:
        score += min(15, merchant.comments / 10)
    if merchant.response_time_min is not None:
        score += 20 if merchant.response_time_min <= 15 else 10 if merchant.response_time_min <= 120 else 0
    return _round_half_up(min(100, score))
