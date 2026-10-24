"""Amazon Trust Score — puntaje de seguridad de un VENDEDOR de Amazon para una oferta concreta.

En Amazon el riesgo no es la plataforma sino el vendedor externo (third-party seller):
falsificaciones, productos usados vendidos como nuevos, envíos que no llegan al casillero
y cuentas de vendedor robadas que reaparecen con precios bajísimos.

Actores:
  - junglee/Amazon-crawler            (página del producto: ASIN, precio, vendedor, fulfillment)
  - reefapi/amazon-seller-scraper     (perfil del vendedor y sus reseñas de feedback)

⚠️ Antes de producción:
  - Corre ambos actores con 3–4 productos reales (uno vendido por Amazon, uno FBA y uno
    enviado por el vendedor) y ajusta normalize_offer() / normalize_seller().
  - La API oficial (PA-API 5) está deprecada; su sucesora, Creators API, es para afiliados
    y no está claro que exponga el feedback del vendedor. Por eso se usa Apify.

pip install apify-client
"""

import asyncio
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from apify_client import ApifyClientAsync

apify = ApifyClientAsync(os.environ.get("APIFY_TOKEN"))
PRODUCT_ACTOR = "junglee/Amazon-crawler"
SELLER_ACTOR = "reefapi/amazon-seller-scraper"

# ───────────────────────── Tipos ─────────────────────────

Verdict = Literal["confiable", "precaucion", "riesgosa", "sin_datos"]
# Vendido por Amazon / gestionado por Amazon (FBA) / enviado por el vendedor.
Fulfillment = Literal["amazon", "fba", "merchant"] | None


@dataclass
class Offer:
    asin: str
    title: str
    price: float | None
    seller_id: str | None
    seller_name: str | None
    fulfillment: Fulfillment
    product_rating: float | None
    product_reviews: float | None


@dataclass
class Seller:
    id: str
    name: str | None
    positive_pct: float | None  # 0..1
    ratings_lifetime: float | None
    ratings_12m: float | None
    ratings_90d: float | None


@dataclass
class FeedbackReview:
    rating: float | None
    text: str
    date: datetime | None


@dataclass
class ExternalInputs:
    # Precio de esta oferta vs. la mediana de las otras ofertas del MISMO ASIN
    # (o el precio de Amazon como vendedor). -0.35 = 35% más barato.
    price_deviation: float | None = None
    # Reportes verificados de usuarios de Prais contra este vendedor.
    verified_reports: int | None = None


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
    asin: str
    seller_id: str | None
    score: int | None
    coverage: float
    verdict: Verdict
    red_flags: list[str] = field(default_factory=list)
    reasons: list[Reason] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)


# ───────────────────────── Fetch ─────────────────────────


async def _run(actor: str, run_input: dict[str, Any]) -> list[dict[str, Any]]:
    run = await apify.actor(actor).call(run_input=run_input)
    if run is None:
        return []
    return (await apify.dataset(run.default_dataset_id).list_items()).items


async def fetch_offer(product_url: str) -> Offer | None:
    items = await _run(
        PRODUCT_ACTOR,
        {
            "categoryOrProductUrls": [{"url": product_url}],
            "maxItemsPerStartUrl": 1,
            "scrapeSellers": True,  # verifica el nombre del flag en el input schema
        },
    )
    return normalize_offer(items[0]) if items else None


async def fetch_seller(seller_id: str, marketplace: str = "com") -> Seller | None:
    items = await _run(SELLER_ACTOR, {"action": "seller/profile", "seller_id": seller_id, "marketplace": marketplace})
    return normalize_seller(seller_id, items[0]) if items else None


async def fetch_feedback(seller_id: str, marketplace: str = "com") -> list[FeedbackReview]:
    try:
        items = await _run(SELLER_ACTOR, {"action": "seller/reviews", "seller_id": seller_id, "marketplace": marketplace})
    except Exception:  # noqa: BLE001  sin reseñas, la señal queda en None
        return []
    return [
        FeedbackReview(
            rating=float(r["rating"]) if r.get("rating") is not None else None,
            text=str(r.get("text") or r.get("body") or ""),
            date=datetime.fromisoformat(str(r["date"])) if r.get("date") else None,
        )
        for r in items[:40]
    ]


def num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(re.sub(r"[^\d.]", "", str(v)))
    except ValueError:
        return None


def normalize_offer(r: dict[str, Any]) -> Offer:
    seller = r.get("seller") or {}
    sold_by = str(seller.get("name") or r.get("soldBy") or "").lower()
    ships_from = str(r.get("shipsFrom") or seller.get("shipsFrom") or "").lower()
    fulfillment: Fulfillment
    if not sold_by and not ships_from:
        fulfillment = None
    elif sold_by.startswith("amazon"):
        fulfillment = "amazon"
    elif "amazon" in ships_from or r.get("isFBA") or r.get("fulfilledByAmazon"):
        fulfillment = "fba"
    else:
        fulfillment = "merchant"
    price = r.get("price")
    return Offer(
        asin=r.get("asin") or r.get("ASIN"),
        title=r.get("title") or "",
        price=num(price.get("value") if isinstance(price, dict) else price),
        seller_id=seller.get("id") or r.get("sellerId"),
        seller_name=seller.get("name") or r.get("soldBy"),
        fulfillment=fulfillment,
        product_rating=num(r.get("stars") or r.get("rating")),
        product_reviews=num(r.get("reviewsCount") or r.get("ratingsCount")),
    )


def normalize_seller(seller_id: str, r: dict[str, Any]) -> Seller:
    pct = num(r.get("feedback_percent") or r.get("positivePercent"))
    return Seller(
        id=seller_id,
        name=r.get("name"),
        positive_pct=(pct / 100 if pct > 1 else pct) if pct is not None else None,
        ratings_lifetime=num(r.get("lifetime_ratings")),
        ratings_12m=num(r.get("ratings_12m")),
        ratings_90d=num(r.get("ratings_90d")),
    )


# ───────────────────────── Helpers ─────────────────────────


def clamp(x: float, lo: float = 0, hi: float = 1) -> float:
    return max(lo, min(hi, x))


def round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def fmt_int(n: float) -> str:
    return f"{int(n):,}".replace(",", ".")


# Reseñas que hablan de falsificación, producto usado o que nunca llegó (es/en).
ALERT_REVIEW = re.compile(
    r"(fake|counterfeit|knock[- ]?off|not (genuine|authentic|original)|falsificad|imitaci[oó]n|no (es )?original"
    r"|used|refurbished|usad[oa]|reacondicionad|never (arrived|received)|not received|nunca lleg|no (me )?lleg"
    r"|scam|estafa)",
    re.IGNORECASE,
)


def count_alerts(reviews: list[FeedbackReview]) -> int:
    return sum(1 for r in reviews if ALERT_REVIEW.search(r.text) and (r.rating if r.rating is not None else 5) <= 2)


# ───────────────────────── Señales ─────────────────────────


def compute_signals(offer: Offer, seller: Seller | None, reviews: list[FeedbackReview], ext: ExternalInputs) -> list[Signal]:
    s: list[Signal] = []

    # ── Cómo se vende (15) ──

    # 1. Quién vende y quién envía (15). Con FBA, Amazon maneja envío y devoluciones.
    if offer.fulfillment:
        v = {"amazon": 1, "fba": 0.8, "merchant": 0.4}[offer.fulfillment]
        reason = {
            "amazon": "Vendido y enviado por Amazon",
            "fba": "Enviado por Amazon (FBA)",
            "merchant": "Enviado directamente por el vendedor",
        }[offer.fulfillment]
        s.append(Signal("fulfillment", 15, v, reason, v >= 0.8))
    else:
        s.append(Signal("fulfillment", 15, None))

    # ── Reputación del vendedor (50) ──

    # 2. Feedback positivo (20): ≥ 95% → 1, ≤ 80% → 0. Solo con 20+ calificaciones.
    if seller and seller.positive_pct is not None and (seller.ratings_lifetime or 0) >= 20:
        p = seller.positive_pct
        v = clamp((p - 0.8) / 0.15)
        s.append(Signal("positive_feedback", 20, v, f"{round_half_up(p * 100)}% de feedback positivo", v >= 0.7))
    else:
        s.append(Signal("positive_feedback", 20, None))

    # 3. Volumen de calificaciones (10): escala log, 1.000+ → 1.
    if seller and seller.ratings_lifetime is not None:
        v = clamp(math.log10(seller.ratings_lifetime + 1) / 3)
        s.append(Signal("ratings_volume", 10, v, f"{fmt_int(seller.ratings_lifetime)} calificaciones", v >= 0.6))
    else:
        s.append(Signal("ratings_volume", 10, None))

    # 4. Actividad reciente (10): una cuenta con historial que lleva un año sin ventas y
    #    reaparece es el patrón clásico de cuenta de vendedor robada.
    if seller and seller.ratings_lifetime is not None and seller.ratings_12m is not None and seller.ratings_lifetime >= 20:
        share = seller.ratings_12m / seller.ratings_lifetime
        v = 0 if seller.ratings_12m == 0 else clamp(share / 0.1)  # ≥ 10% del historial en el último año → 1
        s.append(Signal("recent_activity", 10, v, good=v >= 0.6,
                        reason="Sin ventas calificadas en el último año (cuenta inactiva que reapareció)" if seller.ratings_12m == 0 else None))
    else:
        s.append(Signal("recent_activity", 10, None))

    # 5. Reseñas de alerta recientes (10): falsificado, usado, no llegó.
    if len(reviews) >= 5:
        alerts = count_alerts(reviews)
        v = clamp(1 - alerts / 3)
        s.append(Signal("alert_reviews", 10, v, good=v == 1,
                        reason=f"{alerts} reseña(s) recientes que hablan de falsificación, producto usado o no recibido" if alerts else None))
    else:
        s.append(Signal("alert_reviews", 10, None))

    # ── Producto (5) ──

    # 6. Historial del producto (5): ASIN con reseñas y buena nota.
    if offer.product_reviews is not None and offer.product_rating is not None:
        v = 0.5 * clamp(math.log10(offer.product_reviews + 1) / 2.5) + 0.5 * clamp((offer.product_rating - 3.5) / 1)
        s.append(Signal("product_history", 5, v, good=v >= 0.6))
    else:
        s.append(Signal("product_history", 5, None))

    # ── Contexto Prais (30) ──

    # 7. Precio vs. otras ofertas del mismo ASIN (20)
    if ext.price_deviation is not None:
        d = ext.price_deviation
        v = 1 if d >= -0.15 else clamp(1 - (-d - 0.15) / 0.3)
        s.append(Signal("price_anomaly", 20, v, good=v == 1,
                        reason=f"{round_half_up(-d * 100)}% más barato que las demás ofertas del mismo producto" if v < 1 else None))
    else:
        s.append(Signal("price_anomaly", 20, None))

    # 8. Reportes verificados de usuarios de Prais (10)
    if ext.verified_reports is not None:
        v = clamp(1 - ext.verified_reports / 3)
        s.append(Signal("reports", 10, v, good=v == 1,
                        reason=f"{ext.verified_reports} reporte(s) verificados de usuarios de Prais" if ext.verified_reports else None))
    else:
        s.append(Signal("reports", 10, None))

    return s


def red_flags(offer: Offer, seller: Seller | None, reviews: list[FeedbackReview], ext: ExternalInputs) -> list[str]:
    f: list[str] = []
    if offer.fulfillment == "amazon":
        return f  # Amazon como vendedor: sin banderas de vendedor

    dormant = seller is not None and (seller.ratings_lifetime or 0) >= 20 and seller.ratings_12m == 0
    if dormant and ext.price_deviation is not None and ext.price_deviation <= -0.3:
        f.append("Cuenta inactiva que reapareció con precios muy bajos (posible cuenta robada)")
    if seller and seller.positive_pct is not None and (seller.ratings_lifetime or 0) >= 20 and seller.positive_pct < 0.8:
        f.append("Menos de 80% de feedback positivo")
    if count_alerts(reviews) >= 3:
        f.append("Varias reseñas recientes de falsificación o envíos no recibidos")
    if ext.price_deviation is not None and ext.price_deviation <= -0.5:
        f.append("Más de 50% más barato que las demás ofertas")
    if (ext.verified_reports or 0) >= 3:
        f.append("Múltiples reportes verificados de usuarios de Prais")
    return f


# ───────────────────────── Score ─────────────────────────

MIN_COVERAGE = 0.4


def score_offer(
    offer: Offer, seller: Seller | None, reviews: list[FeedbackReview], ext: ExternalInputs | None = None
) -> TrustResult:
    ext = ext or ExternalInputs()

    # Atajo: vendido y enviado por Amazon. El riesgo de vendedor no aplica.
    if offer.fulfillment == "amazon":
        return TrustResult(offer.asin, offer.seller_id, 95, 1, "confiable", reasons=[Reason("Vendido y enviado por Amazon", True)])

    signals = compute_signals(offer, seller, reviews, ext)
    flags = red_flags(offer, seller, reviews, ext)
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
        return TrustResult(offer.asin, offer.seller_id, 0, coverage, "riesgosa", flags, reasons, signals)
    if coverage < MIN_COVERAGE:
        return TrustResult(offer.asin, offer.seller_id, None, coverage, "sin_datos", [], reasons, signals)

    score = round_half_up(100 * sum(s.weight * s.value for s in avail) / w_avail)
    verdict: Verdict = "confiable" if score >= 75 else "precaucion" if score >= 50 else "riesgosa"
    return TrustResult(offer.asin, offer.seller_id, score, coverage, verdict, [], reasons, signals)


# ───────────────────────── Orquestación ─────────────────────────


async def check_offer(product_url: str, ext: ExternalInputs | None = None) -> TrustResult:
    offer = await fetch_offer(product_url)
    if not offer:
        return TrustResult(product_url, None, None, 0, "sin_datos", reasons=[Reason("No se pudo leer el producto", False)])
    if offer.fulfillment == "amazon" or not offer.seller_id:
        return score_offer(offer, None, [], ext)
    seller, reviews = await asyncio.gather(fetch_seller(offer.seller_id), fetch_feedback(offer.seller_id))
    return score_offer(offer, seller, reviews, ext)


# Ejemplo:
# asyncio.run(check_offer("https://www.amazon.com/dp/B0EXAMPLE", ExternalInputs(price_deviation=-0.08, verified_reports=0)))

