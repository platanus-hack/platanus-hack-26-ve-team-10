"""Foto de la tarjeta. Si el anuncio no trae imagen, se usa una del producto con la marca de Prais.

Esta foto no la abre la persona: la descarga WhatsApp desde la URL que le damos, y esa
descarga vuelve a entrar por cualquiera de las copias de prais-api (infra/config.sh). Si los
bytes viven en el diccionario de una copia, las demás responden 404, y una tarjeta de carrusel
sin imagen no se envía. Por eso van al bucket (``STORAGE_BUCKET``), y el nombre del objeto sale
del producto: la copia que la genera y la que la sirve llegan al mismo nombre sin hablarse.

La memoria del proceso queda delante, como caché: la copia que acaba de hacer la foto la sirve
sin tocar el bucket. Sin bucket (el caso local) todo vive en memoria, como antes.
"""

import asyncio
import hashlib
import io
import logging
import os
import re
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger("prais.card_image")

WIDTH = 1200
HEIGHT = 630
MARK = "imagen de Prais"
# El token es lo único que llega de afuera: 16 hexadecimales, nada más, nunca una ruta.
TOKEN = re.compile(r"[0-9a-f]{16}")
_MAX_BYTES = 3_000_000
_PREFIX = "cards/"
_LOCAL_MAX = 40
_UNSET = object()
_store: dict[str, bytes] = {}
_bucket: Any = _UNSET


def _key(title: str) -> str:
    return " ".join(title.lower().split()) or "producto"


def _token(title: str) -> str:
    """El nombre del objeto sale del producto, así que no hace falta acordarlo entre copias."""
    return hashlib.sha256(_key(title).encode()).hexdigest()[:16]


def _remember(token: str, data: bytes) -> None:
    _store[token] = data
    while len(_store) > _LOCAL_MAX:
        _store.pop(next(iter(_store)))


def _open_bucket() -> Any:
    name = os.environ.get("STORAGE_BUCKET", "").strip()
    if not name:
        return None
    try:
        from google.cloud import storage

        return storage.Client().bucket(name)
    except Exception:  # noqa: BLE001  sin bucket se sigue con la memoria de esta copia
        log.warning("no storage bucket: card images only work while this instance lives")
        return None


def bucket() -> Any:
    """El bucket, una sola vez. None en local y si el cliente no arranca."""
    global _bucket
    if _bucket is _UNSET:
        _bucket = _open_bucket()
    return _bucket


def _blob(token: str) -> Any:
    return bucket().blob(f"{_PREFIX}{token}.jpg")


async def _in_bucket(token: str) -> bool:
    """Si ya está hecha, ninguna copia vuelve a pagar la búsqueda de la foto."""
    if bucket() is None:
        return False
    try:
        return await asyncio.to_thread(lambda: _blob(token).exists())
    except Exception:  # noqa: BLE001  el bucket no responde: se genera de nuevo
        log.info("card image lookup failed")
        return False


async def _from_bucket(token: str) -> bytes | None:
    if bucket() is None:
        return None

    def read() -> bytes | None:
        blob = _blob(token)
        return blob.download_as_bytes() if blob.exists() else None

    try:
        return await asyncio.to_thread(read)
    except Exception:  # noqa: BLE001  una foto que no baja no tumba la respuesta
        log.info("card image read failed")
        return None


async def _to_bucket(token: str, data: bytes) -> bool:
    if bucket() is None:
        return False
    try:
        await asyncio.to_thread(lambda: _blob(token).upload_from_string(data, content_type="image/jpeg"))
    except Exception:  # noqa: BLE001  se queda en esta copia: peor sería no mandar la tarjeta
        log.warning("card image upload failed")
        return False
    return True


async def read_card_image(token: str) -> bytes | None:
    """La foto, de la memoria de esta copia o del bucket. La pide WhatsApp, no la persona."""
    if not TOKEN.fullmatch(token):
        return None
    data = _store.get(token)
    if data is not None:
        return data
    data = await _from_bucket(token)
    if data is not None:
        _remember(token, data)
    return data


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
    base = public_base()
    if base is None:
        log.warning("card image has no public https base")
        return None
    token = _token(title)
    url = f"{base}/card-images/{token}.jpg"
    if token in _store or await _in_bucket(token):
        return url
    try:
        photo = await asyncio.wait_for(_product_photo(_key(title)), 20)
    except Exception:  # noqa: BLE001  sin foto pública no se inventa una
        log.info("product image search failed")
        return None
    if not photo:
        return None
    try:
        data = _stamp(Image.open(io.BytesIO(photo)))
    except (OSError, ValueError):
        log.info("product image stamp failed")
        return None
    _remember(token, data)
    await _to_bucket(token, data)
    return url
