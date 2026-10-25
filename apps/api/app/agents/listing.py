"""Misma forma de listado para todos los especialistas, y las tarjetas de WhatsApp."""

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


def choose_options(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hasta 5 ofertas con precio. Primero las reales, de menor a mayor."""
    priced = [item for item in listings if item.get("price") and _https(item.get("url"))]
    real = sorted((item for item in priced if not item.get("example")), key=_price_key)
    sample = sorted((item for item in priced if item.get("example")), key=_price_key)
    chosen = real[:TARGET_OPTIONS]
    if len(chosen) < TARGET_OPTIONS:
        chosen.extend(sample[: TARGET_OPTIONS - len(chosen)])
    return chosen


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
