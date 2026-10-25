"""La confianza de una oferta de la web abierta, en el contrato de trust.py.

Antes esto devolvía un veredicto suyo (`riesgosa`, `precaucion`, `sin_datos`) calculado con tres
heurísticas, fuera del contrato. Usaba las mismas palabras que el puntaje real pero no significaban
lo mismo: su `sin_datos` quería decir "no saltó ninguna alarma", o sea que todo está bien, mientras
que en el contrato quiere decir "no me alcanzó para saber". Y una tienda impecable nunca podía
salir `confiable`, porque esa palabra no existía ahí.

Ahora mide las señales de `web-v1` (ver sources/web_trust.py) y deja el puntaje en `parcial`, como
cualquier otro especialista. Lo cierra el agregador con la mediana de todas las fuentes. Las dos
banderas rojas que valía la pena conservar —dominio que imita una marca, anuncio que es un
accesorio— siguen, ahora dentro del puntaje. La tercera, el precio muy por debajo del resto, no se
repite: es `price_anomaly` y el agregador ya la aplica con el mismo umbral del 50 %.
"""

from typing import Any

from app.lib import contract_build
from app.lib.rate import get_rate
from app.lib.sources.web_trust import Domain, host_of, look_up, web_trust
from app.lib.types import Money

_EMPTY = Domain()


def _money(offer: dict[str, Any]) -> Money | None:
    amount, currency = offer.get("priceAmount"), offer.get("priceCurrency")
    if isinstance(amount, (int, float)) and amount > 0 and currency in {"USD", "VES"}:
        return Money(float(amount), currency)
    return None


async def review_offers(product: str, offers: list[dict[str, Any]]) -> None:
    """Le pone a cada oferta de la web abierta su contrato con el puntaje parcial.

    Las consultas de dominio son gratis (RDAP y DNS sobre HTTPS) pero van por red: se hacen una
    sola vez por host, en paralelo, y se recuerdan un día.
    """
    if not offers:
        return
    hosts = [host_of(str(offer.get("url") or "")) for offer in offers]
    domains, rate = await look_up(hosts), await get_rate()
    for offer, host in zip(offers, hosts):
        url = str(offer.get("url") or "")
        title = str(offer.get("title") or "")
        if not url or not host:
            continue
        merchant = offer.get("merchant") or {}
        trust = web_trust(url, title, product, domains.get(host) or _EMPTY)
        contract_offer, contract_merchant = contract_build.build(
            merchant_id=f"web:{host}",
            name=str(merchant.get("name") or host),
            channel="web",
            merchant_url=f"https://{host}",
            zone=merchant.get("zone"),
            delivers=merchant.get("delivers"),
            title=title,
            url=url,
            seen_at=str(offer.get("seenAt") or ""),
            price=_money(offer),
            price_usd=offer.get("priceUsd"),
            rate=rate,
            product=product,
            trust=trust,
            link_value=host,
        )
        offer.update(contract_build.as_card(contract_offer, contract_merchant))
