"""El especialista de confianza de una tienda web (web-v1).

Mide lo que se puede saber del dominio sin pagar otra lectura de la página: cuándo se registró
(RDAP), si tiene correo configurado (MX), si sirve por HTTPS y qué lenguaje usa el anuncio. Lo que
necesitaría otro scrape —RIF, políticas, catálogo— queda en `None`: no cuenta y su peso se reparte.

Como todo especialista, deja el puntaje en `parcial`. La anomalía de precio y las redes enlazadas
las llena el agregador, que es el único que ve todas las fuentes a la vez. El contrato completo
está en docs/contracts.md.

Las dos banderas rojas vienen de resources/website_trust_score.py y de lo que ya hacía la revisión
anterior: un dominio que imita a una marca y un anuncio que en realidad vende un accesorio. La
tercera que había ahí —precio muy por debajo del resto— no se repite aquí: es `price_anomaly`, y
el agregador ya la aplica con el mismo umbral.
"""

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from app.lib.cadenas import chain_for_host
from app.lib.contracts import TrustScore
from app.lib.trust import (
    Measured,
    age_curve,
    build_signals,
    compute_trust,
    risk_language,
)

RDAP_URL = "https://rdap.org/domain/{domain}"
DNS_URL = "https://dns.google/resolve"
# El dominio no cambia de edad durante una demo: se consulta una vez al día.
LOOKUP_CACHE_S = 24 * 60 * 60
# Las dos consultas son gratis pero van por red: no pueden alargar la búsqueda.
LOOKUP_TIMEOUT_S = 4

ACCESSORY_FLAG = "Es una funda, una copia o un accesorio, no el producto pedido"

# Lo usa también Marketplace: una funda que menciona el teléfono no es el teléfono.
ACCESSORY = re.compile(
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

_cache: dict[str, tuple[float, "Domain"]] = {}


@dataclass(frozen=True)
class Domain:
    """Lo que se sabe del dominio sin leer la página. `None` es "no se pudo averiguar"."""

    registered_at: datetime | None = None
    has_mx: bool | None = None


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.").lower()


def _flat(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def impersonated_brand(host: str, product: str) -> str | None:
    """La marca que el dominio dice ser sin serlo: `iphone-venezuela.com` no es de Apple."""
    flat_host, flat_product = _flat(host), _flat(product)
    for name, domains, marks in _BRANDS:
        if not any(mark in flat_host for mark in marks):
            continue
        if not any(mark in flat_product for mark in marks):
            continue
        if any(host == domain or host.endswith(f".{domain}") for domain in domains):
            continue
        return name
    return None


def _registrable(host: str) -> str:
    """El dominio que se registra: de `tienda.farmatodo.com.ve` sale `farmatodo.com.ve`."""
    parts = host.split(".")
    if len(parts) > 2 and parts[-2] in {"com", "co", "net", "org", "gob", "edu"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


async def _registered_at(client: httpx.AsyncClient, domain: str) -> datetime | None:
    """La fecha de registro, de RDAP. Es público y no pide API key."""
    try:
        response = await client.get(RDAP_URL.format(domain=domain), timeout=LOOKUP_TIMEOUT_S)
        if response.status_code != 200:
            return None
        for event in response.json().get("events") or []:
            if event.get("eventAction") == "registration":
                return datetime.fromisoformat(str(event["eventDate"]))
    except Exception:  # noqa: BLE001  sin dato la señal queda en None, que es lo honesto
        return None
    return None


async def _has_mx(client: httpx.AsyncClient, domain: str) -> bool | None:
    """Si el dominio tiene correo configurado, por DNS sobre HTTPS. También gratis."""
    try:
        response = await client.get(
            DNS_URL, params={"name": domain, "type": "MX"}, timeout=LOOKUP_TIMEOUT_S
        )
        if response.status_code != 200:
            return None
        body = response.json()
        if body.get("Status") != 0:
            return None
        return any(answer.get("type") == 15 for answer in body.get("Answer") or [])
    except Exception:  # noqa: BLE001
        return None


async def look_up(hosts: list[str]) -> dict[str, Domain]:
    """Los datos de cada dominio, una sola vez por host y todos en paralelo."""
    now = time.monotonic()
    pending = [host for host in dict.fromkeys(hosts) if host and _cache.get(host, (0, None))[0] < now]
    if pending:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            domains = [_registrable(host) for host in pending]
            found = await asyncio.gather(
                *(_registered_at(client, domain) for domain in domains),
                *(_has_mx(client, domain) for domain in domains),
            )
            half = len(pending)
            for index, host in enumerate(pending):
                _cache[host] = (now + LOOKUP_CACHE_S, Domain(found[index], found[half + index]))
    return {host: _cache[host][1] for host in hosts if host in _cache}


def web_trust(
    url: str,
    title: str,
    product: str,
    domain: Domain,
    *,
    now: datetime | None = None,
) -> TrustScore:
    """El puntaje parcial de una oferta de la web abierta."""
    moment = now or datetime.now(UTC)
    host = host_of(url)
    values: dict[str, Measured] = {}
    flags: list[str] = []

    if domain.registered_at is not None:
        value, reason = age_curve(domain.registered_at, moment, noun="Dominio registrado")
        values["domain_age"] = Measured(value, reason, value >= 0.6)

    # Una cadena revisada a mano tiene contacto verificable: es una empresa conocida con su
    # tienda propia, no un dominio anónimo. Lo demás que pide la señal (RIF, dirección) haría
    # falta otra lectura de la página, así que sin cadena no se mide.
    chain = chain_for_host(host)
    if chain is not None:
        values["contact"] = Measured(1.0, f"{chain.name}, cadena venezolana con tienda propia", True)

    https = url.startswith("https://")
    values["https"] = Measured(1.0 if https else 0.0, None if https else "El sitio no usa HTTPS", https)

    if domain.has_mx is not None:
        values["mx"] = Measured(
            1.0 if domain.has_mx else 0.0,
            None if domain.has_mx else "El dominio no tiene correo configurado",
            domain.has_mx,
        )

    values["risk_language"] = risk_language(title)

    brand = impersonated_brand(host, product)
    if brand:
        flags.append(f"El dominio imita a {brand}")
    if is_accessory(title, product):
        flags.append(ACCESSORY_FLAG)

    return compute_trust("web-v1", build_signals("web-v1", values), stage="parcial", red_flags=flags, now=moment)


def is_accessory(title: str, product: str) -> bool:
    """El anuncio vende una funda o una copia, y lo pedido no era eso."""
    return bool(ACCESSORY.search(title)) and not ACCESSORY.search(product)
