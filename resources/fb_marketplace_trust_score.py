"""FB Marketplace Trust Score — puntaje de seguridad de un vendedor/anuncio de Facebook Marketplace.

Actor base: deepmine/facebook-marketplace-scraper (con "Add listing details" activo trae
sellerJoinTime, sellerRatingAverage y sellerRatingCount sin cookies).
Marketplace solo se muestra a visitantes sin sesión desde IPs residenciales → proxy residencial.

⚠️ Antes de producción:
  - Corre el actor en Apify Console con anuncios reales de Venezuela y ajusta normalize_listing().
  - Verifica si el actor acepta la URL del perfil de vendedor
    (facebook.com/marketplace/profile/<seller_id>) para traer sus otros anuncios.
  - Calificaciones e insignias son BONUS (+10 máx.), no señal base: en Venezuela casi
    nadie califica en Marketplace. Si el actor no las trae, no pasa nada.

pip install apify-client
"""

import math
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from apify_client import ApifyClientAsync

apify = ApifyClientAsync(os.environ.get("APIFY_TOKEN"))
MARKETPLACE_ACTOR = "deepmine/facebook-marketplace-scraper"

# ───────────────────────── Tipos ─────────────────────────

Verdict = Literal["confiable", "precaucion", "riesgosa", "sin_datos"]


@dataclass
class Seller:
    id: str | None
    name: str | None
    joined_facebook: datetime | None
    rating_avg: float | None
    rating_count: int | None
    badges: list[str] | None


@dataclass
class Listing:
    id: str
    url: str | None
    title: str
    description: str
    price: float | None
    photos: list[str]
    city: str | None
    created_at: datetime | None
    seller: Seller


@dataclass
class ExternalInputs:
    # Precio vs. mediana de mercado (Prais): -0.35 = 35% más barato.
    price_deviation: float | None = None
    # Reportes de estafa verificados contra este vendedor.
    verified_reports: int | None = None
    # Cuántas fotos del anuncio aparecen (por hash perceptual) en anuncios de OTROS vendedores
    # dentro de la base de Prais. Fotos robadas = señal fuerte de estafa.
    photos_seen_elsewhere: int | None = None


@dataclass
class Signal:
    key: str
    weight: int
    value: float | None
    reason: str | None = None
    good: bool = False


@dataclass
class Reason:
    text: str
    good: bool


@dataclass
class TrustResult:
    listing_id: str
    seller_id: str | None
    score: int | None
    coverage: float
    verdict: Verdict
    red_flags: list[str] = field(default_factory=list)
    reasons: list[Reason] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)


# ───────────────────────── Fetch ─────────────────────────


async def _run_actor(urls: list[str], max_items: int = 50) -> list[dict[str, Any]]:
    run = await apify.actor(MARKETPLACE_ACTOR).call(
        run_input={
            "startUrls": [{"url": url} for url in urls],
            "includeListingDetails": True,  # verifica el nombre exacto en el input schema ("Add listing details")
            "maxItems": max_items,
            "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"], "apifyProxyCountry": "VE"},
        }
    )
    if run is None:
        return []
    return (await apify.dataset(run.default_dataset_id).list_items()).items


async def fetch_listing(item_url: str) -> Listing | None:
    items = await _run_actor([item_url], 1)
    return normalize_listing(items[0]) if items else None


async def fetch_seller_listings(seller_id: str) -> list[Listing]:
    try:
        items = await _run_actor([f"https://www.facebook.com/marketplace/profile/{seller_id}"], 50)
        return [normalize_listing(i) for i in items]
    except Exception:  # noqa: BLE001  si el actor no soporta perfiles, la señal de historial queda en None
        return []


def _photo_url(p: Any) -> str | None:
    if isinstance(p, dict):
        return (p.get("image") or {}).get("uri") or p.get("url")
    return p or None


def normalize_listing(r: dict[str, Any]) -> Listing:
    price = (r.get("listingPrice") or {}).get("amount", r.get("price"))
    photos = [u for u in (_photo_url(p) for p in r.get("listingPhotos") or r.get("photos") or []) if u]
    badges = r.get("commerce_badges_info") or r.get("sellerBadges")
    seller_obj = r.get("marketplaceListingSeller") or {}
    creation = r.get("creationTime")
    return Listing(
        id=str(r.get("id") or r.get("listingId")),
        url=r.get("itemUrl") or r.get("url"),
        title=r.get("marketplaceListingTitle") or r.get("title") or "",
        description=(r.get("redactedDescription") or {}).get("text") or r.get("description") or "",
        price=float(price) if price is not None else None,
        photos=photos,
        city=(r.get("locationText") or {}).get("text") or r.get("city"),
        created_at=to_date(creation) if creation else None,
        seller=Seller(
            id=r.get("sellerId") or seller_obj.get("id"),
            name=r.get("sellerName") or seller_obj.get("name"),
            joined_facebook=to_date(r.get("sellerJoinTime")),
            rating_avg=r.get("sellerRatingAverage"),
            rating_count=r.get("sellerRatingCount"),
            badges=[
                (b.get("name") or b.get("badge_type") or str(b)) if isinstance(b, dict) else str(b) for b in badges
            ]
            if isinstance(badges, list)
            else None,
        ),
    )


def to_date(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, int | float):
        return datetime.fromtimestamp(v if v < 1e12 else v / 1000, UTC)
    try:
        d = datetime.fromisoformat(str(v))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except ValueError:
        pass
    y = re.search(r"(19|20)\d{2}", str(v))  # "Se unió en 2016"
    return datetime(int(y.group(0)), 1, 1, tzinfo=UTC) if y else None


# ───────────────────────── Helpers ─────────────────────────


def clamp(x: float, lo: float = 0, hi: float = 1) -> float:
    return max(lo, min(hi, x))


def months_since(d: datetime) -> float:
    return (datetime.now(UTC) - d).total_seconds() / (60 * 60 * 24 * 30.44)


def days_since(d: datetime) -> float:
    return months_since(d) * 30.44


def round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


# Mismos 3 patrones que Instagram (sin pagos ni DM: son normales en ventas legítimas en Venezuela).
RISK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(sin|no hay|no se aceptan)\s+devoluci", re.IGNORECASE), "No acepta devoluciones"),
    (re.compile(r"(últimas?|ultimas?)\s+unidades|solo\s+(por\s+)?hoy|quedan\s+\d+", re.IGNORECASE), "Usa presión de urgencia"),
    (re.compile(r"(precio|oferta)\s+(de\s+)?(locura|regalado|remate)", re.IGNORECASE), "Precios 'demasiado buenos'"),
]

STRONG_BADGES = re.compile(r"super|súper|highly rated|muy bien calificad", re.IGNORECASE)
OTHER_BADGES = re.compile(r"responsive|receptiv|reliable|confiable|shipper|envío", re.IGNORECASE)

# ───────────────────────── Señales ─────────────────────────


def compute_signals(listing: Listing, history: list[Listing] | None, ext: ExternalInputs) -> list[Signal]:
    s: list[Signal] = []
    seller = listing.seller

    # Nota: calificaciones e insignias NO están aquí. En Venezuela casi nadie califica en
    # Marketplace, así que funcionan como BONUS (ver reputation_bonus), no como señal base.

    # ── Identidad (20) ──

    # 3. Antigüedad en Facebook (15): < 6 meses → 0, 5 años → 1.
    if seller.joined_facebook:
        m = months_since(seller.joined_facebook)
        v = 0 if m < 6 else clamp(math.log(m / 6) / math.log(10))
        s.append(Signal("fb_age", 15, v, good=v >= 0.6,
                        reason=f"En Facebook desde {seller.joined_facebook.year}" if v >= 0.6 else f"Perfil de Facebook reciente ({round_half_up(m)} meses)"))
    else:
        s.append(Signal("fb_age", 15, None))

    # 4. Coherencia de ubicación (5): mismo vendedor publicando en muchas ciudades = sospechoso.
    if history and len(history) >= 3:
        cities = {h.city for h in history if h.city}
        v = clamp(1 - (len(cities) - 2) / 3)  # ≤2 ciudades → 1, ≥5 → 0
        s.append(Signal("location", 5, v, f"Publica en {len(cities)} ciudades distintas" if v < 1 else None, v == 1))
    else:
        s.append(Signal("location", 5, None))

    # ── Comportamiento del vendedor (40) — reemplaza a la reputación como señal principal ──

    # 5. Historial de publicaciones (20).
    #    Patrón de cuenta hackeada: perfil viejo, sin calificaciones, que de repente
    #    publica muchos artículos en pocos días.
    if history is not None:
        recent = sum(1 for h in history if h.created_at and days_since(h.created_at) <= 7)
        old = len(history) - recent
        no_ratings = not seller.rating_count
        v = 0.5
        if old >= 5:
            v = 1  # historial sostenido
        elif old >= 1:
            v = 0.75
        burst = recent >= 8 and old == 0  # ráfaga sin historial previo
        if burst:
            v = 0
        looks_hacked = burst and no_ratings and seller.joined_facebook is not None and months_since(seller.joined_facebook) > 24
        if looks_hacked:
            reason = f"Perfil antiguo sin ventas previas que publicó {recent} anuncios en 7 días (posible cuenta robada)"
        elif burst:
            reason = f"{recent} anuncios en 7 días sin historial previo"
        elif old >= 5:
            reason = "Historial de ventas sostenido"
        else:
            reason = None
        s.append(Signal("history", 20, v, reason, v >= 0.75))
    else:
        s.append(Signal("history", 20, None))

    # 6. Fotos originales (20): fotos que también aparecen en anuncios de otros vendedores.
    if ext.photos_seen_elsewhere is not None:
        v = 1 if ext.photos_seen_elsewhere == 0 else 0
        s.append(Signal("photos_original", 20, v, "Fotos propias" if v == 1 else "Fotos usadas también por otros vendedores", v == 1))
    else:
        s.append(Signal("photos_original", 20, None))

    # ── Calidad del anuncio (10) ──

    # 7. Completitud (5): fotos suficientes y descripción con contenido.
    photos_ok = clamp(len(listing.photos) / 4)  # ≥4 fotos → 1
    desc_ok = clamp(len(listing.description.split()) / 25)  # ≥25 palabras → 1
    v = 0.5 * photos_ok + 0.5 * desc_ok
    s.append(Signal("completeness", 5, v, "Anuncio con pocas fotos o sin descripción" if v < 0.4 else None, v >= 0.7))

    # 8. Lenguaje de riesgo (5)
    text = f"{listing.title}\n{listing.description}"
    hits = [label for pattern, label in RISK_PATTERNS if pattern.search(text)]
    s.append(Signal("risk_language", 5, clamp(1 - len(hits) / 3), " · ".join(hits) or None, not hits))

    # ── Contexto Prais (30) — los reportes de Prais son la capa de reputación que FB no da ──

    # 9. Precio vs. mercado (20)
    if ext.price_deviation is not None:
        d = ext.price_deviation
        v = 1 if d >= -0.15 else clamp(1 - (-d - 0.15) / 0.3)
        s.append(Signal("price_anomaly", 20, v, good=v == 1,
                        reason=f"Precio {round_half_up(-d * 100)}% bajo el mercado" if v < 1 else "Precio en línea con el mercado"))
    else:
        s.append(Signal("price_anomaly", 20, None))

    # 10. Reportes verificados (10)
    if ext.verified_reports is not None:
        v = clamp(1 - ext.verified_reports / 3)
        s.append(Signal("reports", 10, v, good=v == 1,
                        reason=f"{ext.verified_reports} reporte(s) de estafa verificados" if ext.verified_reports else None))
    else:
        s.append(Signal("reports", 10, None))

    return s


def reputation_bonus(listing: Listing) -> tuple[int, str | None]:
    """Bonus de reputación: suma hasta +10 puntos sobre el score base, nunca resta.

    Quien no tiene calificaciones (la mayoría en Venezuela) no pierde nada.
    Una mala calificación se maneja como bandera roja (< 3★ con ≥ 5 calificaciones).
    """
    seller = listing.seller
    points = 0.0
    parts: list[str] = []

    # Calificaciones: hasta +7. Promedio bayesiano (prior 3.5★, peso 5) para que
    # un 5★ con 1 calificación no valga lo mismo que un 4.8★ con 40.
    if seller.rating_avg is not None and (seller.rating_count or 0) >= 5:
        n = seller.rating_count
        smoothed = (5 * 3.5 + n * seller.rating_avg) / (5 + n)
        points += 7 * clamp((smoothed - 4.0) / 0.8)  # ≤4.0 → 0, ≥4.8 → +7
        parts.append(f"{seller.rating_avg:.1f}★ con {n} calificaciones")

    # Insignias: hasta +3.
    if seller.badges:
        if any(STRONG_BADGES.search(b) for b in seller.badges):
            points += 3
        elif any(OTHER_BADGES.search(b) for b in seller.badges):
            points += 1.5
        parts.append(f"Insignias: {', '.join(seller.badges)}")

    return round_half_up(points), " · ".join(parts) or None


def red_flags(listing: Listing, ext: ExternalInputs) -> list[str]:
    f: list[str] = []
    seller = listing.seller
    if ext.price_deviation is not None and ext.price_deviation <= -0.5:
        f.append("Precio más de 50% bajo el mercado")
    if (ext.photos_seen_elsewhere or 0) >= 2:
        f.append("Varias fotos copiadas de otros vendedores")
    if seller.rating_avg is not None and (seller.rating_count or 0) >= 5 and seller.rating_avg < 3:
        f.append("Calificación menor a 3★")
    if seller.joined_facebook and months_since(seller.joined_facebook) < 1:
        f.append("Perfil de Facebook creado hace menos de un mes")
    if (ext.verified_reports or 0) >= 3:
        f.append("Múltiples reportes de estafa verificados")
    return f


# ───────────────────────── Score ─────────────────────────

MIN_COVERAGE = 0.4


def score_listing(listing: Listing, history: list[Listing] | None, ext: ExternalInputs | None = None) -> TrustResult:
    ext = ext or ExternalInputs()
    signals = compute_signals(listing, history, ext)
    flags = red_flags(listing, ext)
    total = sum(s.weight for s in signals)
    avail = [s for s in signals if s.value is not None]
    w_avail = sum(s.weight for s in avail)
    coverage = w_avail / total

    ranked = sorted(
        (s for s in signals if s.reason),
        key=lambda s: s.weight * (1 - (s.value if s.value is not None else 1)),
        reverse=True,
    )
    reasons = [Reason(s.reason, s.good) for s in ranked]

    def result(score: int | None, verdict: Verdict, flags: list[str]) -> TrustResult:
        return TrustResult(listing.id, listing.seller.id, score, coverage, verdict, flags, reasons, signals)

    if flags:
        return result(0, "riesgosa", flags)
    if coverage < MIN_COVERAGE:
        return result(None, "sin_datos", [])

    base_score = 100 * sum(s.weight * s.value for s in avail) / w_avail
    bonus_points, bonus_reason = reputation_bonus(listing)
    if bonus_reason:
        reasons.insert(0, Reason(bonus_reason, bonus_points > 0))
    score = min(100, round_half_up(base_score + bonus_points))
    verdict: Verdict = "confiable" if score >= 75 else "precaucion" if score >= 50 else "riesgosa"
    return result(score, verdict, [])


# ───────────────────────── Orquestación ─────────────────────────


async def check_listing(item_url: str, ext: ExternalInputs | None = None) -> TrustResult:
    listing = await fetch_listing(item_url)
    if not listing:
        return TrustResult(item_url, None, None, 0, "sin_datos", reasons=[Reason("No se pudo leer el anuncio", False)])
    history = await fetch_seller_listings(listing.seller.id) if listing.seller.id else []
    return score_listing(listing, history or None, ext)


# Ejemplo:
# asyncio.run(check_listing(
#     "https://www.facebook.com/marketplace/item/1234567890/",
#     ExternalInputs(price_deviation=-0.32, verified_reports=0, photos_seen_elsewhere=0),
# ))
