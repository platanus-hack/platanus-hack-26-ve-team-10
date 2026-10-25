"""La llamada de confianza de una oferta de la web abierta.

Sigue las banderas rojas de resources/website_trust_score.py que se pueden ver
en el listado que ya trajo la búsqueda: precio contra las demás ofertas,
dominio que imita una marca, y un título que es un accesorio o una copia.
No inventa el puntaje estricto (dominio, RIF, políticas, Safe Browsing).
"""

import re
import statistics
from typing import Any
from urllib.parse import urlparse

_ACCESSORY = re.compile(
    r"\b(fundas?|carcasas?|forros?|cases?|covers?|replicas?|réplicas?|clones?|copias?|imitaciones?|fakes?)\b",
    re.IGNORECASE,
)
# Nombre que se dice, dominios de esa marca, y cómo aparece el nombre dentro de un dominio.
_BRANDS = (
    ("Apple", ("apple.com",), ("apple", "iphone")),
    ("Samsung", ("samsung.com",), ("samsung", "galaxy")),
    ("Xiaomi", ("xiaomi.com", "mi.com"), ("xiaomi", "redmi")),
    ("Google", ("google.com",), ("google", "pixel")),
    ("Motorola", ("motorola.com",), ("motorola",)),
    ("Huawei", ("huawei.com",), ("huawei",)),
)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.").lower()


def _flat(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _price(card: dict[str, Any]) -> float | None:
    amount = card.get("price_usd")
    if isinstance(amount, (int, float)) and amount > 0:
        return float(amount)
    return None


def _impersonates(host: str, product: str) -> str | None:
    flat_host = _flat(host)
    flat_product = _flat(product)
    for name, domains, marks in _BRANDS:
        if not any(mark in flat_host for mark in marks):
            continue
        if not any(mark in flat_product for mark in marks):
            continue
        if any(host == domain or host.endswith(f".{domain}") for domain in domains):
            continue
        return name
    return None


def review_one(product: str, card: dict[str, Any], others: list[float]) -> dict[str, Any]:
    """Un listado. `others` son los precios en USD de las demás ofertas de la misma búsqueda."""
    reasons: list[str] = []
    cautions: list[str] = []
    title = str(card.get("title") or "")
    url = str(card.get("url") or "")
    if _ACCESSORY.search(title) and not _ACCESSORY.search(product):
        reasons.append("Es una funda, una copia o un accesorio, no el producto pedido")
    brand = _impersonates(_host(url), product)
    if brand:
        reasons.append(f"El dominio imita a {brand}")
    price = _price(card)
    if price is not None and others:
        middle = statistics.median(others)
        if middle > 0 and price <= middle * 0.5:
            reasons.append("Precio más de 50% bajo las otras ofertas")
    if url.startswith("http://"):
        cautions.append("La página no usa https")
    if reasons:
        return {"verdict": "riesgosa", "reasons": reasons}
    if cautions:
        return {"verdict": "precaucion", "reasons": cautions}
    return {"verdict": "sin_datos", "reasons": []}


def review_listings(product: str, listings: list[dict[str, Any]]) -> None:
    """Escribe trust_review en cada listado de la web abierta."""
    prices = [_price(card) for card in listings]
    for index, card in enumerate(listings):
        others = [amount for other, amount in enumerate(prices) if other != index and amount is not None]
        card["trust_review"] = review_one(product, card, others)
