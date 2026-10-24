/**
 * Amazon Trust Score — puntaje de seguridad de un VENDEDOR de Amazon para una oferta concreta.
 *
 * En Amazon el riesgo no es la plataforma sino el vendedor externo (third-party seller):
 * falsificaciones, productos usados vendidos como nuevos, envíos que no llegan al casillero
 * y cuentas de vendedor robadas que reaparecen con precios bajísimos.
 *
 * Actores:
 *   - junglee/Amazon-crawler            (página del producto: ASIN, precio, vendedor, fulfillment)
 *   - reefapi/amazon-seller-scraper     (perfil del vendedor y sus reseñas de feedback)
 *
 * ⚠️ Antes de producción:
 *   - Corre ambos actores con 3–4 productos reales (uno vendido por Amazon, uno FBA y uno
 *     enviado por el vendedor) y ajusta normalizeOffer() / normalizeSeller().
 *   - La API oficial (PA-API 5) está deprecada; su sucesora, Creators API, es para afiliados
 *     y no está claro que exponga el feedback del vendedor. Por eso se usa Apify.
 *
 * npm i apify-client
 */
import { ApifyClient } from "apify-client";

const apify = new ApifyClient({ token: process.env.APIFY_TOKEN });
const PRODUCT_ACTOR = "junglee/Amazon-crawler";
const SELLER_ACTOR = "reefapi/amazon-seller-scraper";

// ───────────────────────── Tipos ─────────────────────────

type Fulfillment = "amazon" | "fba" | "merchant" | null;

type Offer = {
  asin: string;
  title: string;
  price: number | null;
  sellerId: string | null;
  sellerName: string | null;
  fulfillment: Fulfillment;   // vendido por Amazon / gestionado por Amazon (FBA) / enviado por el vendedor
  productRating: number | null;
  productReviews: number | null;
};

type Seller = {
  id: string;
  name: string | null;
  positivePct: number | null; // 0..1
  ratingsLifetime: number | null;
  ratings12m: number | null;
  ratings90d: number | null;
};

type FeedbackReview = { rating: number | null; text: string; date: Date | null };

export type ExternalInputs = {
  /**
   * Precio de esta oferta vs. la mediana de las otras ofertas del MISMO ASIN
   * (o el precio de Amazon como vendedor). -0.35 = 35% más barato.
   */
  priceDeviation?: number | null;
  /** Reportes verificados de usuarios de Prais contra este vendedor. */
  verifiedReports?: number;
};

type Signal = { key: string; weight: number; value: number | null; reason?: string; good?: boolean };

export type TrustResult = {
  asin: string;
  sellerId: string | null;
  score: number | null;
  coverage: number;
  verdict: "confiable" | "precaucion" | "riesgosa" | "sin_datos";
  redFlags: string[];
  reasons: { text: string; good: boolean }[];
  signals: Signal[];
};

// ───────────────────────── Fetch ─────────────────────────

async function run(actor: string, input: Record<string, unknown>): Promise<any[]> {
  const r = await apify.actor(actor).call(input);
  const { items } = await apify.dataset(r.defaultDatasetId).listItems();
  return items as any[];
}

export async function fetchOffer(productUrl: string): Promise<Offer | null> {
  const items = await run(PRODUCT_ACTOR, {
    categoryOrProductUrls: [{ url: productUrl }],
    maxItemsPerStartUrl: 1,
    scrapeSellers: true, // verifica el nombre del flag en el input schema
  });
  return items[0] ? normalizeOffer(items[0]) : null;
}

export async function fetchSeller(sellerId: string, marketplace = "com"): Promise<Seller | null> {
  const items = await run(SELLER_ACTOR, { action: "seller/profile", seller_id: sellerId, marketplace });
  return items[0] ? normalizeSeller(sellerId, items[0]) : null;
}

export async function fetchFeedback(sellerId: string, marketplace = "com"): Promise<FeedbackReview[]> {
  try {
    const items = await run(SELLER_ACTOR, { action: "seller/reviews", seller_id: sellerId, marketplace });
    return items.slice(0, 40).map((r) => ({
      rating: r.rating != null ? Number(r.rating) : null,
      text: String(r.text ?? r.body ?? ""),
      date: r.date ? new Date(r.date) : null,
    }));
  } catch {
    return [];
  }
}

const num = (v: any): number | null => {
  if (v == null) return null;
  const n = Number(String(v).replace(/[^\d.]/g, ""));
  return isNaN(n) ? null : n;
};

function normalizeOffer(r: any): Offer {
  const soldBy = String(r.seller?.name ?? r.soldBy ?? "").toLowerCase();
  const shipsFrom = String(r.shipsFrom ?? r.seller?.shipsFrom ?? "").toLowerCase();
  const fulfillment: Fulfillment =
    !soldBy && !shipsFrom ? null
    : soldBy.startsWith("amazon") ? "amazon"
    : shipsFrom.includes("amazon") || r.isFBA || r.fulfilledByAmazon ? "fba"
    : "merchant";
  return {
    asin: r.asin ?? r.ASIN,
    title: r.title ?? "",
    price: num(r.price?.value ?? r.price),
    sellerId: r.seller?.id ?? r.sellerId ?? null,
    sellerName: r.seller?.name ?? r.soldBy ?? null,
    fulfillment,
    productRating: num(r.stars ?? r.rating),
    productReviews: num(r.reviewsCount ?? r.ratingsCount),
  };
}

function normalizeSeller(id: string, r: any): Seller {
  const pct = num(r.feedback_percent ?? r.positivePercent);
  return {
    id,
    name: r.name ?? null,
    positivePct: pct != null ? (pct > 1 ? pct / 100 : pct) : null,
    ratingsLifetime: num(r.lifetime_ratings),
    ratings12m: num(r.ratings_12m),
    ratings90d: num(r.ratings_90d),
  };
}

// ───────────────────────── Helpers ─────────────────────────

const clamp = (x: number, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, x));

/** Reseñas que hablan de falsificación, producto usado o que nunca llegó (es/en). */
const ALERT_REVIEW = /(fake|counterfeit|knock[- ]?off|not (genuine|authentic|original)|falsificad|imitaci[oó]n|no (es )?original|used|refurbished|usad[oa]|reacondicionad|never (arrived|received)|not received|nunca lleg|no (me )?lleg|scam|estafa)/i;

// ───────────────────────── Señales ─────────────────────────

function computeSignals(offer: Offer, seller: Seller | null, reviews: FeedbackReview[], ext: ExternalInputs): Signal[] {
  const s: Signal[] = [];

  // ── Cómo se vende (15) ──

  // 1. Quién vende y quién envía (15). Con FBA, Amazon maneja envío y devoluciones.
  if (offer.fulfillment) {
    const v = offer.fulfillment === "amazon" ? 1 : offer.fulfillment === "fba" ? 0.8 : 0.4;
    s.push({ key: "fulfillment", weight: 15, value: v, good: v >= 0.8,
      reason: offer.fulfillment === "amazon" ? "Vendido y enviado por Amazon"
        : offer.fulfillment === "fba" ? "Enviado por Amazon (FBA)"
        : "Enviado directamente por el vendedor" });
  } else s.push({ key: "fulfillment", weight: 15, value: null });

  // ── Reputación del vendedor (50) ──

  // 2. Feedback positivo (20): ≥ 95% → 1, ≤ 80% → 0. Solo con 20+ calificaciones.
  if (seller?.positivePct != null && (seller.ratingsLifetime ?? 0) >= 20) {
    const p = seller.positivePct;
    const v = clamp((p - 0.8) / 0.15);
    s.push({ key: "positive_feedback", weight: 20, value: v, good: v >= 0.7,
      reason: `${Math.round(p * 100)}% de feedback positivo` });
  } else s.push({ key: "positive_feedback", weight: 20, value: null });

  // 3. Volumen de calificaciones (10): escala log, 1.000+ → 1.
  if (seller?.ratingsLifetime != null) {
    const v = clamp(Math.log10(seller.ratingsLifetime + 1) / 3);
    s.push({ key: "ratings_volume", weight: 10, value: v, good: v >= 0.6,
      reason: `${seller.ratingsLifetime.toLocaleString()} calificaciones` });
  } else s.push({ key: "ratings_volume", weight: 10, value: null });

  // 4. Actividad reciente (10): una cuenta con historial que lleva un año sin ventas y
  //    reaparece es el patrón clásico de cuenta de vendedor robada.
  if (seller?.ratingsLifetime != null && seller.ratings12m != null && seller.ratingsLifetime >= 20) {
    const share = seller.ratings12m / seller.ratingsLifetime;
    const v = seller.ratings12m === 0 ? 0 : clamp(share / 0.1); // ≥ 10% del historial en el último año → 1
    s.push({ key: "recent_activity", weight: 10, value: v, good: v >= 0.6,
      reason: seller.ratings12m === 0 ? "Sin ventas calificadas en el último año (cuenta inactiva que reapareció)" : undefined });
  } else s.push({ key: "recent_activity", weight: 10, value: null });

  // 5. Reseñas de alerta recientes (10): falsificado, usado, no llegó.
  if (reviews.length >= 5) {
    const alerts = reviews.filter((r) => ALERT_REVIEW.test(r.text) && (r.rating ?? 5) <= 2).length;
    const v = clamp(1 - alerts / 3);
    s.push({ key: "alert_reviews", weight: 10, value: v, good: v === 1,
      reason: alerts ? `${alerts} reseña(s) recientes que hablan de falsificación, producto usado o no recibido` : undefined });
  } else s.push({ key: "alert_reviews", weight: 10, value: null });

  // ── Producto (5) ──

  // 6. Historial del producto (5): ASIN con reseñas y buena nota.
  if (offer.productReviews != null && offer.productRating != null) {
    const v = 0.5 * clamp(Math.log10(offer.productReviews + 1) / 2.5) + 0.5 * clamp((offer.productRating - 3.5) / 1);
    s.push({ key: "product_history", weight: 5, value: v, good: v >= 0.6 });
  } else s.push({ key: "product_history", weight: 5, value: null });

  // ── Contexto Prais (30) ──

  // 7. Precio vs. otras ofertas del mismo ASIN (20)
  if (ext.priceDeviation != null) {
    const d = ext.priceDeviation;
    const v = d >= -0.15 ? 1 : clamp(1 - (-d - 0.15) / 0.3);
    s.push({ key: "price_anomaly", weight: 20, value: v, good: v === 1,
      reason: v < 1 ? `${Math.round(-d * 100)}% más barato que las demás ofertas del mismo producto` : undefined });
  } else s.push({ key: "price_anomaly", weight: 20, value: null });

  // 8. Reportes verificados de usuarios de Prais (10)
  if (ext.verifiedReports != null) {
    const v = clamp(1 - ext.verifiedReports / 3);
    s.push({ key: "reports", weight: 10, value: v, good: v === 1,
      reason: ext.verifiedReports ? `${ext.verifiedReports} reporte(s) verificados de usuarios de Prais` : undefined });
  } else s.push({ key: "reports", weight: 10, value: null });

  return s;
}

function redFlags(offer: Offer, seller: Seller | null, reviews: FeedbackReview[], ext: ExternalInputs): string[] {
  const f: string[] = [];
  if (offer.fulfillment === "amazon") return f; // Amazon como vendedor: sin banderas de vendedor

  const dormant = seller && (seller.ratingsLifetime ?? 0) >= 20 && seller.ratings12m === 0;
  if (dormant && ext.priceDeviation != null && ext.priceDeviation <= -0.3) {
    f.push("Cuenta inactiva que reapareció con precios muy bajos (posible cuenta robada)");
  }
  if (seller?.positivePct != null && (seller.ratingsLifetime ?? 0) >= 20 && seller.positivePct < 0.8) {
    f.push("Menos de 80% de feedback positivo");
  }
  const alerts = reviews.filter((r) => ALERT_REVIEW.test(r.text) && (r.rating ?? 5) <= 2).length;
  if (alerts >= 3) f.push("Varias reseñas recientes de falsificación o envíos no recibidos");
  if (ext.priceDeviation != null && ext.priceDeviation <= -0.5) f.push("Más de 50% más barato que las demás ofertas");
  if ((ext.verifiedReports ?? 0) >= 3) f.push("Múltiples reportes verificados de usuarios de Prais");
  return f;
}

// ───────────────────────── Score ─────────────────────────

const MIN_COVERAGE = 0.4;

export function scoreOffer(offer: Offer, seller: Seller | null, reviews: FeedbackReview[], ext: ExternalInputs = {}): TrustResult {
  const base0 = { asin: offer.asin, sellerId: offer.sellerId };

  // Atajo: vendido y enviado por Amazon. El riesgo de vendedor no aplica.
  if (offer.fulfillment === "amazon") {
    return { ...base0, score: 95, coverage: 1, verdict: "confiable", redFlags: [],
      reasons: [{ text: "Vendido y enviado por Amazon", good: true }], signals: [] };
  }

  const signals = computeSignals(offer, seller, reviews, ext);
  const flags = redFlags(offer, seller, reviews, ext);
  const total = signals.reduce((a, s) => a + s.weight, 0);
  const avail = signals.filter((s) => s.value != null);
  const wAvail = avail.reduce((a, s) => a + s.weight, 0);
  const coverage = wAvail / total;

  const reasons = signals
    .filter((s) => s.reason)
    .sort((a, b) => b.weight * (1 - (b.value ?? 1)) - a.weight * (1 - (a.value ?? 1)))
    .map((s) => ({ text: s.reason!, good: !!s.good }));

  const base = { ...base0, coverage, reasons, signals };
  if (flags.length) return { ...base, score: 0, verdict: "riesgosa", redFlags: flags };
  if (coverage < MIN_COVERAGE) return { ...base, score: null, verdict: "sin_datos", redFlags: [] };

  const score = Math.round((100 * avail.reduce((a, s) => a + s.weight * s.value!, 0)) / wAvail);
  const verdict = score >= 75 ? "confiable" : score >= 50 ? "precaucion" : "riesgosa";
  return { ...base, score, verdict, redFlags: [] };
}

// ───────────────────────── Orquestación ─────────────────────────

export async function checkOffer(productUrl: string, ext: ExternalInputs = {}): Promise<TrustResult> {
  const offer = await fetchOffer(productUrl);
  if (!offer) {
    return { asin: productUrl, sellerId: null, score: null, coverage: 0, verdict: "sin_datos",
      redFlags: [], reasons: [{ text: "No se pudo leer el producto", good: false }], signals: [] };
  }
  if (offer.fulfillment === "amazon" || !offer.sellerId) return scoreOffer(offer, null, [], ext);
  const [seller, reviews] = await Promise.all([fetchSeller(offer.sellerId), fetchFeedback(offer.sellerId)]);
  return scoreOffer(offer, seller, reviews, ext);
}

// Ejemplo:
// checkOffer("https://www.amazon.com/dp/B0EXAMPLE", { priceDeviation: -0.08, verifiedReports: 0 })
//   .then((r) => console.log(JSON.stringify(r, null, 2)));
