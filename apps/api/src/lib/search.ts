import { exampleRate, merchants, offers } from "./mock-data.js";
import { formatMoney, toUsd, trustScore } from "./prices.js";

export type SearchOptions = { zone?: string; needsDelivery?: boolean };

export type OfferResult = {
  title: string;
  url: string;
  price: string | null; // tal cual lo publica el comercio
  priceUsd: number | null;
  rate: string | null; // tasa usada si hubo conversión
  seenAt: string;
  merchant: { name: string; channel: string; zone: string; delivers: boolean; trust: number };
};

export type SearchResponse = {
  query: string;
  notice: string;
  offers: OfferResult[]; // ordenadas: primero las que tienen precio, de menor a mayor en USD
};

const normalize = (text: string) =>
  text.normalize("NFD").replace(/\p{Diacritic}/gu, "").replace(/[^a-z0-9 ]/gi, "").toLowerCase();

// Hoy busca en los datos de ejemplo. Aquí es donde se conectan Firecrawl, Apify y Mercado Libre.
export function searchOffers(query: string, { zone, needsDelivery }: SearchOptions = {}): SearchResponse {
  const words = normalize(query).split(/\s+/).filter((word) => word.length >= 3);

  const results = offers
    .filter((offer) => {
      const title = normalize(offer.title).replace(/ /g, "");
      return words.every((word) => title.includes(word));
    })
    .flatMap((offer): OfferResult[] => {
      const merchant = merchants.find((m) => m.id === offer.merchantId);
      if (!merchant) return [];
      const sameZone = !zone || normalize(merchant.zone).includes(normalize(zone));
      if (!sameZone && !(needsDelivery && merchant.delivers)) return [];
      if (needsDelivery && !merchant.delivers) return [];
      return [
        {
          title: offer.title,
          url: offer.url,
          price: offer.price ? formatMoney(offer.price) : null,
          priceUsd: offer.price ? toUsd(offer.price, exampleRate) : null,
          rate:
            offer.price?.currency === "VES"
              ? `${exampleRate.usdToVes} Bs/USD (${exampleRate.source}, ${exampleRate.observedAt})`
              : null,
          seenAt: offer.seenAt,
          merchant: {
            name: merchant.name,
            channel: merchant.channel,
            zone: merchant.zone,
            delivers: merchant.delivers,
            trust: trustScore(merchant),
          },
        },
      ];
    })
    .sort((a, b) => (a.priceUsd ?? Infinity) - (b.priceUsd ?? Infinity));

  return {
    query,
    notice: "Datos de ejemplo: todavía no hay fuentes reales conectadas.",
    offers: results,
  };
}
