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
