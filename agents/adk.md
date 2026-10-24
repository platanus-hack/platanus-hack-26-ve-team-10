# Agente con ADK

El agente vive en `src/agent/index.ts` y usa [ADK para TypeScript](https://github.com/google/adk-js) (`@google/adk` 2.3.0).

## Cómo está armado

- `praisAgent`: un `LlmAgent` con sus instrucciones y la tool `buscar_ofertas`.
- `buscar_ofertas`: una `FunctionTool` con parámetros en zod 4 que llama a `searchOffers`.
- `askPrais({ userId, message })`: corre el agente con un `Runner` y devuelve el texto de la respuesta. Cada `userId` tiene su propia conversación (`web:<id>`, `whatsapp:<número>`), así que el agente recuerda lo que ya preguntó.
- Las sesiones están en memoria (`InMemorySessionService`).

## Reglas

1. **No inventa precios.** Todo precio sale de una tool. Si no hay resultados, lo dice.
2. **Una pregunta a la vez** cuando le falta un dato.
3. **Las cuentas las hace el código**, no el modelo: conversión de moneda, orden y confianza están en `src/lib`.

## Agregar una tool

Crea otra `FunctionTool` en `src/agent/index.ts` y súmala a `tools`. Si la tool toca una fuente o hace cálculos, ponle la lógica en `src/lib` y deja la tool como una llamada fina.

## Modelos

El modelo se elige con `PRAIS_MODEL`, y por defecto es `gemini-flash-latest`. ADK 2.3 no trae una lista fija: acepta cualquier nombre que encaje con estos patrones.

| Patrón | Qué es |
|---|---|
| `gemini-*` | Cualquier Gemini, por Google AI Studio o por Vertex AI. Por ejemplo, `gemini-2.5-flash` (el que ADK usa por defecto) o `gemini-flash-latest` |
| `projects/.../endpoints/...` | Un Gemini afinado, publicado en un endpoint de Vertex AI |
| `projects/.../publishers/google/models/gemini...` | Un Gemini de Vertex con el nombre largo |
| `apigee/...` | Gemini a través de un proxy de Apigee |
| `chrome-on-device`, `chrome/...` | El modelo que trae Chrome. Solo corre en el navegador: no nos sirve |

`RoutedLlm` permite repartir los pedidos entre varios modelos. La lista de los Gemini disponibles está en Google AI Studio o en el Model Garden de Vertex AI.

**Otros proveedores y modelos abiertos.** La versión de TypeScript no trae adaptadores para Claude, OpenAI ni modelos abiertos (Llama, Gemma, Qwen…). La de Python sí trae LiteLLM. En TypeScript hay que escribir una clase que extienda `BaseLlm`, registrarla en `LLMRegistry` y llamar a una API compatible con OpenAI: Ollama, vLLM en Cloud Run, Groq u OpenRouter. El trabajo está en traducir mensajes y tool calls. Gemma por la API de Gemini no está probado, y no sabemos si soporta tools. Decisión para la hackathon: Gemini.

## Credenciales

- **En local:** `GOOGLE_GENAI_API_KEY` con una key de Google AI Studio.
- **En Cloud Run:** `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT` y `GOOGLE_CLOUD_LOCATION`. La autenticación la da la cuenta de servicio, sin key.

## Probar sin la web

```bash
npx @google/adk-devtools web
```

Siempre escribe el nombre completo del paquete en `npx`. Un `npx adk` a secas descarga un paquete que no tiene nada que ver.
