"""Qué no se cotiza, y cuándo el estimado ni siquiera merece llamar al courier.

La lista es el punto de partida del issue: medicinas, perecederos, baterías
sueltas y víveres. Líquidos, armas y bultos que no entran en un casillero aéreo
tampoco. Un teléfono no es una batería suelta.
"""

import re

from app.lib.sources.firecrawl import plain

# El margen y la tarifa de referencia se afinan con corridas reales (punto abierto 2).
REFERENCE_USD_PER_LB = 8.0
MARGIN = 0.15
MAX_LB = 50

_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b(medicamento|medicina|farmaco|pastilla|antibiotico|ibuprofeno|acetaminofen"
            r"|paracetamol|amoxicilina|insulina|viagra)\b"
        ),
        "No se cotiza: es un medicamento.",
    ),
    (
        re.compile(r"\b(perecedero|carne|pollo|pescado|leche|queso|yogur|fruta|verdura|helado)\b"),
        "No se cotiza: es un perecedero.",
    ),
    (
        re.compile(r"\b(baterias?|pilas?|lithium battery|power bank)\b"),
        "No se cotiza: es una batería suelta.",
    ),
    (
        re.compile(r"\b(harina|arroz|azucar|caraotas?|lentejas?|viveres|comida|aceite de cocina)\b"),
        "No se cotiza: es un vívere.",
    ),
    (
        re.compile(r"\b(perfume|colonia|licor|whisky|vino|cerveza)\b"),
        "No se cotiza: es un líquido.",
    ),
    (
        re.compile(r"\b(armas?|pistola|rifle|municion)\b"),
        "No se cotiza: es un arma.",
    ),
    (
        re.compile(
            r"\b(nevera|lavadora|secadora|aire acondicionado|caucho|neumatico|mueble|sofa|colchon)\b"
        ),
        "No se cotiza: no entra en un casillero aéreo.",
    ),
)


def blocked(text: str) -> str | None:
    folded = plain(text)
    for pattern, reason in _RULES:
        if pattern.search(folded):
            return reason
    return None


def coarse_estimate(product_usd: float, billable_lb: float) -> float:
    return product_usd + billable_lb * REFERENCE_USD_PER_LB


def worth_quoting(estimate: float, best_local_usd: float | None, margin: float = MARGIN) -> bool:
    """Sin precio local se cotiza igual: importar puede ser la única opción."""
    if best_local_usd is None or best_local_usd <= 0:
        return True
    return estimate <= best_local_usd * (1 + margin)
