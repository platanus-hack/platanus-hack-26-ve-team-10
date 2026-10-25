"""Misma forma de listado para todos los especialistas, y las tarjetas de WhatsApp."""

import re
import unicodedata
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.agents.card_image import marked_product_image

# Límites del carrusel de WhatsApp (Kapso / Meta): 2 a 10 tarjetas, imagen
# obligatoria, cuerpo de tarjeta de 160 caracteres y como mucho 2 saltos de línea.
# El texto de arriba cabe en 1024; Prais usa como mucho 250.
MIN_CARDS = 2
TARGET_OPTIONS = 5
MAX_CARDS = 10
MAX_CARD_CHARS = 160
MAX_SUMMARY = 250
MAX_BUTTON = 20

CHANNEL_LABEL = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "web": "Web",
    "mercadolibre": "Mercado Libre",
    "facebook": "Facebook",
    "amazon": "Amazon",
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
    trust: int | None = None
    price_usd: float | None = None


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
        )
        cards.append(card.model_dump())
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


def _detail_bits(card: dict[str, Any], seller: str) -> list[str]:
    bits = []
    if card.get("trust") is not None:
        bits.append(f"Confianza {card['trust']}")
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


def _published_price(item: dict[str, Any]) -> bool:
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
    priced = [item for item in listings if _published_price(item) and _https(item.get("url"))]
    real = sorted((item for item in priced if not item.get("example")), key=_price_key)
    if real:
        return real[:TARGET_OPTIONS]
    sample = sorted((item for item in priced if item.get("example")), key=_price_key)
    return sample[:TARGET_OPTIONS]


# Lista de WhatsApp (Kapso, misma forma que la API de Meta):
# https://docs.kapso.ai/docs/whatsapp/send-messages/lists.md
# body 1024, botón 20, título de sección 24, título de fila 24, id 188, hasta 10 filas.
_LIST_BODY = 1024
_LIST_BUTTON = 20
_LIST_SECTION = 24
_LIST_ROW = 24
_LIST_ID = 188
_LIST_ROWS = 10


def _row_id(title: str, used: set[str]) -> str:
    plain = unicodedata.normalize("NFKD", title)
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    base = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:_LIST_ID] or "opcion"
    candidate = base
    number = 2
    while candidate in used:
        suffix = f"-{number}"
        candidate = f"{base[: _LIST_ID - len(suffix)]}{suffix}"
        number += 1
    used.add(candidate)
    return candidate


def _list_rows(rows: list[str]) -> list[str]:
    chosen: list[str] = []
    for row in rows:
        title = " ".join(str(row).split())
        if not title or len(title) > _LIST_ROW or title in chosen:
            continue
        chosen.append(title)
    if len(chosen) <= _LIST_ROWS:
        return chosen
    if "Me da igual" in chosen:
        head = [title for title in chosen if title != "Me da igual"][: _LIST_ROWS - 1]
        return head + ["Me da igual"]
    return chosen[:_LIST_ROWS]


def list_message(
    to: str,
    body: str,
    rows: list[str],
    *,
    button: str = "Ver opciones",
    section: str = "Opciones",
) -> dict[str, Any] | None:
    """Arma la lista tappable. La persona también puede contestar con texto."""
    body = " ".join(body.split())
    button = " ".join(button.split())
    section = " ".join(section.split())
    titles = _list_rows(rows)
    if not body or not button or not section or not titles:
        return None
    if len(body) > _LIST_BODY or len(button) > _LIST_BUTTON or len(section) > _LIST_SECTION:
        return None
    used: set[str] = set()
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {
                "button": button,
                "sections": [
                    {
                        "title": section,
                        "rows": [{"id": _row_id(title, used), "title": title} for title in titles],
                    }
                ],
            },
        },
    }


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
    # WhatsApp exige al menos dos tarjetas. Con una, o con ninguna, quien llama
    # manda el texto: la respuesta no falla por no llegar a cinco.
    if len(cards) < MIN_CARDS:
        return None
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "carousel",
            "body": {"text": clamp_summary(summary)},
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
