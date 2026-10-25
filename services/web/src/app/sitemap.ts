import type { MetadataRoute } from "next";
import { getSitemap } from "@/lib/catalogo";
import { empresa } from "@/lib/empresa";
import { guias } from "@/lib/guias";

// Páginas del catálogo: solo las indexables, es decir, con ofertas de fuentes reales (services/api/app/lib/catalogo.py).
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const rutas = ["", ...guias.map((g) => `/${g.slug}`), "/ve/marcas", "/privacidad", "/terminos"];
  const paginas = (await getSitemap()) ?? [];
  return [
    ...rutas.map((ruta) => ({ url: `${empresa.sitio}${ruta}` })),
    ...paginas.map((p) => ({ url: `${empresa.sitio}${p.url}`, lastModified: p.actualizado ?? undefined })),
  ];
}
