# Prais

<img src="./project-logo.png" alt="Prais" width="200" />

Prais encuentra el producto exacto que buscas en los principales canales de venta de Venezuela, compara lo que cobra cada vendedor para que nunca pagues de más y le da a cada comercio un puntaje de confianza. Como paso de apoyo, convierte los precios entre dólares y bolívares para compararlos en una misma moneda.

Pruébalo en [usaprais.com](https://usaprais.com).

> **Estado actual:** Prais corre con datos de ejemplo. La única fuente registrada hoy es `apps/api/src/lib/sources/mock.ts`, con comercios y precios inventados; las fuentes reales se suman en `apps/api/src/lib/sources/`.

## Stack

- **Web** (`apps/web`): Next.js 16, React 19, Tailwind CSS 4 y TypeScript, con un chat web.
- **API** (`apps/api`): Fastify y TypeScript, con un agente de Google ADK (Gemini). Expone `POST /chat`, `POST /whatsapp` (WhatsApp vía Kapso) y `/mcp` (endpoint MCP).
- Monorepo con pnpm.

## Correr en local

```bash
pnpm install
cp apps/api/.env.example apps/api/.env   # pon GOOGLE_GENAI_API_KEY
cp apps/web/.env.example apps/web/.env   # API_URL apunta a la API (puerto 4000)
pnpm dev                                 # api en :4000, web en :3000
```

Variables de `apps/api/.env.example`: `GOOGLE_GENAI_API_KEY`, `KAPSO_API_KEY` y `KAPSO_WEBHOOK_SECRET` (WhatsApp), y opcionales `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `PRAIS_MODEL`, `FIRECRAWL_API_KEY`, `APIFY_TOKEN`, `USE_MOCK_SOURCE`. En `apps/web/.env.example`: `API_URL`.

Otros scripts: `pnpm build`, `pnpm lint`.

## Equipo

Platanus Hack 26: Caracas · Track: 🤝 Trust · team-10

- Jose Leonardo Moreno ([@Pleo2](https://github.com/Pleo2))
- Enrique Uzcategui ([@enriqueuz](https://github.com/enriqueuz))
- Roybert Parada ([@roybertparada](https://github.com/roybertparada))
- Diego Gallovich ([@diegogallovich](https://github.com/diegogallovich))
- Genaro Villegas ([@colarussozz](https://github.com/colarussozz))
