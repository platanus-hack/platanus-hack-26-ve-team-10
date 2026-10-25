"""Peso facturable: el mayor entre el real y el volumétrico.

El divisor 166 es el de carga aérea (pulgadas cúbicas por libra). Si el listing
no trae peso, se usa la tabla por categoría y se declara. La tabla no es una
medida: es el respaldo.
"""

import re
from dataclasses import dataclass
from typing import Literal

from app.lib.sources.firecrawl import plain

# 166 in³ por libra. Zoom aéreo publica kilos físicos; este divisor solo entra
# cuando el listing trae medidas y el courier no publica el suyo.
CUBIC_INCHES_PER_LB = 166
INCHES_PER_CM = 2.54

WeightSource = Literal["listing", "tabla"]

# Libras, con un poco de empaque. La última no es un comodín silencioso:
# si nada coincide, el peso sale de aquí y la oferta dice que vino de la tabla.
_CATEGORIES: tuple[tuple[re.Pattern[str], float], ...] = (
    (re.compile(r"\b(iphone|pixel|smartphone)\b"), 0.8),
    (re.compile(r"\b(ipad|tablet)\b"), 1.5),
    (re.compile(r"\b(macbook|laptop|portatil|notebook)\b"), 4.5),
    (re.compile(r"\b(airpods|audifonos?)\b"), 0.6),
    (re.compile(r"\b(reloj|smartwatch)\b"), 0.4),
    (re.compile(r"\b(libro)\b"), 1.2),
    (re.compile(r"\b(zapatos|zapatillas)\b"), 2.5),
    (re.compile(r"\b(camisa|franela|vestido)\b"), 1.0),
)
_DEFAULT_LB = 2.0

_WEIGHT = re.compile(
    r"([0-9]+(?:[.,][0-9]+)?)\s*(pounds|pound|lbs|lb|ounces|ounce|oz|kilograms|kilogram|kg|grams|gram|g)\b",
    re.IGNORECASE,
)
_DIMS = re.compile(
    r"([0-9]+(?:[.,][0-9]+)?)\s*[x×]\s*([0-9]+(?:[.,][0-9]+)?)\s*[x×]\s*"
    r"([0-9]+(?:[.,][0-9]+)?)(?:\s*(inches|inch|in|cm|centimeters|mm))?",
    re.IGNORECASE,
)
_TO_LB = {"pound": 1, "pounds": 1, "lb": 1, "lbs": 1, "ounce": 1 / 16, "ounces": 1 / 16, "oz": 1 / 16,
          "kilogram": 2.2046226218, "kilograms": 2.2046226218, "kg": 2.2046226218,
          "gram": 0.0022046226218, "grams": 0.0022046226218, "g": 0.0022046226218}


@dataclass(frozen=True)
class Billable:
    lb: float
    source: WeightSource


def billable(text: str, rows: tuple[tuple[str, str], ...] = ()) -> Billable:
    weight = _weight_lb(rows)
    volume = _volumetric_lb(rows)
    if weight is None and volume is None:
        return Billable(_category_lb(text), "tabla")
    chosen = max(value for value in (weight, volume) if value is not None)
    return Billable(_pounds(chosen), "listing")


def _category_lb(text: str) -> float:
    folded = plain(text)
    for pattern, pounds in _CATEGORIES:
        if pattern.search(folded):
            return pounds
    return _DEFAULT_LB


def _weight_lb(rows: tuple[tuple[str, str], ...]) -> float | None:
    for name, value in rows:
        if name.strip().lower() not in _WEIGHT_LABELS:
            continue
        match = _WEIGHT.search(value)
        if not match:
            continue
        amount = _number(match.group(1))
        if amount is None:
            continue
        return amount * _TO_LB[match.group(2).lower()]
    return None


_WEIGHT_LABELS = {label for label in (
    "item weight", "product weight", "package weight", "peso del producto", "peso del articulo", "weight",
)}


def _volumetric_lb(rows: tuple[tuple[str, str], ...]) -> float | None:
    for name, value in rows:
        if name.strip().lower() not in _DIM_LABELS:
            continue
        match = _DIMS.search(value)
        if not match:
            continue
        sides = [_number(match.group(index)) for index in (1, 2, 3)]
        if any(side is None or side <= 0 for side in sides):
            continue
        unit = (match.group(4) or "in").lower()
        inches = [side * _to_inches(unit) for side in sides if side is not None]
        return (inches[0] * inches[1] * inches[2]) / CUBIC_INCHES_PER_LB
    return None


_DIM_LABELS = {
    "product dimensions",
    "item dimensions",
    "package dimensions",
    "dimensiones del producto",
    "dimensiones del articulo",
}


def _to_inches(unit: str) -> float:
    if unit in {"cm", "centimeters"}:
        return 1 / INCHES_PER_CM
    if unit == "mm":
        return 0.1 / INCHES_PER_CM
    return 1


def _number(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def _pounds(value: float) -> float:
    rounded = round(value + 1e-9, 2)
    return int(rounded) if rounded.is_integer() else rounded
