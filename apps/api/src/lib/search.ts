import { formatMoney, toUsd, trustScore } from "./prices.js";
import { getRate } from "./rate.js";
import { sources } from "./sources/index.js";
import type { Merchant, Offer, SearchQuery } from "./types.js";

const SOURCE_TIMEOUT_MS = 8000;

export type OfferResult = {
  title: string;
  url: string;
  price: string | null; // tal cual lo publica el comercio
  priceUsd: number | null;
  rate: string | null; // tasa usada si hubo conversión
  seenAt: string;
  source: string;
  merchant: { name: string; channel: string; zone: string; delivers: boolean; trust: number };
};

export type SearchResponse = {
  query: string;
  notice?: string;
  failedSources: string[]; // fuentes que fallaron o tardaron demasiado: la búsqueda sigue sin ellas
  offers: OfferResult[]; // primero las que tienen precio, de menor a mayor en USD
};

const sameZone = (merchant: Merchant, zone?: string) =>
  !zone || merchant.zone.toLowerCase().includes(zone.toLowerCase());

// Único punto de búsqueda: lo usan el agente y MCP. Llama a todas las fuentes en paralelo.
export async function searchOffers(query: SearchQuery): Promise<SearchResponse> {
  const active = sources.filter((source) => source.enabled);
  const [rate, ...results] = await Promise.all([
    getRate(),
    ...active.map((source) => source.search(query, AbortSignal.timeout(SOURCE_TIMEOUT_MS)).catch(() => null)),
  ]);

  const failedSources = active.filter((_, i) => !results[i]).map((source) => source.id);
  const found = active.flatMap((source, i) => {
    const result = results[i];
    if (!result) return [];
    const merchants = new Map(result.merchants.map((m) => [m.id, m]));
    return result.offers.flatMap((offer: Offer) => {
      const merchant = merchants.get(offer.merchantId);
      return merchant ? [{ source: source.id, offer, merchant }] : [];
    });
  });

  const offers = found
    // Con envío vale cualquier comercio que envíe; sin envío, solo los de la zona.
    .filter(({ merchant }) => (query.needsDelivery ? merchant.delivers : sameZone(merchant, query.zone)))
    .map(({ source, offer, merchant }): OfferResult => ({
      title: offer.title,
      url: offer.url,
      price: offer.price ? formatMoney(offer.price) : null,
      priceUsd: offer.price ? toUsd(offer.price, rate) : null,
      rate: offer.price?.currency === "VES" ? `${rate.usdToVes} Bs/USD (${rate.source}, ${rate.observedAt})` : null,
      seenAt: offer.seenAt,
      source,
      merchant: { name: merchant.name, channel: merchant.channel, zone: merchant.zone, delivers: merchant.delivers, trust: trustScore(merchant) },
    }))
    .sort((a, b) => (a.priceUsd ?? Infinity) - (b.priceUsd ?? Infinity));

  return {
    query: query.text,
    notice: active.some((s) => s.id === "ejemplo") ? "Incluye datos de ejemplo: no todas las fuentes reales están conectadas." : undefined,
    failedSources,
    offers,
  };
}
