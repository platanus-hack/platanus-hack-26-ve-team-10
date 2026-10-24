"""TikTok Trust Score — puntaje de seguridad de una cuenta de TikTok usando Apify.

Actores:
  - clockworks/tiktok-profile-scraper   (perfil en authorMeta + últimos videos)
  - clockworks/tiktok-comments-scraper  (comentarios de los videos más recientes)

⚠️ Antes de producción:
  - Haz una corrida en Apify Console y ajusta normalize() a los campos reales.
  - La fecha de creación NO viene en el actor: se deriva del ID numérico del usuario
    (los 32 bits altos son un timestamp Unix). Verifícalo con 3–4 cuentas de fecha conocida;
    si no cuadra, la señal queda en None y no penaliza.

pip install apify-client
"""

import math
import os
import re
import statistics
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Literal

from apify_client import ApifyClientAsync

apify = ApifyClientAsync(os.environ.get("APIFY_TOKEN"))
PROFILE_ACTOR = "clockworks/tiktok-profile-scraper"
COMMENT_ACTOR = "clockworks/tiktok-comments-scraper"

# ───────────────────────── Tipos ─────────────────────────

Verdict = Literal["confiable", "precaucion", "riesgosa", "sin_datos"]


@dataclass
class Video:
    url: str | None
    created_at: datetime | None
    plays: int
    likes: int
    comments: int
    shares: int
    saves: int
    caption: str
    is_ad: bool


@dataclass
class Profile:
    username: str
    user_id: str | None
    created_at: datetime | None  # derivada del user_id
    region: str | None
    bio: str
    followers: int | None
    total_hearts: int | None  # likes acumulados de toda la cuenta
    video_count: int | None
    is_private: bool
    videos: list[Video]


@dataclass
class Comment:
    text: str | None = None
    author: str | None = None


@dataclass
class ExternalInputs:
    # Precio vs. mediana de mercado (Prais): -0.35 = 35% más barato.
    price_deviation: float | None = None
    # Reportes de estafa verificados contra esta cuenta.
    verified_reports: int | None = None
    # Código de región esperado, p. ej. "VE".
    expected_region: str | None = None


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
    username: str
    score: int | None
    coverage: float
    verdict: Verdict
    red_flags: list[str] = field(default_factory=list)
    reasons: list[Reason] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)


# ───────────────────────── Fetch ─────────────────────────


async def _run_actor(actor: str, run_input: dict[str, Any]) -> list[dict[str, Any]]:
    run = await apify.actor(actor).call(run_input=run_input)
    if run is None:
        return []
    return (await apify.dataset(run.default_dataset_id).list_items()).items


async def fetch_profile(username: str, videos: int = 20) -> Profile | None:
    items = await _run_actor(
        PROFILE_ACTOR,
        {
            "profiles": [username.lstrip("@")],
            "resultsPerPage": videos,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
        },
    )
    return normalize(items) if items else None


async def fetch_comments(video_urls: list[str], per_video: int = 30) -> list[Comment]:
    if not video_urls:
        return []
    items = await _run_actor(COMMENT_ACTOR, {"postURLs": video_urls, "commentsPerPost": per_video})
    return [Comment(text=c.get("text"), author=c.get("uniqueId") or (c.get("user") or {}).get("uniqueId")) for c in items]


def normalize(items: list[dict[str, Any]]) -> Profile:
    """El actor devuelve un item por video, cada uno con authorMeta repetido."""
    a = items[0].get("authorMeta") or {}
    user_id = str(a["id"]) if a.get("id") else None
    videos = []
    for v in items:
        if not (v.get("id") or v.get("webVideoUrl")):
            continue
        if v.get("createTimeISO"):
            created = datetime.fromisoformat(v["createTimeISO"])
        elif v.get("createTime"):
            created = datetime.fromtimestamp(v["createTime"], UTC)
        else:
            created = None
        videos.append(
            Video(
                url=v.get("webVideoUrl"),
                created_at=created,
                plays=v.get("playCount") or 0,
                likes=v.get("diggCount") or 0,
                comments=v.get("commentCount") or 0,
                shares=v.get("shareCount") or 0,
                saves=v.get("collectCount") or 0,
                caption=v.get("text") or "",
                is_ad=bool(v.get("isAd")),
            )
        )
    return Profile(
        username=a.get("name") or a.get("uniqueId"),
        user_id=user_id,
        created_at=date_from_tiktok_id(user_id) if user_id else None,
        region=a.get("region"),
        bio=a.get("signature") or "",
        followers=a.get("fans"),
        total_hearts=a.get("heart"),
        video_count=a.get("video"),
        is_private=bool(a.get("privateAccount")),
        videos=videos,
    )


def date_from_tiktok_id(user_id: str) -> datetime | None:
    """Los IDs de TikTok llevan un timestamp Unix en sus 32 bits altos."""
    try:
        d = datetime.fromtimestamp(int(user_id) >> 32, UTC)
    except (ValueError, OverflowError, OSError):
        return None
    # Fuera de rango → ID viejo sin timestamp.
    return d if d.year >= 2014 and d <= datetime.now(UTC) else None


# ───────────────────────── Helpers ─────────────────────────


def clamp(x: float, lo: float = 0, hi: float = 1) -> float:
    return max(lo, min(hi, x))


def median(xs: list[float]) -> float:
    return statistics.median(xs) if xs else 0


def mean(xs: list[float]) -> float:
    return statistics.fmean(xs) if xs else 0


def stdev(xs: list[float]) -> float:
    return statistics.pstdev(xs) if xs else 0


def months_since(d: datetime) -> float:
    return (datetime.now(UTC) - d).total_seconds() / (60 * 60 * 24 * 30.44)


def round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


# Mismos 3 patrones que IG y Marketplace (sin pagos ni DM/WhatsApp: normales en Venezuela).
RISK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(sin|no hay|no se aceptan)\s+devoluci", re.IGNORECASE), "No acepta devoluciones"),
    (re.compile(r"(últimas?|ultimas?)\s+unidades|solo\s+(por\s+)?hoy|quedan\s+\d+", re.IGNORECASE), "Usa presión de urgencia"),
    (re.compile(r"(precio|oferta)\s+(de\s+)?(locura|regalado|remate)", re.IGNORECASE), "Precios 'demasiado buenos'"),
]


def is_real_comment(text: str | None) -> bool:
    # Más de 3 palabras y no solo emojis o signos (se pide al menos una letra o número).
    return bool(text) and len(text.split()) > 3 and re.search(r"[^\W_]", text) is not None


# ───────────────────────── Señales ─────────────────────────


def compute_signals(p: Profile, comments: list[Comment], ext: ExternalInputs) -> list[Signal]:
    s: list[Signal] = []
    # Los anuncios pagados inflan vistas: se excluyen de las métricas orgánicas.
    vids = [v for v in p.videos if not v.is_ad and v.plays > 0]
    enough = len(vids) >= 3

    # ── Identidad (20) ──

    # 1. Antigüedad (15): derivada del ID. < 3 meses → 0, 36 meses → 1.
    if p.created_at:
        m = months_since(p.created_at)
        v = 0 if m < 3 else clamp(math.log(m / 3) / math.log(12))
        s.append(Signal("age", 15, v, good=v >= 0.6,
                        reason=f"Cuenta desde {p.created_at.year}" if v >= 0.6 else f"Cuenta reciente ({round_half_up(m)} meses)"))
    else:
        s.append(Signal("age", 15, None))

    # 2. Región coherente (5)
    if p.region and ext.expected_region:
        ok = p.region.upper() == ext.expected_region.upper()
        s.append(Signal("region", 5, 1 if ok else 0, None if ok else f"Cuenta registrada en {p.region}, no en {ext.expected_region}", ok))
    else:
        s.append(Signal("region", 5, None))

    # ── Autenticidad de la audiencia (40) ──
    # En TikTok las vistas vienen del algoritmo, no de los seguidores, y los picos virales
    # son normales. Por eso NO se mide likes/seguidores ni la variación de vistas:
    # se mide la PROPORCIÓN entre interacciones, que es lo que delata vistas compradas.

    # 3. Likes / vistas (15): orgánico suele estar entre ~2% y ~15%.
    if enough:
        r = median([v.likes / v.plays for v in vids])
        if r < 0.005:
            v = 0.0
        elif r < 0.02:
            v = (r - 0.005) / 0.015
        elif r <= 0.2:
            v = 1.0
        else:
            v = clamp(1 - (r - 0.2) / 0.2)  # demasiado alto → likes comprados
        if v >= 0.7:
            reason = "Interacción acorde a sus vistas"
        elif r < 0.02:
            reason = "Muchas vistas pero casi sin likes (posibles vistas compradas)"
        else:
            reason = "Likes desproporcionados para sus vistas (posibles likes comprados)"
        s.append(Signal("like_view_ratio", 15, v, reason, v >= 0.7))
    else:
        s.append(Signal("like_view_ratio", 15, None))

    # 4. Consistencia de esa proporción entre videos (5): las compras de vistas se notan
    #    como videos con ratio muy distinto al resto.
    if enough:
        ratios = [v.likes / v.plays for v in vids]
        cv = stdev(ratios) / mean(ratios) if mean(ratios) > 0 else 2
        v = clamp(1 - (cv - 0.5) / 1.0)  # cv ≤ 0.5 → 1, ≥ 1.5 → 0
        s.append(Signal("ratio_consistency", 5, v, "Algunos videos con interacción muy distinta al resto" if v < 0.4 else None, v >= 0.6))
    else:
        s.append(Signal("ratio_consistency", 5, None))

    # 5. Corazones totales / seguidores (5): seguidores comprados no dan likes.
    #    Una cuenta real casi siempre acumula más corazones que seguidores.
    if p.followers and p.followers >= 500 and p.total_hearts is not None:
        r = p.total_hearts / p.followers
        v = clamp((r - 0.5) / 2.5)  # ≤ 0.5 → 0, ≥ 3 → 1
        s.append(Signal("hearts_per_follower", 5, v, good=v >= 0.6,
                        reason=f"Pocos likes totales para {fmt_int(p.followers)} seguidores (posibles seguidores comprados)" if v < 0.3 else None))
    else:
        s.append(Signal("hearts_per_follower", 5, None))

    # 6. Calidad de comentarios (10)
    if len(comments) >= 10:
        real = sum(is_real_comment(c.text) for c in comments) / len(comments)
        authors = len({c.author for c in comments}) / len(comments)
        v = 0.7 * clamp(real / 0.4) + 0.3 * clamp(authors / 0.7)
        s.append(Signal("comment_quality", 10, v, good=v >= 0.6,
                        reason="Comentarios de personas reales y variadas" if v >= 0.6 else "Comentarios genéricos o repetidos"))
    else:
        s.append(Signal("comment_quality", 10, None))

    # 7. Compartidos + guardados (5): son caros de falsificar y señalan interés real en el producto.
    if enough:
        r = median([(v.shares + v.saves) / max(v.likes, 1) for v in vids])
        v = clamp(r / 0.05)  # ≥ 5% de los likes → 1
        s.append(Signal("shares_saves", 5, v, "La gente guarda y comparte sus videos" if v >= 0.6 else None, v >= 0.6))
    else:
        s.append(Signal("shares_saves", 5, None))

    # ── Comportamiento (10) ──

    # 8. Ritmo de publicación (5)
    days = [v.created_at.date().isoformat() for v in vids if v.created_at]
    if len(days) >= 5:
        burst = max(days.count(d) for d in set(days)) / len(days)
        v = clamp(1 - (burst - 0.25) / 0.5)
        s.append(Signal("posting_rhythm", 5, v, "Gran parte de los videos se subieron el mismo día" if v < 0.5 else None, v >= 0.6))
    else:
        s.append(Signal("posting_rhythm", 5, None))

    # 9. Lenguaje de riesgo en bio y captions (5)
    text = "\n".join([p.bio, *(v.caption for v in p.videos)])
    hits = [label for pattern, label in RISK_PATTERNS if pattern.search(text)]
    s.append(Signal("risk_language", 5, clamp(1 - len(hits) / 3), " · ".join(hits) or None, not hits))

    # ── Contexto Prais (30) ──

    # 10. Precio vs. mercado (20)
    if ext.price_deviation is not None:
        d = ext.price_deviation
        v = 1 if d >= -0.15 else clamp(1 - (-d - 0.15) / 0.3)
        s.append(Signal("price_anomaly", 20, v, good=v == 1,
                        reason=f"Precio {round_half_up(-d * 100)}% bajo el mercado" if v < 1 else "Precio en línea con el mercado"))
    else:
        s.append(Signal("price_anomaly", 20, None))

    # 11. Reportes verificados (10)
    if ext.verified_reports is not None:
        v = clamp(1 - ext.verified_reports / 3)
        s.append(Signal("reports", 10, v, good=v == 1,
                        reason=f"{ext.verified_reports} reporte(s) de estafa verificados" if ext.verified_reports else None))
    else:
        s.append(Signal("reports", 10, None))

    return s


def red_flags(p: Profile, ext: ExternalInputs) -> list[str]:
    f: list[str] = []
    if ext.price_deviation is not None and ext.price_deviation <= -0.5:
        f.append("Precio más de 50% bajo el mercado")
    if p.created_at and months_since(p.created_at) < 1:
        f.append("Cuenta creada hace menos de un mes")
    if (ext.verified_reports or 0) >= 3:
        f.append("Múltiples reportes de estafa verificados")
    return f


# ───────────────────────── Score ─────────────────────────

MIN_COVERAGE = 0.4


def score_profile(p: Profile, comments: list[Comment], ext: ExternalInputs | None = None) -> TrustResult:
    ext = ext or ExternalInputs()
    signals = compute_signals(p, comments, ext)
    flags = red_flags(p, ext)
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

    if flags:
        return TrustResult(p.username, 0, coverage, "riesgosa", flags, reasons, signals)
    if coverage < MIN_COVERAGE:
        return TrustResult(p.username, None, coverage, "sin_datos", [], reasons, signals)

    score = round_half_up(100 * sum(s.weight * s.value for s in avail) / w_avail)
    verdict: Verdict = "confiable" if score >= 75 else "precaucion" if score >= 50 else "riesgosa"
    return TrustResult(p.username, score, coverage, verdict, [], reasons, signals)


# ───────────────────────── Orquestación ─────────────────────────


async def check_account(username: str, ext: ExternalInputs | None = None) -> TrustResult:
    ext = ext or ExternalInputs()
    profile = await fetch_profile(username)
    if not profile:
        return TrustResult(username, None, 0, "sin_datos", reasons=[Reason("No se encontró la cuenta", False)])
    if profile.is_private:
        return replace(
            score_profile(profile, [], ext),
            reasons=[Reason("Cuenta privada: un vendedor normalmente no oculta su perfil", False)],
        )
    urls = [v.url for v in [x for x in profile.videos if not x.is_ad][:3] if v.url]
    comments = await fetch_comments(urls, 30)
    return score_profile(profile, comments, ext)


# Ejemplo:
# asyncio.run(check_account(
#     "tienda_ejemplo",
#     ExternalInputs(price_deviation=-0.2, verified_reports=0, expected_region="VE"),
# ))
