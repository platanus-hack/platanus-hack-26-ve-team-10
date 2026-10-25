"""Cadenas venezolanas con tienda propia.

Señal de respaldo comercial: el comercio vende él mismo y su web es el canal
oficial. No dice que el precio sea bueno ni que la oferta sea el producto
buscado. Se compara por dominio, no por nombre. Se ignora un ``www`` inicial.
Otro subdominio no hereda la fila: ``ve.epaenlinea.com`` no cubre
``cr.epaenlinea.com`` ni un dominio parecido.

Revisado el 2026-10-24. Cada URL respondió ese día desde ese host. Si un
cliente HTTP recibía 403, la fila lo dice y el navegador confirmó el dominio.
"""

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

Category = Literal["farmacia", "supermercado", "tecnologia", "hogar"]

REVIEWED_ON = "2026-10-24"


@dataclass(frozen=True)
class Chain:
    name: str
    domain: str  # host exacto, sin esquema ni www
    url: str  # URL que respondió el día de la revisión
    category: Category
    tienda_propia: bool = True
    online_store: bool = False
    price_source: bool = False  # candidata a fuente de precios; todavía sin adapter
    blocks_http_clients: bool = False
    reviewed_on: str = REVIEWED_ON
    note: str = ""
    aliases: tuple[str, ...] = ()  # otros hosts verificados del mismo comercio


# El orden sigue las categorías del relevamiento. No agregues una fila sin
# haber recibido una respuesta HTTP de ese host.
CHAINS: tuple[Chain, ...] = (
    Chain(
        name="Farmatodo",
        domain="farmatodo.com.ve",
        url="https://www.farmatodo.com.ve",
        category="farmacia",
        online_store=True,
    ),
    Chain(
        name="Locatel",
        domain="locatel.com.ve",
        url="https://www.locatel.com.ve",
        category="farmacia",
        online_store=True,
        note="El apex no completa TLS. Responde www.locatel.com.ve.",
    ),
    Chain(
        name="Farmahorro",
        domain="farmahorro.com.ve",
        url="https://farmahorro.com.ve",
        category="farmacia",
        online_store=True,
    ),
    Chain(
        name="FarmaGo",
        domain="farmago.com.ve",
        url="https://www.farmago.com.ve",
        category="farmacia",
        online_store=True,
    ),
    Chain(
        name="Farmacia SAAS",
        domain="farmaciasaas.com",
        url="https://www.farmaciasaas.com",
        category="farmacia",
        online_store=True,
    ),
    Chain(
        name="Redvital",
        domain="redvital.com",
        url="https://www.redvital.com/portal/",
        category="farmacia",
        note="Portal del grupo, con mapa de tiendas. No es el mismo dominio que Makro.",
    ),
    Chain(
        name="Farmacia San Ignacio",
        domain="redfarmaignacio.com",
        url="https://redfarmaignacio.com/",
        category="farmacia",
        note="La portada pide el pedido por sede. No confirmé un catálogo con precios.",
    ),
    Chain(
        name="Gama",
        domain="gamaenlinea.com",
        url="https://gamaenlinea.com/es/",
        category="supermercado",
        online_store=True,
        price_source=True,
        note="www.gamaenlinea.com no resuelve. La tienda es el apex.",
    ),
    Chain(
        name="Central Madeirense",
        domain="tucentralonline.com",
        url="https://tucentralonline.com",
        category="supermercado",
        online_store=True,
    ),
    Chain(
        name="Forum",
        domain="forum.com.ve",
        url="https://forum.com.ve/",
        category="supermercado",
        online_store=True,
    ),
    Chain(
        name="Unicasa",
        domain="unicasa.com.ve",
        url="https://unicasa.com.ve",
        category="supermercado",
        note="Sitio institucional. No vi tienda en línea.",
    ),
    Chain(
        name="Plaza's",
        domain="elplazas.com",
        url="https://elplazas.com",
        category="supermercado",
        blocks_http_clients=True,
        note="HTTP 403 de Cloudflare. El navegador se queda en el reto: no vi el catálogo.",
    ),
    Chain(
        name="Makro",
        domain="makrove.com",
        url="https://makrove.com/",
        category="supermercado",
        note="Localizador de tiendas Redvital Makro. makro.com.ve no respondió.",
    ),
    Chain(
        name="Luvebras",
        domain="automercadosluvebras.com",
        url="https://www.automercadosluvebras.com/",
        category="supermercado",
        note="Responde www. El apex no completa TLS. No vi tienda en línea.",
    ),
    Chain(
        name="Daka",
        domain="tiendasdaka.com",
        url="https://tiendasdaka.com/ve",
        category="tecnologia",
        online_store=True,
        price_source=True,
    ),
    Chain(
        name="IVOO",
        domain="ivoo.com",
        url="https://www.ivoo.com",
        category="tecnologia",
        online_store=True,
        price_source=True,
    ),
    Chain(
        name="Multimax",
        domain="multimax.com.ve",
        url="https://multimax.com.ve",
        category="tecnologia",
        online_store=True,
        note="multimax.net es la tienda de Panamá y no es esta fila.",
    ),
    Chain(
        name="SoyTechno",
        domain="soytechno.com",
        url="https://soytechno.com",
        category="tecnologia",
        blocks_http_clients=True,
        note="HTTP 403 de Cloudflare. El navegador se queda en el reto: no vi el catálogo.",
    ),
    Chain(
        name="Xiaomi Latin",
        domain="xio-online.com",
        url="https://xio-online.com/es/tienda/",
        category="tecnologia",
        online_store=True,
        note="xiaomivenezuela.com no es la tienda: responde un lander, no el catálogo.",
    ),
    Chain(
        name="Venelectronics",
        domain="venelectronics.com",
        url="https://venelectronics.com",
        category="tecnologia",
        online_store=True,
        blocks_http_clients=True,
        note="Un cliente HTTP recibe 403. El navegador carga la tienda, con carrito.",
    ),
    Chain(
        name="Credimport",
        domain="credimport.app",
        url="https://credimport.app/",
        category="tecnologia",
        online_store=True,
    ),
    Chain(
        name="Damasco",
        domain="damascovzla.com",
        url="https://www.damascovzla.com/",
        category="tecnologia",
        note="Solo responde www.damascovzla.com. El apex no resuelve. No vi carrito.",
    ),
    Chain(
        name="EPA",
        domain="ve.epaenlinea.com",
        url="https://ve.epaenlinea.com",
        category="hogar",
        online_store=True,
        price_source=True,
        note=(
            "epaenlinea.com solo elige país. Costa Rica, Guatemala y El Salvador "
            "no son esta tienda."
        ),
    ),
    Chain(
        name="Ferretotal",
        domain="ferretotal.com",
        url="https://ferretotal.com",
        category="hogar",
        online_store=True,
    ),
    Chain(
        name="Total Tools",
        domain="totaltoolsoficial.com.ve",
        url="https://totaltoolsoficial.com.ve",
        category="hogar",
        online_store=True,
    ),
    Chain(
        name="Traki",
        domain="traki.com",
        url="https://traki.com",
        category="hogar",
        online_store=True,
    ),
    Chain(
        name="Sambil",
        domain="asistentesambil.com",
        url="https://www.asistentesambil.com/",
        category="hogar",
        aliases=("sambilonline.com",),
        note="www.sambilonline.com redirige a un asistente de compras por WhatsApp.",
    ),
    Chain(
        name="Beco",
        domain="becoenlinea.com",
        url="https://www.becoenlinea.com/",
        category="hogar",
        online_store=True,
        note="beco.com.ve no completó una respuesta HTTP. La tienda es www.becoenlinea.com.",
    ),
    Chain(
        name="Pintacasa",
        domain="pintacasa.com.ve",
        url="https://pintacasa.com.ve/",
        category="hogar",
        note="Tiene sucursales y delivery. No vi carrito.",
    ),
)


def _host(value: str) -> str:
    raw = value.strip().lower()
    if "://" in raw:
        host = urlparse(raw).hostname or ""
    else:
        host = raw.split("/")[0].split(":")[0]
    return host.removeprefix("www.").rstrip(".")


def _labels(chain: Chain) -> tuple[str, ...]:
    return (_host(chain.domain), *(_host(alias) for alias in chain.aliases))


def _index() -> dict[str, Chain]:
    found: dict[str, Chain] = {}
    for chain in CHAINS:
        if chain.tienda_propia is not True:
            raise RuntimeError(f"{chain.name} no tiene tienda propia")
        for label in _labels(chain):
            if not label or label in found:
                raise RuntimeError(f"dominio repetido o vacío: {label}")
            found[label] = chain
    return found


_BY_HOST = _index()


def chain_for_host(host: str) -> Chain | None:
    """La cadena de ese host, o None. No compara por nombre ni por sufijo."""
    return _BY_HOST.get(_host(host))
