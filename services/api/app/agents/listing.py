"""Misma forma de listado para todos los especialistas, y las tarjetas de WhatsApp."""

import os
import re
import unicodedata
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.agents.card_image import marked_product_image
from app.lib.trust import to_stars

# Límites del carrusel de WhatsApp (Kapso / Meta): 2 a 10 tarjetas, imagen
# obligatoria, cuerpo de tarjeta de 160 caracteres y como mucho 2 saltos de línea.
# El texto de arriba cabe en 1024; Prais usa como mucho 250.
MIN_CARDS = 2
TARGET_OPTIONS = 5
MAX_CARDS = 10
MAX_CARD_CHARS = 160
MAX_SUMMARY = 250
# El cuerpo de arriba llega listo de quien llama: ya acortado y con el producto
# encima, así que aquí solo se topa en el límite duro de WhatsApp.
_CARD_BODY = 1024
MAX_BUTTON = 20
# Cuerpo de un mensaje de texto. La lista cabe de sobra; se topa por seguridad.
_TEXT_BODY = 4096
# Título dentro del renglón de detalle: lo justo para distinguir una variante de otra.
_LIST_TITLE = 48

# Dos formas de contestar la comparación, y se elige una. La lista es texto plano: no
# depende de que la tienda sirva una imagen que WhatsApp acepte, que es lo que tumbaba
# al carrusel (Meta rechaza WebP con un 400 y se perdía la respuesta entera). El carrusel
# queda completo: WHATSAPP_REPLY_STYLE=carousel lo vuelve a poner.
REPLY_STYLE = os.environ.get("WHATSAPP_REPLY_STYLE", "list")

CHANNEL_LABEL = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "web": "Web",
    "mercadolibre": "Mercado Libre",
    "facebook": "Facebook",
    "amazon": "Amazon",
    "importacion": "Traerlo de USA",
}


class ListingCard(BaseModel):
    title: str
    seller: str
    channel: str
    url: str
    price: str | None = None
    rate: str | None = None
    reviews: str | None = None
    image_url: str | None = None
    ships: bool | None = None
    example: bool = False
    trust: int | dict[str, Any] | None = None
    price_usd: float | None = None
    price_kind: str = "publicado"
    fulfiller: str | None = None
    landed: dict[str, Any] | None = None
    seen_at: str | None = None  # cuándo se vio ese precio: con esta inflación, uno sin fecha no es un precio
    zone: str | None = None
    source: str | None = None  # firecrawl, ejemplo o el id de la fuente del registro: lo pide el MCP


class SpecialistReport(BaseModel):
    listings: list[ListingCard] = Field(default_factory=list)


def cards_from_offers(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copia los campos que la tool ya trajo. No inventa imagen, reseñas ni envío."""
    cards = []
    for offer in offers:
        merchant = offer.get("merchant") or {}
        if "ships" in offer:
            ships = offer["ships"]
        else:
            ships = merchant.get("delivers")
        reviews = offer.get("reviews")
        if reviews is None and merchant.get("comments") is not None:
            reviews = f"{merchant['comments']} comentarios recientes"
        url = offer.get("url") or ""
        if not url.startswith("http"):
            continue
        card = ListingCard(
            title=offer.get("title") or "Oferta",
            seller=merchant.get("name") or "Tienda",
            channel=merchant.get("channel") or "web",
            url=url,
            price=offer.get("price"),
            rate=offer.get("rate"),
            reviews=reviews,
            image_url=offer.get("image_url"),
            ships=ships,
            example=bool(offer.get("example")),
            trust=merchant.get("trust"),
            price_usd=offer.get("priceUsd"),
            seen_at=offer.get("seenAt"),
            zone=merchant.get("zone"),
            source=offer.get("source"),
        )
        data = card.model_dump()
        # El contrato viaja con la tarjeta sin que ningún modelo lo reescriba: close_listings lo
        # lee al final del turno para cerrar el puntaje con la mediana de todas las fuentes.
        for key in ("contractOffer", "contractMerchant"):
            if offer.get(key) is not None:
                data[key] = offer[key]
        cards.append(data)
    return cards


def listings_from_tool_response(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, str):
        try:
            payload = SpecialistReport.model_validate_json(payload).model_dump()
        except ValueError:
            return []
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("listings"), list):
        return [item for item in payload["listings"] if isinstance(item, dict) and item.get("url")]
    result = payload.get("result")
    if result is not None and result is not payload:
        return listings_from_tool_response(result)
    return []


def _https(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _bold(text: str) -> str:
    clean = text.replace("*", "").strip()
    return f"*{clean}*" if clean else ""


def _ellipsis(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    if limit <= 1:
        return "…"
    return text[: limit - 1].rstrip() + "…"


def _review_count(reviews: Any) -> str | None:
    number = ""
    for char in str(reviews or ""):
        if char.isdigit():
            number += char
        elif number:
            break
    if not number:
        return None
    return f"{int(number)} reseñas"


def _short_rate(rate: Any) -> str | None:
    text = " ".join(str(rate or "").split())
    if not text:
        return None
    return text.split(" (", 1)[0]


def _trust_points(trust: Any) -> int | None:
    """La búsqueda trae un entero. Tras cerrar el contrato, `trust` es el puntaje completo."""
    if isinstance(trust, bool) or trust is None:
        return None
    if isinstance(trust, (int, float)):
        return int(trust)
    if isinstance(trust, dict):
        score = trust.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            return int(score)
    return None


_MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _stars(card: dict[str, Any]) -> str | None:
    """De 0 a 5, no el entero de 0 a 100: "Confianza 80" no dice sobre qué."""
    stars = card.get("trustStars")
    if not isinstance(stars, int) or isinstance(stars, bool):
        stars = to_stars(_trust_points(card.get("trust")))
    if not isinstance(stars, int):
        return None
    stars = max(0, min(5, stars))
    return "★" * stars + "☆" * (5 - stars)


def _seen(value: Any) -> str | None:
    """"24 oct". Un precio sin fecha no es un precio: lo pide la regla 7."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        seen = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return f"{seen.day} {_MONTHS[seen.month - 1]}"


def _detail_bits(card: dict[str, Any], seller: str) -> list[str]:
    bits = []
    if card.get("price_kind") == "estimado":
        bits.append("estimado")
    stars = _stars(card)
    if stars:
        bits.append(stars)
    seen = _seen(card.get("seen_at") or card.get("seenAt"))
    if seen:
        bits.append(seen)
    if card.get("ships") is True:
        bits.append("Envía")
    elif card.get("ships") is False:
        bits.append("No envía")
    reviews = _review_count(card.get("reviews"))
    if reviews:
        bits.append(reviews)
    rate = _short_rate(card.get("rate"))
    if rate:
        bits.append(rate)
    if card.get("example") and "ejemplo" not in seller.lower():
        bits.append("ejemplo")
    # El veredicto ya cerrado por el agregador: antes venía de una revisión aparte de la web.
    trust = card.get("trust")
    verdict = trust.get("verdict") if isinstance(trust, dict) else None
    if verdict in {"riesgosa", "precaucion"}:
        bits.insert(0, "Ojo")
    return bits


def card_text(card: dict[str, Any]) -> str:
    """Tres líneas, precio y vendedor en negrita, sin pasar de 160 caracteres."""
    price = " ".join(str(card.get("price") or "").split())
    title = " ".join(str(card.get("title") or "Oferta").split())
    seller = " ".join(str(card.get("seller") or "Tienda").split())
    channel = CHANNEL_LABEL.get(card.get("channel") or "", str(card.get("channel") or "Web"))
    bits = _detail_bits(card, seller)
    seller_text = seller
    while True:
        shop = f"{_bold(seller_text)} · {channel}"
        detail = " · ".join(bits)
        prefix = f"{_bold(price)} " if price else ""
        used = len(shop) + 1 + (len(detail) + 1 if detail else 0) + len(prefix)
        title_text = _ellipsis(title, max(1, MAX_CARD_CHARS - used))
        lines = [f"{prefix}{title_text}".strip(), shop]
        if detail:
            lines.append(detail)
        body = "\n".join(lines)
        if len(body) <= MAX_CARD_CHARS and body.count("\n") <= 2:
            return body
        if bits:
            bits.pop()
            continue
        if len(seller_text) > 12:
            seller_text = _ellipsis(seller, len(seller_text) - 4)
            continue
        return body[:MAX_CARD_CHARS]


def clamp_summary(text: str) -> str:
    flat = " ".join((text or "").split())
    if not flat:
        return "Estas son las opciones con precio."
    if len(flat) <= MAX_SUMMARY:
        return flat
    cut = flat[: MAX_SUMMARY - 1].rsplit(" ", 1)[0].rstrip(".,;:")
    return f"{cut}…"


def _price_key(item: dict[str, Any]) -> float:
    value = item.get("price_usd")
    return value if isinstance(value, (int, float)) else float("inf")


def has_published_price(item: dict[str, Any]) -> bool:
    """Un precio publicado es un texto no vacío. None y el espacio no ocupan un lugar."""
    price = item.get("price")
    if price is None or isinstance(price, bool):
        return False
    return bool(str(price).strip())


def choose_options(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hasta 5 ofertas con precio publicado, de la más barata a la más cara.

    Una fila sin precio no cuenta. Si hay precios reales, los de ejemplo no
    completan las cinco: siguen siendo ejemplo y solo entran cuando no hay
    ninguno real. Si hay menos de cinco, se devuelven las que hay. No se inventan.
    """
    priced = [item for item in listings if has_published_price(item) and _https(item.get("url"))]
    real = sorted((item for item in priced if not item.get("example")), key=_price_key)
    if real:
        return real[:TARGET_OPTIONS]
    sample = sorted((item for item in priced if item.get("example")), key=_price_key)
    return sample[:TARGET_OPTIONS]


async def carousel_message(to: str, listings: list[dict[str, Any]], summary: str) -> dict[str, Any] | None:
    """Arma el carrusel. Cada tarjeta abre la página donde se vende."""
    cards = []
    for item in choose_options(listings):
        image = item.get("image_url") if _https(item.get("image_url")) else None
        if not image:
            image = await marked_product_image(str(item.get("title") or "producto"))
        if not _https(image):
            continue
        cards.append({**item, "image_url": image})
        if len(cards) == TARGET_OPTIONS:
            break
    # WhatsApp exige al menos dos tarjetas. Con una sola se manda una tarjeta suelta.
    if len(cards) < MIN_CARDS:
        return None
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "carousel",
            "body": {"text": summary[:_CARD_BODY]},
            "action": {
                "cards": [
                    {
                        "card_index": index,
                        "type": "cta_url",
                        "header": {"type": "image", "image": {"link": card["image_url"]}},
                        "body": {"text": card_text(card)},
                        "action": {
                            "name": "cta_url",
                            "parameters": {"display_text": "Ver oferta", "url": card["url"]},
                        },
                    }
                    for index, card in enumerate(cards)
                ]
            },
        },
    }


async def one_offer_message(to: str, listings: list[dict[str, Any]], summary: str) -> dict[str, Any] | None:
    """Una sola oferta con precio: una tarjeta con botón, no solo un párrafo."""
    chosen = choose_options(listings)
    if len(chosen) != 1:
        return None
    item = chosen[0]
    image = item.get("image_url") if _https(item.get("image_url")) else None
    if not image:
        image = await marked_product_image(str(item.get("title") or "producto"))
    interactive: dict[str, Any] = {
        "type": "cta_url",
        "body": {"text": summary[:_CARD_BODY]},
        "action": {
            "name": "cta_url",
            "parameters": {"display_text": "Ver oferta", "url": item["url"]},
        },
    }
    if _https(image):
        interactive["header"] = {"type": "image", "image": {"link": image}}
    return {"messaging_product": "whatsapp", "to": to, "type": "interactive", "interactive": interactive}


def list_line(card: dict[str, Any]) -> str:
    """Una oferta en tres renglones: precio y vendedor, el detalle, y el enlace.

    El detalle sale de _detail_bits, el mismo que usa la tarjeta: así la lista cumple
    la regla 7 igual que el carrusel (fuente, fecha y la tasa si hubo conversión).
    """
    price = " ".join(str(card.get("price") or "").split())
    seller = " ".join(str(card.get("seller") or "Tienda").split())
    title = " ".join(str(card.get("title") or "").split())
    channel = CHANNEL_LABEL.get(card.get("channel") or "", str(card.get("channel") or "Web"))
    detail = [_ellipsis(title, _LIST_TITLE)] if title else []
    detail.append(channel)
    detail += _detail_bits(card, seller)
    head = f"• {_bold(price)} — {seller}" if price else f"• {seller}"
    return "\n".join([head, "  " + " · ".join(detail), f"  {card['url']}"])


async def list_message(to: str, listings: list[dict[str, Any]], summary: str) -> dict[str, Any] | None:
    """La comparación como lista de texto. Una sola oferta también vale: a diferencia
    del carrusel, que exige dos tarjetas, aquí no hay mínimo."""
    chosen = choose_options(listings)
    if not chosen:
        return None
    body = "\n\n".join([summary, *(list_line(card) for card in chosen)])
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        # Sin vista previa: con cinco enlaces, WhatsApp expandiría el primero y
        # descuadraría la lista. https://docs.kapso.ai/docs/whatsapp/send-messages/text.md
        "text": {"body": body[:_TEXT_BODY], "preview_url": False},
    }


async def carousel_or_card(to: str, listings: list[dict[str, Any]], summary: str) -> dict[str, Any] | None:
    """Carrusel si hay dos o más ofertas. Una tarjeta si hay una. Nada si no hay precio."""
    many = await carousel_message(to, listings, summary)
    if many is not None:
        return many
    return await one_offer_message(to, listings, summary)


async def shopping_message(to: str, listings: list[dict[str, Any]], summary: str) -> dict[str, Any] | None:
    """El despachador: una forma u otra, según REPLY_STYLE. Hoy, la lista."""
    if REPLY_STYLE == "carousel":
        return await carousel_or_card(to, listings, summary)
    return await list_message(to, listings, summary)


# Botones de respuesta (Kapso, misma forma que la API de Meta):
# https://docs.kapso.ai/docs/whatsapp/send-messages/buttons.md
# De 1 a 3, título de 20 caracteres, títulos e ids únicos dentro del mensaje.
MAX_BUTTONS = 3
_BUTTON_BODY = 1024


def _button_id(title: str, used: set[str]) -> str:
    plain = unicodedata.normalize("NFKD", title)
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    base = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:188] or "opcion"
    candidate, number = base, 2
    while candidate in used:
        candidate = f"{base[: 188 - len(str(number)) - 1]}-{number}"
        number += 1
    used.add(candidate)
    return candidate


def button_message(to: str, body: str, titles: list[str]) -> dict[str, Any] | None:
    """Hasta tres opciones, a un toque. Es lo que convierte un texto en una salida."""
    body = " ".join(body.split())
    chosen: list[str] = []
    for title in titles:
        clean = " ".join(str(title).split())
        if clean and len(clean) <= MAX_BUTTON and clean not in chosen:
            chosen.append(clean)
    if not body or len(body) > _BUTTON_BODY or not chosen or len(chosen) > MAX_BUTTONS:
        return None
    used: set[str] = set()
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": _button_id(title, used), "title": title}} for title in chosen
                ]
            },
        },
    }


# Afinar después de ver los precios, cuando la persona ya sabe cuánto cambia cada opción.
# Sin catálogo que diga qué aplica a qué: el filtro sale de lo que trajeron las ofertas.
ONLY_NEW = "Solo nuevos"
ONLY_USED = "Solo usados"
_USED_WORDS = re.compile(r"\b(usad[oa]s?|seminuev[oa]s?|segunda mano|reacondicionad[oa]s?|refurbished)\b")
_NEW_WORDS = re.compile(r"\b(nuev[oa]s?|sellad[oa]s?)\b")


def _folded(text: Any) -> str:
    plain = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(char for char in plain if not unicodedata.combining(char)).lower()


def mixed_condition(listings: list[dict[str, Any]]) -> bool:
    """Si entre las ofertas hay usadas y nuevas, separarlas es una pregunta que vale."""
    titles = [_folded(item.get("title")) for item in choose_options(listings)]
    used = any(_USED_WORDS.search(title) for title in titles)
    new = any(_NEW_WORDS.search(title) for title in titles) or any(
        not _USED_WORDS.search(title) for title in titles
    )
    return bool(titles) and used and new


def says_condition(product: str) -> bool:
    folded = _folded(product)
    return bool(_USED_WORDS.search(folded) or _NEW_WORDS.search(folded))


_CAPACITY = re.compile(r"\b\d+\s?(?:gb|tb)\b")


def narrowed(product: str) -> tuple[str, str] | None:
    """Qué soltar cuando no hubo precios: (etiqueta del botón, producto más amplio).

    Solo quita palabras que la persona escribió, así que no hace falta saber de qué
    producto se trata: lo que no está, no se ofrece.
    """
    folded = _folded(product)
    if _CAPACITY.search(folded):
        wider = re.sub(r"\b\d+\s?(?:gb|tb)\b", "", product, flags=re.IGNORECASE)
        return "Sin la capacidad", " ".join(wider.split())
    if says_condition(product):
        wider = re.sub(
            r"\b(nuev[oa]s?|sellad[oa]s?|usad[oa]s?|seminuev[oa]s?|reacondicionad[oa]s?|refurbished)\b",
            "",
            product,
            flags=re.IGNORECASE,
        )
        return "Nuevos y usados", " ".join(wider.split())
    return None

