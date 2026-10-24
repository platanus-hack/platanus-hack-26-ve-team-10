export type Currency = "USD" | "VES";

export type Money = { amount: number; currency: Currency };

export type ExchangeRate = {
  source: string; // de dónde salió la tasa: "BCV", "paralelo"...
  usdToVes: number;
  observedAt: string; // ISO 8601
};

export type Merchant = {
  id: string;
  name: string;
  channel: "instagram" | "tiktok" | "web" | "mercadolibre" | "facebook";
  url: string;
  zone: string;
  delivers: boolean;
  followers?: number;
  comments?: number; // comentarios recientes en sus publicaciones
  responseTimeMin?: number; // minutos en responder un mensaje
};

export type Offer = {
  merchantId: string;
  title: string; // como lo publica la fuente
  url: string;
  price: Money | null; // null cuando la fuente no publica el precio ("precio al DM")
  seenAt: string; // ISO 8601
};

// ── Contrato de las fuentes ─────────────────────────────────────────────────────────────
// Cada fuente (Firecrawl, Apify, Mercado Libre…) es un archivo en sources/ que exporta un
// Source y se registra en sources/index.ts. La búsqueda las llama en paralelo, junta lo que
// devuelven y se encarga de filtrar, convertir y ordenar: la fuente solo trae datos.

export type SearchQuery = {
  text: string; // lo que busca la persona, ej. "Harina PAN 1 kg"
  zone?: string;
  needsDelivery?: boolean;
};

export type SourceResult = {
  offers: Offer[];
  merchants: Merchant[]; // los comercios de esas ofertas; el id va con prefijo de la fuente, ej. "ig:bodegon"
};

export type Source = {
  id: string; // "firecrawl", "apify-instagram", "mercadolibre"…
  enabled: boolean; // normalmente: si su API key está en el entorno
  search(query: SearchQuery, signal: AbortSignal): Promise<SourceResult>;
};
