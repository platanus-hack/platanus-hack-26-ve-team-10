import type { MetadataRoute } from "next";
import { empresa } from "@/lib/empresa";

export default function sitemap(): MetadataRoute.Sitemap {
  return ["", "/privacidad", "/terminos"].map((path) => ({ url: `${empresa.sitio}${path}` }));
}
