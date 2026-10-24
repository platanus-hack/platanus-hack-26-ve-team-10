import type { ExchangeRate, Merchant, Money } from "./types";

export function toUsd(price: Money, rate: ExchangeRate): number {
  const usd = price.currency === "USD" ? price.amount : price.amount / rate.usdToVes;
  return Math.round(usd * 100) / 100;
}

export function formatMoney({ amount, currency }: Money): string {
  return new Intl.NumberFormat("es-VE", { style: "currency", currency }).format(amount);
}

// Puntaje de 0 a 100. Fórmula inicial: ajustarla cuando tengamos datos reales.
export function trustScore(merchant: Merchant): number {
  let score = 40;
  if (merchant.followers) score += Math.min(25, Math.log10(merchant.followers) * 6);
  if (merchant.comments) score += Math.min(15, merchant.comments / 10);
  if (merchant.responseTimeMin !== undefined) {
    score += merchant.responseTimeMin <= 15 ? 20 : merchant.responseTimeMin <= 120 ? 10 : 0;
  }
  return Math.round(Math.min(100, score));
}
