/**
 * TikTok Trust Score — puntaje de seguridad de una cuenta de TikTok usando Apify.
 *
 * Actores:
 *   - clockworks/tiktok-profile-scraper   (perfil en authorMeta + últimos videos)
 *   - clockworks/tiktok-comments-scraper  (comentarios de los videos más recientes)
 *
 * ⚠️ Antes de producción:
 *   - Haz una corrida en Apify Console y ajusta normalize() a los campos reales.
 *   - La fecha de creación NO viene en el actor: se deriva del ID numérico del usuario
 *     (los 32 bits altos son un timestamp Unix). Verifícalo con 3–4 cuentas de fecha conocida;
 *     si no cuadra, la señal queda en null y no penaliza.
 *
 * npm i apify-client
 */
import { ApifyClient } from "apify-client";

const apify = new ApifyClient({ token: process.env.APIFY_TOKEN });
const PROFILE_ACTOR = "clockworks/tiktok-profile-scraper";
const COMMENT_ACTOR = "clockworks/tiktok-comments-scraper";

// ───────────────────────── Tipos ─────────────────────────

type Video = {
  url: string | null;
  createdAt: Date | null;
  plays: number;
  likes: number;
  comments: number;
  shares: number;
  saves: number;
  caption: string;
  isAd: boolean;
};

type Profile = {
  username: string;
  userId: string | null;
  createdAt: Date | null;     // derivada del userId
  region: string | null;
  bio: string;
  followers: number | null;
  totalHearts: number | null; // likes acumulados de toda la cuenta
  videoCount: number | null;
  isPrivate: boolean;
  videos: Video[];
};

type Comment = { text?: string; author?: string };

export type ExternalInputs = {
  /** Precio vs. mediana de mercado (Prais): -0.35 = 35% más barato. */
  priceDeviation?: number | null;
  /** Reportes de estafa verificados contra esta cuenta. */
  verifiedReports?: number;
  /** Código de región esperado, p. ej. "VE". */
  expectedRegion?: string;
};

type Signal = { key: string; weight: number; value: number | null; reason?: string; good?: boolean };

export type TrustResult = {
  username: string;
  score: number | null;
  coverage: number;
  verdict: "confiable" | "precaucion" | "riesgosa" | "sin_datos";
  redFlags: string[];
  reasons: { text: string; good: boolean }[];
  signals: Signal[];
};

// ───────────────────────── Fetch ─────────────────────────

export async function fetchProfile(username: string, videos = 20): Promise<Profile | null> {
  const run = await apify.actor(PROFILE_ACTOR).call({
    profiles: [username.replace(/^@/, "")],
    resultsPerPage: videos,
    shouldDownloadVideos: false,
    shouldDownloadCovers: false,
  });
  const { items } = await apify.dataset(run.defaultDatasetId).listItems();
  return items.length ? normalize(items as any[]) : null;
}

export async function fetchComments(videoUrls: string[], perVideo = 30): Promise<Comment[]> {
  if (!videoUrls.length) return [];
  const run = await apify.actor(COMMENT_ACTOR).call({ postURLs: videoUrls, commentsPerPost: perVideo });
  const { items } = await apify.dataset(run.defaultDatasetId).listItems();
  return (items as any[]).map((c) => ({ text: c.text, author: c.uniqueId ?? c.user?.uniqueId }));
}

/** El actor devuelve un item por video, cada uno con authorMeta repetido. */
function normalize(items: any[]): Profile {
  const a = items[0].authorMeta ?? {};
  const userId = a.id ? String(a.id) : null;
  return {
    username: a.name ?? a.uniqueId,
    userId,
    createdAt: userId ? dateFromTikTokId(userId) : null,
    region: a.region ?? null,
    bio: a.signature ?? "",
    followers: a.fans ?? null,
    totalHearts: a.heart ?? null,
    videoCount: a.video ?? null,
    isPrivate: !!a.privateAccount,
    videos: items
      .filter((v) => v.id || v.webVideoUrl)
      .map((v) => ({
        url: v.webVideoUrl ?? null,
        createdAt: v.createTimeISO ? new Date(v.createTimeISO) : v.createTime ? new Date(v.createTime * 1000) : null,
        plays: v.playCount ?? 0,
        likes: v.diggCount ?? 0,
        comments: v.commentCount ?? 0,
        shares: v.shareCount ?? 0,
        saves: v.collectCount ?? 0,
        caption: v.text ?? "",
        isAd: !!v.isAd,
      })),
  };
}

/** Los IDs de TikTok llevan un timestamp Unix en sus 32 bits altos. */
function dateFromTikTokId(id: string): Date | null {
  try {
    const secs = Number(BigInt(id) >> 32n);
    const d = new Date(secs * 1000);
    const y = d.getUTCFullYear();
    return y >= 2014 && d.getTime() <= Date.now() ? d : null; // fuera de rango → ID viejo sin timestamp
  } catch {
    return null;
  }
}

// ───────────────────────── Helpers ─────────────────────────

const clamp = (x: number, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, x));
const median = (xs: number[]) => {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / (xs.length || 1);
const stdev = (xs: number[]) => {
  const m = mean(xs);
  return Math.sqrt(mean(xs.map((x) => (x - m) ** 2)));
};
const monthsSince = (d: Date) => (Date.now() - d.getTime()) / (1000 * 60 * 60 * 24 * 30.44);

// Mismos 3 patrones que IG y Marketplace (sin pagos ni DM/WhatsApp: normales en Venezuela).
const RISK_PATTERNS: [RegExp, string][] = [
  [/(sin|no hay|no se aceptan)\s+devoluci/i, "No acepta devoluciones"],
  [/(últimas?|ultimas?)\s+unidades|solo\s+(por\s+)?hoy|quedan\s+\d+/i, "Usa presión de urgencia"],
  [/(precio|oferta)\s+(de\s+)?(locura|regalado|remate)/i, "Precios 'demasiado buenos'"],
];

// ───────────────────────── Señales ─────────────────────────

function computeSignals(p: Profile, comments: Comment[], ext: ExternalInputs): Signal[] {
  const s: Signal[] = [];
  // Los anuncios pagados inflan vistas: se excluyen de las métricas orgánicas.
  const vids = p.videos.filter((v) => !v.isAd && v.plays > 0);
  const enough = vids.length >= 3;

  // ── Identidad (20) ──

  // 1. Antigüedad (15): derivada del ID. < 3 meses → 0, 36 meses → 1.
  if (p.createdAt) {
    const m = monthsSince(p.createdAt);
    const v = m < 3 ? 0 : clamp(Math.log(m / 3) / Math.log(12));
    s.push({ key: "age", weight: 15, value: v, good: v >= 0.6,
      reason: v >= 0.6 ? `Cuenta desde ${p.createdAt.getFullYear()}` : `Cuenta reciente (${Math.round(m)} meses)` });
  } else s.push({ key: "age", weight: 15, value: null });

  // 2. Región coherente (5)
  if (p.region && ext.expectedRegion) {
    const ok = p.region.toUpperCase() === ext.expectedRegion.toUpperCase();
    s.push({ key: "region", weight: 5, value: ok ? 1 : 0, good: ok,
      reason: ok ? undefined : `Cuenta registrada en ${p.region}, no en ${ext.expectedRegion}` });
  } else s.push({ key: "region", weight: 5, value: null });

  // ── Autenticidad de la audiencia (40) ──
  // En TikTok las vistas vienen del algoritmo, no de los seguidores, y los picos virales
  // son normales. Por eso NO se mide likes/seguidores ni la variación de vistas:
  // se mide la PROPORCIÓN entre interacciones, que es lo que delata vistas compradas.

  // 3. Likes / vistas (15): orgánico suele estar entre ~2% y ~15%.
  if (enough) {
    const r = median(vids.map((v) => v.likes / v.plays));
    let v: number;
    if (r < 0.005) v = 0;
    else if (r < 0.02) v = (r - 0.005) / 0.015;
    else if (r <= 0.2) v = 1;
    else v = clamp(1 - (r - 0.2) / 0.2); // demasiado alto → likes comprados
    s.push({ key: "like_view_ratio", weight: 15, value: v, good: v >= 0.7,
      reason: v >= 0.7 ? "Interacción acorde a sus vistas"
        : r < 0.02 ? "Muchas vistas pero casi sin likes (posibles vistas compradas)"
        : "Likes desproporcionados para sus vistas (posibles likes comprados)" });
  } else s.push({ key: "like_view_ratio", weight: 15, value: null });

  // 4. Consistencia de esa proporción entre videos (5): las compras de vistas se notan
  //    como videos con ratio muy distinto al resto.
  if (enough) {
    const ratios = vids.map((v) => v.likes / v.plays);
    const cv = mean(ratios) > 0 ? stdev(ratios) / mean(ratios) : 2;
    const v = clamp(1 - (cv - 0.5) / 1.0); // cv ≤ 0.5 → 1, ≥ 1.5 → 0
    s.push({ key: "ratio_consistency", weight: 5, value: v, good: v >= 0.6,
      reason: v < 0.4 ? "Algunos videos con interacción muy distinta al resto" : undefined });
  } else s.push({ key: "ratio_consistency", weight: 5, value: null });

  // 5. Corazones totales / seguidores (5): seguidores comprados no dan likes.
  //    Una cuenta real casi siempre acumula más corazones que seguidores.
  if (p.followers && p.followers >= 500 && p.totalHearts != null) {
    const r = p.totalHearts / p.followers;
    const v = clamp((r - 0.5) / 2.5); // ≤ 0.5 → 0, ≥ 3 → 1
    s.push({ key: "hearts_per_follower", weight: 5, value: v, good: v >= 0.6,
      reason: v < 0.3 ? `Pocos likes totales para ${p.followers.toLocaleString()} seguidores (posibles seguidores comprados)` : undefined });
  } else s.push({ key: "hearts_per_follower", weight: 5, value: null });

  // 6. Calidad de comentarios (10)
  if (comments.length >= 10) {
    const real = comments.filter((c) => c.text && c.text.trim().split(/\s+/).length > 3
      && !/^[\p{Emoji}\s!.]+$/u.test(c.text)).length / comments.length;
    const authors = new Set(comments.map((c) => c.author)).size / comments.length;
    const v = 0.7 * clamp(real / 0.4) + 0.3 * clamp(authors / 0.7);
    s.push({ key: "comment_quality", weight: 10, value: v, good: v >= 0.6,
      reason: v >= 0.6 ? "Comentarios de personas reales y variadas" : "Comentarios genéricos o repetidos" });
  } else s.push({ key: "comment_quality", weight: 10, value: null });

  // 7. Compartidos + guardados (5): son caros de falsificar y señalan interés real en el producto.
  if (enough) {
    const r = median(vids.map((v) => (v.shares + v.saves) / Math.max(v.likes, 1)));
    const v = clamp(r / 0.05); // ≥ 5% de los likes → 1
    s.push({ key: "shares_saves", weight: 5, value: v, good: v >= 0.6,
      reason: v >= 0.6 ? "La gente guarda y comparte sus videos" : undefined });
  } else s.push({ key: "shares_saves", weight: 5, value: null });

  // ── Comportamiento (10) ──

  // 8. Ritmo de publicación (5)
  const days = vids.map((v) => v.createdAt?.toISOString().slice(0, 10)).filter(Boolean) as string[];
  if (days.length >= 5) {
    const counts = Object.values(days.reduce<Record<string, number>>((a, d) => ((a[d] = (a[d] ?? 0) + 1), a), {}));
    const burst = Math.max(...counts) / days.length;
    const v = clamp(1 - (burst - 0.25) / 0.5);
    s.push({ key: "posting_rhythm", weight: 5, value: v, good: v >= 0.6,
      reason: v < 0.5 ? "Gran parte de los videos se subieron el mismo día" : undefined });
  } else s.push({ key: "posting_rhythm", weight: 5, value: null });

  // 9. Lenguaje de riesgo en bio y captions (5)
  {
    const text = [p.bio, ...p.videos.map((v) => v.caption)].join("\n");
    const hits = RISK_PATTERNS.filter(([re]) => re.test(text)).map(([, t]) => t);
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

function redFlags(p: Profile, ext: ExternalInputs): string[] {
  const f: string[] = [];
  if (ext.priceDeviation != null && ext.priceDeviation <= -0.5) f.push("Precio más de 50% bajo el mercado");
  if (p.createdAt && monthsSince(p.createdAt) < 1) f.push("Cuenta creada hace menos de un mes");
  if ((ext.verifiedReports ?? 0) >= 3) f.push("Múltiples reportes de estafa verificados");
  return f;
}

// ───────────────────────── Score ─────────────────────────

const MIN_COVERAGE = 0.4;

export function scoreProfile(p: Profile, comments: Comment[], ext: ExternalInputs = {}): TrustResult {
  const signals = computeSignals(p, comments, ext);
  const flags = redFlags(p, ext);
  const total = signals.reduce((a, s) => a + s.weight, 0);
  const avail = signals.filter((s) => s.value != null);
  const wAvail = avail.reduce((a, s) => a + s.weight, 0);
  const coverage = wAvail / total;

  const reasons = signals
    .filter((s) => s.reason)
    .sort((a, b) => b.weight * (1 - (b.value ?? 1)) - a.weight * (1 - (a.value ?? 1)))
    .map((s) => ({ text: s.reason!, good: !!s.good }));

  const base = { username: p.username, coverage, reasons, signals };
  if (flags.length) return { ...base, score: 0, verdict: "riesgosa", redFlags: flags };
  if (coverage < MIN_COVERAGE) return { ...base, score: null, verdict: "sin_datos", redFlags: [] };

  const score = Math.round((100 * avail.reduce((a, s) => a + s.weight * s.value!, 0)) / wAvail);
  const verdict = score >= 75 ? "confiable" : score >= 50 ? "precaucion" : "riesgosa";
  return { ...base, score, verdict, redFlags: [] };
}

// ───────────────────────── Orquestación ─────────────────────────

export async function checkAccount(username: string, ext: ExternalInputs = {}): Promise<TrustResult> {
  const profile = await fetchProfile(username);
  if (!profile) {
    return { username, score: null, coverage: 0, verdict: "sin_datos",
      redFlags: [], reasons: [{ text: "No se encontró la cuenta", good: false }], signals: [] };
  }
  if (profile.isPrivate) {
    return { ...scoreProfile(profile, [], ext),
      reasons: [{ text: "Cuenta privada: un vendedor normalmente no oculta su perfil", good: false }] };
  }
  const urls = profile.videos.filter((v) => !v.isAd).slice(0, 3).map((v) => v.url).filter(Boolean) as string[];
  const comments = await fetchComments(urls, 30);
  return scoreProfile(profile, comments, ext);
}

// Ejemplo:
// checkAccount("tienda_ejemplo", { priceDeviation: -0.2, verifiedReports: 0, expectedRegion: "VE" })
//   .then((r) => console.log(JSON.stringify(r, null, 2)));
