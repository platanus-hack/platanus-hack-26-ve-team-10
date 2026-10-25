"""Modelos del puntaje de confianza.

Una señal mide una cosa de 0 a 1. `null` es "no hay dato" y no entra en la cuenta.
`0` es "está mal" y sí entra. `"pending"` lo llena el agregador; en `stage="final"`
no puede quedar ninguno.

Los pesos de cada canal suman 100 y viven aquí, al lado del validador, para que
un canal nuevo no compile con la tabla a medias. Las fórmulas de cada dato están
en trust.py. Los borradores de resources/ no se importan.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.lib.types import Channel

SignalFamily = Literal[
    "identidad",
    "reputacion",
    "interaccion",
    "contenido",
    "tecnico",
    "riesgo",
    "precio",
    "reportes",
]
TrustVerdict = Literal["confiable", "precaucion", "riesgosa", "sin_datos"]
TrustStage = Literal["parcial", "final"]
Condition = Literal["nuevo", "usado", "reacondicionado"]
FilledBy = Literal["specialist", "aggregator", "nobody"]

# Cortes del veredicto. Las estrellas usan los mismos 75 y 50.
RELIABLE_MIN = 75
CAUTION_MIN = 50
MIN_COVERAGE = 0.40


def _camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


class Model(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")


def verdict_for(score: int) -> TrustVerdict:
    if score >= RELIABLE_MIN:
        return "confiable"
    if score >= CAUTION_MIN:
        return "precaucion"
    return "riesgosa"


@dataclass(frozen=True)
class SignalSpec:
    family: SignalFamily
    key: str
    weight: float
    filled_by: FilledBy


def _row(*rows: tuple[SignalFamily, str, float, FilledBy]) -> tuple[SignalSpec, ...]:
    return tuple(SignalSpec(family, key, weight, filled_by) for family, key, weight, filled_by in rows)


# Quién llena price_anomaly, photos_original y linked_socials: el agregador.
# reports no lo llena nadie todavía: sale null, no "pending".
CATALOGS: dict[str, tuple[SignalSpec, ...]] = {
    "ig-v1": _row(
        ("identidad", "age", 15, "specialist"),
        ("identidad", "username_changes", 5, "specialist"),
        ("identidad", "country", 5, "specialist"),
        ("interaccion", "engagement", 15, "specialist"),
        ("interaccion", "consistency", 10, "specialist"),
        ("interaccion", "comment_like_ratio", 5, "specialist"),
        ("interaccion", "comment_quality", 10, "specialist"),
        ("interaccion", "posting_rhythm", 5, "specialist"),
        ("riesgo", "risk_language", 10, "specialist"),
        ("precio", "price_anomaly", 15, "aggregator"),
        ("reportes", "reports", 5, "nobody"),
    ),
    "tiktok-v1": _row(
        ("identidad", "age", 15, "specialist"),
        ("identidad", "region", 5, "specialist"),
        ("interaccion", "like_view_ratio", 15, "specialist"),
        ("interaccion", "ratio_consistency", 5, "specialist"),
        ("interaccion", "hearts_per_follower", 5, "specialist"),
        ("interaccion", "comment_quality", 10, "specialist"),
        ("interaccion", "shares_saves", 5, "specialist"),
        ("interaccion", "posting_rhythm", 5, "specialist"),
        ("riesgo", "risk_language", 5, "specialist"),
        ("precio", "price_anomaly", 20, "aggregator"),
        ("reportes", "reports", 10, "nobody"),
    ),
    "fb-v1": _row(
        ("identidad", "fb_age", 15, "specialist"),
        ("identidad", "location", 5, "specialist"),
        ("contenido", "history", 20, "specialist"),
        ("contenido", "photos_original", 20, "aggregator"),
        ("contenido", "completeness", 5, "specialist"),
        ("riesgo", "risk_language", 5, "specialist"),
        ("precio", "price_anomaly", 20, "aggregator"),
        ("reportes", "reports", 10, "nobody"),
    ),
    "ml-v1": _row(
        ("reputacion", "thermometer", 15, "specialist"),
        ("reputacion", "power_seller", 5, "specialist"),
        ("reputacion", "sales_volume", 10, "specialist"),
        ("reputacion", "negative_ratings", 10, "specialist"),
        ("identidad", "account_age", 10, "specialist"),
        ("identidad", "location", 5, "specialist"),
        ("contenido", "completeness", 5, "specialist"),
        ("contenido", "warranty", 5, "specialist"),
        ("riesgo", "risk_language", 5, "specialist"),
        ("precio", "price_anomaly", 20, "aggregator"),
        ("reportes", "reports", 10, "nobody"),
    ),
    "web-v1": _row(
        ("identidad", "domain_age", 15, "specialist"),
        ("contenido", "contact", 10, "specialist"),
        ("contenido", "policies", 10, "specialist"),
        ("contenido", "catalog", 5, "specialist"),
        ("tecnico", "https", 5, "specialist"),
        ("tecnico", "mx", 5, "specialist"),
        ("tecnico", "safe_browsing", 5, "specialist"),
        ("tecnico", "linked_socials", 10, "aggregator"),
        ("riesgo", "risk_language", 5, "specialist"),
        ("precio", "price_anomaly", 20, "aggregator"),
        ("reportes", "reports", 10, "nobody"),
    ),
    "amazon-v1": _row(
        ("reputacion", "fulfillment", 15, "specialist"),
        ("reputacion", "positive_feedback", 20, "specialist"),
        ("reputacion", "ratings_volume", 10, "specialist"),
        ("reputacion", "recent_activity", 10, "specialist"),
        ("contenido", "alert_reviews", 10, "specialist"),
        ("contenido", "product_history", 5, "specialist"),
        ("precio", "price_anomaly", 20, "aggregator"),
        ("reportes", "reports", 10, "nobody"),
    ),
    # courier_trust queda null hasta confirmar courier-v1 (issue 58, punto abierto 1).
    "import-v1": _row(
        ("reputacion", "amazon_seller", 25, "specialist"),
        ("reputacion", "courier_trust", 20, "specialist"),
        ("contenido", "weight_source", 10, "specialist"),
        ("contenido", "tax_source", 10, "specialist"),
        ("contenido", "eta_spread", 5, "specialist"),
        ("precio", "price_anomaly", 20, "aggregator"),
        ("reportes", "reports", 10, "nobody"),
    ),
}


class TrustSignal(Model):
    """Una señal del canal, la haya medido o no. El peso que falta es la cobertura."""

    family: SignalFamily
    key: str
    weight: float = Field(gt=0)
    value: float | Literal["pending"] | None = None
    reason: str | None = None
    good: bool | None = None
    evidence_id: str | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _value(cls, value: Any) -> float | Literal["pending"] | None:
        if value is None or value == "pending":
            return value
        # ValueError, not TypeError: pydantic turns it into ValidationError. TypeError escapes.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("signal value must be a number from 0 to 1, 'pending', or null")  # noqa: TRY004
        number = float(value)
        if number < 0 or number > 1:
            raise ValueError("signal value must be from 0 to 1")
        return number


class Adjustment(Model):
    """Capa que no puntúa sola. Hoy, Meta Ads: suma o resta sobre un puntaje ya cerrado."""

    source: str
    bonus: float = Field(default=0, ge=0, le=5)
    penalty: float = Field(default=0, ge=0, le=15)
    reasons: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)


class TrustScore(Model):
    score: int | None = Field(default=None, ge=0, le=100)
    coverage: float = Field(ge=0, le=1)
    verdict: TrustVerdict
    stage: TrustStage
    red_flags: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    signals: list[TrustSignal] = Field(default_factory=list)
    adjustments: list[Adjustment] = Field(default_factory=list)
    formula: str
    computed_at: datetime

    @model_validator(mode="after")
    def _consistent(self) -> "TrustScore":
        keys = [signal.key for signal in self.signals]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate signal key")
        if not self.signals:
            if _amazon_shortcut(self):
                return self
            raise ValueError("a score without signals is only the Amazon sold-and-shipped shortcut")
        total = sum(signal.weight for signal in self.signals)
        if abs(total - 100) > 1e-6:
            raise ValueError(f"weights sum to {total}, not 100")
        if not _matches_catalog(self.formula, self.signals):
            raise ValueError(f"signals do not match the {self.formula} catalog")
        measured = sum(signal.weight for signal in self.signals if isinstance(signal.value, float))
        if abs(self.coverage - measured / total) > 1e-6:
            raise ValueError("coverage does not match the measured weight")
        if self.stage == "final" and any(signal.value == "pending" for signal in self.signals):
            raise ValueError("a final score still has a pending signal")
        if self.stage == "parcial":
            if self.score is not None or self.verdict != "sin_datos":
                raise ValueError("a partial score stays open: null score and sin_datos")
            return self
        flags = _all_flags(self)
        if flags:
            if self.score != 0 or self.verdict != "riesgosa":
                raise ValueError("a red flag forces score 0 and verdict riesgosa")
            return self
        if self.coverage < MIN_COVERAGE:
            if self.score is not None or self.verdict != "sin_datos":
                raise ValueError("coverage under 0.40 has no score")
            return self
        if self.score is None or self.verdict == "sin_datos":
            raise ValueError("enough coverage needs a score and a verdict")
        if self.verdict != verdict_for(self.score):
            raise ValueError("verdict does not match the score")
        return self


def _amazon_shortcut(score: TrustScore) -> bool:
    # Vendido y enviado por Amazon: 95, sin calcular señales.
    return (
        score.formula == "amazon-v1"
        and score.stage == "final"
        and score.score == 95
        and score.coverage == 1
        and score.verdict == "confiable"
        and not score.red_flags
        and not any(item.red_flags for item in score.adjustments)
    )


def _matches_catalog(formula: str, signals: list[TrustSignal]) -> bool:
    specs = CATALOGS.get(formula)
    if specs is None:
        return True
    if len(specs) != len(signals):
        return False
    for spec, signal in zip(specs, signals, strict=True):
        if (spec.family, spec.key, spec.weight) != (signal.family, signal.key, signal.weight):
            return False
    return True


def _all_flags(score: TrustScore) -> list[str]:
    flags = list(score.red_flags)
    for item in score.adjustments:
        flags.extend(item.red_flags)
    return flags


class Money(Model):
    amount: float
    currency: Literal["USD", "VES"]


class Location(Model):
    city: str | None = None
    state: str | None = None


class CanonicalProduct(Model):
    key: str
    label: str | None = None


class RateRef(Model):
    source: str
    usd_to_ves: float
    observed_at: datetime


class Judgement(Model):
    """Nota de precio del agregador. El veredicto del vendedor vive en el TrustScore."""

    price_deviation: float | None = None
    comparables: int | None = None


class MerchantLink(Model):
    kind: Literal["instagram", "tiktok", "facebook", "whatsapp", "dominio", "rif"]
    value: str


class Merchant(Model):
    id: str
    name: str
    channel: Channel
    url: str
    entity_id: str | None = None
    location: Location | None = None
    delivers: bool | None = None
    links: list[MerchantLink] = Field(default_factory=list)
    facebook_page_id: str | None = None
    # Crudo de la fuente. El puntaje no lo lee: solo lee señales ya armadas.
    source_data: dict[str, Any] = Field(default_factory=dict)
    trust: TrustScore | None = None


class CourierQuote(Model):
    courier_id: str
    courier_name: str
    freight_usd: float
    tax_usd: float
    insurance_usd: float = 0
    includes_tax: bool
    quoted_at: datetime
    source: Literal["cotizador", "tabla"]
    tax_source: Literal["cotizado", "tabla"]
    eta_days_min: int | None = None
    eta_days_max: int | None = None


class Landed(Model):
    """Desglose puesto en Venezuela. `total_usd` es el `price_usd` de la oferta."""

    product_usd: float
    freight_usd: float
    tax_usd: float
    insurance_usd: float = 0
    total_usd: float
    billable_lb: float
    weight_source: Literal["listing", "tabla"]
    tax_source: Literal["cotizado", "tabla"]
    asin: str
    requirements: list[str] = Field(default_factory=list)
    quotes: list[CourierQuote] = Field(default_factory=list)
    eta_days_min: int | None = None
    eta_days_max: int | None = None
    asin_median_usd: float | None = None


class Offer(Model):
    id: str
    merchant_id: str
    product: CanonicalProduct
    condition: Condition
    title: str
    url: str
    seen_at: datetime
    evidence_ids: list[str] = Field(min_length=1)
    trust: TrustScore
    image_url: str | None = None
    price: Money | None = None
    price_kind: Literal["publicado", "al_dm", "estimado"] = "publicado"
    price_usd: float | None = None
    price_ves: float | None = None
    rate_used: RateRef | None = None
    judge: Judgement | None = None
    fulfiller_id: str | None = None
    landed: Landed | None = None

    @model_validator(mode="after")
    def _price_kind(self) -> "Offer":
        missing = self.price is None
        if missing != (self.price_kind == "al_dm"):
            raise ValueError("a missing price is price_kind al_dm, and a published price is not")
        if self.price_kind == "estimado":
            if self.landed is None or not self.fulfiller_id:
                raise ValueError("an estimate needs a fulfiller and a landed breakdown")
            if self.price_usd is None or abs(float(self.price_usd) - float(self.landed.total_usd)) > 0.02:
                raise ValueError("price_usd is the landed total")
        return self


class MerchantIdentity(Model):
    entity_id: str
    members: list[str] = Field(min_length=1)
    method: Literal["rif", "dominio", "declarado", "telefono", "handle", "manual"]
    confidence: float = Field(ge=0, le=1)


class PriceStat(Model):
    product_key: str
    condition: Condition
    median_usd: float
    comparables: int
    sources: list[str] = Field(default_factory=list)


class OfferCard(Model):
    """Lo que lee quien redacta la respuesta. Sin señales ni source_data."""

    offer_id: str
    title: str
    url: str
    seen_at: datetime
    merchant_name: str
    channel: Channel
    trust_verdict: TrustVerdict
    is_example: bool
    rank: int
    price_display: str | None = None
    price_usd: float | None = None
    rate_note: str | None = None
    city: str | None = None
    delivers: bool | None = None
    trust_score: int | None = None
    trust_stars: int | None = None
    trust_reasons: list[str] = Field(default_factory=list, max_length=3)
    trust_red_flags: list[str] = Field(default_factory=list)


class AnswerPayload(Model):
    job_id: str
    product_label: str
    comparables: int
    cards: list[OfferCard] = Field(default_factory=list, max_length=5)
    best: OfferCard | None = None
    median_usd: float | None = None
    failed_tools: list[str] = Field(default_factory=list)
    notice: str | None = None
