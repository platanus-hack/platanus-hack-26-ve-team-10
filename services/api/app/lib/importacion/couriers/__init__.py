"""Un cotizador por courier. El que no responde se omite; no se inventa su tarifa."""

import asyncio
import logging

from app.lib.importacion.couriers.client import PageClient, Shipment
from app.lib.importacion.couriers.http import HttpPages
from app.lib.importacion.couriers.liberty import quote_liberty
from app.lib.importacion.couriers.zoom import quote_zoom
from app.lib.types import CourierQuote

log = logging.getLogger("prais.courier")

QUOTE_TIMEOUT_S = 8


async def quote_couriers(shipment: Shipment, client: PageClient | None = None) -> list[CourierQuote]:
    pages = client or HttpPages()
    found = await asyncio.gather(
        _one("zoom", quote_zoom, shipment, pages),
        _one("liberty", quote_liberty, shipment, pages),
    )
    return [quote for quote in found if quote is not None]


async def _one(name: str, quote, shipment: Shipment, client: PageClient) -> CourierQuote | None:
    try:
        return await asyncio.wait_for(quote(shipment, client), QUOTE_TIMEOUT_S)
    except Exception as error:  # noqa: BLE001  un courier que falla no tumba al otro
        log.info("courier %s no cotizó: %s", name, error)
        return None
