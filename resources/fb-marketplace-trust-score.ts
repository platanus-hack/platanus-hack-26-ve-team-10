/**
 * FB Marketplace Trust Score — puntaje de seguridad de un vendedor/anuncio de Facebook Marketplace.
 *
 * Actor base: deepmine/facebook-marketplace-scraper (con "Add listing details" activo trae
 * sellerJoinTime, sellerRatingAverage y sellerRatingCount sin cookies).
 * Marketplace solo se muestra a visitantes sin sesión desde IPs residenciales → proxy residencial.
 *
 * ⚠️ Antes de producción:
 *   - Corre el actor en Apify Console con anuncios reales de Venezuela y ajusta normalizeListing().
 *   - Verifica si el actor acepta la URL del perfil de vendedor
 *     (facebook.com/marketplace/profile/<sellerId>) para traer sus otros anuncios.
 *   - Calificaciones e insignias son BONUS (+10 máx.), no señal base: en Venezuela casi
 *     nadie califica en Marketplace. Si el actor no las trae, no pasa nada.
 *
 * npm i apify-client
 */
import { ApifyClient } from "apify-client";

const apify = new ApifyClient({ token: process.env.APIFY_TOKEN });
const MARKETPLACE_ACTOR = "deepmine/facebook-marketplace-scraper";

// ───────────────────────── Tipos ─────────────────────────

type Listing = {
  id: string;
  url: string;
  title: string;
  description: string;
  price: number | null;
  photos: string[];
  city: string | null;
  createdAt: Date | null;
  seller: {
    id: string | null;
    name: string | null;
    joinedFacebook: Date | null;
    ratingAvg: number | null;
    ratingCount: number | null;
    badges: string[] | null;
  };
};

export type ExternalInputs = {
  /** Precio vs. mediana de mercado (Prais): -0.35 = 35% más barato. */
  priceDeviation?: number | null;
  /** Reportes de estafa verificados contra este vendedor. */
  verifiedReports?: number;
  /**
   * Cuántas fotos del anuncio aparecen (por hash perceptual) en anuncios de OTROS vendedores
   * dentro de la base de Prais. Fotos robadas = señal fuerte de estafa.
   */
  photosSeenElsewhere?: number | null;
};

type Signal = { key: string; weight: number; value: number | null; reason?: string; good?: boolean };

export type TrustResult = {
  listingId: string;
  sellerId: string | null;
  score: number | null;
  coverage: number;
  verdict: "confiable" | "precaucion" | "riesgosa" | "sin_datos";
  redFlags: string[];
  reasons: { text: string; good: boolean }[];
  signals: Signal[];
};

// ───────────────────────── Fetch ─────────────────────────

async function runActor(urls: string[], maxItems = 50): Promise<any[]> {
  const run = await apify.actor(MARKETPLACE_ACTOR).call({
    startUrls: urls.map((url) => ({ url })),
    includeListingDetails: true, // verifica el nombre exacto en el input schema ("Add listing details")
    maxItems,
    proxyConfiguration: { useApifyProxy: true, apifyProxyGroups: ["RESIDENTIAL"], apifyProxyCountry: "VE" },
  });
  const { items } = await apify.dataset(run.defaultDatasetId).listItems();
  return items as any[];
}

export async function fetchListing(itemUrl: string): Promise<Listing | null> {
  const items = await runActor([itemUrl], 1);
  return items[0] ? normalizeListing(items[0]) : null;
}

export async function fetchSellerListings(sellerId: string): Promise<Listing[]> {
  try {
    const items = await runActor([`https://www.facebook.com/marketplace/profile/${sellerId}`], 50);
    return items.map(normalizeListing);
  } catch {
    return []; // si el actor no soporta perfiles, la señal de historial queda en null
  }
}

function normalizeListing(r: any): Listing {
  const price = r.listingPrice?.amount ?? r.price ?? null;
  const photos = (r.listingPhotos ?? r.photos ?? []).map((p: any) => p?.image?.uri ?? p?.url ?? p).filter(Boolean);
  const badges = r.commerce_badges_info ?? r.sellerBadges ?? null;
  return {
    id: String(r.id ?? r.listingId),
    url: r.itemUrl ?? r.url,
    title: r.marketplaceListingTitle ?? r.title ?? "",
    description: r.redactedDescription?.text ?? r.description ?? "",
    price: price != null ? Number(price) : null,
    photos,
    city: r.locationText?.text ?? r.city ?? null,
    createdAt: r.creationTime ? new Date(r.creationTime * (r.creationTime < 1e12 ? 1000 : 1)) : null,
    seller: {
      id: r.sellerId ?? r.marketplaceListingSeller?.id ?? null,
      name: r.sellerName ?? r.marketplaceListingSeller?.name ?? null,
      joinedFacebook: toDate(r.sellerJoinTime),
      ratingAvg: r.sellerRatingAverage ?? null,
      ratingCount: r.sellerRatingCount ?? null,
      badges: Array.isArray(badges) ? badges.map((b: any) => b?.name ?? b?.badge_type ?? String(b)) : null,
    },
  };
}

function toDate(v: any): Date | null {
  if (v == null) return null;
  if (typeof v === "number") return new Date(v < 1e12 ? v * 1000 : v);
  const d = new Date(v);
  if (!isNaN(d.getTime())) return d;
  const y = String(v).match(/(19|20)\d{2}/); // "Se unió en 2016"
  return y ? new Date(`${y[0]}-01-01`) : null;
}

// ───────────────────────── Helpers ─────────────────────────

const clamp = (x: number, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, x));
const monthsSince = (d: Date) => (Date.now() - d.getTime()) / (1000 * 60 * 60 * 24 * 30.44);
const daysSince = (d: Date) => monthsSince(d) * 30.44;

// Mismos 3 patrones que Instagram (sin pagos ni DM: son normales en ventas legítimas en Venezuela).
const RISK_PATTERNS: [RegExp, string][] = [
  [/(sin|no hay|no se aceptan)\s+devoluci/i, "No acepta devoluciones"],
  [/(últimas?|ultimas?)\s+unidades|solo\s+(por\s+)?hoy|quedan\s+\d+/i, "Usa presión de urgencia"],
  [/(precio|oferta)\s+(de\s+)?(locura|regalado|remate)/i, "Precios 'demasiado buenos'"],
];

const STRONG_BADGES = /super|súper|highly rated|muy bien calificad/i;
const OTHER_BADGES = /responsive|receptiv|reliable|confiable|shipper|envío/i;

// ───────────────────────── Señales ─────────────────────────

function computeSignals(l: Listing, history: Listing[] | null, ext: ExternalInputs): Signal[] {
  const s: Signal[] = [];
  const { seller } = l;

  // Nota: calificaciones e insignias NO están aquí. En Venezuela casi nadie califica en
  // Marketplace, así que funcionan como BONUS (ver reputationBonus), no como señal base.

  // ── Identidad (20) ──

  // 3. Antigüedad en Facebook (15): < 6 meses → 0, 5 años → 1.
  if (seller.joinedFacebook) {
    const m = monthsSince(seller.joinedFacebook);
    const v = m < 6 ? 0 : clamp(Math.log(m / 6) / Math.log(10));
    s.push({ key: "fb_age", weight: 15, value: v, good: v >= 0.6,
      reason: v >= 0.6 ? `En Facebook desde ${seller.joinedFacebook.getFullYear()}` : `Perfil de Facebook reciente (${Math.round(m)} meses)` });
  } else s.push({ key: "fb_age", weight: 15, value: null });

  // 4. Coherencia de ubicación (5): mismo vendedor publicando en muchas ciudades = sospechoso.
  if (history && history.length >= 3) {
    const cities = new Set(history.map((h) => h.city).filter(Boolean));
    const v = clamp(1 - (cities.size - 2) / 3); // ≤2 ciudades → 1, ≥5 → 0
    s.push({ key: "location", weight: 5, value: v, good: v === 1,
      reason: v < 1 ? `Publica en ${cities.size} ciudades distintas` : undefined });
  } else s.push({ key: "location", weight: 5, value: null });

  // ── Comportamiento del vendedor (40) — reemplaza a la reputación como señal principal ──

  // 5. Historial de publicaciones (20).
  //    Patrón de cuenta hackeada: perfil viejo, sin calificaciones, que de repente
  //    publica muchos artículos en pocos días.
  if (history) {
    const recent = history.filter((h) => h.createdAt && daysSince(h.createdAt) <= 7).length;
    const total = history.length;
    const old = total - recent;
    const noRatings = !seller.ratingCount;
    let v = 0.5;
    if (old >= 5) v = 1;                 // historial sostenido
    else if (old >= 1) v = 0.75;
    const burst = recent >= 8 && old === 0; // ráfaga sin historial previo
    if (burst) v = 0;
    const looksHacked = burst && noRatings && !!seller.joinedFacebook && monthsSince(seller.joinedFacebook) > 24;
    s.push({ key: "history", weight: 20, value: v, good: v >= 0.75,
      reason: looksHacked ? `Perfil antiguo sin ventas previas que publicó ${recent} anuncios en 7 días (posible cuenta robada)`
        : burst ? `${recent} anuncios en 7 días sin historial previo`
        : old >= 5 ? "Historial de ventas sostenido" : undefined });
  } else s.push({ key: "history", weight: 20, value: null });

  // 6. Fotos originales (20): fotos que también aparecen en anuncios de otros vendedores.
  if (ext.photosSeenElsewhere != null) {
    const v = ext.photosSeenElsewhere === 0 ? 1 : 0;
    s.push({ key: "photos_original", weight: 20, value: v, good: v === 1,
      reason: v === 1 ? "Fotos propias" : "Fotos usadas también por otros vendedores" });
  } else s.push({ key: "photos_original", weight: 20, value: null });

  // ── Calidad del anuncio (10) ──

  // 7. Completitud (5): fotos suficientes y descripción con contenido.
  {
    const photosOk = clamp(l.photos.length / 4);                          // ≥4 fotos → 1
    const descOk = clamp(l.description.trim().split(/\s+/).length / 25);  // ≥25 palabras → 1
    const v = 0.5 * photosOk + 0.5 * descOk;
    s.push({ key: "completeness", weight: 5, value: v, good: v >= 0.7,
      reason: v < 0.4 ? "Anuncio con pocas fotos o sin descripción" : undefined });
  }

  // 8. Lenguaje de riesgo (5)
  {
    const hits = RISK_PATTERNS.filter(([re]) => re.test(`${l.title}\n${l.description}`)).map(([, t]) => t);
    s.push({ key: "risk_language", weight: 5, value: clamp(1 - hits.length / 3), good: !hits.length,
      reason: hits.length ? hits.join(" · ") : undefined });
  }

  // ── Contexto Prais (30) — los reportes de Prais son la capa de reputación que FB no da ──

  // 9. Precio vs. mercado (20)
  if (ext.priceDeviation != null) {
    const d = ext.priceDeviation;
    const v = d >= -0.15 ? 1 : clamp(1 - (-d - 0.15) / 0.3);
    s.push({ key: "price_anomaly", weight: 20, value: v, good: v === 1,
      reason: v < 1 ? `Precio ${Math.round(-d * 100)}% bajo el mercado` : "Precio en línea con el mercado" });
  } else s.push({ key: "price_anomaly", weight: 20, value: null });

  // 10. Reportes verificados (10)
  if (ext.verifiedReports != null) {
    const v = clamp(1 - ext.verifiedReports / 3);
    s.push({ key: "reports", weight: 10, value: v, good: v === 1,
      reason: ext.verifiedReports ? `${ext.verifiedReports} reporte(s) de estafa verificados` : undefined });
  } else s.push({ key: "reports", weight: 10, value: null });

  return s;
}

/**
 * Bonus de reputación: suma hasta +10 puntos sobre el score base, nunca resta.
 * Quien no tiene calificaciones (la mayoría en Venezuela) no pierde nada.
 * Una mala calificación se maneja como bandera roja (< 3★ con ≥ 5 calificaciones).
 */
function reputationBonus(l: Listing): { points: number; reason?: string } {
  const { seller } = l;
  let points = 0;
  const parts: string[] = [];

  // Calificaciones: hasta +7. Promedio bayesiano (prior 3.5★, peso 5) para que
  // un 5★ con 1 calificación no valga lo mismo que un 4.8★ con 40.
  if (seller.ratingAvg != null && (seller.ratingCount ?? 0) >= 5) {
    const n = seller.ratingCount!;
    const smoothed = (5 * 3.5 + n * seller.ratingAvg) / (5 + n);
    points += 7 * clamp((smoothed - 4.0) / 0.8); // ≤4.0 → 0, ≥4.8 → +7
    parts.push(`${seller.ratingAvg.toFixed(1)}★ con ${n} calificaciones`);
  }

  // Insignias: hasta +3.
  if (seller.badges?.length) {
    if (seller.badges.some((b) => STRONG_BADGES.test(b))) points += 3;
    else if (seller.badges.some((b) => OTHER_BADGES.test(b))) points += 1.5;
    parts.push(`Insignias: ${seller.badges.join(", ")}`);
  }

  return { points: Math.round(points), reason: parts.length ? parts.join(" · ") : undefined };
}

function redFlags(l: Listing, ext: ExternalInputs): string[] {
  const f: string[] = [];
  const { seller } = l;
  if (ext.priceDeviation != null && ext.priceDeviation <= -0.5) f.push("Precio más de 50% bajo el mercado");
  if ((ext.photosSeenElsewhere ?? 0) >= 2) f.push("Varias fotos copiadas de otros vendedores");
  if (seller.ratingAvg != null && (seller.ratingCount ?? 0) >= 5 && seller.ratingAvg < 3) f.push("Calificación menor a 3★");
  if (seller.joinedFacebook && monthsSince(seller.joinedFacebook) < 1) f.push("Perfil de Facebook creado hace menos de un mes");
  if ((ext.verifiedReports ?? 0) >= 3) f.push("Múltiples reportes de estafa verificados");
  return f;
}

// ───────────────────────── Score ─────────────────────────

const MIN_COVERAGE = 0.4;

export function scoreListing(l: Listing, history: Listing[] | null, ext: ExternalInputs = {}): TrustResult {
  const signals = computeSignals(l, history, ext);
  const flags = redFlags(l, ext);
  const total = signals.reduce((a, s) => a + s.weight, 0);
  const avail = signals.filter((s) => s.value != null);
  const wAvail = avail.reduce((a, s) => a + s.weight, 0);
  const coverage = wAvail / total;

  const reasons = signals
    .filter((s) => s.reason)
    .sort((a, b) => b.weight * (1 - (b.value ?? 1)) - a.weight * (1 - (a.value ?? 1)))
    .map((s) => ({ text: s.reason!, good: !!s.good }));

  const base = { listingId: l.id, sellerId: l.seller.id, coverage, reasons, signals };
  if (flags.length) return { ...base, score: 0, verdict: "riesgosa", redFlags: flags };
  if (coverage < MIN_COVERAGE) return { ...base, score: null, verdict: "sin_datos", redFlags: [] };

  const baseScore = (100 * avail.reduce((a, s) => a + s.weight * s.value!, 0)) / wAvail;
  const bonus = reputationBonus(l);
  if (bonus.reason) reasons.unshift({ text: bonus.reason, good: bonus.points > 0 });
  const score = Math.min(100, Math.round(baseScore + bonus.points));
  const verdict = score >= 75 ? "confiable" : score >= 50 ? "precaucion" : "riesgosa";
  return { ...base, score, verdict, redFlags: [] };
}

// ───────────────────────── Orquestación ─────────────────────────

export async function checkListing(itemUrl: string, ext: ExternalInputs = {}): Promise<TrustResult> {
  const listing = await fetchListing(itemUrl);
  if (!listing) {
    return { listingId: itemUrl, sellerId: null, score: null, coverage: 0, verdict: "sin_datos",
      redFlags: [], reasons: [{ text: "No se pudo leer el anuncio", good: false }], signals: [] };
  }
  const history = listing.seller.id ? await fetchSellerListings(listing.seller.id) : [];
  return scoreListing(listing, history.length ? history : null, ext);
}

// Ejemplo:
// checkListing("https://www.facebook.com/marketplace/item/1234567890/", {
//   priceDeviation: -0.32, verifiedReports: 0, photosSeenElsewhere: 0,
// }).then((r) => console.log(JSON.stringify(r, null, 2)));
