import logging
import time

import httpx
from pydantic import BaseModel

from app.lib.types import ExchangeRate

log = logging.getLogger("prais.rate")

# Tasa con la que se convierten a USD los precios publicados en bolívares. Se usa la oficial del
# BCV, que es la legal y la que facturan las cadenas formales. La sirve dolarapi.com, sin API key.
# El paralelo está en el mismo sitio (/v1/dolares/paralelo) si alguna vez se decide cambiar.
RATE_URL = "https://ve.dolarapi.com/v1/dolares/oficial"

# El BCV publica una vez por día hábil: media hora de caché la mantiene al día sin pedirla en cada
# búsqueda. get_rate() corre dentro del mismo asyncio.gather que las fuentes, así que si dolarapi
# no responde se reintenta en un minuto, no en cada búsqueda.
CACHE_S = 30 * 60
RETRY_S = 60

# Las fuentes tienen 8 s. La tasa no puede ser el cuello de botella de una búsqueda.
TIMEOUT_S = 3

# Si dolarapi no responde se sigue usando la última tasa buena, por vieja que sea: su fecha viaja
# con cada precio convertido (regla 7), así que la persona ve de cuándo es. Esta es la semilla para
# el único caso sin última tasa buena: el proceso acaba de arrancar y la API está caída. Es una
# tasa real con su fecha real, y la fuente dice que no se pudo confirmar.
SEED = ExchangeRate(
    source="última tasa oficial del BCV conocida",
    usd_to_ves=886.2271,
    observed_at="2026-10-23T00:00:00-04:00",
)

_cached = SEED
_until = 0.0


# Lo que publica dolarapi. En Venezuela compra y venta vienen en null: el valor está en promedio.
class _Published(BaseModel):
    promedio: float
    fechaActualizacion: str  # ISO 8601, como pide el contrato de ExchangeRate


async def get_rate() -> ExchangeRate:
    global _cached, _until
    if time.monotonic() < _until:
        return _cached
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            response = await client.get(RATE_URL)
            response.raise_for_status()
            published = _Published.model_validate_json(response.content)
        if published.promedio <= 0:
            raise ValueError(f"tasa no positiva: {published.promedio}")
    except Exception:  # noqa: BLE001  dolarapi falló, tardó o respondió otra cosa: se sigue con la última tasa buena
        log.warning("no se pudo leer la tasa en %s; se sigue con «%s»", RATE_URL, _cached.source)
        _until = time.monotonic() + RETRY_S
        return _cached
    _cached = ExchangeRate(
        source="tasa oficial del BCV",
        usd_to_ves=published.promedio,
        observed_at=published.fechaActualizacion,
    )
    _until = time.monotonic() + CACHE_S
    return _cached
