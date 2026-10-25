"""Casillero aéreo de Zoom, con la tarifa que publican en su página de precios.

No llamamos a CalcularTarifa: esa API está documentada para Canguro Azul y el
contrato del casillero internacional no está publicado. La página sí dice la
fórmula: cada ½ kg o fracción, sin mínimo, más la protección de encomienda.
"""

import math
import re
from datetime import UTC, datetime

from app.lib.importacion.couriers.client import PageClient, Shipment
from app.lib.importacion.landed import TAX_TABLE_RATE, usd
from app.lib.types import CourierQuote

ZOOM_URL = "https://casilleros.zoom.red/consulta-de-precios/"
_LB_PER_KG = 2.2046226218

# "Cada ½ Kg $6" o "Cada 1/2 Kg $6". El monto sale de la página, no de una constante.
_HALF_KG = re.compile(r"cada\s+(?:½|1/2)\s*kg\s*\$\s*([0-9]+(?:[.,][0-9]+)?)", re.IGNORECASE)
_LOW = re.compile(
    r"\$\s*([0-9]+(?:[.,][0-9]+)?)\s+adicional si el paquete es de bajo valor\s*"
    r"\(monto factura menos de \$\s*([0-9]+)",
    re.IGNORECASE,
)
_HIGH = re.compile(
    r"alto valor\s*\(monto factura m[aá]s de \$\s*[0-9]+\)\s*pagaras solo el\s*"
    r"([0-9]+(?:[.,][0-9]+)?)\s*%",
    re.IGNORECASE,
)


async def quote_zoom(shipment: Shipment, client: PageClient) -> CourierQuote | None:
    text = _visible(await client.get_text(ZOOM_URL))
    return zoom_from_text(text, shipment.billable_lb, shipment.product_usd)


def zoom_from_text(text: str, billable_lb: float, product_usd: float, now: datetime | None = None) -> CourierQuote | None:
    half = _HALF_KG.search(text)
    low = _LOW.search(text)
    high = _HIGH.search(text)
    if not half or not low or not high or billable_lb <= 0:
        return None
    rate = _amount(half.group(1))
    flat = _amount(low.group(1))
    ceiling = _amount(low.group(2))
    percent = _amount(high.group(1))
    if rate is None or flat is None or ceiling is None or percent is None or rate <= 0:
        return None
    halves = max(1, math.ceil((billable_lb / _LB_PER_KG) / 0.5 - 1e-9))
    freight = usd(halves * rate)
    insurance = usd(flat if product_usd < ceiling else product_usd * percent / 100)
    # La página no incluye el arancel. La tabla todavía no tiene tasa confirmada.
    tax = usd(product_usd * TAX_TABLE_RATE)
    moment = now or datetime.now(UTC)
    return CourierQuote(
        courier_id="cur:zoom",
        courier_name="Zoom",
        freight_usd=freight,
        tax_usd=tax,
        insurance_usd=insurance,
        includes_tax=False,
        quoted_at=moment.isoformat(),
        source="cotizador",
        tax_source="tabla",
    )


def _visible(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def _amount(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None
