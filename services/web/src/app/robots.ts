import type { MetadataRoute } from "next";
import { empresa } from "@/lib/empresa";

// Dejamos pasar a los crawlers de IA a propósito: queremos que nos citen (docs/seo-geo.md).
const crawlersDeIA = [
  "GPTBot",
  "OAI-SearchBot",
  "ChatGPT-User",
  "ClaudeBot",
  "Claude-SearchBot",
  "Claude-User",
  "PerplexityBot",
  "Perplexity-User",
  "Google-Extended",
  "Applebot-Extended",
];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      { userAgent: "*", allow: "/", disallow: "/api/" },
      { userAgent: crawlersDeIA, allow: "/", disallow: "/api/" },
    ],
    sitemap: `${empresa.sitio}/sitemap.xml`,
  };
}
