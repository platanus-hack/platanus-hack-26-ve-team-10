"""Instagram y TikTok con Apify.

Las dos fuentes comparten cliente, caché y lectura de captions, así que van en un archivo.

Una corrida de actor tarda de segundos a minutos y `search_offers` corta a los 8 s: la búsqueda
arranca el actor, lo espera LIVE_WAIT_S y sigue sin esperarlo más. La corrida queda andando y
deja sus publicaciones en la caché, así que la próxima búsqueda del mismo producto sí las ve.
Precalentar antes de una demo es buscar el producto una vez.

Ningún precio se inventa: sale del caption, y solo si está escrito con su moneda. Una publicación
que nombra varios precios no deja ninguno. "Precio al DM" va con price=None, como pide
docs/sources.md.
"""

import asyncio
import json
import logging
import os
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from apify_client import ApifyClientAsync

from app.lib.sources.apify_trust import instagram_trust, tiktok_trust
from app.lib.sources.firecrawl import matches_product, plain, published_prices
from app.lib.types import Channel, Merchant, Money, Offer, SearchQuery, SourceResult

log = logging.getLogger("prais.apify")

INSTAGRAM_ACTOR = "apify/instagram-scraper"
TIKTOK_ACTOR = "clockworks/tiktok-scraper"
# El actor cobra por publicación (unos USD 2,70 por 1.000 en Instagram): el tope va en el input
# y además en max_items, que la API respeta aunque el actor pida más.
RESULTS = 20
POSTS_SINCE = "3 months"
# Publicaciones por comercio en la segunda corrida. Con menos de 3 el puntaje no puede medir
# proporciones ni ritmo, y la cobertura se queda bajo el 40 %.
PROFILE_POSTS = 10
# Lo que la búsqueda espera a un actor recién arrancado. search_offers corta a los 8 s.
LIVE_WAIT_S = 6
CACHE_S = 6 * 60 * 60
# Una corrida sin publicaciones útiles (o que falló) no se repite enseguida: cada una cuesta.
EMPTY_CACHE_S = 15 * 60
# Instagram no dice de qué ciudad es una publicación. La zona del comercio queda sin afinar.
ZONE = "Venezuela"

_cache: dict[tuple[str, str], tuple[float, SourceResult]] = {}
_runs: dict[tuple[str, str], asyncio.Task[None]] = {}

_DELIVERS = re.compile(r"\b(envio|envios|enviamos|delivery|despacho|despachamos|encomienda)\b")
_ASKS_DM = re.compile(r"precios?\s*(?:al|por|via)?\s*(?:dm|inbox|interno|privado|mensaje|whatsapp|wasap)")
# Una cifra con su unidad no va en el hashtag: nadie etiqueta #harinapan1kg ni #iphone15128gb.
_UNITS = {"kg", "kgs", "g", "gr", "grs", "ml", "l", "lt", "lts", "gb", "tb", "mah", "w", "cc",
          "pulgada", "pulgadas", "litro", "litros", "kilo", "kilos", "unidad", "unidades"}  # fmt: skip


def _hashtag(product: str) -> str:
    """El hashtag del producto: "Harina PAN 1 kg" es #harinapan; "iPhone 15 128 GB", #iphone15.

    Instagram no busca por frase: la única entrada que devuelve publicaciones es la página de un
    hashtag. Una cifra seguida de su unidad se cae, porque es la presentación y no el modelo.
    """
    words = re.findall(r"[a-z0-9]+", plain(product))
    tag = []
    for i, word in enumerate(words):
        following = words[i + 1] if i + 1 < len(words) else ""
        if word in _UNITS or (word.isdigit() and following in _UNITS):
            continue
        tag.append(word)
    return "".join(tag[:3])[:30]


def _price(text: str) -> Money | None:
    """El precio de la publicación, solo si no hay dudas de cuál es.

    Muchas tiendas publican el mismo producto en dólares y en bolívares: manda el de dólares. Si
    la publicación lista varios productos con su precio, no se usa ninguno.
    """
    written = {amount: {c for c in currencies if c} for amount, currencies in published_prices(text).items()}
    usd = [amount for amount, currencies in written.items() if amount > 0 and currencies == {"USD"}]
    ves = [amount for amount, currencies in written.items() if amount > 0 and currencies == {"VES"}]
    if len(usd) == 1:
        return Money(usd[0], "USD")
    if not usd and len(ves) == 1:
        return Money(ves[0], "VES")
    return None


def _title(text: str, product: str) -> str:
    line = next((part.strip() for part in text.splitlines() if part.strip()), "")
    line = " ".join(re.sub(r"#\S+", "", line).split())
    return line[:90] if len(line) >= 3 else product


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _seen_at(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _instagram_input(product: str) -> dict[str, Any] | None:
    tag = _hashtag(product)
    if not tag:
        return None
    return {
        # El tipo de URL manda sobre la salida: la del hashtag es la que devuelve publicaciones.
        # searchType "hashtag" devuelve el volumen del hashtag, no sus posts.
        "directUrls": [f"https://www.instagram.com/explore/tags/{tag}/"],
        "resultsType": "posts",
        "resultsLimit": RESULTS,
        "onlyPostsNewerThan": POSTS_SINCE,
        "addParentData": False,
    }


def _moment() -> datetime:
    return datetime.now(UTC)


def _by_owner(items: list[dict[str, Any]], key: str, owner: str) -> list[dict[str, Any]]:
    return [item for item in items if item.get(key) == owner]


def _instagram_profiles(handles: list[str]) -> dict[str, Any]:
    return {
        "directUrls": [f"https://www.instagram.com/{handle}/" for handle in handles],
        "resultsType": "posts",
        "resultsLimit": PROFILE_POSTS,
        "onlyPostsNewerThan": POSTS_SINCE,
        "addParentData": False,
    }


def _instagram_offers(items: list[dict[str, Any]], product: str, now: str) -> SourceResult:
    offers, merchants = [], {}
    for item in items:
        caption = item.get("caption") or ""
        user, url = item.get("ownerUsername"), item.get("url")
        if not user or not url or not matches_product(product, caption):
            continue
        price = _price(caption)
        if price is None and not _ASKS_DM.search(plain(caption)):
            continue
        merchant_id = f"ig:{user}"
        if merchant_id not in merchants:
            merchants[merchant_id] = Merchant(
                id=merchant_id,
                name=item.get("ownerFullName") or user,
                channel="instagram",
                url=f"https://www.instagram.com/{user}/",
                zone=ZONE,
                delivers=bool(_DELIVERS.search(plain(caption))),
                comments=_count(item.get("commentsCount")),
            )
        offers.append(Offer(merchant_id, _title(caption, product), url, price, _seen_at(item.get("timestamp"), now)))
    # El puntaje es de la cuenta, así que lo mide con todas sus publicaciones, no solo con las
    # que coincidieron con el producto.
    trust = {
        merchant_id: instagram_trust({}, _by_owner(items, "ownerUsername", merchant_id[3:]), now=_moment())
        for merchant_id in merchants
    }
    return SourceResult(offers=offers, merchants=list(merchants.values()), trust=trust)


def _tiktok_input(product: str) -> dict[str, Any] | None:
    return {
        "searchQueries": [f"{product} precio Venezuela"],
        "searchSection": "/video",
        "resultsPerPage": RESULTS,
        # Sin proxy venezolano TikTok responde con lo que se ve desde el centro de datos.
        "proxyCountryCode": "VE",
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadSlideshowImages": False,
        "shouldDownloadAvatars": False,
        "shouldDownloadMusicCovers": False,
    }


def _tiktok_profiles(handles: list[str]) -> dict[str, Any]:
    return {
        "profiles": handles,
        "resultsPerPage": PROFILE_POSTS,
        "profileScrapeSections": ["videos"],
        "proxyCountryCode": "VE",
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadSlideshowImages": False,
        "shouldDownloadAvatars": False,
        "shouldDownloadMusicCovers": False,
    }


def _tiktok_offers(items: list[dict[str, Any]], product: str, now: str) -> SourceResult:
    offers, merchants = [], {}
    for item in items:
        author = item.get("authorMeta") or {}
        text = item.get("text") or ""
        user, url = author.get("name"), item.get("webVideoUrl")
        if not user or not url or not matches_product(product, text):
            continue
        price = _price(text)
        if price is None and not _ASKS_DM.search(plain(text)):
            continue
        merchant_id = f"tt:{user}"
        if merchant_id not in merchants:
            merchants[merchant_id] = Merchant(
                id=merchant_id,
                name=author.get("nickName") or user,
                channel="tiktok",
                url=author.get("profileUrl") or f"https://www.tiktok.com/@{user}",
                zone=ZONE,
                delivers=bool(_DELIVERS.search(plain(text))),
                followers=_count(author.get("fans")),
                comments=_count(item.get("commentCount")),
            )
        offers.append(Offer(merchant_id, _title(text, product), url, price, _seen_at(item.get("createTimeISO"), now)))
    trust = {}
    for merchant_id in merchants:
        videos = [item for item in items if (item.get("authorMeta") or {}).get("name") == merchant_id[3:]]
        trust[merchant_id] = tiktok_trust(videos[0].get("authorMeta") or {}, videos, now=_moment())
    return SourceResult(offers=offers, merchants=list(merchants.values()), trust=trust)


async def run_actor(actor: str, run_input: dict[str, Any]) -> list[dict[str, Any]]:
    """Corre el actor hasta que termina y devuelve lo que dejó en su dataset."""
    client = ApifyClientAsync(os.environ["APIFY_TOKEN"])
    # logger=None para que los logs del actor no se mezclen con los de la API.
    run = await client.actor(actor).call(run_input=run_input, max_items=RESULTS, logger=None)
    if run is None:
        return []
    page = await client.dataset(run.default_dataset_id).list_items(clean=True)
    return [item for item in page.items if isinstance(item, dict)]


class ApifySource:
    """Una fuente de Apify. Cada plataforma pone su actor, su input y cómo leer sus publicaciones."""

    def __init__(
        self,
        id: str,
        channel: Channel,
        actor: str,
        run_input: Callable[[str], dict[str, Any] | None],
        read: Callable[[list[dict[str, Any]], str, str], SourceResult],
        profiles: Callable[[list[str]], dict[str, Any]],
    ) -> None:
        self.id = id
        self.channel = channel
        self.actor = actor
        self.enabled = bool(os.environ.get("APIFY_TOKEN"))
        self._run_input = run_input
        self._read = read
        self._profiles = profiles

    async def search(self, query: SearchQuery) -> SourceResult:
        key = (self.id, " ".join(query.text.lower().split()))
        hit = _cache.get(key)
        if hit and time.monotonic() < hit[0]:
            return hit[1]
        task = _runs.get(key)
        if task is None or task.done():
            task = asyncio.create_task(self._fill(key, query.text))
            _runs[key] = task
        # La corrida no se cancela al vencer el plazo: sigue y deja sus publicaciones en la caché.
        await asyncio.wait([task], timeout=LIVE_WAIT_S)
        hit = _cache.get(key)
        return hit[1] if hit else SourceResult(offers=[], merchants=[])

    async def _fill(self, key: tuple[str, str], product: str) -> None:
        started = time.monotonic()
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        items: list[dict[str, Any]] = []
        detail = None
        run_input = self._run_input(product)
        try:
            if run_input:
                items = await run_actor(self.actor, run_input)
        except Exception as error:  # noqa: BLE001  una fuente que falla no tumba la búsqueda
            detail = f"{type(error).__name__}: {error}"
        result = self._read(items, product, now) if items else SourceResult(offers=[], merchants=[])
        # Segunda corrida: las publicaciones recientes de los comercios que sí dieron oferta. La
        # búsqueda deja una publicación por cuenta, y con una sola no se pueden medir las
        # proporciones ni el ritmo que pide el puntaje. Solo se paga por quien ya aportó algo.
        deepened = 0
        if result.merchants:
            handles = [merchant.id.split(":", 1)[-1] for merchant in result.merchants]
            try:
                extra = await run_actor(self.actor, self._profiles(handles))
            except Exception as error:  # noqa: BLE001  sin la segunda corrida el puntaje queda con menos cobertura
                detail = f"{type(error).__name__}: {error}"
                extra = []
            if extra:
                deepened = len(extra)
                items = items + extra
                result = self._read(items, product, now)
        # Lo vacío también se recuerda un rato: si no, cada búsqueda vuelve a pagar una corrida.
        _cache[key] = (time.monotonic() + (CACHE_S if result.offers else EMPTY_CACHE_S), result)
        _runs.pop(key, None)
        log.info(
            "apify %s",
            json.dumps(
                {
                    "source": self.id,
                    "query": product,
                    "seconds": round(time.monotonic() - started, 2),
                    "items": len(items),
                    "offers": len(result.offers),
                    "deepened": deepened,
                    **({"input": run_input} if run_input else {"skipped": "sin hashtag"}),
                    **({"detail": detail} if detail else {}),
                },
                ensure_ascii=False,
            ),
        )


instagram_source = ApifySource(
    "apify-instagram", "instagram", INSTAGRAM_ACTOR, _instagram_input, _instagram_offers, _instagram_profiles
)
tiktok_source = ApifySource("apify-tiktok", "tiktok", TIKTOK_ACTOR, _tiktok_input, _tiktok_offers, _tiktok_profiles)
