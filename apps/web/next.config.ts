import type { NextConfig } from "next";

// El backend (apps/api, Fastify) vive aparte: /api/* se reenvía a él, así el navegador
// habla con el mismo dominio y no hace falta CORS.
const apiUrl = process.env.API_URL ?? "http://localhost:4000";

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  // API_URL solo existe al construir (Dockerfile): se fija aquí para que lib/catalogo.ts la tenga
  // también al revalidar o generar páginas en Cloud Run. Es la URL pública del backend, no un secreto.
  env: { API_URL: apiUrl },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
  async redirects() {
    return [{ source: "/ve/marca", destination: "/ve/marcas", permanent: true }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
