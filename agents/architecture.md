# Arquitectura

Prais tiene un cerebro, varias fuentes y varios canales. La ingesta recorre las fuentes y llena un índice de precios y comercios. El agente responde con ese índice y, cuando hace falta, busca en vivo. La web, WhatsApp y MCP son formas distintas de preguntarle al agente. Todo corre en Google Cloud.

```
FUENTES   Firecrawl · Apify (Instagram, TikTok, FB Marketplace) · Mercado Libre · Meta Ads
                                          │
                                          ▼
                                apps/ingest (Cloud Run Jobs + Cloud Scheduler)
                                          │ escribe
                                          ▼
                                Índice de precios y comercios
                                          ▲ lee
CANALES                                   │
WhatsApp ─► Kapso ─► apps/whatsapp ─┐     │
Instagram (por definir) ────────────┤     │
Web: directorio + chat ─► apps/web ─┼─► apps/agent (ADK): orquestador "prais"
ChatGPT / Claude ─► apps/mcp ───────┘    ├─ onboarding: zona, envío, características del producto
                                         ├─ búsqueda: índice + búsqueda en vivo
                                         └─ confianza: seguidores, comentarios, tiempo de respuesta, benchmarks
                                          │
                                          ▼
                                Human loop: el equipo revisa en el admin lo que el agente no puede confirmar
```

## Componentes

| Componente | Responsabilidad | Doc |
|---|---|---|
| `apps/ingest` | Recorre las fuentes cada cierto tiempo, normaliza lo que encuentra y lo guarda en el índice. | [sources.md](sources.md) |
| `apps/agent` | Orquestador con tres sub-agentes: onboarding, búsqueda y confianza. Expone `POST /search`. | [adk.md](adk.md) |
| `packages/core` | Tipos compartidos, adapters de fuentes, conversión de monedas, ranking de ofertas y puntaje de confianza. No depende de ningún framework. | [adk.md](adk.md), [sources.md](sources.md) |
| `apps/web` | Landing y blog (SEO/GEO), directorio de comercios y productos, chat con el agente, dashboard del usuario y admin del equipo, con la cola del human loop. | [web.md](web.md), [seo-geo.md](seo-geo.md) |
| `apps/whatsapp` | Recibe mensajes de Kapso, le pregunta al agente y responde por WhatsApp. | [kapso.md](kapso.md) |
| `apps/mcp` | Expone la búsqueda como tools de MCP para otros asistentes. | [mcp-tool.md](mcp-tool.md) |
| Infraestructura | Cloud Run, Cloud Build, Secret Manager, Vertex AI, Cloud Tasks y Cloud Scheduler. | [gcp.md](gcp.md) |

## El flujo de una consulta

1. **Onboarding.** Si falta algo para buscar bien, el agente lo pregunta: zona, si necesita envío, características del producto. Lo que ya sabe del usuario no lo vuelve a preguntar.
2. **Búsqueda.** Primero busca en el índice. Si no hay resultados recientes, busca en vivo con las fuentes rápidas.
3. **Confianza.** A cada comercio le calcula un puntaje con seguidores, comentarios, tiempo de respuesta y benchmarks.
4. **Respuesta.** Devuelve el mejor precio en general con su fuente, su fecha y el puntaje del comercio, y explica por qué.
5. **Human loop.** Si no puede confirmar un precio (por ejemplo, "precio al DM") o tiene poca confianza en el resultado, crea un caso en el admin. El equipo lo resuelve, y la respuesta del comercio también sirve para medir su tiempo de respuesta.

## Contrato entre apps

Las apps solo hablan con el agente por `POST /search`. Los tipos viven en `packages/core`:

```ts
// packages/core: forma inicial, se ajusta en el PR que la implemente
type Money = { amount: number; currency: "USD" | "VES" };

type ExchangeRate = {
  source: "BCV" | "paralelo" | string; // de dónde salió la tasa
  usdToVes: number;
  observedAt: string; // ISO 8601
};

type Merchant = {
  id: string;
  name: string;
  channels: { kind: "instagram" | "tiktok" | "web" | "mercadolibre" | "facebook"; url: string }[];
  zone?: string;
  delivers?: boolean;
  trust: TrustScore;
};

type TrustScore = {
  score: number;           // 0 a 100
  followers?: number;
  comments?: number;       // comentarios recientes en sus publicaciones
  responseTimeMin?: number; // minutos en responder, medido en el human loop
  benchmarks?: string[];   // señales extra: antigüedad, reseñas, verificación
  computedAt: string;
};

type Offer = {
  sourceId: string;          // id del adapter de la fuente
  merchantId?: string;
  title: string;             // como lo publica la fuente
  url: string;
  price: Money | null;       // null si la fuente no publica el precio ("precio al DM")
  priceUsd: Money | null;    // precio normalizado para comparar
  rateUsed?: ExchangeRate;   // solo si hubo conversión
  available: boolean;
  seenAt: string;            // ISO 8601
};

type SearchRequest = {
  query: string;
  channel: "web" | "whatsapp" | "instagram" | "mcp";
  userId?: string;           // para recordar zona y preferencias
};

type SearchResult =
  | { kind: "question"; question: string }  // al agente le falta un dato
  | {
      kind: "result";
      query: string;
      best: Offer | null;
      offers: Offer[];
      merchants: Record<string, Merchant>;
      failedSources: string[]; // fuentes que no respondieron: la búsqueda sigue
      pendingReview: boolean;  // se abrió un caso en el human loop
      explanation: string;     // por qué esa es la mejor opción
      searchedAt: string;
    };
```

"Mejor precio en general" significa, por ahora, la oferta disponible con el menor `priceUsd` entre comercios con un puntaje de confianza mínimo. El umbral y el peso del envío se definen en `packages/core/rank.ts` y en este doc.

## Deploy

Todo corre en Google Cloud: los detalles están en [gcp.md](gcp.md). Cloud Build se conecta a `Pleo2/prais.com`, que se sincroniza cada 5 minutos con `main` de la org.

| App | Servicio | Dominio |
|---|---|---|
| `apps/web` | Cloud Run | usaprais.com |
| `apps/agent` | Cloud Run | api.usaprais.com |
| `apps/whatsapp` | Cloud Run | wa.usaprais.com |
| `apps/mcp` | Cloud Run | mcp.usaprais.com |
| `apps/ingest` | Cloud Run Jobs, disparados por Cloud Scheduler | — |

## Decisiones tomadas (2026-10-24)

- Monorepo con pnpm workspaces, todo en TypeScript.
- Infraestructura en Google Cloud. Cloudflare solo maneja el DNS de usaprais.com.
- Agentes con ADK para TypeScript (`@google/adk`) y Gemini en Vertex AI.
- Un orquestador con sub-agentes, como en la pizarra.
- Fuentes: Firecrawl, Apify (Instagram, TikTok, Facebook Marketplace), Mercado Libre y Meta Ads.
- La web es una sola app de Next.js con landing, blog, directorio, chat, dashboard y admin.
- El canal de WhatsApp va por Kapso.
- Hay ingesta por lotes y búsqueda en vivo, porque los scrapers son demasiado lentos para responder en cada consulta.
- Las reglas para construir viven en `agents/`, con un doc por área, y `AGENTS.md` es el índice.

## Decisiones abiertas

1. **Base de datos del índice.** Firestore (sin esquema, más rápido para empezar) o Cloud SQL con Postgres (mejor para historial de precios y consultas). Ver [gcp.md](gcp.md).
2. **Tasa de referencia.** Si comparamos con la tasa del BCV, la paralela o ambas, y de dónde la sacamos.
3. **Los tres sub-agentes.** En la pizarra no tienen nombre. La propuesta de [adk.md](adk.md) es onboarding, búsqueda y confianza.
4. **Instagram como canal.** Responder DMs exige la API de mensajería de Instagram y que Meta revise la app. Probablemente no entra en la hackathon.
5. **Fórmula de confianza.** Cuánto pesa cada señal, y qué son exactamente los "benchmarks".
6. **Auth** del dashboard y del admin.

Cuando una decisión se cierre, pásala a "Decisiones tomadas". Si tiene matices, escribe un registro en `docs/decisions/`.
