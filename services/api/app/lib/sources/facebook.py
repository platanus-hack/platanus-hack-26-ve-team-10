"""Facebook Marketplace, por un actor de Apify.

Marketplace no se puede leer directo: la página redirige a `/login/`. No es un muro anti-bots como
el de Mercado Libre, es autenticación. Entrar con las cookies de una cuenta real queda descartado
—expone esa cuenta a bloqueo y va contra los términos de Meta—, así que el canal entra por
`curious_coder/facebook-marketplace`, que no pide sesión ni proxy residencial.

Marketplace es entre personas, no tiendas: los vendedores son "Betty Rumbos", no "Daka". Son los
precios más bajos de todos los canales y donde más riesgo de estafa hay, que es justo donde el
puntaje de confianza sirve. Las fórmulas de `fb-v1` salen de resources/fb_marketplace_trust_score.py.
"""

from datetime import UTC, datetime
from typing import Any

from app.lib.contracts import TrustScore
from app.lib.sources.apify import ApifySource, count_of, seen_at_of
from app.lib.sources.firecrawl import matches_product, plain, published_prices
from app.lib.sources.web_trust import is_accessory
from app.lib.trust import (
    Measured,
    age_curve,
    build_signals,
    clamp,
    compute_trust,
    facebook_rating_bonus,
    risk_language,
)
from app.lib.types import Merchant, Money, Offer, SourceResult

ACTOR = "curious_coder/facebook-marketplace"
# Marketplace busca por ciudad y radio, no por país: tres entradas cubren el grueso de Venezuela.
# Cada aviso cuesta medio milésimo de dólar, así que tres corridas siguen siendo centavos.
CITIES = (
    "Caracas, Distrito Capital, Venezuela",
    "Maracaibo, Zulia, Venezuela",
    "Valencia, Carabobo, Venezuela",
)
RADIUS_KM = 60
RESULTS = 20

NEW_PROFILE_FLAG = "Perfil de Facebook creado hace menos de un mes"
LOW_RATING_FLAG = "Calificación menor a 3★"
MIN_RATINGS = 5


def entries(product: str) -> list[tuple[str, dict[str, Any]]]:
    return [
        (
            ACTOR,
            {
                "searchKeyword": product,
                "location": city,
                "radiusKm": RADIUS_KM,
                "sortBy": "",
            },
        )
        for city in CITIES
    ]


def _text(item: dict[str, Any]) -> str:
    """El título y la descripción del aviso, que es de donde sale casi todo."""
    description = item.get("redacted_description")
    if isinstance(description, dict):
        description = description.get("text")
    title = item.get("marketplace_listing_title") or item.get("custom_title") or ""
    return f"{title}\n{description or ''}"


def _price(item: dict[str, Any]) -> Money | None:
    """El precio, solo cuando se puede confirmar en qué moneda está.

    Facebook etiqueta como **VEF** —el bolívar anterior a 2018, que ya no circula— casi todos los
    avisos venezolanos: 19 de 21 en una corrida real, con descripciones que decían "440$". Nadie
    pone precios en una moneda que no existe hace siete años: el aviso está en dólares.

    Manda lo que escriba el vendedor en el texto, que es la única fuente de verdad y además
    reconoce un precio en bolívares de verdad ("Bs. 5.000"). Si el texto no dice nada, la etiqueta
    VEF se lee como dólares, y eso es lo seguro: equivocarse hacia el dólar **sobreestima** el
    precio unas 900 veces, así que esa oferta se hunde al fondo de la lista. Leer el 440 como
    bolívares lo volvería medio dólar y lo pondría primero, anunciado como el mejor precio del
    mercado. El error peligroso es el otro.
    """
    price = item.get("listing_price") or {}
    try:
        amount = float(price.get("amount"))
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    written = published_prices(_text(item)).get(round(amount, 2))
    currencies = {currency for currency in (written or set()) if currency}
    if len(currencies) == 1:
        return Money(amount, currencies.pop())
    label = str(price.get("currency") or "").upper()
    if label in {"USD", "VEF", "VES"}:
        return Money(amount, "USD")
    return None


def _joined_at(seller: dict[str, Any]) -> datetime | None:
    raw = seller.get("joined_at")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def facebook_trust(item: dict[str, Any], *, now: datetime) -> TrustScore:
    """fb-v1 con lo que devuelve el actor. `history` pide otra corrida: por ahora queda en None."""
    seller = item.get("marketplace_listing_seller") or {}
    values: dict[str, Measured] = {}
    flags: list[str] = []

    joined = _joined_at(seller)
    if joined is not None:
        value, reason = age_curve(joined, now, noun="En Facebook desde", floor=6, span=10)
        values["fb_age"] = Measured(value, reason, value >= 0.6)
        if (now - joined).days < 30:
            flags.append(NEW_PROFILE_FLAG)

    city = _city(item)
    if city:
        inside = "venezuela" in plain(city) or any(plain(name.split(",")[0]) in plain(city) for name in CITIES)
        values["location"] = Measured(
            1.0 if inside else 0.0, None if inside else f"Publicado en {city}", inside
        )

    photos = len(item.get("listing_photos") or [])
    words = len(_text(item).split())
    value = 0.5 * clamp(photos / 4) + 0.5 * clamp(words / 25)
    values["completeness"] = Measured(
        value, "Anuncio con pocas fotos o sin descripción" if value < 0.4 else None, value >= 0.7
    )

    values["risk_language"] = risk_language(_text(item))

    rating, count = seller.get("rating_avg"), count_of(seller.get("rating_count"))
    if isinstance(rating, (int, float)) and (count or 0) >= MIN_RATINGS and rating < 3:
        flags.append(LOW_RATING_FLAG)
    bonus = facebook_rating_bonus(
        rating if isinstance(rating, (int, float)) else None,
        count,
        _badges(item),
    )
    return compute_trust(
        "fb-v1",
        build_signals("fb-v1", values),
        stage="parcial",
        red_flags=flags,
        extra_bonus=bonus,
        now=now,
    )


def _badges(item: dict[str, Any]) -> list[str]:
    """Las insignias de comercio del vendedor. Vienen con texto nulo más veces que con texto."""
    badges = (item.get("commerce_badges_info") or {}).get("badges") or []
    return [badge["text"] for badge in badges if isinstance(badge, dict) and isinstance(badge.get("text"), str)]


def _city(item: dict[str, Any]) -> str | None:
    location = item.get("location_text")
    if isinstance(location, dict):
        location = location.get("text")
    return location if isinstance(location, str) and location else None


def read(items: list[dict[str, Any]], product: str, now: str) -> SourceResult:
    offers, merchants, trust, seen = [], {}, {}, set()
    moment = datetime.now(UTC)
    for item in items:
        title = str(item.get("marketplace_listing_title") or item.get("custom_title") or "")
        url = str(item.get("listingUrl") or "")
        price = _price(item)
        # El producto se busca en el texto entero, porque el título de Marketplace es un renglón.
        # Pero una funda que menciona el teléfono en su descripción no es el teléfono.
        if not url or not price or is_accessory(title, product) or not matches_product(product, _text(item)):
            continue
        if url in seen:
            continue
        seen.add(url)
        seller = item.get("marketplace_listing_seller") or {}
        merchant_id = f"fb:{seller.get('id') or 'anonimo'}"
        if merchant_id not in merchants:
            merchants[merchant_id] = Merchant(
                id=merchant_id,
                name=str(seller.get("name") or "Vendedor de Marketplace"),
                channel="facebook",
                url=str(seller.get("url") or url),
                zone=_city(item) or "Venezuela",
                delivers=bool(item.get("shipping_offered")),
                comments=count_of(seller.get("rating_count")),
            )
            trust[merchant_id] = facebook_trust(item, now=moment)
        offers.append(Offer(merchant_id, title, url, price, seen_at_of(item.get("creation_time"), now)))
    return SourceResult(offers=offers, merchants=list(merchants.values()), trust=trust)


facebook_source = ApifySource("facebook", "facebook", ACTOR, entries, read)
