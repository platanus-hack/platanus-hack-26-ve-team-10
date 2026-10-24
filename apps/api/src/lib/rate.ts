import type { ExchangeRate } from "./types.js";

// Tasa con la que se convierten los precios en bolívares a USD.
// Pendiente: traer la tasa real (BCV, paralela o ambas: decisión abierta en agents/architecture.md).
export async function getRate(): Promise<ExchangeRate> {
  return { source: "tasa de ejemplo", usdToVes: 200, observedAt: "2026-10-24T08:00:00-04:00" };
}
