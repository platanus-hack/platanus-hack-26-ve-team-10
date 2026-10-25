"""El especialista de confianza de Instagram y TikTok.

Un especialista mide **solo lo que ve su canal** y entrega un puntaje `parcial`: nunca cierra,
porque `price_anomaly` necesita la mediana de todas las fuentes y eso lo sabe el agregador
(`trust.aggregate`). Las señales, sus pesos y quién las llena están en `CATALOGS` de
contracts.py: `build_signals` rechaza una clave que no esté ahí y `TrustScore` rechaza una lista
que no cuadre con el catálogo. Por eso una fuente no puede inventarse una señal ni un peso.

Las fórmulas son las de los borradores del equipo ([resources/ig_trust_score.py] y
[resources/tiktok_trust_score.py]). Lo que la fuente no trae queda en `None`: no cuenta y su peso
se reparte. Si se mide menos del 40 % del peso, el veredicto es `sin_datos`, que es la respuesta
honesta y no un número inventado.
"""

import math
import statistics
from datetime import UTC, datetime
from typing import Any

from app.lib.contracts import TrustScore
from app.lib.trust import (
    Measured,
    build_signals,
    clamp,
    compute_trust,
    fmt_int,
    risk_language,
    round_half_up,
)

# Una cuenta recién creada es la bandera roja de los dos canales.
NEW_ACCOUNT_FLAG = "Cuenta con menos de un mes"
PRIVATE_FLAG = "Cuenta privada"
# Los borradores piden al menos 3 publicaciones para una mediana y 5 días distintos para el ritmo.
MIN_POSTS = 3
MIN_DAYS = 5
MIN_COMMENTS = 10
MIN_FOLLOWERS_FOR_HEARTS = 500


def _months_since(moment: datetime, now: datetime) -> float:
    return max((now - moment).days, 0) / 30.44


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _cv(values: list[float]) -> float | None:
    """Coeficiente de variación: cuánto se dispersan los números alrededor de su media."""
    if len(values) < 2:
        return None
    mean = _mean(values)
    return statistics.stdev(values) / mean if mean > 0 else 2.0


def _is_real_comment(text: str | None) -> bool:
    """Un comentario con palabras, no solo emojis ni un "🔥🔥🔥"."""
    words = [word for word in (text or "").split() if any(char.isalpha() for char in word)]
    return len(words) >= 3


# ── Instagram ─────────────────────────────────────────────────────────────────────────────────


def instagram_trust(profile: dict[str, Any], posts: list[dict[str, Any]], *, now: datetime) -> TrustScore:
    """ig-v1 con lo que devuelve apify/instagram-scraper.

    `profile` son los datos de la cuenta (vacío si solo entramos por el hashtag: una publicación
    no trae seguidores). `posts` son sus publicaciones, la más reciente primero.
    """
    values: dict[str, Measured] = {}
    flags: list[str] = []

    followers = profile.get("followersCount")
    if not isinstance(followers, int) or followers <= 0:
        followers = None
    likes = [float(post["likesCount"]) for post in posts if isinstance(post.get("likesCount"), int)]
    comments_count = [float(post["commentsCount"]) for post in posts if isinstance(post.get("commentsCount"), int)]
    enough = len(likes) >= MIN_POSTS

    # Antigüedad, cambios de usuario y país salen del bloque "about", que es una opción de pago
    # del actor. Sin esa corrida quedan en None: no se adivinan.

    if enough and followers:
        rate = _mean(likes) / followers
        low, high = 0.005, 0.20
        if rate < low:
            value = clamp(rate / low) * 0.5
        elif rate <= high:
            value = 1.0
        else:
            value = clamp(1 - (rate - high) / 0.15)
        if value >= 0.7:
            reason = "Interacción acorde a sus seguidores"
        elif rate < low:
            reason = f"Muy poca interacción para {fmt_int(followers)} seguidores (posibles seguidores comprados)"
        else:
            reason = "Interacción inusualmente alta (posibles likes comprados)"
        values["engagement"] = Measured(value, reason, value >= 0.7)

    cv = _cv(likes) if enough else None
    if cv is not None:
        value = clamp(1 - (cv - 0.6) / 1.4)  # cv ≤ 0,6 → 1; cv ≥ 2 → 0
        values["consistency"] = Measured(
            value, None if value >= 0.6 else "Likes con picos irregulares entre posts", value >= 0.6
        )

    if enough and _mean(likes) > 20 and comments_count:
        ratio = _mean(comments_count) / _mean(likes)
        value = clamp(ratio / 0.02)  # 2 % o más → 1
        values["comment_like_ratio"] = Measured(
            value, "Muchos likes pero casi ningún comentario" if value < 0.3 else None, value >= 0.6
        )

    days = [str(post["timestamp"])[:10] for post in posts if post.get("timestamp")]
    if len(days) >= MIN_DAYS:
        burst = max(days.count(day) for day in set(days)) / len(days)
        value = clamp(1 - (burst - 0.25) / 0.5)
        values["posting_rhythm"] = Measured(
            value, "Gran parte de los posts se subieron el mismo día" if value < 0.5 else None, value >= 0.6
        )

    comments = [comment for post in posts for comment in (post.get("latestComments") or [])]
    if len(comments) >= MIN_COMMENTS:
        real = sum(_is_real_comment(comment.get("text")) for comment in comments) / len(comments)
        authors = len({comment.get("ownerUsername") for comment in comments}) / len(comments)
        value = clamp(0.7 * clamp(real / 0.4) + 0.3 * clamp(authors / 0.7))
        values["comment_quality"] = Measured(
            value,
            "Comentarios de personas reales y variadas" if value >= 0.6 else "Comentarios genéricos o repetidos",
            value >= 0.6,
        )

    values["risk_language"] = risk_language(
        profile.get("biography"), *(post.get("caption") for post in posts)
    )

    if profile.get("private") is True:
        flags.append(PRIVATE_FLAG)

    return compute_trust("ig-v1", build_signals("ig-v1", values), stage="parcial", red_flags=flags, now=now)


# ── TikTok ────────────────────────────────────────────────────────────────────────────────────


def tiktok_created_at(user_id: Any) -> datetime | None:
    """La fecha de creación va en los 32 bits altos del id numérico de la cuenta."""
    try:
        seconds = int(user_id) >> 32
    except (TypeError, ValueError):
        return None
    if not 1_000_000_000 < seconds < 4_000_000_000:  # fuera de rango: el id no era de este tipo
        return None
    return datetime.fromtimestamp(seconds, UTC)


def tiktok_trust(author: dict[str, Any], videos: list[dict[str, Any]], *, now: datetime) -> TrustScore:
    """tiktok-v1 con lo que devuelve clockworks/tiktok-scraper.

    En TikTok las vistas las reparte el algoritmo, no los seguidores: por eso se mide la
    proporción entre interacciones y no likes por seguidor.
    """
    values: dict[str, Measured] = {}
    flags: list[str] = []

    created = tiktok_created_at(author.get("id"))
    if created is not None:
        months = _months_since(created, now)
        value = 0.0 if months < 3 else clamp(math.log(months / 3) / math.log(12))
        values["age"] = Measured(
            value,
            f"Cuenta desde {created.year}" if value >= 0.6 else f"Cuenta reciente ({round_half_up(months)} meses)",
            value >= 0.6,
        )
        if months < 1:
            flags.append(NEW_ACCOUNT_FLAG)

    region = author.get("region")
    if isinstance(region, str) and region:
        ok = region.upper() == "VE"
        values["region"] = Measured(
            1.0 if ok else 0.0, None if ok else f"Cuenta registrada en {region}, no en Venezuela", ok
        )

    plays = [
        (float(video["playCount"]), float(video.get("diggCount") or 0))
        for video in videos
        if isinstance(video.get("playCount"), int) and video["playCount"] > 0
    ]
    enough = len(plays) >= MIN_POSTS
    if enough:
        ratios = [likes / views for views, likes in plays]
        rate = statistics.median(ratios)
        if rate < 0.005:
            value = 0.0
        elif rate < 0.02:
            value = (rate - 0.005) / 0.015
        elif rate <= 0.2:
            value = 1.0
        else:
            value = clamp(1 - (rate - 0.2) / 0.2)  # demasiado alto: likes comprados
        if value >= 0.7:
            reason = "Interacción acorde a sus vistas"
        elif rate < 0.02:
            reason = "Muchas vistas pero casi sin likes (posibles vistas compradas)"
        else:
            reason = "Likes desproporcionados para sus vistas (posibles likes comprados)"
        values["like_view_ratio"] = Measured(value, reason, value >= 0.7)

        spread = _cv(ratios)
        if spread is not None:
            value = clamp(1 - (spread - 0.5) / 1.0)  # cv ≤ 0,5 → 1; ≥ 1,5 → 0
            values["ratio_consistency"] = Measured(
                value, "Algunos videos con interacción muy distinta al resto" if value < 0.4 else None, value >= 0.6
            )

    followers, hearts = author.get("fans"), author.get("heart")
    if isinstance(followers, int) and followers >= MIN_FOLLOWERS_FOR_HEARTS and isinstance(hearts, int):
        value = clamp((hearts / followers - 0.5) / 2.5)  # ≤ 0,5 → 0; ≥ 3 → 1
        values["hearts_per_follower"] = Measured(
            value,
            f"Pocos likes totales para {fmt_int(followers)} seguidores (posibles seguidores comprados)"
            if value < 0.3
            else None,
            value >= 0.6,
        )

    shares = [
        (float(video.get("shareCount") or 0) + float(video.get("collectCount") or 0)) / max(float(video["diggCount"]), 1)
        for video in videos
        if isinstance(video.get("diggCount"), int)
    ]
    if len(shares) >= MIN_POSTS:
        value = clamp(statistics.median(shares) / 0.05)  # 5 % de los likes o más → 1
        values["shares_saves"] = Measured(
            value, "La gente guarda y comparte sus videos" if value >= 0.6 else None, value >= 0.6
        )

    dates = [str(video["createTimeISO"])[:10] for video in videos if video.get("createTimeISO")]
    if len(dates) >= MIN_DAYS:
        burst = max(dates.count(day) for day in set(dates)) / len(dates)
        value = clamp(1 - (burst - 0.25) / 0.5)
        values["posting_rhythm"] = Measured(
            value, "Gran parte de los videos se subieron el mismo día" if value < 0.5 else None, value >= 0.6
        )

    values["risk_language"] = risk_language(author.get("signature"), *(video.get("text") for video in videos))

    return compute_trust("tiktok-v1", build_signals("tiktok-v1", values), stage="parcial", red_flags=flags, now=now)
