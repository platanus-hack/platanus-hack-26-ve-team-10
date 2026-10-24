"""Meta Ads Signals — capa transversal del Trust Score basada en la Biblioteca de Anuncios de Meta.

No genera un score propio: produce AJUSTES (bonus, penalización, banderas rojas, razones)
que se aplican sobre el resultado de ig_trust_score, fb_marketplace_trust_score o
tiktok_trust_score con `apply_meta_adjustments()`.

Fuente: scraping de la web de la Biblioteca vía Apify. La API oficial no sirve para
Venezuela: fuera de la UE solo devuelve anuncios políticos/sociales.

⚠️ Antes de producción:
  - Corre el actor con 2–3 páginas venezolanas que anuncien y ajusta normalize_ad() /
    normalize_page_info() a los campos reales (los nombres varían entre actores y versiones).
  - La "Transparencia de la página" (fecha de creación, cambios de nombre, país de admins)
    no está confirmada en este actor. Si no viene, esas señales quedan en None y no afectan.

pip install apify-client
"""

import inspect
import math
import os
import re
import statistics
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, TypeVar
from urllib.parse import parse_qs, quote, urlparse

from apify_client import ApifyClientAsync

apify = ApifyClientAsync(os.environ.get("APIFY_TOKEN"))
ADS_ACTOR = "curious_coder/facebook-ads-library-scraper"

# ───────────────────────── Tipos ─────────────────────────


@dataclass
class Ad:
    id: str
    page_id: str | None
    page_name: str | None
    start: datetime | None
    end: datetime | None  # None si sigue activo
    is_active: bool
    variants: int  # collation count: copias casi idénticas del mismo anuncio
    text: str
    link_url: str | None


@dataclass
class PageTransparency:
    created_at: datetime | None = None
    name_changes: int | None = None
    admin_countries: list[str] | None = None


# Lo que Prais aporta: desviación de precio para un texto de anuncio.
PriceLookup = Callable[[str], float | None | Awaitable[float | None]]


@dataclass
class Brand:
    name: str
    official_domains: list[str]


@dataclass
class MetaAdsOptions:
    # Código de país esperado de los administradores, p. ej. "VE".
    expected_country: str | None = None
    # Marcas y sus dominios oficiales, para detectar dominios que las imitan.
    brands: list[Brand] = field(default_factory=list)
    price_lookup: PriceLookup | None = None


@dataclass
class Reason:
    text: str
    good: bool


@dataclass
class MetaStats:
    total_ads: int
    active_ads: int
    median_duration_days: int | None
    short_lived_last_30d: int


@dataclass
class MetaAdjustments:
    advertises: bool
    bonus: int  # 0..+5
    penalty: int  # 0..15 (se resta)
    red_flags: list[str]
    reasons: list[Reason]
    # Datos de identidad para alimentar las señales base de IG/FB cuando falten.
    identity_hints: PageTransparency
    stats: MetaStats


# ───────────────────────── Fetch ─────────────────────────


def library_url_for_page(page_id: str) -> str:
    return f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=ALL&view_all_page_id={page_id}"


def library_url_for_keyword(q: str, country: str) -> str:
    return (
        f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country={country}"
        f"&q={quote(q)}&search_type=keyword_unordered"
    )


async def _run_actor(urls: list[str], limit: int = 100) -> list[dict[str, Any]]:
    run = await apify.actor(ADS_ACTOR).call(
        run_input={
            # Verifica estos nombres en el Input tab del actor.
            "urls": [{"url": url} for url in urls],
            "count": limit,
            "scrapeAdDetails": False,
        }
    )
    if run is None:
        return []
    return (await apify.dataset(run.default_dataset_id).list_items()).items


async def fetch_page_ads(page_id: str, limit: int = 100) -> tuple[list[Ad], PageTransparency]:
    items = await _run_actor([library_url_for_page(page_id)], limit)
    return [normalize_ad(i) for i in items], normalize_page_info(items[0] if items else None)


def to_date(v: Any) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, int | float):
        return datetime.fromtimestamp(v if v < 1e12 else v / 1000, UTC)
    try:
        d = datetime.fromisoformat(str(v))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except ValueError:
        return None


def normalize_ad(r: dict[str, Any]) -> Ad:
    snap = r.get("snapshot") or {}
    body = snap.get("body") or {}
    html = (body.get("markup") or {}).get("__html")
    text = (
        body.get("text")
        or (re.sub(r"<[^>]+>", " ", html) if html else None)
        or " ".join(f"{c.get('title') or ''} {c.get('body') or ''}" for c in snap.get("cards") or [])
    )
    cards = snap.get("cards") or [{}]
    try:
        variants = int(r.get("collation_count") or r.get("collationCount") or 1) or 1
    except (TypeError, ValueError):
        variants = 1
    return Ad(
        id=str(r.get("ad_archive_id") or r.get("adArchiveID") or r.get("id")),
        page_id=r.get("page_id") or r.get("pageId") or snap.get("page_id"),
        page_name=r.get("page_name") or r.get("pageName") or snap.get("page_name"),
        start=to_date(r.get("start_date") or r.get("startDate")),
        end=to_date(r.get("end_date") or r.get("endDate")),
        is_active=bool(r.get("is_active", r.get("isActive"))),
        variants=variants,
        text=str(text or "").strip(),
        link_url=snap.get("link_url") or cards[0].get("link_url"),
    )


def normalize_page_info(r: dict[str, Any] | None) -> PageTransparency:
    r = r or {}
    p = r.get("page_info") or r.get("pageInfo") or (r.get("snapshot") or {}).get("page_info") or {}
    countries = p.get("admin_countries") or p.get("page_admin_countries")
    if p.get("name_changes") is not None:
        name_changes = int(p["name_changes"])
    elif isinstance(p.get("previous_names"), list):
        name_changes = len(p["previous_names"])
    else:
        name_changes = None
    return PageTransparency(
        created_at=to_date(p.get("creation_date") or p.get("page_creation_date")),
        name_changes=name_changes,
        admin_countries=[str(c) for c in countries] if isinstance(countries, list) else None,
    )


# ───────────────────────── Helpers ─────────────────────────

DAY = timedelta(days=1)


def clamp(x: float, lo: float = 0, hi: float = 1) -> float:
    return max(lo, min(hi, x))


def median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def duration_days(a: Ad) -> float | None:
    if not a.start:
        return None
    return ((a.end or datetime.now(UTC)) - a.start) / DAY


def host_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        # Meta envuelve los links en l.facebook.com/l.php?u=...
        inner = parse_qs(urlparse(url).query).get("u", [None])[0]
        host = urlparse(inner or url).hostname
        return host.removeprefix("www.").lower() if host else None
    except ValueError:
        return None


def impersonated_brand(host: str, brands: list[Brand]) -> str | None:
    """Dominio que imita a una marca.

    Contiene el nombre de la marca pero no es un dominio oficial ni subdominio de uno
    (p. ej. samsung-ve-ofertas.shop).
    """
    flat = re.sub(r"[^a-z0-9]", "", host)
    for b in brands:
        key = re.sub(r"[^a-z0-9]", "", b.name.lower())
        if not key or key not in flat:
            continue
        official = any(host == d or host.endswith(f".{d}") for d in b.official_domains)
        if not official:
            return b.name
    return None


async def _lookup(price_lookup: PriceLookup, text: str) -> float | None:
    result = price_lookup(text)
    return await result if inspect.isawaitable(result) else result


# ───────────────────────── Señales ─────────────────────────

SHORT_LIVED_DAYS = 3
SHORT_LIVED_THRESHOLD = 10  # ≥ 10 anuncios cortos en 30 días → rotación
LONG_RUNNING_DAYS = 30


async def compute_meta_adjustments(
    ads: list[Ad],
    page: PageTransparency,
    opts: MetaAdsOptions | None = None,
) -> MetaAdjustments:
    opts = opts or MetaAdsOptions()
    reasons: list[Reason] = []
    red_flags: list[str] = []
    bonus = 0
    penalty = 0

    now = datetime.now(UTC)
    durations = [d for d in (duration_days(a) for a in ads) if d is not None]
    med_dur = median(durations)
    active = [a for a in ads if a.is_active]

    def is_short_lived(a: Ad) -> bool:
        d = duration_days(a)
        return not a.is_active and d is not None and d <= SHORT_LIVED_DAYS and a.start is not None and now - a.start <= 30 * DAY

    short_lived = [a for a in ads if is_short_lived(a)]
    # Cada anuncio corto con muchas variantes cuenta como varios intentos.
    short_lived_weighted = sum(min(a.variants, 5) for a in short_lived)

    # ── Sin anuncios: no afecta. La mayoría de los vendedores pequeños no anuncia. ──
    if not ads:
        return MetaAdjustments(False, 0, 0, [], [], page, MetaStats(0, 0, None, 0))

    # 1. Bonus por anuncios de larga duración (hasta +5).
    if med_dur is not None and med_dur >= LONG_RUNNING_DAYS and short_lived_weighted < SHORT_LIVED_THRESHOLD:
        bonus = round_half_up(5 * clamp(med_dur / 90))  # 30 días → ~2, 90+ días → 5
        reasons.append(Reason(f"Anuncia de forma sostenida (anuncios de ~{round_half_up(med_dur)} días)", True))

    # 2. Rotación rápida (−15): patrón de evasión de moderación.
    if short_lived_weighted >= SHORT_LIVED_THRESHOLD:
        penalty += 15
        reasons.append(Reason(f"{len(short_lived)} anuncios que duraron {SHORT_LIVED_DAYS} días o menos en el último mes", False))

    # 3. Transparencia: cambios de nombre + administradores fuera del país.
    foreign_admins = (
        [c for c in page.admin_countries if c.upper() != opts.expected_country.upper()]
        if page.admin_countries is not None and opts.expected_country
        else None
    )
    name_changes = page.name_changes or 0
    if name_changes >= 2 and foreign_admins:
        red_flags.append(f"Página renombrada {name_changes} veces y administrada desde {', '.join(foreign_admins)}")
    else:
        if name_changes >= 2:
            reasons.append(Reason(f"La página cambió de nombre {name_changes} veces", False))
        if foreign_admins:
            reasons.append(Reason(f"Administrada desde {', '.join(foreign_admins)}", False))

    # 4. Dominios de destino que imitan una marca.
    hosts = list(dict.fromkeys(h for h in (host_of(a.link_url) for a in ads) if h))
    for h in hosts:
        brand = impersonated_brand(h, opts.brands)
        if brand:
            red_flags.append(f"Anuncios que llevan a {h}, que imita a {brand}")

    # 5. Precio del anuncio fuera de mercado (usa la mediana de Prais).
    if opts.price_lookup:
        recent = (active or ads)[:15]
        worst: float | None = None
        for a in recent:
            if not a.text:
                continue
            dev = await _lookup(opts.price_lookup, a.text)
            if dev is not None and (worst is None or dev < worst):
                worst = dev
        if worst is not None and worst <= -0.5:
            red_flags.append(f"Anuncia precios {round_half_up(-worst * 100)}% bajo el mercado")
        elif worst is not None and worst <= -0.3:
            penalty += 5
            reasons.append(Reason(f"Algún anuncio con precio {round_half_up(-worst * 100)}% bajo el mercado", False))

    return MetaAdjustments(
        advertises=True,
        bonus=bonus,
        penalty=min(penalty, 15),
        red_flags=red_flags,
        reasons=reasons,
        identity_hints=page,
        stats=MetaStats(
            total_ads=len(ads),
            active_ads=len(active),
            median_duration_days=round_half_up(med_dur) if med_dur is not None else None,
            short_lived_last_30d=len(short_lived),
        ),
    )


# ───────────────────────── Aplicación sobre cualquier TrustResult ─────────────────────────


class AnyTrustResult(Protocol):
    score: int | None
    verdict: str
    red_flags: list[str]
    reasons: list[Any]


T = TypeVar("T", bound=AnyTrustResult)


def apply_meta_adjustments(result: T, adj: MetaAdjustments) -> T:
    """Aplica los ajustes de Meta Ads sobre el resultado de IG, Marketplace o TikTok."""
    reasons = [*adj.reasons, *result.reasons]
    red_flags = [*result.red_flags, *adj.red_flags]

    if red_flags:
        return replace(result, score=0, verdict="riesgosa", red_flags=red_flags, reasons=reasons)
    if result.score is None:
        return replace(result, reasons=reasons)  # sin datos base: no inventamos un número

    score = max(0, min(100, result.score + adj.bonus - adj.penalty))
    verdict = "confiable" if score >= 75 else "precaucion" if score >= 50 else "riesgosa"
    return replace(result, score=score, verdict=verdict, red_flags=red_flags, reasons=reasons)


async def check_page_ads(page_id: str, opts: MetaAdsOptions | None = None) -> MetaAdjustments:
    """Atajo: trae los anuncios de una página y devuelve los ajustes."""
    ads, page = await fetch_page_ads(page_id)
    return await compute_meta_adjustments(ads, page, opts)


# ───────────────────────── Radar de estafas ─────────────────────────


@dataclass
class RadarHit:
    page_id: str | None
    page_name: str | None
    ad_id: str
    deviation: float
    text: str


async def scam_radar(
    keywords: list[str],
    price_lookup: PriceLookup,
    country: str = "VE",
    threshold: float = -0.5,
) -> list[RadarHit]:
    """Busca anuncios activos con precios muy por debajo del mercado.

    Busca por palabra clave en un país. Pensado para correr a diario (scheduled task /
    n8n) y alimentar la lista de reportes de Prais antes de que un usuario pregunte.
    """
    items = await _run_actor([library_url_for_keyword(k, country) for k in keywords], 200)
    hits: list[RadarHit] = []
    for ad in (normalize_ad(i) for i in items):
        if not ad.text:
            continue
        dev = await _lookup(price_lookup, ad.text)
        if dev is not None and dev <= threshold:
            hits.append(RadarHit(ad.page_id, ad.page_name, ad.id, dev, ad.text[:280]))
    return sorted(hits, key=lambda h: h.deviation)


# ───────────────────────── Ejemplo ─────────────────────────
#
# from ig_trust_score import ExternalInputs, check_account
#
# base = await check_account("tienda_ejemplo", ExternalInputs(price_deviation=-0.1, expected_country="Venezuela"))
# adj = await check_page_ads("123456789012345", MetaAdsOptions(
#     expected_country="VE",
#     brands=[Brand("Samsung", ["samsung.com"]), Brand("Apple", ["apple.com"])],
#     price_lookup=prais.price_deviation_from_text,  # tu función de Prais
# ))
# final = apply_meta_adjustments(base, adj)
#
# Radar diario:
# hits = await scam_radar(["iphone", "playstation 5", "starlink"], prais.price_deviation_from_text)
