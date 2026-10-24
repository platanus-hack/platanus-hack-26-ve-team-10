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

El modelo se elige con `PRAIS_MODEL`, y por defecto es `gemini-flash-latest`. ADK 2.3 reconoce por nombre:

- `gemini-*`: cualquier Gemini, por Google AI Studio o por Vertex AI.
- Endpoints de Vertex AI con modelos de Gemini afinados (`projects/.../endpoints/...`).
- `apigee/...`: Gemini a través de un proxy de Apigee.

Para usar otro proveedor (Claude, OpenAI...) hay que escribir una clase que extienda `BaseLlm` y registrarla en `LLMRegistry`. La versión de TypeScript no trae el adaptador LiteLLM que sí tiene la de Python.

## Credenciales

- **En local:** `GOOGLE_GENAI_API_KEY` con una key de Google AI Studio.
- **En Cloud Run:** `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT` y `GOOGLE_CLOUD_LOCATION`. La autenticación la da la cuenta de servicio, sin key.

## Probar sin la web

```bash
npx @google/adk-devtools web
```

Siempre escribe el nombre completo del paquete en `npx`. Un `npx adk` a secas descarga un paquete que no tiene nada que ver.
