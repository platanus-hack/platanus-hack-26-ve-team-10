"""Website Trust Score — puntaje de seguridad de una tienda o sitio web usando Firecrawl.

Fuentes:
  - Firecrawl (scrape): contenido, links y extracción estructurada (JSON schema) del sitio.
  - RDAP (rdap.org): fecha de registro del dominio. Gratis, sin API key.
  - DNS (dnspython): registros MX del dominio.
  - Google Safe Browsing (opcional): si el sitio está marcado como phishing/malware.

⚠️ Antes de producción:
  - Verifica en el SDK de Python los nombres de `doc.links`, `doc.json` y `doc.metadata`;
    aquí se leen de forma defensiva.
  - RDAP no siempre cubre dominios .ve; si no responde, la antigüedad queda en None.

pip install firecrawl dnspython httpx
env: FIRECRAWL_API_KEY, GOOGLE_SAFE_BROWSING_KEY (opcional)
"""

import asyncio
import math
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

import dns.asyncresolver
import dns.exception
import dns.resolver
import httpx
from firecrawl import AsyncFirecrawl

firecrawl = AsyncFirecrawl(api_key=os.environ.get("FIRECRAWL_API_KEY"))

# ───────────────────────── Tipos ─────────────────────────

Verdict = Literal["confiable", "precaucion", "riesgosa", "sin_datos"]
PolicyKind = Literal["contacto", "nosotros", "terminos", "devoluciones", "garantia", "privacidad"]


@dataclass
class SiteInfo:
    store_name: str | None = None
    claims_to_be_official_store_of: str | None = None  # "Tienda oficial de Samsung", etc.
    legal_name: str | None = None
    rif: str | None = None  # RIF venezolano (J-12345678-9)
    address: str | None = None
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    social_profiles: list[str] = field(default_factory=list)
    payment_methods: list[str] = field(default_factory=list)
    product_count: int | None = None


@dataclass
class PolicyPage:
    kind: PolicyKind
    url: str
    words: int


@dataclass
class Site:
    url: str
    host: str
    domain: str  # dominio registrable (tienda.com.ve)
    https: bool
    markdown: str
    links: list[str]
    info: SiteInfo
    policy_pages: list[PolicyPage]


@dataclass
class Brand:
    name: str
    official_domains: list[str]


@dataclass
class ExternalInputs:
    # Precio vs. mediana de mercado (Prais): -0.35 = 35% más barato.
    price_deviation: float | None = None
    # Reportes de estafa verificados contra este dominio.
    verified_reports: int | None = None
    # Marcas y sus dominios oficiales, para detectar suplantación.
    brands: list[Brand] = field(default_factory=list)
    # Scores de las redes que el sitio enlaza, si ya los corriste con los otros módulos
    # (ig_trust_score, tiktok_trust_score...). 0..100.
    linked_social_scores: list[int] = field(default_factory=list)


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
    url: str
    domain: str
    score: int | None
    coverage: float
    verdict: Verdict
    red_flags: list[str] = field(default_factory=list)
    reasons: list[Reason] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)


# ───────────────────────── Fetch ─────────────────────────

INFO_SCHEMA = {
    "type": "object",
    "properties": {
        "storeName": {"type": "string"},
        "claimsToBeOfficialStoreOf": {"type": "string", "description": "Marca de la que dice ser tienda o distribuidor oficial, si lo dice"},
        "legalName": {"type": "string", "description": "Razón social"},
        "rif": {"type": "string", "description": "RIF venezolano, formato J-12345678-9"},
        "address": {"type": "string", "description": "Dirección física"},
        "phones": {"type": "array", "items": {"type": "string"}},
        "emails": {"type": "array", "items": {"type": "string"}},
        "socialProfiles": {"type": "array", "items": {"type": "string"}, "description": "URLs de Instagram, Facebook, TikTok, etc."},
        "paymentMethods": {"type": "array", "items": {"type": "string"}},
        "productCount": {"type": "number", "description": "Número aproximado de productos visibles"},
    },
}

POLICY_PATTERNS: list[tuple[PolicyKind, re.Pattern[str]]] = [
    ("contacto", re.compile(r"contact", re.IGNORECASE)),
    ("nosotros", re.compile(r"nosotros|quienes-somos|about", re.IGNORECASE)),
    ("terminos", re.compile(r"t[eé]rminos|terms|condiciones", re.IGNORECASE)),
    ("devoluciones", re.compile(r"devoluci|cambios|returns|reembolso|refund", re.IGNORECASE)),
    ("garantia", re.compile(r"garant[ií]a|warranty", re.IGNORECASE)),
    ("privacidad", re.compile(r"privacidad|privacy", re.IGNORECASE)),
]


def _get(obj: Any, name: str) -> Any:
    """El SDK devuelve objetos; algunas versiones, dicts. Se lee de las dos formas."""
    if obj is None:
        return None
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def _info_from_json(data: dict[str, Any] | None) -> SiteInfo:
    data = data or {}
    count = data.get("productCount")
    return SiteInfo(
        store_name=data.get("storeName"),
        claims_to_be_official_store_of=data.get("claimsToBeOfficialStoreOf"),
        legal_name=data.get("legalName"),
        rif=data.get("rif"),
        address=data.get("address"),
        phones=list(data.get("phones") or []),
        emails=list(data.get("emails") or []),
        social_profiles=list(data.get("socialProfiles") or []),
        payment_methods=list(data.get("paymentMethods") or []),
        product_count=int(count) if isinstance(count, int | float) else None,
    )


async def fetch_site(input_url: str) -> Site | None:
    url = input_url if re.match(r"^https?://", input_url, re.IGNORECASE) else f"https://{input_url}"
    try:
        doc = await firecrawl.scrape(
            url,
            formats=["markdown", "links", {"type": "json", "schema": INFO_SCHEMA}],
            only_main_content=False,  # el footer suele tener RIF, dirección y redes
            location={"country": "VE", "languages": ["es-VE"]},
        )
    except Exception:  # noqa: BLE001  el sitio no se pudo leer: sin_datos
        return None

    metadata = _get(doc, "metadata")
    final_url: str = _get(metadata, "url") or _get(metadata, "source_url") or url
    host = (urlparse(final_url).hostname or "").removeprefix("www.").lower()
    links = [link for link in _get(doc, "links") or [] if isinstance(link, str)]
    markdown: str = _get(doc, "markdown") or ""
    # Lo que extrae el LLM manda; el regex rellena lo que falte.
    info = _info_from_json(_get(doc, "json"))
    merge_info(info, regex_info(markdown))

    # Una página por tipo de política, del mismo dominio, máximo 4 scrapes extra.
    same_site = [link for link in links if (safe_host(link) or "").endswith(registrable_domain(host))]
    picked: list[tuple[PolicyKind, str]] = []
    for kind, pattern in POLICY_PATTERNS:
        hit = next((link for link in same_site if pattern.search(urlparse(link).path)), None)
        if hit and all(u != hit for _, u in picked):
            picked.append((kind, hit))

    async def scrape_policy(kind: PolicyKind, page_url: str) -> PolicyPage:
        try:
            d = await firecrawl.scrape(page_url, formats=["markdown"], only_main_content=True)
            md: str = _get(d, "markdown") or ""
            merge_info(info, regex_info(md))  # contacto/nosotros suelen tener RIF y teléfono
            return PolicyPage(kind, page_url, len(md.split()))
        except Exception:  # noqa: BLE001  la política cuenta como vacía
            return PolicyPage(kind, page_url, 0)

    policy_pages = await asyncio.gather(*(scrape_policy(k, u) for k, u in picked[:4]))

    return Site(
        url=final_url,
        host=host,
        domain=registrable_domain(host),
        https=final_url.startswith("https://"),
        markdown=markdown,
        links=links,
        info=info,
        policy_pages=list(policy_pages),
    )


PHONE_RE = re.compile(r"(?:\+?58[\s-]?)?\(?0?(?:2\d{2}|4(?:12|14|16|24|26))\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
SOCIAL_RE = re.compile(r"https?://(?:www\.)?(?:instagram|facebook|tiktok)\.com/[^\s)\"']+", re.IGNORECASE)
RIF_RE = re.compile(r"\b[JVGEP][-\s]?\d{7,9}[-\s]?\d\b", re.IGNORECASE)


def regex_info(md: str) -> SiteInfo:
    """Respaldo por regex para lo que la extracción por LLM a veces omite."""
    rif = RIF_RE.search(md)
    return SiteInfo(
        rif=rif.group(0) if rif else None,
        phones=list(dict.fromkeys(PHONE_RE.findall(md))),
        emails=list(dict.fromkeys(EMAIL_RE.findall(md))),
        social_profiles=list(dict.fromkeys(SOCIAL_RE.findall(md))),
    )


def merge_info(into: SiteInfo, src: SiteInfo) -> None:
    into.rif = into.rif or src.rif
    into.phones = list(dict.fromkeys([*into.phones, *src.phones]))
    into.emails = list(dict.fromkeys([*into.emails, *src.emails]))
    into.social_profiles = list(dict.fromkeys([*into.social_profiles, *src.social_profiles]))


def safe_host(u: str) -> str | None:
    try:
        host = urlparse(u).hostname
    except ValueError:
        return None
    return host.removeprefix("www.").lower() if host else None


TWO_LEVEL_SUFFIXES = re.compile(r"\.(com|net|org|co|gob|gov|edu|info|web)\.[a-z]{2}$")


def registrable_domain(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-3:] if TWO_LEVEL_SUFFIXES.search(host) else parts[-2:])


# ── Fuentes externas al sitio ──


async def domain_registered_at(domain: str) -> datetime | None:
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            res = await client.get(f"https://rdap.org/domain/{domain}")
        if res.status_code != 200:
            return None
        ev = next((e for e in res.json().get("events") or [] if e.get("eventAction") == "registration"), None)
        return datetime.fromisoformat(ev["eventDate"]) if ev and ev.get("eventDate") else None
    except (httpx.HTTPError, ValueError):
        return None


async def has_mx(domain: str) -> bool | None:
    try:
        answer = await dns.asyncresolver.resolve(domain, "MX")
        return len(answer) > 0
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return False
    except dns.exception.DNSException:
        return None


async def safe_browsing_flagged(url: str) -> bool | None:
    """True = marcado como peligroso; False = limpio; None = no se pudo consultar."""
    key = os.environ.get("GOOGLE_SAFE_BROWSING_KEY")
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            res = await client.post(
                "https://safebrowsing.googleapis.com/v4/threatMatches:find",
                params={"key": key},
                json={
                    "client": {"clientId": "prais", "clientVersion": "1.0"},
                    "threatInfo": {
                        "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
                        "platformTypes": ["ANY_PLATFORM"],
                        "threatEntryTypes": ["URL"],
                        "threatEntries": [{"url": url}],
                    },
                },
            )
        if res.status_code != 200:
            return None
        return bool(res.json().get("matches"))
    except (httpx.HTTPError, ValueError):
        return None


# ───────────────────────── Helpers ─────────────────────────


def clamp(x: float, lo: float = 0, hi: float = 1) -> float:
    return max(lo, min(hi, x))


def months_since(d: datetime) -> float:
    return (datetime.now(UTC) - d).total_seconds() / (60 * 60 * 24 * 30.44)


def round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


# Mismos 3 patrones que en redes, más contadores de "oferta termina en".
# Pago Móvil, Zelle, Binance o WhatsApp NO se penalizan: son normales en Venezuela.
RISK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(sin|no hay|no se aceptan)\s+devoluci", re.IGNORECASE), "No acepta devoluciones"),
    (
        re.compile(
            r"(últimas?|ultimas?)\s+unidades|solo\s+(por\s+)?hoy|quedan\s+\d+|(oferta|promo)\w*\s+(termina|acaba|finaliza)\s+en",
            re.IGNORECASE,
        ),
        "Usa presión de urgencia",
    ),
    (re.compile(r"(precio|oferta)\s+(de\s+)?(locura|regalado|remate)", re.IGNORECASE), "Precios 'demasiado buenos'"),
]

FREE_MAIL = re.compile(r"@(gmail|hotmail|outlook|yahoo|icloud|live)\.", re.IGNORECASE)


def _is_official(domain: str, brand: Brand) -> bool:
    return any(domain == d or domain.endswith(f".{d}") for d in brand.official_domains)


def impersonated_brand(domain: str, brands: list[Brand]) -> str | None:
    flat = re.sub(r"[^a-z0-9]", "", domain)
    for b in brands:
        key = re.sub(r"[^a-z0-9]", "", b.name.lower())
        if key and key in flat and not _is_official(domain, b):
            return b.name
    return None


# ───────────────────────── Señales ─────────────────────────


@dataclass
class Externals:
    registered_at: datetime | None
    mx: bool | None
    flagged: bool | None


def compute_signals(site: Site, x: Externals, ext: ExternalInputs) -> list[Signal]:
    s: list[Signal] = []
    info = site.info

    # ── Identidad (25) ──

    # 1. Antigüedad del dominio (15): < 3 meses → 0, 3 años → 1.
    if x.registered_at:
        m = months_since(x.registered_at)
        v = 0 if m < 3 else clamp(math.log(m / 3) / math.log(12))
        s.append(Signal("domain_age", 15, v, good=v >= 0.6,
                        reason=f"Dominio registrado en {x.registered_at.year}" if v >= 0.6 else f"Dominio reciente ({round_half_up(m)} meses)"))
    else:
        s.append(Signal("domain_age", 15, None))

    # 2. Datos de contacto verificables (10): RIF, dirección, teléfono, correo del propio dominio.
    own_email = any(e.lower().endswith(f"@{site.domain}") for e in info.emails)
    if own_email or info.emails and not all(FREE_MAIL.search(e) for e in info.emails):
        email_part = 0.2
    elif info.emails:
        email_part = 0.1
    else:
        email_part = 0
    v = (0.35 if info.rif else 0) + (0.25 if info.address else 0) + (0.2 if info.phones else 0) + email_part
    found = [label for label, ok in (("RIF", info.rif), ("dirección", info.address), ("teléfono", info.phones)) if ok]
    if v >= 0.6:
        reason = f"Publica {', '.join(found)}"
    elif v < 0.3:
        reason = "No publica RIF, dirección ni teléfono"
    else:
        reason = None
    s.append(Signal("contact", 10, v, reason, v >= 0.6))

    # ── Sustancia de la tienda (25) ──

    # 3. Políticas (10): términos, devoluciones, garantía y privacidad con contenido real.
    kinds: list[PolicyKind] = ["terminos", "devoluciones", "garantia", "privacidad"]
    ok_count = sum(1 for k in kinds if any(p.kind == k and p.words >= 120 for p in site.policy_pages))
    v = ok_count / len(kinds)
    s.append(Signal("policies", 10, v, good=v >= 0.5,
                    reason="Tiene políticas de devolución, garantía o términos" if v >= 0.5 else "Sin políticas de devolución ni garantía"))

    # 4. Profundidad del catálogo (5): una "tienda" de 3 productos es sospechosa.
    if info.product_count is not None:
        v = clamp((info.product_count - 3) / 27)  # ≤ 3 → 0, ≥ 30 → 1
        s.append(Signal("catalog", 5, v, "Catálogo muy pequeño" if v < 0.3 else None, v >= 0.6))
    else:
        s.append(Signal("catalog", 5, None))

    # 5. Redes sociales enlazadas (10): si ya las puntuaste con los otros módulos, usa ese score.
    if ext.linked_social_scores:
        best = max(ext.linked_social_scores)
        v = best / 100
        s.append(Signal("linked_socials", 10, v, f"Sus redes enlazadas tienen score {best}/100", v >= 0.75))
    else:
        n = len(info.social_profiles)
        # Sin verificar: crédito parcial.
        s.append(Signal("linked_socials", 10, 0.5 if n else 0.2, None if n else "No enlaza ninguna red social"))

    # ── Técnico (15) ──

    # 6. HTTPS (5)
    s.append(Signal("https", 5, 1 if site.https else 0, None if site.https else "El sitio no usa HTTPS", site.https))

    # 7. Correo del dominio configurado (5): MX en el dominio.
    if x.mx is not None:
        s.append(Signal("mx", 5, 1 if x.mx else 0, None if x.mx else "El dominio no tiene correo configurado", x.mx))
    else:
        s.append(Signal("mx", 5, None))

    # 8. Google Safe Browsing limpio (5). Marcado = bandera roja (ver red_flags).
    if x.flagged is not None:
        s.append(Signal("safe_browsing", 5, 0 if x.flagged else 1, good=not x.flagged))
    else:
        s.append(Signal("safe_browsing", 5, None))

    # ── Comportamiento (5) ──

    # 9. Lenguaje de riesgo (5)
    hits = [label for pattern, label in RISK_PATTERNS if pattern.search(site.markdown)]
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


def red_flags(site: Site, x: Externals, ext: ExternalInputs) -> list[str]:
    f: list[str] = []
    if x.flagged:
        f.append("Google lo marca como sitio peligroso")
    if x.registered_at and months_since(x.registered_at) < 1:
        f.append("Dominio registrado hace menos de un mes")
    imitated = impersonated_brand(site.domain, ext.brands)
    if imitated:
        f.append(f"El dominio imita a {imitated}")
    claimed = site.info.claims_to_be_official_store_of
    brand = next((b for b in ext.brands if claimed and b.name.lower() == claimed.lower()), None)
    if brand and not _is_official(site.domain, brand):
        f.append(f"Dice ser tienda oficial de {brand.name} sin estar en su dominio")
    if ext.price_deviation is not None and ext.price_deviation <= -0.5:
        f.append("Precio más de 50% bajo el mercado")
    if (ext.verified_reports or 0) >= 3:
        f.append("Múltiples reportes de estafa verificados")
    return f


# ───────────────────────── Score ─────────────────────────

MIN_COVERAGE = 0.4


def score_site(site: Site, x: Externals, ext: ExternalInputs | None = None) -> TrustResult:
    ext = ext or ExternalInputs()
    signals = compute_signals(site, x, ext)
    flags = red_flags(site, x, ext)
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
        return TrustResult(site.url, site.domain, 0, coverage, "riesgosa", flags, reasons, signals)
    if coverage < MIN_COVERAGE:
        return TrustResult(site.url, site.domain, None, coverage, "sin_datos", [], reasons, signals)

    score = round_half_up(100 * sum(s.weight * s.value for s in avail) / w_avail)
    verdict: Verdict = "confiable" if score >= 75 else "precaucion" if score >= 50 else "riesgosa"
    return TrustResult(site.url, site.domain, score, coverage, verdict, [], reasons, signals)


# ───────────────────────── Orquestación ─────────────────────────


async def check_site(url: str, ext: ExternalInputs | None = None) -> TrustResult:
    site = await fetch_site(url)
    if not site:
        return TrustResult(url, safe_host(url) or url, None, 0, "sin_datos", reasons=[Reason("No se pudo leer el sitio", False)])
    registered_at, mx, flagged = await asyncio.gather(
        domain_registered_at(site.domain),
        has_mx(site.domain),
        safe_browsing_flagged(site.url),
    )
    return score_site(site, Externals(registered_at, mx, flagged), ext)


# Ejemplo:
# asyncio.run(check_site("tiendaejemplo.com.ve", ExternalInputs(
#     price_deviation=-0.1,
#     verified_reports=0,
#     brands=[Brand("Samsung", ["samsung.com"])],
# )))
#
# Para enriquecer con redes: toma site.info.social_profiles, corre ig_trust_score /
# tiktok_trust_score sobre esas cuentas y pasa sus scores en `linked_social_scores`.
