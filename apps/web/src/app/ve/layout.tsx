// Páginas del catálogo de Venezuela. Todas se generan estáticas (y se revalidan con el cache de
// lib/catalogo.ts): un crawler tiene que ver los precios en el HTML (agents/seo-geo.md).
export const ensureStatic = "navigation";

export default function CatalogoLayout({ children }: LayoutProps<"/ve">) {
  return children;
}
