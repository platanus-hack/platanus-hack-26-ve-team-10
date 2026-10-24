import type { MetadataRoute } from "next";
import { empresa } from "@/lib/empresa";

// Dejamos pasar a los crawlers de IA a propósito: queremos que nos citen (agents/seo-geo.md).
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      { userAgent: "*", allow: "/", disallow: "/api/" },
      { userAgent: ["GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"], allow: "/" },
    ],
    sitemap: `${empresa.sitio}/sitemap.xml`,
  };
}
