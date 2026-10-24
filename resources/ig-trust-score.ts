/**
 * IG Trust Score — puntaje de seguridad de una cuenta de Instagram usando Apify.
 *
 * Actores usados:
 *   - apify/instagram-profile-scraper  (perfil + últimos posts + "Información sobre esta cuenta")
 *   - apify/instagram-comment-scraper  (comentarios de los últimos posts)
 *
 * ⚠️ Los nombres exactos de los campos de input/output (sobre todo los del bloque "about")
 *    pueden variar entre versiones del actor. Haz una corrida en Apify Console con una
 *    cuenta conocida y ajusta `normalizeProfile()` a lo que realmente devuelve.
 *
 * npm i apify-client
 */
import { ApifyClient } from "apify-client";

const apify = new ApifyClient({ token: process.env.APIFY_TOKEN });

const PROFILE_ACTOR = "apify/instagram-profile-scraper";
const COMMENT_ACTOR = "apify/instagram-comment-scraper";

// ───────────────────────── Tipos ─────────────────────────

type Post = {
  likesCount?: number;
  commentsCount?: number;
  timestamp?: string;
  caption?: string;
  url?: string;
};

type Profile = {
  username: string;
  followers: number | null;
  postsCount: number | null;
  bio: string;
  externalUrl: string | null;
  isBusiness: boolean;
  isPrivate: boolean;
  dateJoined: Date | null;
  country: string | null;
  formerUsernames: number | null;
  posts: Post[];
};

type Comment = { text?: string; ownerUsername?: string };

/** Datos que vienen de Prais, no de Instagram. */
export type ExternalInputs = {
  /** Precio ofrecido vs. mediana de mercado: -0.35 = 35% más barato. null si no aplica. */
  priceDeviation?: number | null;
  /** Reportes verificados de estafa contra esta cuenta. */
  verifiedReports?: number;
  /** País esperado del vendedor (ISO o nombre como lo devuelve el actor). */
  expectedCountry?: string;
};

type Signal = {
  key: string;
  weight: number;
  value: number | null; // 0..1, null = sin dato
  reason?: string;      // texto para mostrar al usuario
  good?: boolean;
};

export type TrustResult = {
  username: string;
  score: number | null;       // 0..100, null si no hay datos suficientes
  coverage: number;           // 0..1, qué % del peso total se pudo medir
  verdict: "confiable" | "precaucion" | "riesgosa" | "sin_datos";
  redFlags: string[];
  reasons: { text: string; good: boolean }[];
  signals: Signal[];
};

// ───────────────────────── Fetch ─────────────────────────

export async function fetchProfile(username: string): Promise<Profile | null> {
  const run = await apify.actor(PROFILE_ACTOR).call({
    usernames: [username.replace(/^@/, "")],
    // Opción de pago del actor para "Información sobre esta cuenta".
    // Verifica el nombre exacto del campo en el input schema del actor.
    includeAboutSection: true,
  });
  const { items } = await apify.dataset(run.defaultDatasetId).listItems();
  return items[0] ? normalizeProfile(items[0] as any) : null;
}

export async function fetchComments(postUrls: string[], perPost = 30): Promise<Comment[]> {
  if (!postUrls.length) return [];
  const run = await apify.actor(COMMENT_ACTOR).call({ directUrls: postUrls, resultsLimit: perPost });
  const { items } = await apify.dataset(run.defaultDatasetId).listItems();
  return items as Comment[];
}

function normalizeProfile(raw: any): Profile {
  const about = raw.about ?? raw.aboutSection ?? {};
  const joined = about.dateJoined ?? about.date_joined ?? raw.dateJoined ?? null;
  const former = about.formerUsernames ?? about.former_usernames ?? raw.formerUsernames;
  return {
    username: raw.username,
    followers: raw.followersCount ?? null,
    postsCount: raw.postsCount ?? null,
    bio: raw.biography ?? "",
    externalUrl: raw.externalUrl ?? null,
    isBusiness: !!raw.isBusinessAccount,
    isPrivate: !!raw.private,
    dateJoined: joined ? parseLooseDate(joined) : null,
    country: about.country ?? about.accountBasedIn ?? null,
    formerUsernames: Array.isArray(former) ? former.length : typeof former === "number" ? former : null,
    posts: (raw.latestPosts ?? []) as Post[],
  };
}

/** Instagram a veces da "March 2019" en vez de una fecha ISO. */
function parseLooseDate(v: string): Date | null {
  const d = new Date(v);
  if (!isNaN(d.getTime())) return d;
  const d2 = new Date(`1 ${v}`);
  return isNaN(d2.getTime()) ? null : d2;
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

// Nota: "solo transferencia/Zelle/USDT/Binance" y "escríbeme al DM/WhatsApp" NO se usan:
// en Venezuela son prácticas normales en ventas legítimas y generarían falsos positivos.
const RISK_PATTERNS: [RegExp, string][] = [
  [/(sin|no hay|no se aceptan)\s+devoluci/i, "No acepta devoluciones"],
  [/(últimas?|ultimas?)\s+unidades|solo\s+(por\s+)?hoy|quedan\s+\d+/i, "Usa presión de urgencia"],
  [/(precio|oferta)\s+(de\s+)?(locura|regalado|remate)/i, "Precios 'demasiado buenos'"],
];

// ───────────────────────── Señales ─────────────────────────

function computeSignals(p: Profile, comments: Comment[], ext: ExternalInputs): Signal[] {
  const s: Signal[] = [];
  const likes = p.posts.map((x) => x.likesCount ?? 0);
  const comms = p.posts.map((x) => x.commentsCount ?? 0);
  const hasPosts = p.posts.length >= 3;

  // 1. Antigüedad (15): 0 si < 3 meses, 1 a los 36 meses, curva logarítmica.
  if (p.dateJoined) {
    const m = monthsSince(p.dateJoined);
    const v = m < 3 ? 0 : clamp(Math.log(m / 3) / Math.log(12));
    const yrs = (m / 12).toFixed(1);
    s.push({ key: "age", weight: 15, value: v, good: v >= 0.6,
      reason: v >= 0.6 ? `Cuenta con ${yrs} años` : `Cuenta reciente (${Math.round(m)} meses)` });
  } else s.push({ key: "age", weight: 15, value: null });

  // 2. Cambios de @ (5)
  if (p.formerUsernames != null) {
    const v = clamp(1 - p.formerUsernames / 3);
    s.push({ key: "username_changes", weight: 5, value: v, good: v === 1,
      reason: p.formerUsernames === 0 ? "Nunca cambió de nombre" : `Cambió de nombre ${p.formerUsernames} veces` });
  } else s.push({ key: "username_changes", weight: 5, value: null });

  // 3. País coherente (5)
  if (p.country && ext.expectedCountry) {
    const ok = p.country.toLowerCase().includes(ext.expectedCountry.toLowerCase());
    s.push({ key: "country", weight: 5, value: ok ? 1 : 0, good: ok,
      reason: ok ? `Cuenta registrada en ${p.country}` : `Cuenta registrada en ${p.country}, no en ${ext.expectedCountry}` });
  } else s.push({ key: "country", weight: 5, value: null });

  // 4. Engagement relativo (15): banda sana ~0.5%–8% (más estrecha en cuentas grandes).
  if (hasPosts && p.followers && p.followers > 0) {
    const er = median(likes.map((l, i) => l + comms[i])) / p.followers;
    const hi = p.followers > 100_000 ? 0.05 : 0.08;
    let v: number;
    if (er < 0.001) v = 0;
    else if (er < 0.005) v = (er - 0.001) / 0.004;
    else if (er <= hi) v = 1;
    else v = clamp(1 - (er - hi) / 0.15); // engagement irrealmente alto también es raro
    s.push({ key: "engagement", weight: 15, value: v, good: v >= 0.7,
      reason: v >= 0.7 ? "Interacción acorde a sus seguidores"
        : er < 0.005 ? `Muy poca interacción para ${p.followers.toLocaleString()} seguidores (posibles seguidores comprados)`
        : "Interacción inusualmente alta (posibles likes comprados)" });
  } else s.push({ key: "engagement", weight: 15, value: null });

  // 5. Consistencia de likes entre posts (10): coeficiente de variación.
  if (hasPosts && mean(likes) > 0) {
    const cv = stdev(likes) / mean(likes);
    const v = clamp(1 - (cv - 0.6) / 1.4); // cv<=0.6 → 1, cv>=2 → 0
    s.push({ key: "consistency", weight: 10, value: v, good: v >= 0.6,
      reason: v >= 0.6 ? undefined : "Likes con picos irregulares entre posts" });
  } else s.push({ key: "consistency", weight: 10, value: null });

  // 6. Ratio comentarios/likes (5): comprar likes es barato, comentarios creíbles no.
  if (hasPosts && mean(likes) > 20) {
    const r = mean(comms) / mean(likes);
    const v = clamp(r / 0.02); // >=2% → 1
    s.push({ key: "comment_like_ratio", weight: 5, value: v, good: v >= 0.6,
      reason: v < 0.3 ? "Muchos likes pero casi ningún comentario" : undefined });
  } else s.push({ key: "comment_like_ratio", weight: 5, value: null });

  // 7. Regularidad al publicar (5): penaliza ráfagas (muchos posts el mismo día).
  const days = p.posts.map((x) => x.timestamp?.slice(0, 10)).filter(Boolean) as string[];
  if (days.length >= 5) {
    const counts = Object.values(days.reduce<Record<string, number>>((a, d) => ((a[d] = (a[d] ?? 0) + 1), a), {}));
    const burst = Math.max(...counts) / days.length;
    const v = clamp(1 - (burst - 0.25) / 0.5);
    s.push({ key: "posting_rhythm", weight: 5, value: v, good: v >= 0.6,
      reason: v < 0.5 ? "Gran parte de los posts se subieron el mismo día" : undefined });
  } else s.push({ key: "posting_rhythm", weight: 5, value: null });

  // 8. Calidad de comentarios (10): texto real + diversidad de autores.
  const real = comments.filter((c) => c.text && c.text.trim().split(/\s+/).length > 3
    && !/^[\p{Emoji}\s!.]+$/u.test(c.text));
  if (comments.length >= 10) {
    const realPct = real.length / comments.length;
    const authors = new Set(comments.map((c) => c.ownerUsername)).size / comments.length;
    // ≥40% comentarios con texto real → 1 ; ≥70% autores únicos → 1
    const v = 0.7 * clamp(realPct / 0.4) + 0.3 * clamp(authors / 0.7);
    s.push({ key: "comment_quality", weight: 10, value: clamp(v), good: v >= 0.6,
      reason: v >= 0.6 ? "Comentarios de personas reales y variadas" : "Comentarios genéricos o repetidos" });
  } else s.push({ key: "comment_quality", weight: 10, value: null });

  // 9. Lenguaje de riesgo en bio y captions (10).
  const text = [p.bio, ...p.posts.map((x) => x.caption ?? "")].join("\n");
  const hits = RISK_PATTERNS.filter(([re]) => re.test(text)).map(([, label]) => label);
  s.push({ key: "risk_language", weight: 10, value: clamp(1 - hits.length / 3), good: hits.length === 0,
    reason: hits.length ? hits.join(" · ") : undefined });

  // 10. Precio vs. mercado (15) — dato de Prais.
  if (ext.priceDeviation != null) {
    const d = ext.priceDeviation; // negativo = más barato
    const v = d >= -0.15 ? 1 : clamp(1 - (-d - 0.15) / 0.3); // -15% ok, -45% → 0
    s.push({ key: "price_anomaly", weight: 15, value: v, good: v === 1,
      reason: v < 1 ? `Precio ${Math.round(-d * 100)}% bajo el mercado` : "Precio en línea con el mercado" });
  } else s.push({ key: "price_anomaly", weight: 15, value: null });

  // 11. Reportes de usuarios (5) — crecerá en peso cuando haya volumen.
  if (ext.verifiedReports != null) {
    const v = clamp(1 - ext.verifiedReports / 3);
    s.push({ key: "reports", weight: 5, value: v, good: v === 1,
      reason: ext.verifiedReports ? `${ext.verifiedReports} reporte(s) de estafa verificados` : undefined });
  } else s.push({ key: "reports", weight: 5, value: null });

  return s;
}

function redFlags(p: Profile, ext: ExternalInputs): string[] {
  const f: string[] = [];
  if (ext.priceDeviation != null && ext.priceDeviation <= -0.5) f.push("Precio más de 50% bajo el mercado");
  if (p.dateJoined && monthsSince(p.dateJoined) < 1) f.push("Cuenta creada hace menos de un mes");
  if ((p.formerUsernames ?? 0) >= 4) f.push("Cambió de nombre 4 o más veces");
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
    .sort((a, b) => b.weight * (1 - (b.value ?? 1)) - a.weight * (1 - (a.value ?? 1))) // lo más grave primero
    .map((s) => ({ text: s.reason!, good: !!s.good }));

  if (flags.length) {
    return { username: p.username, score: 0, coverage, verdict: "riesgosa", redFlags: flags, reasons, signals };
  }
  if (coverage < MIN_COVERAGE) {
    return { username: p.username, score: null, coverage, verdict: "sin_datos", redFlags: [], reasons, signals };
  }

  const score = Math.round((100 * avail.reduce((a, s) => a + s.weight * s.value!, 0)) / wAvail);
  const verdict = score >= 75 ? "confiable" : score >= 50 ? "precaucion" : "riesgosa";
  return { username: p.username, score, coverage, verdict, redFlags: [], reasons, signals };
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
  // Comentarios solo de los 3 posts más recientes para controlar costo.
  const urls = profile.posts.slice(0, 3).map((x) => x.url).filter(Boolean) as string[];
  const comments = await fetchComments(urls, 30);
  return scoreProfile(profile, comments, ext);
}

// Ejemplo:
// checkAccount("tienda_ejemplo", { priceDeviation: -0.38, verifiedReports: 0, expectedCountry: "Venezuela" })
//   .then((r) => console.log(JSON.stringify(r, null, 2)));
