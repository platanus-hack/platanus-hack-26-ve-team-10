// Formato venezolano (docs/design-system/README.md): punto de miles, coma decimal, sin ",00" en dólares.
// Solo da formato a lo que manda la API: no calcula precios.
export function usd(n: number) {
  const entero = Number.isInteger(n);
  return `$${n.toLocaleString("es-VE", { minimumFractionDigits: entero ? 0 : 2, maximumFractionDigits: 2 })}`;
}

export function bs(n: number) {
  return `Bs. ${n.toLocaleString("es-VE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// Canal de venta tal como lo nombra la gente (sin logos: docs/design-system/README.md).
export const CANALES: Record<string, string> = {
  web: "Web",
  instagram: "Instagram",
  mercadolibre: "Mercado Libre",
  facebook: "Marketplace",
  tiktok: "TikTok",
};

export function fecha(iso: string | null | undefined) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("es-VE", { day: "numeric", month: "long", timeZone: "America/Caracas" });
}
