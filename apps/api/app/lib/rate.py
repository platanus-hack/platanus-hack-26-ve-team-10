from app.lib.types import ExchangeRate


# Tasa con la que se convierten los precios en bolívares a USD.
# Pendiente: traer la tasa real (BCV, paralela o ambas: decisión abierta en agents/architecture.md).
async def get_rate() -> ExchangeRate:
    return ExchangeRate(source="tasa de ejemplo", usd_to_ves=200, observed_at="2026-10-24T08:00:00-04:00")
