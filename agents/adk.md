# Agente con ADK

El agente vive en `apps/api/app/agent.py` y usa [ADK para Python](https://adk.dev) (`google-adk` 2.13.0).

## Cómo está armado

- `root_agent` (`app/agents/orchestrator.py`): el orquestador. Entiende qué producto o servicio quiere comparar la persona. Cuando lo sabe, llama a cada especialista y le pasa ese producto. Después resume los hallazgos. Es el único que habla con la persona. `ask_prais` corre este agente.
- Seis especialistas (`app/agents/specialists.py`), uno por fuente de la pizarra: web abierta, Meta Ad Library, Mercado Libre, Facebook Marketplace, Instagram y TikTok. El orquestador los llama con `AgentTool`. Cada uno corre en su propia sesión y devuelve un informe corto. Ese texto no entra al chat de la persona: solo lo lee el orquestador, que es quien responde.
- La instrucción de cada especialista sale de una plantilla: busca ofertas en su fuente, mira la fidelidad del vendedor y reporta solo al orquestador (`root-agent`). El producto le llega en el argumento `product`.
- Cada especialista, salvo la web abierta, tiene una tool que llama a `search_offers` y se queda con las ofertas de su canal. La web abierta llama a Firecrawl (`app/lib/sources/firecrawl.py`): busca el producto en Venezuela y lee el precio publicado de hasta 3 páginas. La confianza del vendedor es `merchant.trust`, la fórmula de `app/lib/prices.py`; en la web abierta todavía no hay puntaje. No hay un puntaje aparte para el precio, y la respuesta no dice que falte. Meta Ad Library todavía no tiene fuente: su tool devuelve cero ofertas.
- `ask_prais(user_id, message)`: corre el orquestador con un `Runner` y devuelve el texto de la respuesta. Cada `user_id` tiene su propia conversación (`web:<id>`, `whatsapp:<número>`), así que el orquestador recuerda lo que ya preguntó.
- Las sesiones están en memoria (`InMemorySessionService`).

## Reglas

1. **No inventa nada.** Precios, tiendas, tasas, puntajes y cualquier explicación salen de una tool. Si la persona pregunta algo que las tools no dicen, Prais dice que no lo sabe. Si la oferta es de ejemplo (`example: true` o el comercio se llama "(ejemplo)"), lo dice y no la presenta como real.
2. **Una pregunta a la vez** cuando le falta un dato.
3. **Habla como Prais.** La voz y los límites del personaje están en `docs/design-system/prais.md`; las instrucciones del agente los resumen. Si cambia el personaje, cambian las dos cosas.
4. **Las cuentas las hace el código**, no el modelo: conversión de moneda, orden y confianza están en `apps/api/app/lib`.

## Agregar una tool

Una tool de especialista va en `apps/api/app/agents/specialists.py`, en el especialista de esa fuente. Si la tool toca una fuente o hace cálculos, la lógica va en `apps/api/app/lib` y la tool queda como una llamada fina.

## Modelos

El modelo se elige con `PRAIS_MODEL`. En local el valor por defecto del código es `gemini-flash-latest` (AI Studio). En Vertex, Cloud Run incluido, se fija `gemini-3.8-flash`, el Flash más nuevo que responde en `global`. ADK acepta cualquier nombre que encaje con estos patrones.

| Patrón | Qué es |
|---|---|
| `gemini-*` | Cualquier Gemini, por Google AI Studio o por Vertex AI. Por ejemplo, `gemini-3.8-flash` o `gemini-flash-latest` |
| `projects/.../endpoints/...` | Un Gemini afinado, publicado en un endpoint de Vertex AI |
| `projects/.../publishers/google/models/gemini...` | Un Gemini de Vertex con el nombre largo |

**Ojo en Vertex.** El alias `gemini-flash-latest` no existe ahí, y los Gemini 2.5 ya no están disponibles para el proyecto (404). Los vigentes (3.x) viven en la ubicación `global`, no en `us-east1`. Cloud Run usa `GOOGLE_CLOUD_LOCATION=global` y `PRAIS_MODEL=gemini-3.8-flash`. Para ver qué responde: `curl -H "Authorization: Bearer $(gcloud auth print-access-token)" -H "x-goog-user-project: prais-app" https://aiplatform.googleapis.com/v1beta1/publishers/google/models`.

**Otros proveedores y modelos abiertos.** ADK para Python trae LiteLLM para Claude, OpenAI y modelos abiertos. Decisión para la hackathon: Gemini.

## Credenciales

- **En local:** `GOOGLE_GENAI_API_KEY` en `apps/api/.env`, con una key de Google AI Studio. `app/config.py` la copia a `GOOGLE_API_KEY`, que es la que lee la librería de Gemini.
- **En Cloud Run:** `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT` y `GOOGLE_CLOUD_LOCATION`. La autenticación la da la cuenta de servicio (rol `Vertex AI User`), sin key.

## Probar sin la web

```bash
pnpm dev
curl -X POST localhost:4000/chat -H 'content-type: application/json' \
  -d '{"sessionId":"prueba","message":"harina pan 1 kg en Caracas"}'
```
