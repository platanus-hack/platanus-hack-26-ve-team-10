/**
 * Website Trust Score — puntaje de seguridad de una tienda o sitio web usando Firecrawl.
 *
 * Fuentes:
 *   - Firecrawl (scrape): contenido, links y extracción estructurada (JSON schema) del sitio.
 *   - RDAP (rdap.org): fecha de registro del dominio. Gratis, sin API key.
 *   - DNS (node:dns): registros MX del dominio.
 *   - Google Safe Browsing (opcional): si el sitio está marcado como phishing/malware.
 *
 * ⚠️ Antes de producción:
 *   - El paquete `firecrawl` requiere Node.js >= 22.
 *   - Verifica en los tipos del SDK los nombres de `doc.links`, `doc.json` y `doc.metadata`;
 *     aquí se leen de forma defensiva.
 *   - RDAP no siempre cubre dominios .ve; si no responde, la antigüedad queda en null.
 *
 * npm i firecrawl
 * env: FIRECRAWL_API_KEY, GOOGLE_SAFE_BROWSING_KEY (opcional)
 */
import { Firecrawl } from "firecrawl";
import { promises as dns } from "node:dns";

const firecrawl = new Firecrawl({ apiKey: process.env.FIRECRAWL_API_KEY });

// ───────────────────────── Tipos ─────────────────────────

type SiteInfo = {
  storeName?: string;
  claimsToBeOfficialStoreOf?: string; // "Tienda oficial de Samsung", etc.
  legalName?: string;
  rif?: string;                       // RIF venezolano (J-12345678-9)
  address?: string;
  phones?: string[];
  emails?: string[];
  socialProfiles?: string[];
  paymentMethods?: string[];
  productCount?: number;
};

type Site = {
  url: string;
  host: string;
  domain: string;          // dominio registrable (tienda.com.ve)
  https: boolean;
  markdown: string;
  links: string[];
  info: SiteInfo;
  policyPages: { kind: PolicyKind; url: string; words: number }[];
};

type PolicyKind = "contacto" | "nosotros" | "terminos" | "devoluciones" | "garantia" | "privacidad";

export type ExternalInputs = {
  /** Precio vs. mediana de mercado (Prais): -0.35 = 35% más barato. */
  priceDeviation?: number | null;
  /** Reportes de estafa verificados contra este dominio. */
  verifiedReports?: number;
  /** Marcas y sus dominios oficiales, para detectar suplantación. */
  brands?: { name: string; officialDomains: string[] }[];
  /**
   * Scores de las redes que el sitio enlaza, si ya los corriste con los otros módulos
   * (ig-trust-score, tiktok-trust-score...). 0..100.
   */
  linkedSocialScores?: number[];
};

type Signal = { key: string; weight: number; value: number | null; reason?: string; good?: boolean };

export type TrustResult = {
  url: string;
  domain: string;
  score: number | null;
  coverage: number;
  verdict: "confiable" | "precaucion" | "riesgosa" | "sin_datos";
  redFlags: string[];
  reasons: { text: string; good: boolean }[];
  signals: Signal[];
};

// ───────────────────────── Fetch ─────────────────────────

const INFO_SCHEMA = {
  type: "object",
  properties: {
    storeName: { type: "string" },
    claimsToBeOfficialStoreOf: { type: "string", description: "Marca de la que dice ser tienda o distribuidor oficial, si lo dice" },
    legalName: { type: "string", description: "Razón social" },
    rif: { type: "string", description: "RIF venezolano, formato J-12345678-9" },
    address: { type: "string", description: "Dirección física" },
    phones: { type: "array", items: { type: "string" } },
    emails: { type: "array", items: { type: "string" } },
    socialProfiles: { type: "array", items: { type: "string" }, description: "URLs de Instagram, Facebook, TikTok, etc." },
    paymentMethods: { type: "array", items: { type: "string" } },
    productCount: { type: "number", description: "Número aproximado de productos visibles" },
  },
};

const POLICY_PATTERNS: [PolicyKind, RegExp][] = [
  ["contacto", /contact/i],
  ["nosotros", /nosotros|quienes-somos|about/i],
  ["terminos", /t[eé]rminos|terms|condiciones/i],
  ["devoluciones", /devoluci|cambios|returns|reembolso|refund/i],
  ["garantia", /garant[ií]a|warranty/i],
  ["privacidad", /privacidad|privacy/i],
];

export async function fetchSite(inputUrl: string): Promise<Site | null> {
  const url = /^https?:\/\//i.test(inputUrl) ? inputUrl : `https://${inputUrl}`;
  let doc: any;
  try {
    doc = await firecrawl.scrape(url, {
      formats: ["markdown", "links", { type: "json", schema: INFO_SCHEMA }],
      onlyMainContent: false, // el footer suele tener RIF, dirección y redes
      location: { country: "VE", languages: ["es-VE"] },
    });
  } catch {
    return null;
  }

  const finalUrl: string = doc.metadata?.url ?? doc.metadata?.sourceURL ?? url;
  const host = new URL(finalUrl).hostname.replace(/^www\./, "").toLowerCase();
  const links: string[] = (doc.links ?? []).filter((l: any) => typeof l === "string");
  const markdown: string = doc.markdown ?? "";
  const info: SiteInfo = { ...regexInfo(markdown), ...(doc.json ?? {}) };

  // Una página por tipo de política, del mismo dominio, máximo 4 scrapes extra.
  const sameSite = links.filter((l) => safeHost(l)?.endsWith(registrableDomain(host)));
  const picked: { kind: PolicyKind; url: string }[] = [];
  for (const [kind, re] of POLICY_PATTERNS) {
    const hit = sameSite.find((l) => re.test(new URL(l).pathname));
    if (hit && !picked.some((p) => p.url === hit)) picked.push({ kind, url: hit });
  }
  const policyPages = await Promise.all(
    picked.slice(0, 4).map(async (p) => {
      try {
        const d: any = await firecrawl.scrape(p.url, { formats: ["markdown"], onlyMainContent: true });
        const md: string = d.markdown ?? "";
        mergeInfo(info, regexInfo(md)); // contacto/nosotros suelen tener RIF y teléfono
        return { ...p, words: md.split(/\s+/).filter(Boolean).length };
      } catch {
        return { ...p, words: 0 };
      }
    }),
  );

  return {
    url: finalUrl,
    host,
    domain: registrableDomain(host),
    https: finalUrl.startsWith("https://"),
    markdown,
    links,
    info,
    policyPages,
  };
}

/** Respaldo por regex para lo que la extracción por LLM a veces omite. */
function regexInfo(md: string): SiteInfo {
  const rif = md.match(/\b[JVGEP][-\s]?\d{7,9}[-\s]?\d\b/i)?.[0];
  const phones = [...new Set(md.match(/(?:\+?58[\s-]?)?\(?0?(?:2\d{2}|4(?:12|14|16|24|26))\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}/g) ?? [])];
  const emails = [...new Set(md.match(/[\w.+-]+@[\w-]+\.[\w.]+/g) ?? [])];
  const socialProfiles = [...new Set(md.match(/https?:\/\/(?:www\.)?(?:instagram|facebook|tiktok)\.com\/[^\s)"']+/gi) ?? [])];
  return { rif, phones, emails, socialProfiles };
}

function mergeInfo(into: SiteInfo, from: SiteInfo) {
  into.rif ??= from.rif;
  for (const k of ["phones", "emails", "socialProfiles"] as const) {
    into[k] = [...new Set([...(into[k] ?? []), ...(from[k] ?? [])])];
  }
}

function safeHost(u: string): string | null {
  try {
    return new URL(u).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return null;
  }
}

const TWO_LEVEL_SUFFIXES = /\.(com|net|org|co|gob|gov|edu|info|web)\.[a-z]{2}$/;
function registrableDomain(host: string): string {
  const parts = host.split(".");
  return parts.slice(TWO_LEVEL_SUFFIXES.test(host) ? -3 : -2).join(".");
}

// ── Fuentes externas al sitio ──

async function domainRegisteredAt(domain: string): Promise<Date | null> {
  try {
    const res = await fetch(`https://rdap.org/domain/${domain}`, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) return null;
    const data: any = await res.json();
    const ev = (data.events ?? []).find((e: any) => e.eventAction === "registration");
    return ev?.eventDate ? new Date(ev.eventDate) : null;
  } catch {
    return null;
  }
}

async function hasMx(domain: string): Promise<boolean | null> {
  try {
    return (await dns.resolveMx(domain)).length > 0;
  } catch (e: any) {
    return e?.code === "ENODATA" || e?.code === "ENOTFOUND" ? false : null;
  }
}

/** true = marcado como peligroso; false = limpio; null = no se pudo consultar. */
async function safeBrowsingFlagged(url: string): Promise<boolean | null> {
  const key = process.env.GOOGLE_SAFE_BROWSING_KEY;
  if (!key) return null;
  try {
    const res = await fetch(`https://safebrowsing.googleapis.com/v4/threatMatches:find?key=${key}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client: { clientId: "prais", clientVersion: "1.0" },
        threatInfo: {
          threatTypes: ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
          platformTypes: ["ANY_PLATFORM"],
          threatEntryTypes: ["URL"],
          threatEntries: [{ url }],
        },
      }),
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return null;
    const data: any = await res.json();
    return Array.isArray(data.matches) && data.matches.length > 0;
  } catch {
    return null;
  }
}

// ───────────────────────── Helpers ─────────────────────────

const clamp = (x: number, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, x));
const monthsSince = (d: Date) => (Date.now() - d.getTime()) / (1000 * 60 * 60 * 24 * 30.44);

// Mismos 3 patrones que en redes, más contadores de "oferta termina en".
// Pago Móvil, Zelle, Binance o WhatsApp NO se penalizan: son normales en Venezuela.
const RISK_PATTERNS: [RegExp, string][] = [
  [/(sin|no hay|no se aceptan)\s+devoluci/i, "No acepta devoluciones"],
  [/(últimas?|ultimas?)\s+unidades|solo\s+(por\s+)?hoy|quedan\s+\d+|(oferta|promo)\w*\s+(termina|acaba|finaliza)\s+en/i, "Usa presión de urgencia"],
  [/(precio|oferta)\s+(de\s+)?(locura|regalado|remate)/i, "Precios 'demasiado buenos'"],
];

const FREE_MAIL = /@(gmail|hotmail|outlook|yahoo|icloud|live)\./i;

function impersonatedBrand(domain: string, brands: ExternalInputs["brands"] = []): string | null {
  const flat = domain.replace(/[^a-z0-9]/g, "");
  for (const b of brands) {
    const key = b.name.toLowerCase().replace(/[^a-z0-9]/g, "");
    if (!key || !flat.includes(key)) continue;
    if (!b.officialDomains.some((d) => domain === d || domain.endsWith(`.${d}`))) return b.name;
  }
  return null;
}

// ───────────────────────── Señales ─────────────────────────

type Externals = { registeredAt: Date | null; mx: boolean | null; flagged: boolean | null };

function computeSignals(site: Site, x: Externals, ext: ExternalInputs): Signal[] {
  const s: Signal[] = [];
  const { info } = site;

  // ── Identidad (25) ──

  // 1. Antigüedad del dominio (15): < 3 meses → 0, 3 años → 1.
  if (x.registeredAt) {
    const m = monthsSince(x.registeredAt);
    const v = m < 3 ? 0 : clamp(Math.log(m / 3) / Math.log(12));
    s.push({ key: "domain_age", weight: 15, value: v, good: v >= 0.6,
      reason: v >= 0.6 ? `Dominio registrado en ${x.registeredAt.getFullYear()}` : `Dominio reciente (${Math.round(m)} meses)` });
  } else s.push({ key: "domain_age", weight: 15, value: null });

  // 2. Datos de contacto verificables (10): RIF, dirección, teléfono, correo del propio dominio.
  {
    const ownEmail = (info.emails ?? []).some((e) => e.toLowerCase().endsWith(`@${site.domain}`));
    const anyEmail = (info.emails ?? []).length > 0;
    const parts = [
      info.rif ? 0.35 : 0,
      info.address ? 0.25 : 0,
      (info.phones ?? []).length ? 0.2 : 0,
      ownEmail ? 0.2 : anyEmail && !(info.emails ?? []).every((e) => FREE_MAIL.test(e)) ? 0.2 : anyEmail ? 0.1 : 0,
    ];
    const v = parts.reduce((a, b) => a + b, 0);
    const found = [info.rif && "RIF", info.address && "dirección", (info.phones ?? []).length && "teléfono"].filter(Boolean);
    s.push({ key: "contact", weight: 10, value: v, good: v >= 0.6,
      reason: v >= 0.6 ? `Publica ${found.join(", ")}` : v < 0.3 ? "No publica RIF, dirección ni teléfono" : undefined });
  }

  // ── Sustancia de la tienda (25) ──

  // 3. Políticas (10): términos, devoluciones, garantía y privacidad con contenido real.
  {
    const kinds: PolicyKind[] = ["terminos", "devoluciones", "garantia", "privacidad"];
    const ok = kinds.filter((k) => site.policyPages.some((p) => p.kind === k && p.words >= 120)).length;
    const v = ok / kinds.length;
    s.push({ key: "policies", weight: 10, value: v, good: v >= 0.5,
      reason: v >= 0.5 ? "Tiene políticas de devolución, garantía o términos" : "Sin políticas de devolución ni garantía" });
  }

  // 4. Profundidad del catálogo (5): una "tienda" de 3 productos es sospechosa.
  if (info.productCount != null) {
    const v = clamp((info.productCount - 3) / 27); // ≤ 3 → 0, ≥ 30 → 1
    s.push({ key: "catalog", weight: 5, value: v, good: v >= 0.6,
      reason: v < 0.3 ? "Catálogo muy pequeño" : undefined });
  } else s.push({ key: "catalog", weight: 5, value: null });

  // 5. Redes sociales enlazadas (10): si ya las puntuaste con los otros módulos, usa ese score.
  if (ext.linkedSocialScores?.length) {
    const best = Math.max(...ext.linkedSocialScores);
    const v = best / 100;
    s.push({ key: "linked_socials", weight: 10, value: v, good: v >= 0.75,
      reason: `Sus redes enlazadas tienen score ${best}/100` });
  } else {
    const n = (info.socialProfiles ?? []).length;
    s.push({ key: "linked_socials", weight: 10, value: n ? 0.5 : 0.2, // sin verificar: crédito parcial
      reason: n ? undefined : "No enlaza ninguna red social" });
  }

  // ── Técnico (15) ──

  // 6. HTTPS (5)
  s.push({ key: "https", weight: 5, value: site.https ? 1 : 0, good: site.https,
    reason: site.https ? undefined : "El sitio no usa HTTPS" });

  // 7. Correo del dominio configurado (5): MX en el dominio.
  if (x.mx != null) {
    s.push({ key: "mx", weight: 5, value: x.mx ? 1 : 0, good: x.mx,
      reason: x.mx ? undefined : "El dominio no tiene correo configurado" });
  } else s.push({ key: "mx", weight: 5, value: null });

  // 8. Google Safe Browsing limpio (5). Marcado = bandera roja (ver redFlags).
  if (x.flagged != null) {
    s.push({ key: "safe_browsing", weight: 5, value: x.flagged ? 0 : 1, good: !x.flagged });
  } else s.push({ key: "safe_browsing", weight: 5, value: null });

  // ── Comportamiento (5) ──

  // 9. Lenguaje de riesgo (5)
  {
    const hits = RISK_PATTERNS.filter(([re]) => re.test(site.markdown)).map(([, t]) => t);
    s.push({ key: "risk_language", weight: 5, value: clamp(1 - hits.length / 3), good: !hits.length,
      reason: hits.length ? hits.join(" · ") : undefined });
  }

  // ── Contexto Prais (30) ──

  // 10. Precio vs. mercado (20)
  if (ext.priceDeviation != null) {
    const d = ext.priceDeviation;
    const v = d >= -0.15 ? 1 : clamp(1 - (-d - 0.15) / 0.3);
    s.push({ key: "price_anomaly", weight: 20, value: v, good: v === 1,
      reason: v < 1 ? `Precio ${Math.round(-d * 100)}% bajo el mercado` : "Precio en línea con el mercado" });
  } else s.push({ key: "price_anomaly", weight: 20, value: null });

  // 11. Reportes verificados (10)
  if (ext.verifiedReports != null) {
    const v = clamp(1 - ext.verifiedReports / 3);
    s.push({ key: "reports", weight: 10, value: v, good: v === 1,
      reason: ext.verifiedReports ? `${ext.verifiedReports} reporte(s) de estafa verificados` : undefined });
  } else s.push({ key: "reports", weight: 10, value: null });

  return s;
}

function redFlags(site: Site, x: Externals, ext: ExternalInputs): string[] {
  const f: string[] = [];
  if (x.flagged) f.push("Google lo marca como sitio peligroso");
  if (x.registeredAt && monthsSince(x.registeredAt) < 1) f.push("Dominio registrado hace menos de un mes");
  const imitated = impersonatedBrand(site.domain, ext.brands);
  if (imitated) f.push(`El dominio imita a ${imitated}`);
  const claimed = site.info.claimsToBeOfficialStoreOf;
  const brand = claimed && ext.brands?.find((b) => b.name.toLowerCase() === claimed.toLowerCase());
  if (brand && !brand.officialDomains.some((d) => site.domain === d || site.domain.endsWith(`.${d}`))) {
    f.push(`Dice ser tienda oficial de ${brand.name} sin estar en su dominio`);
  }
  if (ext.priceDeviation != null && ext.priceDeviation <= -0.5) f.push("Precio más de 50% bajo el mercado");
  if ((ext.verifiedReports ?? 0) >= 3) f.push("Múltiples reportes de estafa verificados");
  return f;
}

// ───────────────────────── Score ─────────────────────────

const MIN_COVERAGE = 0.4;

export function scoreSite(site: Site, x: Externals, ext: ExternalInputs = {}): TrustResult {
  const signals = computeSignals(site, x, ext);
  const flags = redFlags(site, x, ext);
  const total = signals.reduce((a, s) => a + s.weight, 0);
  const avail = signals.filter((s) => s.value != null);
  const wAvail = avail.reduce((a, s) => a + s.weight, 0);
  const coverage = wAvail / total;

  const reasons = signals
    .filter((s) => s.reason)
    .sort((a, b) => b.weight * (1 - (b.value ?? 1)) - a.weight * (1 - (a.value ?? 1)))
    .map((s) => ({ text: s.reason!, good: !!s.good }));

  const base = { url: site.url, domain: site.domain, coverage, reasons, signals };
  if (flags.length) return { ...base, score: 0, verdict: "riesgosa", redFlags: flags };
  if (coverage < MIN_COVERAGE) return { ...base, score: null, verdict: "sin_datos", redFlags: [] };

  const score = Math.round((100 * avail.reduce((a, s) => a + s.weight * s.value!, 0)) / wAvail);
  const verdict = score >= 75 ? "confiable" : score >= 50 ? "precaucion" : "riesgosa";
  return { ...base, score, verdict, redFlags: [] };
}

// ───────────────────────── Orquestación ─────────────────────────

export async function checkSite(url: string, ext: ExternalInputs = {}): Promise<TrustResult> {
  const site = await fetchSite(url);
  if (!site) {
    return { url, domain: safeHost(url) ?? url, score: null, coverage: 0, verdict: "sin_datos",
      redFlags: [], reasons: [{ text: "No se pudo leer el sitio", good: false }], signals: [] };
  }
  const [registeredAt, mx, flagged] = await Promise.all([
    domainRegisteredAt(site.domain),
    hasMx(site.domain),
    safeBrowsingFlagged(site.url),
  ]);
  return scoreSite(site, { registeredAt, mx, flagged }, ext);
}

// Ejemplo:
// checkSite("tiendaejemplo.com.ve", {
//   priceDeviation: -0.1,
//   verifiedReports: 0,
//   brands: [{ name: "Samsung", officialDomains: ["samsung.com"] }],
// }).then((r) => console.log(JSON.stringify(r, null, 2)));
//
// Para enriquecer con redes: toma site.info.socialProfiles, corre ig-trust-score /
// tiktok-trust-score sobre esas cuentas y pasa sus scores en `linkedSocialScores`.
