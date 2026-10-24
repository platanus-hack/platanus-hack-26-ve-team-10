/**
 * MercadoLibre Trust Score — puntaje de seguridad de una publicación y su vendedor en
 * Mercado Libre Venezuela (site MLV), usando la API oficial.
 *
 * A diferencia de Instagram o Marketplace, aquí la reputación nativa SÍ es la señal
 * principal: el termómetro, MercadoLíder y las calificaciones se construyen con ventas
 * concretadas en la plataforma.
 *
 * ⚠️ Antes de producción:
 *   - Crea una app en developers.mercadolibre.com y usa su access token (ML_ACCESS_TOKEN).
 *     Varios endpoints públicos ahora piden token; con él funcionan items y users.
 *   - Verifica con 3–4 vendedores reales de MLV qué devuelve GET /users/{id}:
 *     `registration_date` y `metrics` no siempre vienen para usuarios de terceros.
 *     Lo que no venga queda en null y no penaliza.
 *   - En Venezuela muchas ventas se pagan fuera de la plataforma; aun así la calificación
 *     existe y es la mejor señal disponible.
 *
 * Node 18+ (fetch nativo). Sin dependencias.
 */

const API = "https://api.mercadolibre.com";

// ───────────────────────── Tipos ─────────────────────────

type Item = {
  id: string;
  title: string;
  price: number | null;
  currency: string | null;
  condition: string | null;           // new | used
  pictures: number;
  description: string;
  warranty: string | null;
  createdAt: Date | null;
  soldQuantity: number | null;
  status: string | null;
  sellerId: number;
  state: string | null;               // estado de Venezuela de la publicación
};

type Seller = {
  id: number;
  nickname: string;
  registeredAt: Date | null;
  state: string | null;
  levelId: string | null;             // "5_green", "4_light_green", ..., "1_red"
  powerSeller: string | null;         // platinum | gold | silver | null
  completed: number | null;
  canceled: number | null;
  total: number | null;
  ratings: { positive: number; neutral: number; negative: number } | null;
  claimsRate: number | null;
  status: string | null;              // "active", o suspendido
};

export type ExternalInputs = {
  /** Precio vs. mediana de mercado (Prais): -0.35 = 35% más barato. */
  priceDeviation?: number | null;
  /** Reportes de estafa verificados contra este vendedor. */
  verifiedReports?: number;
};

type Signal = { key: string; weight: number; value: number | null; reason?: string; good?: boolean };

export type TrustResult = {
  itemId: string;
  sellerId: number | null;
  score: number | null;
  coverage: number;
  verdict: "confiable" | "precaucion" | "riesgosa" | "sin_datos";
  redFlags: string[];
  reasons: { text: string; good: boolean }[];
  signals: Signal[];
};

// ───────────────────────── Fetch ─────────────────────────

async function ml(path: string): Promise<any | null> {
  try {
    const res = await fetch(`${API}${path}`, {
      headers: process.env.ML_ACCESS_TOKEN ? { Authorization: `Bearer ${process.env.ML_ACCESS_TOKEN}` } : {},
      signal: AbortSignal.timeout(10000),
    });
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

/** Acepta "MLV-123456789", "MLV123456789" o la URL completa de la publicación. */
export function parseItemId(input: string): string | null {
  const m = input.match(/MLV-?(\d{6,})/i);
  return m ? `MLV${m[1]}` : null;
}

export async function fetchItem(itemId: string): Promise<Item | null> {
  const [it, desc] = await Promise.all([ml(`/items/${itemId}`), ml(`/items/${itemId}/description`)]);
  if (!it) return null;
  return {
    id: it.id,
    title: it.title ?? "",
    price: it.price ?? null,
    currency: it.currency_id ?? null,
    condition: it.condition ?? null,
    pictures: (it.pictures ?? []).length,
    description: desc?.plain_text ?? "",
    warranty: it.warranty ?? it.sale_terms?.find((t: any) => t.id === "WARRANTY_TIME")?.value_name ?? null,
    createdAt: it.date_created ? new Date(it.date_created) : null,
    soldQuantity: it.sold_quantity ?? null,
    status: it.status ?? null,
    sellerId: it.seller_id,
    state: it.seller_address?.state?.name ?? it.location?.state?.name ?? null,
  };
}

export async function fetchSeller(sellerId: number): Promise<Seller | null> {
  const u = await ml(`/users/${sellerId}`);
  if (!u) return null;
  const rep = u.seller_reputation ?? {};
  const tx = rep.transactions ?? {};
  return {
    id: u.id,
    nickname: u.nickname,
    registeredAt: u.registration_date ? new Date(u.registration_date) : null,
    state: u.address?.state ?? null,
    levelId: rep.level_id ?? null,
    powerSeller: rep.power_seller_status ?? null,
    completed: tx.completed ?? null,
    canceled: tx.canceled ?? null,
    total: tx.total ?? null,
    ratings: tx.ratings ?? null,
    claimsRate: rep.metrics?.claims?.rate ?? null,
    status: u.status?.site_status ?? null,
  };
}

// ───────────────────────── Helpers ─────────────────────────

const clamp = (x: number, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, x));
const monthsSince = (d: Date) => (Date.now() - d.getTime()) / (1000 * 60 * 60 * 24 * 30.44);

// Mismos 3 patrones de siempre. Coordinar pago o entrega por WhatsApp NO se penaliza:
// en MLV es la norma, porque el pago casi nunca pasa por la plataforma.
const RISK_PATTERNS: [RegExp, string][] = [
  [/(sin|no hay|no se aceptan)\s+devoluci/i, "No acepta devoluciones"],
  [/(últimas?|ultimas?)\s+unidades|solo\s+(por\s+)?hoy|quedan\s+\d+/i, "Usa presión de urgencia"],
  [/(precio|oferta)\s+(de\s+)?(locura|regalado|remate)/i, "Precios 'demasiado buenos'"],
];

const LEVEL_VALUE: Record<string, number> = {
  "5_green": 1, "4_light_green": 0.75, "3_yellow": 0.4, "2_orange": 0.15, "1_red": 0,
};
const LEVEL_LABEL: Record<string, string> = {
  "5_green": "verde", "4_light_green": "verde claro", "3_yellow": "amarillo", "2_orange": "naranja", "1_red": "rojo",
};

// ───────────────────────── Señales ─────────────────────────

function computeSignals(item: Item, seller: Seller | null, ext: ExternalInputs): Signal[] {
  const s: Signal[] = [];

  // ── Reputación en Mercado Libre (40) ──
  // Un vendedor sin reputación todavía (nuevo) queda en null: no se le castiga, pero
  // tampoco suma, y la cobertura lo refleja.

  // 1. Termómetro (15)
  if (seller?.levelId && seller.levelId in LEVEL_VALUE) {
    const v = LEVEL_VALUE[seller.levelId];
    s.push({ key: "thermometer", weight: 15, value: v, good: v >= 0.75,
      reason: `Reputación ${LEVEL_LABEL[seller.levelId]} en Mercado Libre` });
  } else s.push({ key: "thermometer", weight: 15, value: null });

  // 2. MercadoLíder (5)
  if (seller?.levelId) {
    const v = seller.powerSeller === "platinum" ? 1 : seller.powerSeller === "gold" ? 0.8
      : seller.powerSeller === "silver" ? 0.6 : 0;
    s.push({ key: "power_seller", weight: 5, value: v, good: v > 0,
      reason: seller.powerSeller ? `MercadoLíder ${seller.powerSeller}` : undefined });
  } else s.push({ key: "power_seller", weight: 5, value: null });

  // 3. Volumen de ventas concretadas (10): escala log, 100+ → 1.
  if (seller?.completed != null) {
    const v = clamp(Math.log10(seller.completed + 1) / 2);
    s.push({ key: "sales_volume", weight: 10, value: v, good: v >= 0.6,
      reason: seller.completed > 0 ? `${seller.completed.toLocaleString()} ventas concretadas` : "Sin ventas concretadas" });
  } else s.push({ key: "sales_volume", weight: 10, value: null });

  // 4. Calificaciones negativas (10): ≤ 2% → 1, ≥ 15% → 0. Solo con 10+ ventas.
  if (seller?.ratings && (seller.total ?? 0) >= 10) {
    const neg = seller.ratings.negative; // proporción 0..1
    const v = clamp(1 - (neg - 0.02) / 0.13);
    s.push({ key: "negative_ratings", weight: 10, value: v, good: v >= 0.7,
      reason: neg > 0.05 ? `${Math.round(neg * 100)}% de calificaciones negativas` : undefined });
  } else s.push({ key: "negative_ratings", weight: 10, value: null });

  // ── Identidad (15) ──

  // 5. Antigüedad de la cuenta (10): < 3 meses → 0, 3 años → 1.
  if (seller?.registeredAt) {
    const m = monthsSince(seller.registeredAt);
    const v = m < 3 ? 0 : clamp(Math.log(m / 3) / Math.log(12));
    s.push({ key: "account_age", weight: 10, value: v, good: v >= 0.6,
      reason: v >= 0.6 ? `En Mercado Libre desde ${seller.registeredAt.getFullYear()}` : `Cuenta reciente (${Math.round(m)} meses)` });
  } else s.push({ key: "account_age", weight: 10, value: null });

  // 6. Ubicación coherente (5): estado de la publicación = estado del vendedor.
  if (seller?.state && item.state) {
    const ok = seller.state.toLowerCase() === item.state.toLowerCase();
    s.push({ key: "location", weight: 5, value: ok ? 1 : 0.4, good: ok,
      reason: ok ? undefined : `Publica en ${item.state} pero su cuenta está en ${seller.state}` });
  } else s.push({ key: "location", weight: 5, value: null });

  // ── Publicación (15) ──

  // 7. Completitud (5): fotos y descripción.
  {
    const v = 0.5 * clamp(item.pictures / 4) + 0.5 * clamp(item.description.split(/\s+/).filter(Boolean).length / 40);
    s.push({ key: "completeness", weight: 5, value: v, good: v >= 0.7,
      reason: v < 0.4 ? "Publicación con pocas fotos o sin descripción" : undefined });
  }

  // 8. Garantía declarada (5)
  s.push({ key: "warranty", weight: 5, value: item.warranty && !/sin garant/i.test(item.warranty) ? 1 : 0.3,
    good: !!item.warranty && !/sin garant/i.test(item.warranty),
    reason: item.warranty && !/sin garant/i.test(item.warranty) ? `Garantía: ${item.warranty}` : "Sin garantía declarada" });

  // 9. Lenguaje de riesgo (5)
  {
    const hits = RISK_PATTERNS.filter(([re]) => re.test(`${item.title}\n${item.description}`)).map(([, t]) => t);
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

function redFlags(item: Item, seller: Seller | null, ext: ExternalInputs): string[] {
  const f: string[] = [];
  if (seller?.status && seller.status !== "active") f.push("Cuenta de vendedor suspendida o inactiva");
  if (seller?.levelId === "1_red" && (seller.total ?? 0) >= 10) f.push("Reputación roja con más de 10 ventas");
  if (seller?.ratings && (seller.total ?? 0) >= 10 && seller.ratings.negative >= 0.25) f.push("25% o más de calificaciones negativas");
  if (seller?.registeredAt && monthsSince(seller.registeredAt) < 1) f.push("Cuenta creada hace menos de un mes");
  if (ext.priceDeviation != null && ext.priceDeviation <= -0.5) f.push("Precio más de 50% bajo el mercado");
  if ((ext.verifiedReports ?? 0) >= 3) f.push("Múltiples reportes de estafa verificados");
  return f;
}

// ───────────────────────── Score ─────────────────────────

const MIN_COVERAGE = 0.4;

export function scoreItem(item: Item, seller: Seller | null, ext: ExternalInputs = {}): TrustResult {
  const signals = computeSignals(item, seller, ext);
  const flags = redFlags(item, seller, ext);
  const total = signals.reduce((a, s) => a + s.weight, 0);
  const avail = signals.filter((s) => s.value != null);
  const wAvail = avail.reduce((a, s) => a + s.weight, 0);
  const coverage = wAvail / total;

  const reasons = signals
    .filter((s) => s.reason)
    .sort((a, b) => b.weight * (1 - (b.value ?? 1)) - a.weight * (1 - (a.value ?? 1)))
    .map((s) => ({ text: s.reason!, good: !!s.good }));

  const base = { itemId: item.id, sellerId: seller?.id ?? item.sellerId, coverage, reasons, signals };
  if (flags.length) return { ...base, score: 0, verdict: "riesgosa", redFlags: flags };
  if (coverage < MIN_COVERAGE) return { ...base, score: null, verdict: "sin_datos", redFlags: [] };

  const score = Math.round((100 * avail.reduce((a, s) => a + s.weight * s.value!, 0)) / wAvail);
  const verdict = score >= 75 ? "confiable" : score >= 50 ? "precaucion" : "riesgosa";
  return { ...base, score, verdict, redFlags: [] };
}

// ───────────────────────── Orquestación ─────────────────────────

export async function checkItem(urlOrId: string, ext: ExternalInputs = {}): Promise<TrustResult> {
  const id = parseItemId(urlOrId);
  const item = id ? await fetchItem(id) : null;
  if (!item) {
    return { itemId: id ?? urlOrId, sellerId: null, score: null, coverage: 0, verdict: "sin_datos",
      redFlags: [], reasons: [{ text: "No se pudo leer la publicación", good: false }], signals: [] };
  }
  const seller = await fetchSeller(item.sellerId);
  return scoreItem(item, seller, ext);
}

// Ejemplo:
// checkItem("https://articulo.mercadolibre.com.ve/MLV-123456789-iphone-15-128gb-_JM", {
//   priceDeviation: -0.12, verifiedReports: 0,
// }).then((r) => console.log(JSON.stringify(r, null, 2)));
