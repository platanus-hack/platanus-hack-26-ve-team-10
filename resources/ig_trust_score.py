"""IG Trust Score — puntaje de seguridad de una cuenta de Instagram usando Apify.

Actores usados:
  - apify/instagram-profile-scraper  (perfil + últimos posts + "Información sobre esta cuenta")
  - apify/instagram-comment-scraper  (comentarios de los últimos posts)

⚠️ Los nombres exactos de los campos de input/output (sobre todo los del bloque "about")
   pueden variar entre versiones del actor. Haz una corrida en Apify Console con una
   cuenta conocida y ajusta `normalize_profile()` a lo que realmente devuelve.

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

PROFILE_ACTOR = "apify/instagram-profile-scraper"
COMMENT_ACTOR = "apify/instagram-comment-scraper"

# ───────────────────────── Tipos ─────────────────────────

Verdict = Literal["confiable", "precaucion", "riesgosa", "sin_datos"]


@dataclass
class Post:
    likes_count: int | None = None
    comments_count: int | None = None
    timestamp: str | None = None
    caption: str | None = None
    url: str | None = None


@dataclass
class Profile:
    username: str
    followers: int | None
    posts_count: int | None
    bio: str
    external_url: str | None
    is_business: bool
    is_private: bool
    date_joined: datetime | None
    country: str | None
    former_usernames: int | None
    posts: list[Post]


@dataclass
class Comment:
    text: str | None = None
    owner_username: str | None = None


@dataclass
class ExternalInputs:
    """Datos que vienen de Prais, no de Instagram."""

    # Precio ofrecido vs. mediana de mercado: -0.35 = 35% más barato. None si no aplica.
    price_deviation: float | None = None
    # Reportes verificados de estafa contra esta cuenta.
    verified_reports: int | None = None
    # País esperado del vendedor (ISO o nombre como lo devuelve el actor).
    expected_country: str | None = None


@dataclass
class Signal:
    key: str
    weight: int
    value: float | None  # 0..1, None = sin dato
    reason: str | None = None  # texto para mostrar al usuario
    good: bool = False


@dataclass
class Reason:
    text: str
    good: bool


@dataclass
class TrustResult:
    username: str
    score: int | None  # 0..100, None si no hay datos suficientes
    coverage: float  # 0..1, qué % del peso total se pudo medir
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


async def fetch_profile(username: str) -> Profile | None:
    items = await _run_actor(
        PROFILE_ACTOR,
        {
            "usernames": [username.lstrip("@")],
            # Opción de pago del actor para "Información sobre esta cuenta".
            # Verifica el nombre exacto del campo en el input schema del actor.
            "includeAboutSection": True,
        },
    )
    return normalize_profile(items[0]) if items else None


async def fetch_comments(post_urls: list[str], per_post: int = 30) -> list[Comment]:
    if not post_urls:
        return []
    items = await _run_actor(COMMENT_ACTOR, {"directUrls": post_urls, "resultsLimit": per_post})
    return [Comment(text=c.get("text"), owner_username=c.get("ownerUsername")) for c in items]


def normalize_profile(raw: dict[str, Any]) -> Profile:
    about = raw.get("about") or raw.get("aboutSection") or {}
    joined = about.get("dateJoined") or about.get("date_joined") or raw.get("dateJoined")
    former = about.get("formerUsernames", about.get("former_usernames", raw.get("formerUsernames")))
    if isinstance(former, list):
        former_count = len(former)
    elif isinstance(former, int):
        former_count = former
    else:
        former_count = None
    return Profile(
        username=raw["username"],
        followers=raw.get("followersCount"),
        posts_count=raw.get("postsCount"),
        bio=raw.get("biography") or "",
        external_url=raw.get("externalUrl"),
        is_business=bool(raw.get("isBusinessAccount")),
        is_private=bool(raw.get("private")),
        date_joined=parse_loose_date(joined) if joined else None,
        country=about.get("country") or about.get("accountBasedIn"),
        former_usernames=former_count,
        posts=[
            Post(
                likes_count=p.get("likesCount"),
                comments_count=p.get("commentsCount"),
                timestamp=p.get("timestamp"),
                caption=p.get("caption"),
                url=p.get("url"),
            )
            for p in raw.get("latestPosts") or []
        ],
    )


def parse_loose_date(v: str) -> datetime | None:
    """Instagram a veces da "March 2019" en vez de una fecha ISO."""
    try:
        d = datetime.fromisoformat(v)
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except ValueError:
        pass
    for fmt in ("%B %Y", "%b %Y"):
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


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
    # Math.round de JavaScript redondea .5 hacia arriba; round() de Python, al par más cercano.
    return math.floor(x + 0.5)


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


# Nota: "solo transferencia/Zelle/USDT/Binance" y "escríbeme al DM/WhatsApp" NO se usan:
# en Venezuela son prácticas normales en ventas legítimas y generarían falsos positivos.
RISK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(sin|no hay|no se aceptan)\s+devoluci", re.IGNORECASE), "No acepta devoluciones"),
    (re.compile(r"(últimas?|ultimas?)\s+unidades|solo\s+(por\s+)?hoy|quedan\s+\d+", re.IGNORECASE), "Usa presión de urgencia"),
    (re.compile(r"(precio|oferta)\s+(de\s+)?(locura|regalado|remate)", re.IGNORECASE), "Precios 'demasiado buenos'"),
]


def is_real_comment(text: str | None) -> bool:
    # Más de 3 palabras y no solo emojis o signos (Python no tiene \p{Emoji}: se pide al
    # menos una letra o número).
    return bool(text) and len(text.split()) > 3 and re.search(r"[^\W_]", text) is not None


# ───────────────────────── Señales ─────────────────────────


def compute_signals(p: Profile, comments: list[Comment], ext: ExternalInputs) -> list[Signal]:
    s: list[Signal] = []
    likes = [x.likes_count or 0 for x in p.posts]
    comms = [x.comments_count or 0 for x in p.posts]
    has_posts = len(p.posts) >= 3

    # 1. Antigüedad (15): 0 si < 3 meses, 1 a los 36 meses, curva logarítmica.
    if p.date_joined:
        m = months_since(p.date_joined)
        v = 0 if m < 3 else clamp(math.log(m / 3) / math.log(12))
        s.append(Signal("age", 15, v, good=v >= 0.6,
                        reason=f"Cuenta con {m / 12:.1f} años" if v >= 0.6 else f"Cuenta reciente ({round_half_up(m)} meses)"))
    else:
        s.append(Signal("age", 15, None))

    # 2. Cambios de @ (5)
    if p.former_usernames is not None:
        v = clamp(1 - p.former_usernames / 3)
        s.append(Signal("username_changes", 5, v, good=v == 1,
                        reason="Nunca cambió de nombre" if p.former_usernames == 0 else f"Cambió de nombre {p.former_usernames} veces"))
    else:
        s.append(Signal("username_changes", 5, None))

    # 3. País coherente (5)
    if p.country and ext.expected_country:
        ok = ext.expected_country.lower() in p.country.lower()
        s.append(Signal("country", 5, 1 if ok else 0, good=ok,
                        reason=f"Cuenta registrada en {p.country}" if ok else f"Cuenta registrada en {p.country}, no en {ext.expected_country}"))
    else:
        s.append(Signal("country", 5, None))

    # 4. Engagement relativo (15): banda sana ~0.5%–8% (más estrecha en cuentas grandes).
    if has_posts and p.followers:
        er = median([lk + cm for lk, cm in zip(likes, comms, strict=True)]) / p.followers
        hi = 0.05 if p.followers > 100_000 else 0.08
        if er < 0.001:
            v = 0.0
        elif er < 0.005:
            v = (er - 0.001) / 0.004
        elif er <= hi:
            v = 1.0
        else:
            v = clamp(1 - (er - hi) / 0.15)  # engagement irrealmente alto también es raro
        if v >= 0.7:
            reason = "Interacción acorde a sus seguidores"
        elif er < 0.005:
            reason = f"Muy poca interacción para {fmt_int(p.followers)} seguidores (posibles seguidores comprados)"
        else:
            reason = "Interacción inusualmente alta (posibles likes comprados)"
        s.append(Signal("engagement", 15, v, reason, v >= 0.7))
    else:
        s.append(Signal("engagement", 15, None))

    # 5. Consistencia de likes entre posts (10): coeficiente de variación.
    if has_posts and mean(likes) > 0:
        cv = stdev(likes) / mean(likes)
        v = clamp(1 - (cv - 0.6) / 1.4)  # cv<=0.6 → 1, cv>=2 → 0
        s.append(Signal("consistency", 10, v, None if v >= 0.6 else "Likes con picos irregulares entre posts", v >= 0.6))
    else:
        s.append(Signal("consistency", 10, None))

    # 6. Ratio comentarios/likes (5): comprar likes es barato, comentarios creíbles no.
    if has_posts and mean(likes) > 20:
        r = mean(comms) / mean(likes)
        v = clamp(r / 0.02)  # >=2% → 1
        s.append(Signal("comment_like_ratio", 5, v, "Muchos likes pero casi ningún comentario" if v < 0.3 else None, v >= 0.6))
    else:
        s.append(Signal("comment_like_ratio", 5, None))

    # 7. Regularidad al publicar (5): penaliza ráfagas (muchos posts el mismo día).
    days = [x.timestamp[:10] for x in p.posts if x.timestamp]
    if len(days) >= 5:
        burst = max(days.count(d) for d in set(days)) / len(days)
        v = clamp(1 - (burst - 0.25) / 0.5)
        s.append(Signal("posting_rhythm", 5, v, "Gran parte de los posts se subieron el mismo día" if v < 0.5 else None, v >= 0.6))
    else:
        s.append(Signal("posting_rhythm", 5, None))

    # 8. Calidad de comentarios (10): texto real + diversidad de autores.
    if len(comments) >= 10:
        real_pct = sum(is_real_comment(c.text) for c in comments) / len(comments)
        authors = len({c.owner_username for c in comments}) / len(comments)
        # ≥40% comentarios con texto real → 1 ; ≥70% autores únicos → 1
        v = 0.7 * clamp(real_pct / 0.4) + 0.3 * clamp(authors / 0.7)
        s.append(Signal("comment_quality", 10, clamp(v), good=v >= 0.6,
                        reason="Comentarios de personas reales y variadas" if v >= 0.6 else "Comentarios genéricos o repetidos"))
    else:
        s.append(Signal("comment_quality", 10, None))

    # 9. Lenguaje de riesgo en bio y captions (10).
    text = "\n".join([p.bio, *(x.caption or "" for x in p.posts)])
    hits = [label for pattern, label in RISK_PATTERNS if pattern.search(text)]
    s.append(Signal("risk_language", 10, clamp(1 - len(hits) / 3), " · ".join(hits) or None, not hits))

    # 10. Precio vs. mercado (15) — dato de Prais.
    if ext.price_deviation is not None:
        d = ext.price_deviation  # negativo = más barato
        v = 1 if d >= -0.15 else clamp(1 - (-d - 0.15) / 0.3)  # -15% ok, -45% → 0
        s.append(Signal("price_anomaly", 15, v, good=v == 1,
                        reason=f"Precio {round_half_up(-d * 100)}% bajo el mercado" if v < 1 else "Precio en línea con el mercado"))
    else:
        s.append(Signal("price_anomaly", 15, None))

    # 11. Reportes de usuarios (5) — crecerá en peso cuando haya volumen.
    if ext.verified_reports is not None:
        v = clamp(1 - ext.verified_reports / 3)
        s.append(Signal("reports", 5, v, good=v == 1,
                        reason=f"{ext.verified_reports} reporte(s) de estafa verificados" if ext.verified_reports else None))
    else:
        s.append(Signal("reports", 5, None))

    return s


def red_flags(p: Profile, ext: ExternalInputs) -> list[str]:
    f: list[str] = []
    if ext.price_deviation is not None and ext.price_deviation <= -0.5:
        f.append("Precio más de 50% bajo el mercado")
    if p.date_joined and months_since(p.date_joined) < 1:
        f.append("Cuenta creada hace menos de un mes")
    if (p.former_usernames or 0) >= 4:
        f.append("Cambió de nombre 4 o más veces")
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

    # Lo más grave primero.
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
    # Comentarios solo de los 3 posts más recientes para controlar costo.
    urls = [x.url for x in profile.posts[:3] if x.url]
    comments = await fetch_comments(urls, 30)
    return score_profile(profile, comments, ext)


# Ejemplo:
# asyncio.run(check_account(
#     "tienda_ejemplo",
#     ExternalInputs(price_deviation=-0.38, verified_reports=0, expected_country="Venezuela"),
# ))
