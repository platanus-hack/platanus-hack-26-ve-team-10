# Contratos

Los puntos donde se conectan las piezas. Si respetas el contrato, puedes trabajar en tu parte sin tocar las demás. **Cambiar un contrato** es la única cosa que se avisa al equipo antes de mergear.

```
Web ──► POST /chat ─────┐
Kapso ─► POST /whatsapp ┼─► askPrais() ─► tool buscar_ofertas ─┐
                        │                                       ├─► searchOffers() ─┬─► Source × N (en paralelo)
Asistentes ─► /mcp ─────┴─► tool search_prices ─────────────────┘                   └─► getRate()
```

| Contrato | Dónde | Forma |
|---|---|---|
| **Web → API** | `apps/api/src/routes/chat.ts` | `POST /chat` `{ sessionId, message }` → `{ reply }`. La web lo llama como `/api/chat` |
| **Kapso → API** | `apps/api/src/routes/whatsapp.ts` | `POST /whatsapp`, firmado con `X-Webhook-Signature`. Responde 200 y contesta por la API de Kapso: ver [kapso.md](kapso.md) |
| **Canal → agente** | `apps/api/src/agent.ts` | `askPrais({ userId, message })` → texto. `userId` lleva el canal delante (`web:…`, `whatsapp:…`), y cada uno tiene su conversación |
| **Agente / MCP → búsqueda** | `apps/api/src/lib/search.ts` | `searchOffers({ text, zone?, needsDelivery? })` → `{ offers, failedSources, notice? }`, ordenadas por precio en USD |
| **Búsqueda → fuente** | `apps/api/src/lib/types.ts` (`Source`) | `search(query, signal)` → `{ offers, merchants }`. Tiene 8 s; si falla o tarda más, la búsqueda sigue sin ella |
| **Búsqueda → tasa** | `apps/api/src/lib/rate.ts` | `getRate()` → `{ source, usdToVes, observedAt }` |

## Sumar una fuente

1. Crea `apps/api/src/lib/sources/<fuente>.ts` que exporte un `Source`. Copia `sources/mock.ts` como modelo.
2. `enabled` depende de su API key: `enabled: Boolean(process.env.FIRECRAWL_API_KEY)`. Agrega la variable a `apps/api/.env.example`.
3. Agrégala a la lista de `sources/index.ts`. Es la única línea que tocas fuera de tu archivo.
4. Los ids de comercio llevan el prefijo de tu fuente (`ig:bodegon`, `ml:12345`), para no chocar con otras fuentes.
5. Tu fuente solo trae datos. No filtres por zona, no conviertas monedas ni ordenes: eso lo hace `searchOffers` para todas.

Las particularidades de cada fuente están en [sources.md](sources.md).
