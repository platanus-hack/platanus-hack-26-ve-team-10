import type { ExchangeRate, Merchant, Offer } from "./types";

// Datos de ejemplo para probar el flujo completo mientras conectamos las fuentes reales.
// Los comercios y los precios son inventados.

export const exampleRate: ExchangeRate = {
  source: "tasa de ejemplo",
  usdToVes: 200,
  observedAt: "2026-10-24T08:00:00-04:00",
};

export const merchants: Merchant[] = [
  {
    id: "bodegon-la-esquina",
    name: "Bodegón La Esquina (ejemplo)",
    channel: "instagram",
    url: "https://instagram.com/ejemplo_bodegon",
    zone: "Caracas",
    delivers: true,
    followers: 18500,
    comments: 120,
    responseTimeMin: 10,
  },
  {
    id: "mercado-express",
    name: "Mercado Express (ejemplo)",
    channel: "web",
    url: "https://example.com/mercado-express",
    zone: "Caracas",
    delivers: true,
    followers: 4200,
    comments: 35,
    responseTimeMin: 60,
  },
  {
    id: "tienda-maracaibo",
    name: "Tienda Maracaibo (ejemplo)",
    channel: "mercadolibre",
    url: "https://example.com/tienda-maracaibo",
    zone: "Maracaibo",
    delivers: false,
    followers: 900,
    comments: 8,
  },
  {
    id: "ventas-tiktok",
    name: "Ofertas VE (ejemplo)",
    channel: "tiktok",
    url: "https://tiktok.com/@ejemplo_ofertas",
    zone: "Valencia",
    delivers: true,
    followers: 52000,
    comments: 400,
    responseTimeMin: 240,
  },
];

const seenAt = "2026-10-24T09:00:00-04:00";

export const offers: Offer[] = [
  { merchantId: "bodegon-la-esquina", title: "Harina PAN 1 kg", url: "https://instagram.com/p/ejemplo1", price: { amount: 1.35, currency: "USD" }, seenAt },
  { merchantId: "mercado-express", title: "Harina P.A.N. maíz blanco 1kg", url: "https://example.com/p/harina-pan", price: { amount: 250, currency: "VES" }, seenAt },
  { merchantId: "tienda-maracaibo", title: "Harina Pan 1 kilo", url: "https://example.com/ml/harina-pan", price: { amount: 1.1, currency: "USD" }, seenAt },
  { merchantId: "ventas-tiktok", title: "Harina PAN 1kg (bulto de 20)", url: "https://tiktok.com/@ejemplo_ofertas/video/1", price: null, seenAt },
  { merchantId: "bodegon-la-esquina", title: "Aceite Diana 1 litro", url: "https://instagram.com/p/ejemplo2", price: { amount: 3.2, currency: "USD" }, seenAt },
  { merchantId: "mercado-express", title: "Aceite Diana 1L", url: "https://example.com/p/aceite-diana", price: { amount: 610, currency: "VES" }, seenAt },
  { merchantId: "ventas-tiktok", title: "iPhone 15 128 GB", url: "https://tiktok.com/@ejemplo_ofertas/video/2", price: { amount: 690, currency: "USD" }, seenAt },
  { merchantId: "tienda-maracaibo", title: "iPhone 15 128GB nuevo", url: "https://example.com/ml/iphone-15", price: { amount: 720, currency: "USD" }, seenAt },
];
