/**
 * Meta Ads Signals — capa transversal del Trust Score basada en la Biblioteca de Anuncios de Meta.
 *
 * No genera un score propio: produce AJUSTES (bonus, penalización, banderas rojas, razones)
 * que se aplican sobre el resultado de ig-trust-score, fb-marketplace-trust-score o
 * tiktok-trust-score con `applyMetaAdjustments()`.
 *
 * Fuente: scraping de la web de la Biblioteca vía Apify. La API oficial no sirve para
 * Venezuela: fuera de la UE solo devuelve anuncios políticos/sociales.
 *
 * ⚠️ Antes de producción:
 *   - Corre el actor con 2–3 páginas venezolanas que anuncien y ajusta normalizeAd() /
 *     normalizePageInfo() a los campos reales (los nombres varían entre actores y versiones).
 *   - La "Transparencia de la página" (fecha de creación, cambios de nombre, país de admins)
 *     no está confirmada en este actor. Si no viene, esas señales quedan en null y no afectan.
 *
 * npm i apify-client
 */
import { ApifyClient } from "apify-client";

const apify = new ApifyClient({ token: process.env.APIFY_TOKEN });
const ADS_ACTOR = "curious_coder/facebook-ads-library-scraper";

// ───────────────────────── Tipos ─────────────────────────

export type Ad = {
  id: string;
  pageId: string | null;
  pageName: string | null;
  start: Date | null;
  end: Date | null;          // null si sigue activo
  isActive: boolean;
  variants: number;          // collation count: copias casi idénticas del mismo anuncio
  text: string;
  linkUrl: string | null;
};

export type PageTransparency = {
  createdAt: Date | null;
  nameChanges: number | null;
  adminCountries: string[] | null;
};

/** Lo que Prais aporta: desviación de precio para un texto de anuncio. */
export type PriceLookup = (adText: string) => Promise<number | null> | number | null;

export type MetaAdsOptions = {
  /** Código de país esperado de los administradores, p. ej. "VE". */
  expectedCountry?: string;
  /** Marcas y sus dominios oficiales, para detectar dominios que las imitan. */
  brands?: { name: string; officialDomains: string[] }[];
  priceLookup?: PriceLookup;
};

export type MetaAdjustments = {
  advertises: boolean;
  bonus: number;             // 0..+5
  penalty: number;           // 0..15 (se resta)
  redFlags: string[];
  reasons: { text: string; good: boolean }[];
  /** Datos de identidad para alimentar las señales base de IG/FB cuando falten. */
  identityHints: PageTransparency;
  stats: {
    totalAds: number;
    activeAds: number;
    medianDurationDays: number | null;
    shortLivedLast30d: number;
  };
};

// ───────────────────────── Fetch ─────────────────────────

const libraryUrlForPage = (pageId: string) =>
  `https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=ALL&view_all_page_id=${pageId}`;

const libraryUrlForKeyword = (q: string, country: string) =>
  `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=${country}` +
  `&q=${encodeURIComponent(q)}&search_type=keyword_unordered`;

async function runActor(urls: string[], limit = 100): Promise<any[]> {
  const run = await apify.actor(ADS_ACTOR).call({
    // Verifica estos nombres en el Input tab del actor.
    urls: urls.map((url) => ({ url })),
    count: limit,
    scrapeAdDetails: false,
  });
  const { items } = await apify.dataset(run.defaultDatasetId).listItems();
  return items as any[];
}

export async function fetchPageAds(pageId: string, limit = 100): Promise<{ ads: Ad[]; page: PageTransparency }> {
  const items = await runActor([libraryUrlForPage(pageId)], limit);
  return { ads: items.map(normalizeAd), page: normalizePageInfo(items[0]) };
}

function toDate(v: any): Date | null {
  if (v == null || v === "") return null;
  if (typeof v === "number") return new Date(v < 1e12 ? v * 1000 : v);
  const d = new Date(v);
  return isNaN(d.getTime()) ? null : d;
}

function normalizeAd(r: any): Ad {
  const snap = r.snapshot ?? {};
  const text =
    snap.body?.text ??
    snap.body?.markup?.__html?.replace(/<[^>]+>/g, " ") ??
    (snap.cards ?? []).map((c: any) => `${c.title ?? ""} ${c.body ?? ""}`).join(" ") ??
    "";
  return {
    id: String(r.ad_archive_id ?? r.adArchiveID ?? r.id),
    pageId: r.page_id ?? r.pageId ?? snap.page_id ?? null,
    pageName: r.page_name ?? r.pageName ?? snap.page_name ?? null,
    start: toDate(r.start_date ?? r.startDate),
    end: toDate(r.end_date ?? r.endDate),
    isActive: !!(r.is_active ?? r.isActive),
    variants: Number(r.collation_count ?? r.collationCount ?? 1) || 1,
    text: String(text).trim(),
    linkUrl: snap.link_url ?? snap.cards?.[0]?.link_url ?? null,
  };
}

function normalizePageInfo(r: any): PageTransparency {
  const p = r?.page_info ?? r?.pageInfo ?? r?.snapshot?.page_info ?? {};
  const countries = p.admin_countries ?? p.page_admin_countries ?? null;
  return {
    createdAt: toDate(p.creation_date ?? p.page_creation_date),
    nameChanges: p.name_changes != null ? Number(p.name_changes)
      : Array.isArray(p.previous_names) ? p.previous_names.length : null,
    adminCountries: Array.isArray(countries) ? countries.map(String) : null,
  };
}

// ───────────────────────── Helpers ─────────────────────────

const DAY = 1000 * 60 * 60 * 24;
const clamp = (x: number, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, x));
const median = (xs: number[]) => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const durationDays = (a: Ad) => a.start ? ((a.end ?? new Date()).getTime() - a.start.getTime()) / DAY : null;

function hostOf(url: string | null): string | null {
  if (!url) return null;
  try {
    // Meta envuelve los links en l.facebook.com/l.php?u=...
    const u = new URL(url);
    const inner = u.searchParams.get("u");
    return new URL(inner ?? url).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return null;
  }
}

/**
 * Dominio que imita a una marca: contiene el nombre de la marca pero no es un dominio
 * oficial ni subdominio de uno (p. ej. samsung-ve-ofertas.shop).
 */
function impersonatedBrand(host: string, brands: MetaAdsOptions["brands"] = []): string | null {
  const flat = host.replace(/[^a-z0-9]/g, "");
  for (const b of brands) {
    const key = b.name.toLowerCase().replace(/[^a-z0-9]/g, "");
    if (!key || !flat.includes(key)) continue;
    const official = b.officialDomains.some((d) => host === d || host.endsWith(`.${d}`));
    if (!official) return b.name;
  }
  return null;
}

// ───────────────────────── Señales ─────────────────────────

const SHORT_LIVED_DAYS = 3;
const SHORT_LIVED_THRESHOLD = 10;   // ≥ 10 anuncios cortos en 30 días → rotación
const LONG_RUNNING_DAYS = 30;

export async function computeMetaAdjustments(
  ads: Ad[],
  page: PageTransparency,
  opts: MetaAdsOptions = {},
): Promise<MetaAdjustments> {
  const reasons: MetaAdjustments["reasons"] = [];
  const redFlags: string[] = [];
  let bonus = 0;
  let penalty = 0;

  const now = Date.now();
  const durations = ads.map(durationDays).filter((d): d is number => d != null);
  const medDur = median(durations);
  const active = ads.filter((a) => a.isActive);
  const shortLived = ads.filter((a) => {
    const d = durationDays(a);
    return !a.isActive && d != null && d <= SHORT_LIVED_DAYS && a.start && now - a.start.getTime() <= 30 * DAY;
  });
  // Cada anuncio corto con muchas variantes cuenta como varios intentos.
  const shortLivedWeighted = shortLived.reduce((n, a) => n + Math.min(a.variants, 5), 0);

  // ── Sin anuncios: no afecta. La mayoría de los vendedores pequeños no anuncia. ──
  if (!ads.length) {
    return { advertises: false, bonus: 0, penalty: 0, redFlags: [], reasons: [], identityHints: page,
      stats: { totalAds: 0, activeAds: 0, medianDurationDays: null, shortLivedLast30d: 0 } };
  }

  // 1. Bonus por anuncios de larga duración (hasta +5).
  if (medDur != null && medDur >= LONG_RUNNING_DAYS && shortLivedWeighted < SHORT_LIVED_THRESHOLD) {
    bonus = Math.round(5 * clamp(medDur / 90)); // 30 días → ~2, 90+ días → 5
    reasons.push({ text: `Anuncia de forma sostenida (anuncios de ~${Math.round(medDur)} días)`, good: true });
  }

  // 2. Rotación rápida (−15): patrón de evasión de moderación.
  if (shortLivedWeighted >= SHORT_LIVED_THRESHOLD) {
    penalty += 15;
    reasons.push({ text: `${shortLived.length} anuncios que duraron ${SHORT_LIVED_DAYS} días o menos en el último mes`, good: false });
  }

  // 3. Transparencia: cambios de nombre + administradores fuera del país.
  const foreignAdmins = page.adminCountries && opts.expectedCountry
    ? page.adminCountries.filter((c) => c.toUpperCase() !== opts.expectedCountry!.toUpperCase())
    : null;
  if ((page.nameChanges ?? 0) >= 2 && foreignAdmins?.length) {
    redFlags.push(`Página renombrada ${page.nameChanges} veces y administrada desde ${foreignAdmins.join(", ")}`);
  } else {
    if ((page.nameChanges ?? 0) >= 2) reasons.push({ text: `La página cambió de nombre ${page.nameChanges} veces`, good: false });
    if (foreignAdmins?.length) reasons.push({ text: `Administrada desde ${foreignAdmins.join(", ")}`, good: false });
  }

  // 4. Dominios de destino que imitan una marca.
  const hosts = [...new Set(ads.map((a) => hostOf(a.linkUrl)).filter((h): h is string => !!h))];
  for (const h of hosts) {
    const brand = impersonatedBrand(h, opts.brands);
    if (brand) redFlags.push(`Anuncios que llevan a ${h}, que imita a ${brand}`);
  }

  // 5. Precio del anuncio fuera de mercado (usa la mediana de Prais).
  if (opts.priceLookup) {
    const recent = (active.length ? active : ads).slice(0, 15);
    let worst: number | null = null;
    for (const a of recent) {
      if (!a.text) continue;
      const dev = await opts.priceLookup(a.text);
      if (dev != null && (worst == null || dev < worst)) worst = dev;
    }
    if (worst != null && worst <= -0.5) {
      redFlags.push(`Anuncia precios ${Math.round(-worst * 100)}% bajo el mercado`);
    } else if (worst != null && worst <= -0.3) {
      penalty += 5;
      reasons.push({ text: `Algún anuncio con precio ${Math.round(-worst * 100)}% bajo el mercado`, good: false });
    }
  }

  return {
    advertises: true,
    bonus,
    penalty: Math.min(penalty, 15),
    redFlags,
    reasons,
    identityHints: page,
    stats: {
      totalAds: ads.length,
      activeAds: active.length,
      medianDurationDays: medDur != null ? Math.round(medDur) : null,
      shortLivedLast30d: shortLived.length,
    },
  };
}

// ───────────────────────── Aplicación sobre cualquier TrustResult ─────────────────────────

type AnyTrustResult = {
  score: number | null;
  verdict: "confiable" | "precaucion" | "riesgosa" | "sin_datos";
  redFlags: string[];
  reasons: { text: string; good: boolean }[];
};

/** Aplica los ajustes de Meta Ads sobre el resultado de IG, Marketplace o TikTok. */
export function applyMetaAdjustments<T extends AnyTrustResult>(result: T, adj: MetaAdjustments): T {
  const reasons = [...adj.reasons, ...result.reasons];
  const redFlags = [...result.redFlags, ...adj.redFlags];

  if (redFlags.length) return { ...result, score: 0, verdict: "riesgosa", redFlags, reasons };
  if (result.score == null) return { ...result, reasons }; // sin datos base: no inventamos un número

  const score = Math.max(0, Math.min(100, result.score + adj.bonus - adj.penalty));
  const verdict = score >= 75 ? "confiable" : score >= 50 ? "precaucion" : "riesgosa";
  return { ...result, score, verdict, redFlags, reasons };
}

/** Atajo: trae los anuncios de una página y devuelve los ajustes. */
export async function checkPageAds(pageId: string, opts: MetaAdsOptions = {}): Promise<MetaAdjustments> {
  const { ads, page } = await fetchPageAds(pageId);
  return computeMetaAdjustments(ads, page, opts);
}

// ───────────────────────── Radar de estafas ─────────────────────────

export type RadarHit = { pageId: string | null; pageName: string | null; adId: string; deviation: number; text: string };

/**
 * Busca anuncios activos por palabra clave en un país y devuelve los que anuncian precios
 * muy por debajo del mercado. Pensado para correr a diario (scheduled task / n8n) y
 * alimentar la lista de reportes de Prais antes de que un usuario pregunte.
 */
export async function scamRadar(
  keywords: string[],
  priceLookup: PriceLookup,
  country = "VE",
  threshold = -0.5,
): Promise<RadarHit[]> {
  const items = await runActor(keywords.map((k) => libraryUrlForKeyword(k, country)), 200);
  const hits: RadarHit[] = [];
  for (const ad of items.map(normalizeAd)) {
    if (!ad.text) continue;
    const dev = await priceLookup(ad.text);
    if (dev != null && dev <= threshold) {
      hits.push({ pageId: ad.pageId, pageName: ad.pageName, adId: ad.id, deviation: dev, text: ad.text.slice(0, 280) });
    }
  }
  return hits.sort((a, b) => a.deviation - b.deviation);
}

// ───────────────────────── Ejemplo ─────────────────────────
//
// import { checkAccount } from "./ig-trust-score";
//
// const base = await checkAccount("tienda_ejemplo", { priceDeviation: -0.1, expectedCountry: "Venezuela" });
// const adj = await checkPageAds("123456789012345", {
//   expectedCountry: "VE",
//   brands: [
//     { name: "Samsung", officialDomains: ["samsung.com"] },
//     { name: "Apple", officialDomains: ["apple.com"] },
//   ],
//   priceLookup: (text) => prais.priceDeviationFromText(text), // tu función de Prais
// });
// const final = applyMetaAdjustments(base, adj);
//
// Radar diario:
// const hits = await scamRadar(["iphone", "playstation 5", "starlink"], prais.priceDeviationFromText);
