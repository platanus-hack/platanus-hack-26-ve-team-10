"""Motor del puntaje de confianza. Igual para todos los canales, importación incluida.

El puntaje es el promedio de las señales que sí tienen un número, pesado por su
`weight`. Un `null` no resta: solo baja la cobertura. Un `0` sí resta. Una
bandera roja deja el puntaje en 0. Si en el cierre se midió menos del 40 % del
peso, no hay puntaje.

`"pending"` es un hueco del agregador. Al cerrar, o se llena o pasa a `null`.
Un `TrustScore` final no puede conservar un `"pending"`.
"""

import hashlib
import math
import re
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import ValidationError

from app.lib.contracts import (
    CATALOGS,
    MIN_COVERAGE,
    Adjustment,
    Condition,
    Judgement,
    Merchant,
    MerchantIdentity,
    MerchantLink,
    Offer,
    OfferCard,
    PriceStat,
    TrustScore,
    TrustSignal,
    TrustStage,
    verdict_for,
)
from app.lib.prices import format_money
from app.lib.types import Money as PriceMoney

PRICE_RED_FLAG = "Precio más de 50% bajo el mercado"
ASIN_RED_FLAG = "Precio más de 50% bajo la mediana del mismo ASIN"
PHOTO_RED_FLAG = "Varias fotos copiadas de otros vendedores"
JOIN_MIN = 0.70
META_CHANNELS = frozenset({"instagram", "facebook", "tiktok"})
CHANNEL_OF = {
    "ig-v1": "instagram",
    "tiktok-v1": "tiktok",
    "fb-v1": "facebook",
    "ml-v1": "mercadolibre",
    "web-v1": "web",
    "amazon-v1": "amazon",
    "import-v1": "importacion",
}
_METHOD_RANK = {"rif": 6, "dominio": 5, "declarado": 4, "telefono": 3, "handle": 2, "manual": 1}
_SOCIAL = frozenset({"instagram", "tiktok", "facebook"})
_SKIP_FACEBOOK_PATH = frozenset({"marketplace", "profile", "people"})

_NO_WARRANTY = re.compile(r"sin garant", re.IGNORECASE)
_RISK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(sin|no hay|no se aceptan)\s+devoluci", re.IGNORECASE), "No acepta devoluciones"),
    (
        re.compile(r"(últimas?|ultimas?)\s+unidades|solo\s+(por\s+)?hoy|quedan\s+\d+", re.IGNORECASE),
        "Usa presión de urgencia",
    ),
    (
        re.compile(r"(precio|oferta)\s+(de\s+)?(locura|regalado|remate)", re.IGNORECASE),
        "Precios 'demasiado buenos'",
    ),
]
_LEVEL_VALUE = {"5_green": 1.0, "4_light_green": 0.75, "3_yellow": 0.4, "2_orange": 0.15, "1_red": 0.0}
_LEVEL_LABEL = {
    "5_green": "verde",
    "4_light_green": "verde claro",
    "3_yellow": "amarillo",
    "2_orange": "naranja",
    "1_red": "rojo",
}
_POWER_SELLER = {"platinum": 1.0, "gold": 0.8, "silver": 0.6}
_STRONG_BADGES = re.compile(r"super|súper|highly rated|muy bien calificad", re.IGNORECASE)
_OTHER_BADGES = re.compile(r"responsive|receptiv|reliable|confiable|shipper|envío", re.IGNORECASE)

MethodName = Literal["rif", "dominio", "declarado", "telefono", "handle", "manual"]


@dataclass(frozen=True)
class Measured:
    value: float | Literal["pending"] | None
    reason: str | None = None
    good: bool | None = None


@dataclass(frozen=True)
class Fill:
    value: float
    reason: str | None = None
    good: bool | None = None


@dataclass(frozen=True)
class AdjustmentBinding:
    adjustment: Adjustment
    merchant_id: str | None = None
    facebook_page_id: str | None = None


@dataclass(frozen=True)
class IdentityCandidate:
    """Par que no llega a 0,70. Se anota y no cambia el puntaje."""

    left: str
    right: str
    method: MethodName
    confidence: float
    evidence: str


@dataclass(frozen=True)
class ParseNote:
    offer_id: str
    code: str
    detail: str


@dataclass(frozen=True)
class AggregateResult:
    offers: list[Offer]
    merchants: list[Merchant]
    identities: list[MerchantIdentity]
    candidates: list[IdentityCandidate]
    price_stats: list[PriceStat]
    dropped: list[ParseNote]


def round_half_up(value: float) -> int:
    """0,5 sube. round() de Python iría al par más cercano."""
    return math.floor(value + 0.5)


def clamp(value: float, lo: float = 0, hi: float = 1) -> float:
    return max(lo, min(hi, value))


def to_stars(score: int | None) -> int | None:
    """0–100 interno → 0–5 de la interfaz. null no tiene estrellas."""
    if score is None:
        return None
    if score <= 0:
        return 0
    if score < 50:
        return 1
    if score < 60:
        return 2
    if score < 75:
        return 3
    if score < 90:
        return 4
    return 5


def entity_id_for(evidence: str) -> str:
    return hashlib.sha256(evidence.encode()).hexdigest()[:24]


def anomaly_from_deviation(deviation: float) -> tuple[float, str, bool]:
    """`(precio - mediana) / mediana`. Negativo: más barato que el mercado."""
    if deviation >= -0.15:
        value = 1.0
        return value, "Precio en línea con el mercado", True
    value = clamp(1 - ((-deviation) - 0.15) / 0.3)
    percent = round_half_up(-deviation * 100)
    return value, f"Precio {percent}% bajo el mercado", value == 1


def build_signals(formula: str, values: dict[str, Measured] | None = None) -> list[TrustSignal]:
    """Arma la lista completa del canal. Lo que no viene queda null o pending."""
    provided = values or {}
    specs = CATALOGS[formula]
    unknown = set(provided) - {spec.key for spec in specs}
    if unknown:
        raise ValueError(f"unknown signals for {formula}: {sorted(unknown)}")
    signals: list[TrustSignal] = []
    for spec in specs:
        if spec.key in provided:
            measured = provided[spec.key]
            value, reason, good = measured.value, measured.reason, measured.good
        elif spec.filled_by == "aggregator":
            value, reason, good = "pending", None, None
        else:
            value, reason, good = None, None, None
        signals.append(
            TrustSignal(
                family=spec.family,
                key=spec.key,
                weight=spec.weight,
                value=value,
                reason=reason,
                good=good,
            )
        )
    return signals


def compute_trust(
    formula: str,
    signals: list[TrustSignal],
    *,
    stage: TrustStage,
    red_flags: list[str] | None = None,
    adjustments: list[Adjustment] | None = None,
    extra_bonus: float = 0,
    now: datetime | None = None,
) -> TrustScore:
    """Cierra o deja abierto un puntaje. extra_bonus es el +10 de Marketplace."""
    if extra_bonus < 0 or extra_bonus > 10:
        raise ValueError("extra_bonus must be from 0 to 10")
    # model_copy no vuelve a validar: un 0 entero no es float y si no se cuenta, null y 0 se confunden.
    signals = _numbers_as_floats(signals)
    adjustments = list(adjustments or [])
    flags = _dedupe([*(red_flags or []), *[flag for item in adjustments for flag in item.red_flags]])
    coverage = _coverage(signals)
    reasons = _reasons(signals, flags, adjustments)
    moment = now or datetime.now(UTC)
    if stage == "parcial":
        return TrustScore(
            score=None,
            coverage=coverage,
            verdict="sin_datos",
            stage="parcial",
            red_flags=flags,
            reasons=reasons,
            signals=signals,
            adjustments=adjustments,
            formula=formula,
            computed_at=moment,
        )
    if flags:
        return TrustScore(
            score=0,
            coverage=coverage,
            verdict="riesgosa",
            stage="final",
            red_flags=flags,
            reasons=reasons,
            signals=signals,
            adjustments=adjustments,
            formula=formula,
            computed_at=moment,
        )
    if coverage < MIN_COVERAGE:
        return TrustScore(
            score=None,
            coverage=coverage,
            verdict="sin_datos",
            stage="final",
            red_flags=flags,
            reasons=reasons,
            signals=signals,
            adjustments=adjustments,
            formula=formula,
            computed_at=moment,
        )
    base = _weighted(signals)
    bonus = extra_bonus + sum(item.bonus for item in adjustments)
    penalty = sum(item.penalty for item in adjustments)
    score = round_half_up(clamp(base + bonus - penalty, 0, 100))
    return TrustScore(
        score=score,
        coverage=coverage,
        verdict=verdict_for(score),
        stage="final",
        red_flags=flags,
        reasons=reasons,
        signals=signals,
        adjustments=adjustments,
        formula=formula,
        computed_at=moment,
    )


def finalize(
    score: TrustScore,
    fills: dict[str, Fill | None],
    *,
    extra_flags: list[str] | None = None,
    adjustments: list[Adjustment] | None = None,
    extra_bonus: float = 0,
    now: datetime | None = None,
) -> TrustScore:
    """Pasa a final. Cada pending se llena o baja a null. No queda ninguno."""
    signals: list[TrustSignal] = []
    for signal in score.signals:
        if signal.value != "pending":
            signals.append(signal)
            continue
        fill = fills.get(signal.key)
        if fill is None:
            signals.append(signal.model_copy(update={"value": None, "reason": None, "good": None}))
            continue
        signals.append(
            signal.model_copy(update={"value": float(fill.value), "reason": fill.reason, "good": fill.good})
        )
    return compute_trust(
        score.formula,
        signals,
        stage="final",
        red_flags=_dedupe([*score.red_flags, *(extra_flags or [])]),
        adjustments=[*score.adjustments, *(adjustments or [])],
        extra_bonus=extra_bonus,
        now=now or score.computed_at,
    )


def score_import(
    *,
    amazon_score: float | None,
    weight_source: Literal["listing", "tabla"],
    tax_source: Literal["cotizado", "tabla"],
    eta_days_min: int | None = None,
    eta_days_max: int | None = None,
    now: datetime | None = None,
) -> TrustScore:
    """import-v1 en parcial. El agregador llena price_anomaly contra la mediana del ASIN.

    `courier_trust` queda null: courier-v1 no está confirmado, y null no es cero.
    """
    values: dict[str, Measured] = {
        "weight_source": Measured(
            1.0 if weight_source == "listing" else 0.4,
            "Peso del listing de Amazon" if weight_source == "listing" else "Peso de la tabla por categoría",
            weight_source == "listing",
        ),
        "tax_source": Measured(
            1.0 if tax_source == "cotizado" else 0.5,
            "Impuesto que cotizó el courier" if tax_source == "cotizado" else "Impuesto de la tabla",
            tax_source == "cotizado",
        ),
    }
    if amazon_score is not None:
        shown = round_half_up(amazon_score)
        values["amazon_seller"] = Measured(
            amazon_score / 100,
            f"Vendedor de Amazon {shown}/100",
            amazon_score >= 75,
        )
    spread = _eta_spread(eta_days_min, eta_days_max)
    if spread is not None:
        values["eta_spread"] = Measured(
            spread,
            f"Entrega en {eta_days_min}-{eta_days_max} días",
            spread >= 0.7,
        )
    return compute_trust("import-v1", build_signals("import-v1", values), stage="parcial", now=now)


def _eta_spread(low: int | None, high: int | None) -> float | None:
    """Rango declarado y corto vale 1. Sin días, no hay dato."""
    if low is None or high is None or high < low:
        return None
    span = high - low
    if span <= 7:
        return 1.0
    return clamp(1 - (span - 7) / 14)


def amazon_sold_and_shipped(now: datetime | None = None) -> TrustScore:
    """Si vende y envía Amazon, no se calculan señales."""
    return TrustScore(
        score=95,
        coverage=1,
        verdict="confiable",
        stage="final",
        reasons=["Vendido y enviado por Amazon"],
        formula="amazon-v1",
        computed_at=now or datetime.now(UTC),
    )


def facebook_rating_bonus(
    rating_avg: float | None,
    rating_count: int | None,
    badges: list[str] | None = None,
) -> int:
    """Hasta +10. Sin calificaciones no resta: en Marketplace casi nadie califica."""
    points = 0.0
    if rating_avg is not None and (rating_count or 0) >= 5:
        count = rating_count or 0
        smoothed = (5 * 3.5 + count * rating_avg) / (5 + count)
        points += 7 * clamp((smoothed - 4.0) / 0.8)
    names = badges or []
    if any(_STRONG_BADGES.search(badge) for badge in names):
        points += 3
    elif any(_OTHER_BADGES.search(badge) for badge in names):
        points += 1.5
    return min(10, round_half_up(points))


def score_mercadolibre(
    item: dict[str, Any],
    seller: dict[str, Any] | None = None,
    *,
    description: str | None = None,
    price_deviation: float | None = None,
    verified_reports: int | None = None,
    now: datetime | None = None,
    stage: TrustStage = "parcial",
) -> TrustScore:
    """Puntaje ml-v1 desde el JSON de /items y /users. No llama a la API."""
    moment = now or datetime.now(UTC)
    text = _description(item, description)
    flags: list[str] = []
    values: dict[str, Measured] = {}
    if seller is not None:
        flags.extend(_ml_flags(seller, moment))
        values.update(_ml_seller_signals(seller, _item_state(item), moment))
    pictures = _picture_count(item)
    words = len(text.split())
    completeness = 0.5 * clamp(pictures / 4) + 0.5 * clamp(words / 40)
    values["completeness"] = Measured(
        completeness,
        "Publicación con pocas fotos o sin descripción" if completeness < 0.4 else None,
        completeness >= 0.7,
    )
    warranty = _warranty(item)
    has_warranty = bool(warranty) and _NO_WARRANTY.search(warranty or "") is None
    values["warranty"] = Measured(
        1.0 if has_warranty else 0.3,
        f"Garantía: {warranty}" if has_warranty else "Sin garantía declarada",
        has_warranty,
    )
    hits = [label for pattern, label in _RISK_PATTERNS if pattern.search(f"{item.get('title') or ''}\n{text}")]
    values["risk_language"] = Measured(clamp(1 - len(hits) / 3), " · ".join(hits) or None, not hits)
    if price_deviation is None:
        values["price_anomaly"] = Measured("pending")
    else:
        number, reason, good = anomaly_from_deviation(price_deviation)
        values["price_anomaly"] = Measured(number, reason, good)
        if price_deviation <= -0.5:
            flags.append(PRICE_RED_FLAG)
    if verified_reports is None:
        values["reports"] = Measured(None)
    else:
        number = clamp(1 - verified_reports / 3)
        reason = f"{verified_reports} reporte(s) de estafa verificados" if verified_reports else None
        values["reports"] = Measured(number, reason, number == 1)
        if verified_reports >= 3:
            flags.append("Múltiples reportes de estafa verificados")
    partial = compute_trust("ml-v1", build_signals("ml-v1", values), stage="parcial", red_flags=flags, now=moment)
    if stage == "parcial":
        return partial
    return finalize(partial, {}, now=moment)


def resolve_identities(
    merchants: list[Merchant],
) -> tuple[list[MerchantIdentity], list[IdentityCandidate]]:
    """Une comercios desde confianza 0,70. Por debajo solo queda el candidato."""
    unique: dict[str, Merchant] = {}
    order: list[str] = []
    for merchant in merchants:
        if merchant.id not in unique:
            order.append(merchant.id)
        unique[merchant.id] = merchant
    owns = {merchant_id: _owns(unique[merchant_id]) for merchant_id in order}
    declared = {merchant_id: _declared(unique[merchant_id]) for merchant_id in order}
    joins: list[tuple[str, str, float, MethodName, str]] = []
    weak: list[IdentityCandidate] = []

    def add(left: str, right: str, confidence: float, method: MethodName, evidence: str) -> None:
        if left == right:
            return
        a, b = sorted((left, right))
        if confidence >= JOIN_MIN:
            joins.append((a, b, confidence, method, evidence))
        else:
            weak.append(IdentityCandidate(a, b, method, confidence, evidence))

    by_rif: dict[str, set[str]] = {}
    by_domain: dict[str, set[str]] = {}
    by_phone: dict[str, set[str]] = {}
    for merchant_id in order:
        for kind, value in owns[merchant_id] | declared[merchant_id]:
            if kind == "rif":
                by_rif.setdefault(value, set()).add(merchant_id)
            elif kind == "dominio":
                by_domain.setdefault(value, set()).add(merchant_id)
            elif kind == "whatsapp":
                by_phone.setdefault(value, set()).add(merchant_id)
    _join_index(by_rif, 1.0, "rif", "rif", add)
    _join_index(by_domain, 0.90, "dominio", "dominio", add)
    _join_index(by_phone, 0.80, "telefono", "telefono", add)
    for index, left in enumerate(order):
        for right in order[index + 1 :]:
            forward = bool(declared[left] & owns[right])
            backward = bool(declared[right] & owns[left])
            if not forward and not backward:
                continue
            evidence = f"declarado:{min(left, right)}:{max(left, right)}"
            if forward and backward:
                add(left, right, 0.90, "declarado", evidence)
            else:
                add(left, right, 0.60, "declarado", evidence)
    by_handle: dict[str, list[tuple[str, str]]] = {}
    for merchant_id in order:
        for kind, value in owns[merchant_id]:
            if kind in _SOCIAL:
                by_handle.setdefault(value, []).append((merchant_id, kind))
    for value, rows in by_handle.items():
        for index, (left, left_kind) in enumerate(rows):
            for right, right_kind in rows[index + 1 :]:
                if left == right or left_kind == right_kind:
                    continue
                add(left, right, 0.50, "handle", f"handle:{value}")

    parent = {merchant_id: merchant_id for merchant_id in order}
    best: dict[str, tuple[float, int, MethodName, str]] = {}

    def find(merchant_id: str) -> str:
        while parent[merchant_id] != merchant_id:
            parent[merchant_id] = parent[parent[merchant_id]]
            merchant_id = parent[merchant_id]
        return merchant_id

    for left, right, confidence, method, evidence in joins:
        incoming = (confidence, _METHOD_RANK[method], method, evidence)
        ra, rb = find(left), find(right)
        if ra == rb:
            best[ra] = _better(best[ra], incoming) if ra in best else incoming
            continue
        parent[rb] = ra
        chosen = incoming
        if ra in best:
            chosen = _better(best[ra], chosen)
        if rb in best:
            chosen = _better(best[rb], chosen)
        best[ra] = chosen
        best.pop(rb, None)

    identities: list[MerchantIdentity] = []
    groups: dict[str, list[str]] = {}
    for merchant_id in order:
        groups.setdefault(find(merchant_id), []).append(merchant_id)
    for root, members in groups.items():
        ordered = sorted(members)
        if root in best:
            confidence, _rank, method, evidence = best[root]
        else:
            only = unique[ordered[0]]
            confidence, method, evidence = _self_evidence(only, owns[only.id], declared[only.id])
        identities.append(
            MerchantIdentity(
                entity_id=entity_id_for(evidence),
                members=ordered,
                method=method,
                confidence=confidence,
            )
        )
    seen: set[tuple[str, str, str, str]] = set()
    candidates: list[IdentityCandidate] = []
    for candidate in weak:
        if find(candidate.left) == find(candidate.right):
            continue
        key = (candidate.left, candidate.right, candidate.method, candidate.evidence)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    candidates.sort(key=lambda item: (item.left, item.right, item.method, item.evidence))
    identities.sort(key=lambda item: item.members[0])
    return identities, candidates


def aggregate(
    offers: list[Offer],
    merchants: list[Merchant],
    adjustments: list[AdjustmentBinding] | None = None,
    *,
    photos_seen_elsewhere: dict[str, int] | None = None,
    now: datetime | None = None,
) -> AggregateResult:
    """Cuatro pasadas: mediana e identidad, canales directos, web, Meta Ads."""
    moment = now or datetime.now(UTC)
    bindings = list(adjustments or [])
    people = _unique_merchants(merchants)
    identities, candidates = resolve_identities(people)
    entity_of = {member: identity.entity_id for identity in identities for member in identity.members}
    people = [merchant.model_copy(update={"entity_id": entity_of.get(merchant.id)}) for merchant in people]
    by_id = {merchant.id: merchant for merchant in people}

    kept: list[Offer] = []
    dropped: list[ParseNote] = []
    for offer in offers:
        problem = _evidence_problem(offer)
        if problem:
            dropped.append(ParseNote(offer.id, "parseo", problem))
            continue
        kept.append(offer)

    groups: dict[tuple[str, Condition], list[Offer]] = {}
    for offer in kept:
        groups.setdefault((offer.product.key, offer.condition), []).append(offer)
    medians: dict[tuple[str, Condition], tuple[float, int]] = {}
    stats: list[PriceStat] = []
    for key, group in groups.items():
        priced = [offer for offer in group if _priced(offer)]
        if len(priced) < 5:
            continue
        prices = [float(offer.price_usd) for offer in priced if offer.price_usd is not None]
        median = float(statistics.median(prices))
        medians[key] = (median, len(priced))
        sources = sorted(
            by_id[offer.merchant_id].channel if offer.merchant_id in by_id else "unknown" for offer in priced
        )
        stats.append(
            PriceStat(
                product_key=key[0],
                condition=key[1],
                median_usd=median,
                comparables=len(priced),
                sources=sources,
            )
        )

    def judge_for(offer: Offer) -> tuple[Judgement, float | None]:
        priced = [item for item in groups.get((offer.product.key, offer.condition), []) if _priced(item)]
        found = medians.get((offer.product.key, offer.condition))
        if not _priced(offer) or found is None or found[0] == 0 or offer.price_usd is None:
            return Judgement(price_deviation=None, comparables=len(priced)), None
        deviation = (offer.price_usd - found[0]) / found[0]
        return Judgement(price_deviation=deviation, comparables=len(priced)), deviation

    # Pasada 2: instagram, tiktok, facebook, mercadolibre, amazon.
    # La web espera, porque linked_socials necesita estos puntajes ya cerrados.
    staged: list[Offer] = []
    for offer in kept:
        judge, deviation = judge_for(offer)
        if _channel(offer, by_id) == "web":
            staged.append(offer.model_copy(update={"judge": judge}))
            continue
        staged.append(_close_offer(offer, judge, deviation, None, photos_seen_elsewhere, moment))

    social: dict[tuple[str, str], int] = {}
    for offer in staged:
        merchant = by_id.get(offer.merchant_id)
        if merchant is None or merchant.entity_id is None or offer.trust.score is None:
            continue
        if merchant.channel in {"instagram", "tiktok"}:
            key = (merchant.entity_id, merchant.channel)
            social[key] = max(social.get(key, offer.trust.score), offer.trust.score)

    # Pasada 3: la tienda web, con el mejor puntaje de sus redes ya cerradas.
    after_web: list[Offer] = []
    for offer in staged:
        if _channel(offer, by_id) != "web":
            after_web.append(offer)
            continue
        judge, deviation = judge_for(offer)
        merchant = by_id.get(offer.merchant_id)
        linked = _linked_fill(merchant, social)
        after_web.append(_close_offer(offer, judge, deviation, linked, photos_seen_elsewhere, moment))

    # Pasada 4: Meta Ads corrige un puntaje que ya existe. No crea uno nuevo.
    final: list[Offer] = []
    for offer in after_web:
        merchant = by_id.get(offer.merchant_id)
        channel = merchant.channel if merchant is not None else _channel(offer, by_id)
        adjustment = _adjustment_for(merchant, bindings) if channel in META_CHANNELS else None
        if adjustment is None:
            final.append(offer)
            continue
        trust = finalize(offer.trust, {}, adjustments=[adjustment], now=moment)
        final.append(offer.model_copy(update={"trust": trust}))

    stats.sort(key=lambda item: (item.product_key, item.condition))
    return AggregateResult(final, people, identities, candidates, stats, dropped)


def to_card(offer: Offer, merchant: Merchant, *, rank: int, is_example: bool) -> OfferCard:
    """Tarjeta para quien redacta. Las señales y source_data no viajan."""
    city = None
    if merchant.location is not None:
        city = merchant.location.city or merchant.location.state
    rate_note = None
    if offer.rate_used is not None:
        amount = offer.rate_used.usd_to_ves
        shown = int(amount) if float(amount).is_integer() else amount
        day = offer.rate_used.observed_at.date().isoformat()
        rate_note = f"{shown} Bs/USD ({offer.rate_used.source}, {day})"
    price_display = None
    if offer.price is not None:
        price_display = format_money(PriceMoney(offer.price.amount, offer.price.currency))
    return OfferCard(
        offer_id=offer.id,
        title=offer.title,
        url=offer.url,
        seen_at=offer.seen_at,
        merchant_name=merchant.name,
        channel=merchant.channel,
        trust_verdict=offer.trust.verdict,
        is_example=is_example,
        rank=rank,
        price_display=price_display,
        price_usd=offer.price_usd,
        rate_note=rate_note,
        city=city,
        delivers=merchant.delivers,
        trust_score=offer.trust.score,
        trust_stars=to_stars(offer.trust.score),
        trust_reasons=offer.trust.reasons[:3],
        trust_red_flags=list(offer.trust.red_flags),
    )


def close_listings(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cierra las ofertas de contrato que vengan en el JSON de una tool.

    Una tarjeta con `trust` entero (la búsqueda de hoy) se devuelve igual.
    """
    output = [dict(item) for item in listings]
    prepared: list[tuple[int, Offer, Merchant]] = []
    bindings: list[AdjustmentBinding] = []
    for index, item in enumerate(output):
        raw_offer = item.get("contractOffer")
        raw_merchant = item.get("contractMerchant")
        if raw_offer is None and raw_merchant is None:
            _bind_adjustment(item, bindings)
            continue
        if not isinstance(raw_offer, dict) or not isinstance(raw_merchant, dict):
            item["trustError"] = "parseo"
            continue
        try:
            offer = Offer.model_validate(raw_offer)
            merchant = Merchant.model_validate(raw_merchant)
        except ValidationError:
            item["trustError"] = "parseo"
            continue
        prepared.append((index, offer, merchant))
        _bind_adjustment(item, bindings)
    if not prepared:
        return output
    result = aggregate(
        [offer for _index, offer, _merchant in prepared],
        [merchant for _index, _offer, merchant in prepared],
        bindings,
    )
    closed = {offer.id: offer for offer in result.offers}
    failed = {note.offer_id for note in result.dropped}
    merchants = {merchant.id: merchant for merchant in result.merchants}
    for index, offer, _merchant in prepared:
        if offer.id in failed:
            output[index]["trustError"] = "parseo"
            continue
        done = closed[offer.id]
        output[index]["trust"] = done.trust.model_dump(mode="json", by_alias=True)
        output[index]["trustStars"] = to_stars(done.trust.score)
        output[index]["contractOffer"] = done.model_dump(mode="json", by_alias=True)
        merchant = merchants.get(done.merchant_id)
        if merchant is not None:
            output[index]["contractMerchant"] = merchant.model_dump(mode="json", by_alias=True)
    return output


def _numbers_as_floats(signals: list[TrustSignal]) -> list[TrustSignal]:
    normalized: list[TrustSignal] = []
    for signal in signals:
        if isinstance(signal.value, bool) or not isinstance(signal.value, int):
            normalized.append(signal)
            continue
        normalized.append(signal.model_copy(update={"value": float(signal.value)}))
    return normalized


def _coverage(signals: list[TrustSignal]) -> float:
    total = sum(signal.weight for signal in signals)
    if total == 0:
        return 0.0
    measured = sum(signal.weight for signal in signals if isinstance(signal.value, float))
    return measured / total


def _weighted(signals: list[TrustSignal]) -> int:
    chosen = [signal for signal in signals if isinstance(signal.value, float)]
    weight = sum(signal.weight for signal in chosen)
    if weight == 0:
        return 0
    raw = 100 * sum(signal.weight * float(signal.value) for signal in chosen) / weight
    return round_half_up(raw)


def _reasons(signals: list[TrustSignal], flags: list[str], adjustments: list[Adjustment]) -> list[str]:
    ranked = sorted(
        (signal for signal in signals if signal.reason),
        key=lambda signal: signal.weight * (1 - (float(signal.value) if isinstance(signal.value, float) else 1.0)),
        reverse=True,
    )
    ordered = [*flags, *[signal.reason for signal in ranked if signal.reason]]
    for item in adjustments:
        ordered.extend(item.reasons)
    return _dedupe(ordered)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _close_offer(
    offer: Offer,
    judge: Judgement,
    deviation: float | None,
    linked: Fill | None,
    photos: dict[str, int] | None,
    now: datetime,
) -> Offer:
    trust = offer.trust
    if trust.formula == "amazon-v1" and not trust.signals and trust.score == 95:
        return offer.model_copy(update={"judge": judge})
    seen = None if photos is None or offer.id not in photos else photos[offer.id]
    fills, flags = _pending_fills(offer, deviation=deviation, photos_seen=seen, linked=linked)
    return offer.model_copy(update={"trust": finalize(trust, fills, extra_flags=flags, now=now), "judge": judge})


def _pending_fills(
    offer: Offer,
    *,
    deviation: float | None,
    photos_seen: int | None,
    linked: Fill | None,
) -> tuple[dict[str, Fill | None], list[str]]:
    fills: dict[str, Fill | None] = {}
    flags: list[str] = []
    for signal in offer.trust.signals:
        if signal.value != "pending":
            continue
        if signal.key == "price_anomaly":
            # La importación no se compara con Venezuela: un total más barato
            # que las tiendas locales es el hallazgo, no un fraude. La señal
            # mira el precio de Amazon contra la mediana del mismo ASIN.
            if offer.trust.formula == "import-v1":
                fill, flag = _asin_price_fill(offer)
                fills[signal.key] = fill
                if flag:
                    flags.append(flag)
            elif deviation is None:
                fills[signal.key] = None
            else:
                value, reason, good = anomaly_from_deviation(deviation)
                fills[signal.key] = Fill(value, reason, good)
                if deviation <= -0.5:
                    flags.append(PRICE_RED_FLAG)
        elif signal.key == "photos_original":
            if photos_seen is None:
                fills[signal.key] = None
            else:
                own = photos_seen == 0
                fills[signal.key] = Fill(
                    1.0 if own else 0.0,
                    "Fotos propias" if own else "Fotos usadas también por otros vendedores",
                    own,
                )
                if photos_seen >= 2:
                    flags.append(PHOTO_RED_FLAG)
        elif signal.key == "linked_socials":
            fills[signal.key] = linked
        else:
            fills[signal.key] = None
    return fills, flags


def _linked_fill(merchant: Merchant | None, social: dict[tuple[str, str], int]) -> Fill | None:
    if merchant is None or merchant.entity_id is None:
        return None
    best: int | None = None
    for channel in ("instagram", "tiktok"):
        score = social.get((merchant.entity_id, channel))
        if score is not None:
            best = score if best is None else max(best, score)
    if best is None:
        return None
    return Fill(best / 100, f"Sus redes enlazadas tienen score {best}/100", best >= 75)


def _channel(offer: Offer, merchants: dict[str, Merchant]) -> str | None:
    merchant = merchants.get(offer.merchant_id)
    if merchant is not None:
        return merchant.channel
    return CHANNEL_OF.get(offer.trust.formula)


def _asin_price_fill(offer: Offer) -> tuple[Fill | None, str | None]:
    landed = offer.landed
    if landed is None or landed.asin_median_usd is None or landed.asin_median_usd <= 0:
        return None, None
    deviation = (landed.product_usd - landed.asin_median_usd) / landed.asin_median_usd
    value, reason, good = anomaly_from_deviation(deviation)
    reason = reason.replace("el mercado", "la mediana de su ASIN")
    flag = ASIN_RED_FLAG if deviation <= -0.5 else None
    return Fill(value, reason, good), flag


def _priced(offer: Offer) -> bool:
    # "estimado" es el total puesto en Venezuela. No entra en la mediana local:
    # si entrara, una importación barata bajaría el mercado contra el que se mide.
    return offer.price_usd is not None and offer.price_kind == "publicado"


def _evidence_problem(offer: Offer) -> str | None:
    known = set(offer.evidence_ids)
    for signal in offer.trust.signals:
        if signal.evidence_id and signal.evidence_id not in known:
            return f"signal {signal.key} cites evidence that the offer does not include"
    return None


def _adjustment_for(merchant: Merchant | None, bindings: list[AdjustmentBinding]) -> Adjustment | None:
    if merchant is None:
        return None
    for binding in bindings:
        if binding.merchant_id and binding.merchant_id == merchant.id:
            return binding.adjustment
        if binding.facebook_page_id and binding.facebook_page_id == merchant.facebook_page_id:
            return binding.adjustment
    return None


def _unique_merchants(merchants: list[Merchant]) -> list[Merchant]:
    unique: dict[str, Merchant] = {}
    order: list[str] = []
    for merchant in merchants:
        if merchant.id not in unique:
            order.append(merchant.id)
        unique[merchant.id] = merchant
    return [unique[merchant_id] for merchant_id in order]


def _bind_adjustment(item: dict[str, Any], bindings: list[AdjustmentBinding]) -> None:
    raw = item.get("contractAdjustment")
    if not isinstance(raw, dict):
        return
    try:
        adjustment = Adjustment.model_validate(raw)
    except ValidationError:
        return
    merchant = item.get("contractMerchant")
    merchant_id = item.get("merchantId")
    if merchant_id is None and isinstance(merchant, dict):
        merchant_id = merchant.get("id")
    page = item.get("facebookPageId")
    if page is None and isinstance(merchant, dict):
        page = merchant.get("facebookPageId") or merchant.get("facebook_page_id")
    bindings.append(
        AdjustmentBinding(
            adjustment=adjustment,
            merchant_id=merchant_id if isinstance(merchant_id, str) else None,
            facebook_page_id=page if isinstance(page, str) else None,
        )
    )


def _better(
    left: tuple[float, int, MethodName, str],
    right: tuple[float, int, MethodName, str],
) -> tuple[float, int, MethodName, str]:
    if left[0] != right[0]:
        return left if left[0] > right[0] else right
    if left[1] != right[1]:
        return left if left[1] > right[1] else right
    return left if left[3] <= right[3] else right


def _join_index(
    index: dict[str, set[str]],
    confidence: float,
    method: MethodName,
    prefix: str,
    add: Any,
) -> None:
    for value, ids in index.items():
        ordered = sorted(ids)
        for index_left, left in enumerate(ordered):
            for right in ordered[index_left + 1 :]:
                add(left, right, confidence, method, f"{prefix}:{value}")


def _owns(merchant: Merchant) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    parsed = urlparse(merchant.url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    first = parsed.path.strip("/").split("/")[0].lstrip("@").lower() if parsed.path.strip("/") else ""
    if merchant.channel == "instagram" and first:
        keys.add(("instagram", first))
    elif merchant.channel == "tiktok" and first:
        keys.add(("tiktok", first))
    elif merchant.channel == "facebook" and first and first not in _SKIP_FACEBOOK_PATH:
        keys.add(("facebook", first))
    elif merchant.channel in {"web", "amazon"} and host:
        keys.add(("dominio", host))
    return keys


def _declared(merchant: Merchant) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for link in merchant.links:
        normalized = _norm_link(link)
        if normalized is not None:
            keys.add(normalized)
    return keys


def _norm_link(link: MerchantLink) -> tuple[str, str] | None:
    raw = link.value.strip()
    if link.kind == "rif":
        value = re.sub(r"[^0-9A-Za-z]", "", raw).upper()
        return ("rif", value) if len(value) >= 6 else None
    if link.kind == "whatsapp":
        digits = re.sub(r"\D", "", raw)
        return ("whatsapp", digits) if len(digits) >= 7 else None
    if link.kind == "dominio":
        host = raw.lower().removeprefix("https://").removeprefix("http://").split("/")[0]
        host = host.removeprefix("www.")
        return ("dominio", host) if host else None
    value = raw.lstrip("@").lower()
    return (link.kind, value) if value else None


def _self_evidence(
    merchant: Merchant,
    owns: set[tuple[str, str]],
    declared: set[tuple[str, str]],
) -> tuple[float, MethodName, str]:
    keys = owns | declared
    rifs = sorted(value for kind, value in keys if kind == "rif")
    if rifs:
        return 1.0, "rif", f"rif:{rifs[0]}"
    domains = sorted(value for kind, value in keys if kind == "dominio")
    if domains:
        return 0.90, "dominio", f"dominio:{domains[0]}"
    phones = sorted(value for kind, value in keys if kind == "whatsapp")
    if phones:
        return 0.80, "telefono", f"telefono:{phones[0]}"
    handles = sorted(value for kind, value in owns if kind in _SOCIAL)
    if handles:
        return 0.50, "handle", f"handle:{handles[0]}"
    return 1.0, "manual", f"merchant:{merchant.id}"


def _ml_flags(seller: dict[str, Any], now: datetime) -> list[str]:
    flags: list[str] = []
    status = _seller_status(seller)
    if status and status != "active":
        flags.append("Cuenta de vendedor suspendida o inactiva")
    total = _tx_number(seller, "total") or 0
    if _level_id(seller) == "1_red" and total >= 10:
        flags.append("Reputación roja con más de 10 ventas")
    ratings = _ratings(seller)
    if ratings is not None and total >= 10 and ratings["negative"] >= 0.25:
        flags.append("25% o más de calificaciones negativas")
    registered = _parse_date(seller.get("registration_date"))
    if registered is not None and _months_since(registered, now) < 1:
        flags.append("Cuenta creada hace menos de un mes")
    return flags


def _ml_seller_signals(seller: dict[str, Any], item_state: str | None, now: datetime) -> dict[str, Measured]:
    values: dict[str, Measured] = {}
    level = _level_id(seller)
    if level in _LEVEL_VALUE:
        value = _LEVEL_VALUE[level]
        values["thermometer"] = Measured(value, f"Reputación {_LEVEL_LABEL[level]} en Mercado Libre", value >= 0.75)
    if level:
        power = _reputation(seller).get("power_seller_status")
        name = power if isinstance(power, str) else ""
        value = _POWER_SELLER.get(name, 0.0)
        values["power_seller"] = Measured(value, f"MercadoLíder {name}" if name else None, value > 0)
    completed = _tx_number(seller, "completed")
    if completed is not None:
        value = clamp(math.log10(completed + 1) / 2)
        count = int(completed)
        reason = f"{fmt_int(count)} ventas concretadas" if count > 0 else "Sin ventas concretadas"
        values["sales_volume"] = Measured(value, reason, value >= 0.6)
    total = _tx_number(seller, "total")
    ratings = _ratings(seller)
    if ratings is not None and (total or 0) >= 10:
        negative = ratings["negative"]
        value = clamp(1 - (negative - 0.02) / 0.13)
        reason = f"{round_half_up(negative * 100)}% de calificaciones negativas" if negative > 0.05 else None
        values["negative_ratings"] = Measured(value, reason, value >= 0.7)
    registered = _parse_date(seller.get("registration_date"))
    if registered is not None:
        months = _months_since(registered, now)
        value = 0.0 if months < 3 else clamp(math.log(months / 3) / math.log(12))
        if value >= 0.6:
            reason = f"En Mercado Libre desde {registered.year}"
        else:
            reason = f"Cuenta reciente ({round_half_up(months)} meses)"
        values["account_age"] = Measured(value, reason, value >= 0.6)
    seller_state = _seller_state(seller)
    if seller_state and item_state:
        same = seller_state.lower() == item_state.lower()
        reason = None if same else f"Publica en {item_state} pero su cuenta está en {seller_state}"
        values["location"] = Measured(1.0 if same else 0.4, reason, same)
    return values


def _months_since(moment: datetime, now: datetime) -> float:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return (now - moment).total_seconds() / (60 * 60 * 24 * 30.44)


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def fmt_int(number: int) -> str:
    return f"{number:,}".replace(",", ".")


def _reputation(seller: dict[str, Any]) -> dict[str, Any]:
    rep = seller.get("seller_reputation")
    return rep if isinstance(rep, dict) else {}


def _transactions(seller: dict[str, Any]) -> dict[str, Any]:
    raw = _reputation(seller).get("transactions")
    return raw if isinstance(raw, dict) else {}


def _level_id(seller: dict[str, Any]) -> str | None:
    level = _reputation(seller).get("level_id")
    return level if isinstance(level, str) else None


def _tx_number(seller: dict[str, Any], key: str) -> float | None:
    raw = _transactions(seller)
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _ratings(seller: dict[str, Any]) -> dict[str, float] | None:
    raw = _transactions(seller).get("ratings")
    if not isinstance(raw, dict):
        return None
    parsed: dict[str, float] = {}
    for key in ("positive", "neutral", "negative"):
        value = raw.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        parsed[key] = float(value)
    return parsed


def _seller_status(seller: dict[str, Any]) -> str | None:
    status = seller.get("status")
    if not isinstance(status, dict):
        return None
    site = status.get("site_status")
    return site if isinstance(site, str) else None


def _seller_state(seller: dict[str, Any]) -> str | None:
    address = seller.get("address")
    if not isinstance(address, dict):
        return None
    state = address.get("state")
    return state if isinstance(state, str) and state else None


def _item_state(item: dict[str, Any]) -> str | None:
    address = item.get("seller_address")
    if isinstance(address, dict):
        state = address.get("state")
        if isinstance(state, dict) and isinstance(state.get("name"), str):
            return state["name"]
        if isinstance(state, str) and state:
            return state
    location = item.get("location")
    if isinstance(location, dict):
        state = location.get("state")
        if isinstance(state, dict) and isinstance(state.get("name"), str):
            return state["name"]
    return None


def _picture_count(item: dict[str, Any]) -> int:
    pictures = item.get("pictures")
    if isinstance(pictures, list):
        return len(pictures)
    if isinstance(pictures, int) and not isinstance(pictures, bool):
        return pictures
    return 0


def _warranty(item: dict[str, Any]) -> str | None:
    warranty = item.get("warranty")
    if isinstance(warranty, str) and warranty:
        return warranty
    for term in item.get("sale_terms") or []:
        if isinstance(term, dict) and term.get("id") == "WARRANTY_TIME" and isinstance(term.get("value_name"), str):
            return term["value_name"]
    return None


def _description(item: dict[str, Any], description: str | None) -> str:
    if description is not None:
        return description
    for key in ("description", "plain_text"):
        value = item.get(key)
        if isinstance(value, str):
            return value
    return ""
