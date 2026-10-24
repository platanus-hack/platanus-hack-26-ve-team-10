# Agente: apps/agent y packages/core

El agente hace la búsqueda inteligente. Está hecho con [ADK para TypeScript](https://github.com/google/adk-js) (`@google/adk`) y usa Gemini en Vertex AI. La lógica que no necesita un modelo vive en `packages/core`, y el agente la usa como tools.

## Orquestador y sub-agentes

La pizarra tiene un agente central con tres sub-agentes. Esta es la propuesta para los tres, que coincide con lo que la pizarra pide en el onboarding y en la confianza:

| Agente | Qué hace | Tools |
|---|---|---|
| `prais` (orquestador) | Recibe la consulta, delega y arma la respuesta final | Los tres sub-agentes |
| `onboarding` | Junta lo que falta para buscar bien: zona, si necesita envío, características del producto. Recuerda lo que el usuario ya dijo | Leer y guardar el perfil del usuario |
| `search` | Busca ofertas: primero en el índice, después en vivo si hace falta | `searchIndex`, `searchLive`, `convertCurrency`, `rankOffers` |
| `trust` | Califica a cada comercio y decide si un resultado necesita revisión humana | `getMerchantTrust`, `openReviewCase` |

Si el equipo los define distinto, cambia esta tabla primero.

## Reparto entre core y el agente

| Va en `packages/core` | Va en `apps/agent` |
|---|---|
| Tipos: `Offer`, `Merchant`, `TrustScore`, `SearchResult` | Entender la consulta y decidir qué preguntar |
| Adapters de fuentes ([sources.md](sources.md)) | Decidir cuándo buscar en vivo |
| Conversión de monedas con la tasa registrada | Explicar por qué una oferta es la mejor |
| Ranking de ofertas | Decidir cuándo abrir un caso en el human loop |
| Puntaje de confianza | El servidor HTTP `POST /search` |
| Formateo de precios | |

Regla práctica: si se puede probar con un test sin llamar a un modelo, va en core.

## Estructura

```
packages/core/src/
  types.ts
  money.ts              Conversión y formateo
  rank.ts               Mejor precio en general
  trust.ts              Puntaje de confianza del comercio
  sources/              Un adapter por fuente
apps/agent/src/
  agent.ts              Orquestador (rootAgent)
  agents/               onboarding.ts, search.ts, trust.ts
  tools/                Tools finas sobre core
  server.ts             POST /search → SearchResult
  .env.example
```

## Reglas del agente

1. **No inventa precios.** Todo precio de la respuesta sale de una tool. Si no hay resultados, lo dice.
2. **Cita.** Cada oferta de la respuesta trae su fuente, su fecha, su enlace y el puntaje del comercio.
3. **Convierte con core.** El modelo nunca hace cuentas de moneda.
4. **Pregunta una sola cosa a la vez.** Si le falta un dato, devuelve `kind: "question"` con una pregunta concreta.
5. **Si duda, escala.** Un precio que no puede confirmar o un comercio con poca confianza abren un caso en el human loop. Mientras tanto, el agente le avisa al usuario.
6. **Contesta en español de Venezuela**, con un tono breve y directo.

## Desarrollo

- `@google/adk` va por la versión 2.x (2.3.0 al 2026-10-24). Fija la versión exacta.
- Usa zod 4, la misma versión de la que depende ADK.
- En local, el modelo puede usar una API key de Google AI Studio en `.env`. En Cloud Run usa Vertex AI con la cuenta de servicio. El README de adk-js explica las dos configuraciones.
- Para empezar, el modelo es `gemini-flash-latest`.

```bash
npx @google/adk-devtools web                # UI de desarrollo
npx @google/adk-devtools run src/agent.ts   # Probar en la terminal
```

Siempre escribe el nombre completo del paquete en `npx`. Un `npx adk` a secas descarga un paquete que no tiene nada que ver.

Las consultas de ejemplo para probar el agente van en `resources/`. Cuando cambies un prompt o una tool, córrelas otra vez.

## Deploy

Es un servicio de Cloud Run, privado: solo lo invocan las otras apps con sus cuentas de servicio. Ver [gcp.md](gcp.md).
