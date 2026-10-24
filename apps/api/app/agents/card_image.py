"""Foto de la tarjeta. Si el anuncio no trae imagen, se usa una del producto con la marca de Prais."""

import asyncio
import io
import logging
import os
import secrets
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger("prais.card_image")

WIDTH = 1200
HEIGHT = 630
MARK = "imagen de Prais"
_MAX_BYTES = 3_000_000
_store: dict[str, bytes] = {}
_ready: dict[str, str] = {}


def read_card_image(token: str) -> bytes | None:
    return _store.get(token)


def public_base() -> str | None:
    base = (os.environ.get("PUBLIC_BASE_URL") or os.environ.get("SELF_URL") or "").rstrip("/")
    if base.startswith("https://"):
        return base
    return None


def _font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def _cover(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, rgba)
    image = image.convert("RGB")
    scale = max(WIDTH / image.width, HEIGHT / image.height)
    resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))))
    left = (resized.width - WIDTH) // 2
    top = (resized.height - HEIGHT) // 2
    return resized.crop((left, top, left + WIDTH, top + HEIGHT))


def _stamp(image: Image.Image) -> bytes:
    """Pone la marca encima de la foto, en una franja que se lee sobre cualquier fondo."""
    framed = _cover(image).convert("RGBA")
    veil = Image.new("RGBA", framed.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(veil)
    font = _font(54)
    left, top, right, bottom = draw.textbbox((0, 0), MARK, font=font)
    text_w, text_h = right - left, bottom - top
    x = (WIDTH - text_w) // 2
    y = 36
    pad = 18
    draw.rounded_rectangle(
        (x - pad, y - pad, x + text_w + pad, y + text_h + pad),
        radius=12,
        fill=(0, 0, 0, 190),
    )
    draw.text((x, y), MARK, fill=(255, 255, 255, 255), font=font)
    framed = Image.alpha_composite(framed, veil).convert("RGB")
    out = io.BytesIO()
    framed.save(out, format="JPEG", quality=82, optimize=True)
    return out.getvalue()


def _save(data: bytes) -> str | None:
    base = public_base()
    if base is None:
        log.warning("card image has no public https base")
        return None
    token = secrets.token_urlsafe(9)
    _store[token] = data
    while len(_store) > 40:
        _store.pop(next(iter(_store)))
    return f"{base}/card-images/{token}.jpg"


async def _download(url: str) -> bytes | None:
    if not url.startswith("https://"):
        return None
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*"},
            )
        if response.status_code != 200 or len(response.content) > _MAX_BYTES or len(response.content) < 2000:
            return None
        kind = response.headers.get("content-type", "")
        if "svg" in kind or kind.startswith("text/"):
            return None
        return response.content
    except Exception:  # noqa: BLE001  una foto caída no tumba la tarjeta
        log.info("product image download failed")
        return None


def _is_image(data: bytes) -> bool:
    try:
        Image.open(io.BytesIO(data)).verify()
    except (OSError, ValueError):
        return False
    return True


def _usable_photo(item: dict[str, Any]) -> str | None:
    url = item.get("imageUrl") or item.get("image_url")
    if not isinstance(url, str) or not url.startswith("https://"):
        return None
    width, height = item.get("imageWidth") or item.get("image_width"), item.get("imageHeight") or item.get("image_height")
    if isinstance(width, int) and isinstance(height, int) and (width < 200 or height < 200):
        return None
    return url


async def _product_photo(title: str) -> bytes | None:
    """La búsqueda de imágenes de Firecrawl trae la foto en imageUrl. El cliente async la pierde."""
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return None
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.firecrawl.dev/v2/search",
            headers={"Authorization": f"Bearer {key}"},
            json={"query": title, "limit": 5, "sources": ["images"], "timeout": 15000},
        )
    if response.status_code != 200:
        return None
    hits = ((response.json().get("data") or {}).get("images")) or []
    for item in hits:
        if not isinstance(item, dict):
            continue
        data = await _download(_usable_photo(item) or "")
        if data and _is_image(data):
            return data
    return None


async def marked_product_image(title: str) -> str | None:
    """URL pública de una foto del producto con «imagen de Prais» encima."""
    key = " ".join(title.lower().split()) or "producto"
    ready = _ready.get(key)
    if ready:
        return ready
    try:
        photo = await asyncio.wait_for(_product_photo(key), 20)
    except Exception:  # noqa: BLE001  sin foto pública no se inventa una
        log.info("product image search failed")
        return None
    if not photo:
        return None
    try:
        url = _save(_stamp(Image.open(io.BytesIO(photo))))
    except (OSError, ValueError):
        log.info("product image stamp failed")
        return None
    if url:
        _ready[key] = url
    return url
