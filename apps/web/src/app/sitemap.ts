import type { MetadataRoute } from "next";
import { empresa } from "@/lib/empresa";
import { guias } from "@/lib/guias";

export default function sitemap(): MetadataRoute.Sitemap {
  const rutas = ["", ...guias.map((g) => `/${g.slug}`), "/privacidad", "/terminos"];
  return rutas.map((ruta) => ({ url: `${empresa.sitio}${ruta}` }));
}
