"""MercadoLibre Trust Score — puntaje de seguridad de una publicación y su vendedor.

Para Mercado Libre Venezuela (site MLV), usando la API oficial.

A diferencia de Instagram o Marketplace, aquí la reputación nativa SÍ es la señal
principal: el termómetro, MercadoLíder y las calificaciones se construyen con ventas
concretadas en la plataforma.

⚠️ Antes de producción:
  - Crea una app en developers.mercadolibre.com y usa su access token (ML_ACCESS_TOKEN).
    Varios endpoints públicos ahora piden token; con él funcionan items y users.
  - Verifica con 3–4 vendedores reales de MLV qué devuelve GET /users/{id}:
    `registration_date` y `metrics` no siempre vienen para usuarios de terceros.
    Lo que no venga queda en None y no penaliza.
  - En Venezuela muchas ventas se pagan fuera de la plataforma; aun así la calificación
    existe y es la mejor señal disponible.

Solo usa httpx, que ya está en apps/api/requirements.txt.
"""

import asyncio
import math
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

API = "https://api.mercadolibre.com"

# ───────────────────────── Tipos ─────────────────────────

Verdict = Literal["confiable", "precaucion", "riesgosa", "sin_datos"]


@dataclass
class Item:
    id: str
    title: str
    price: float | None
    currency: str | None
    condition: str | None  # new | used
    pictures: int
    description: str
    warranty: str | None
    created_at: datetime | None
    sold_quantity: int | None
    status: str | None
    seller_id: int
    state: str | None  # estado de Venezuela de la publicación


@dataclass
class Ratings:
    positive: float
    neutral: float
    negative: float


@dataclass
class Seller:
    id: int
    nickname: str
    registered_at: datetime | None
    state: str | None
    level_id: str | None  # "5_green", "4_light_green", ..., "1_red"
    power_seller: str | None  # platinum | gold | silver | None
    completed: int | None
    canceled: int | None
    total: int | None
    ratings: Ratings | None
    claims_rate: float | None
    status: str | None  # "active", o suspendido


@dataclass
class ExternalInputs:
    # Precio vs. mediana de mercado (Prais): -0.35 = 35% más barato.
    price_deviation: float | None = None
    # Reportes de estafa verificados contra este vendedor.
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
    item_id: str
    seller_id: int | None
    score: int | None
    coverage: float
    verdict: Verdict
    red_flags: list[str] = field(default_factory=list)
    reasons: list[Reason] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)


# ───────────────────────── Fetch ─────────────────────────


async def ml(client: httpx.AsyncClient, path: str) -> Any | None:
    try:
        res = await client.get(f"{API}{path}")
        return res.json() if res.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def _client() -> httpx.AsyncClient:
    token = os.environ.get("ML_ACCESS_TOKEN")
    return httpx.AsyncClient(timeout=10, headers={"Authorization": f"Bearer {token}"} if token else {})


def parse_item_id(text: str) -> str | None:
    """Acepta "MLV-123456789", "MLV123456789" o la URL completa de la publicación."""
    m = re.search(r"MLV-?(\d{6,})", text, re.IGNORECASE)
    return f"MLV{m.group(1)}" if m else None


def _parse_date(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v) if v else None


async def fetch_item(client: httpx.AsyncClient, item_id: str) -> Item | None:
    it, desc = await asyncio.gather(ml(client, f"/items/{item_id}"), ml(client, f"/items/{item_id}/description"))
    if not it:
        return None
    warranty_term = next((t for t in it.get("sale_terms") or [] if t.get("id") == "WARRANTY_TIME"), None)
    return Item(
        id=it["id"],
        title=it.get("title") or "",
        price=it.get("price"),
        currency=it.get("currency_id"),
        condition=it.get("condition"),
        pictures=len(it.get("pictures") or []),
        description=(desc or {}).get("plain_text") or "",
        warranty=it.get("warranty") or (warranty_term or {}).get("value_name"),
        created_at=_parse_date(it.get("date_created")),
        sold_quantity=it.get("sold_quantity"),
        status=it.get("status"),
        seller_id=it["seller_id"],
        state=((it.get("seller_address") or {}).get("state") or {}).get("name")
        or ((it.get("location") or {}).get("state") or {}).get("name"),
    )


async def fetch_seller(client: httpx.AsyncClient, seller_id: int) -> Seller | None:
    u = await ml(client, f"/users/{seller_id}")
    if not u:
        return None
    rep = u.get("seller_reputation") or {}
    tx = rep.get("transactions") or {}
    ratings = tx.get("ratings")
    return Seller(
        id=u["id"],
        nickname=u.get("nickname"),
        registered_at=_parse_date(u.get("registration_date")),
        state=(u.get("address") or {}).get("state"),
        level_id=rep.get("level_id"),
        power_seller=rep.get("power_seller_status"),
        completed=tx.get("completed"),
        canceled=tx.get("canceled"),
        total=tx.get("total"),
        ratings=Ratings(ratings.get("positive", 0), ratings.get("neutral", 0), ratings.get("negative", 0)) if ratings else None,
        claims_rate=((rep.get("metrics") or {}).get("claims") or {}).get("rate"),
        status=(u.get("status") or {}).get("site_status"),
    )


# ───────────────────────── Helpers ─────────────────────────


def clamp(x: float, lo: float = 0, hi: float = 1) -> float:
    return max(lo, min(hi, x))


def months_since(d: datetime) -> float:
    return (datetime.now(UTC) - d).total_seconds() / (60 * 60 * 24 * 30.44)


def round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


# Mismos 3 patrones de siempre. Coordinar pago o entrega por WhatsApp NO se penaliza:
# en MLV es la norma, porque el pago casi nunca pasa por la plataforma.
RISK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(sin|no hay|no se aceptan)\s+devoluci", re.IGNORECASE), "No acepta devoluciones"),
    (re.compile(r"(últimas?|ultimas?)\s+unidades|solo\s+(por\s+)?hoy|quedan\s+\d+", re.IGNORECASE), "Usa presión de urgencia"),
    (re.compile(r"(precio|oferta)\s+(de\s+)?(locura|regalado|remate)", re.IGNORECASE), "Precios 'demasiado buenos'"),
]

LEVEL_VALUE = {"5_green": 1, "4_light_green": 0.75, "3_yellow": 0.4, "2_orange": 0.15, "1_red": 0}
LEVEL_LABEL = {"5_green": "verde", "4_light_green": "verde claro", "3_yellow": "amarillo", "2_orange": "naranja", "1_red": "rojo"}
POWER_SELLER_VALUE = {"platinum": 1, "gold": 0.8, "silver": 0.6}

NO_WARRANTY = re.compile(r"sin garant", re.IGNORECASE)

# ───────────────────────── Señales ─────────────────────────


def compute_signals(item: Item, seller: Seller | None, ext: ExternalInputs) -> list[Signal]:
    s: list[Signal] = []

    # ── Reputación en Mercado Libre (40) ──
    # Un vendedor sin reputación todavía (nuevo) queda en None: no se le castiga, pero
    # tampoco suma, y la cobertura lo refleja.

    # 1. Termómetro (15)
    if seller and seller.level_id in LEVEL_VALUE:
        v = LEVEL_VALUE[seller.level_id]
        s.append(Signal("thermometer", 15, v, f"Reputación {LEVEL_LABEL[seller.level_id]} en Mercado Libre", v >= 0.75))
    else:
        s.append(Signal("thermometer", 15, None))

    # 2. MercadoLíder (5)
    if seller and seller.level_id:
        v = POWER_SELLER_VALUE.get(seller.power_seller or "", 0)
        s.append(Signal("power_seller", 5, v, f"MercadoLíder {seller.power_seller}" if seller.power_seller else None, v > 0))
    else:
        s.append(Signal("power_seller", 5, None))

    # 3. Volumen de ventas concretadas (10): escala log, 100+ → 1.
    if seller and seller.completed is not None:
        v = clamp(math.log10(seller.completed + 1) / 2)
        s.append(Signal("sales_volume", 10, v, good=v >= 0.6,
                        reason=f"{fmt_int(seller.completed)} ventas concretadas" if seller.completed > 0 else "Sin ventas concretadas"))
    else:
        s.append(Signal("sales_volume", 10, None))

    # 4. Calificaciones negativas (10): ≤ 2% → 1, ≥ 15% → 0. Solo con 10+ ventas.
    if seller and seller.ratings and (seller.total or 0) >= 10:
        neg = seller.ratings.negative  # proporción 0..1
        v = clamp(1 - (neg - 0.02) / 0.13)
        s.append(Signal("negative_ratings", 10, v, f"{round_half_up(neg * 100)}% de calificaciones negativas" if neg > 0.05 else None, v >= 0.7))
    else:
        s.append(Signal("negative_ratings", 10, None))

    # ── Identidad (15) ──

    # 5. Antigüedad de la cuenta (10): < 3 meses → 0, 3 años → 1.
    if seller and seller.registered_at:
        m = months_since(seller.registered_at)
        v = 0 if m < 3 else clamp(math.log(m / 3) / math.log(12))
        s.append(Signal("account_age", 10, v, good=v >= 0.6,
                        reason=f"En Mercado Libre desde {seller.registered_at.year}" if v >= 0.6 else f"Cuenta reciente ({round_half_up(m)} meses)"))
    else:
        s.append(Signal("account_age", 10, None))

    # 6. Ubicación coherente (5): estado de la publicación = estado del vendedor.
    if seller and seller.state and item.state:
        ok = seller.state.lower() == item.state.lower()
        s.append(Signal("location", 5, 1 if ok else 0.4, None if ok else f"Publica en {item.state} pero su cuenta está en {seller.state}", ok))
    else:
        s.append(Signal("location", 5, None))

    # ── Publicación (15) ──

    # 7. Completitud (5): fotos y descripción.
    v = 0.5 * clamp(item.pictures / 4) + 0.5 * clamp(len(item.description.split()) / 40)
    s.append(Signal("completeness", 5, v, "Publicación con pocas fotos o sin descripción" if v < 0.4 else None, v >= 0.7))

    # 8. Garantía declarada (5)
    has_warranty = bool(item.warranty) and not NO_WARRANTY.search(item.warranty)
    s.append(Signal("warranty", 5, 1 if has_warranty else 0.3, f"Garantía: {item.warranty}" if has_warranty else "Sin garantía declarada", has_warranty))

    # 9. Lenguaje de riesgo (5)
    text = f"{item.title}\n{item.description}"
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


def red_flags(seller: Seller | None, ext: ExternalInputs) -> list[str]:
    f: list[str] = []
    if seller and seller.status and seller.status != "active":
        f.append("Cuenta de vendedor suspendida o inactiva")
    if seller and seller.level_id == "1_red" and (seller.total or 0) >= 10:
        f.append("Reputación roja con más de 10 ventas")
    if seller and seller.ratings and (seller.total or 0) >= 10 and seller.ratings.negative >= 0.25:
        f.append("25% o más de calificaciones negativas")
    if seller and seller.registered_at and months_since(seller.registered_at) < 1:
        f.append("Cuenta creada hace menos de un mes")
    if ext.price_deviation is not None and ext.price_deviation <= -0.5:
        f.append("Precio más de 50% bajo el mercado")
    if (ext.verified_reports or 0) >= 3:
        f.append("Múltiples reportes de estafa verificados")
    return f


# ───────────────────────── Score ─────────────────────────

MIN_COVERAGE = 0.4


def score_item(item: Item, seller: Seller | None, ext: ExternalInputs | None = None) -> TrustResult:
    ext = ext or ExternalInputs()
    signals = compute_signals(item, seller, ext)
    flags = red_flags(seller, ext)
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
    seller_id = seller.id if seller else item.seller_id

    if flags:
        return TrustResult(item.id, seller_id, 0, coverage, "riesgosa", flags, reasons, signals)
    if coverage < MIN_COVERAGE:
        return TrustResult(item.id, seller_id, None, coverage, "sin_datos", [], reasons, signals)

    score = round_half_up(100 * sum(s.weight * s.value for s in avail) / w_avail)
    verdict: Verdict = "confiable" if score >= 75 else "precaucion" if score >= 50 else "riesgosa"
    return TrustResult(item.id, seller_id, score, coverage, verdict, [], reasons, signals)


# ───────────────────────── Orquestación ─────────────────────────


async def check_item(url_or_id: str, ext: ExternalInputs | None = None) -> TrustResult:
    item_id = parse_item_id(url_or_id)
    async with _client() as client:
        item = await fetch_item(client, item_id) if item_id else None
        if not item:
            return TrustResult(item_id or url_or_id, None, None, 0, "sin_datos", reasons=[Reason("No se pudo leer la publicación", False)])
        seller = await fetch_seller(client, item.seller_id)
    return score_item(item, seller, ext)


# Ejemplo:
# asyncio.run(check_item(
#     "https://articulo.mercadolibre.com.ve/MLV-123456789-iphone-15-128gb-_JM",
#     ExternalInputs(price_deviation=-0.12, verified_reports=0),
# ))
