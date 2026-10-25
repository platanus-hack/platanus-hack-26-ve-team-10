# Contratos

Los puntos donde se conectan las piezas. Hay una vista visual para el equipo en el [Mapa de contratos de Prais](https://claude.ai/artifact/D8LWNtrGdgCUncfBmDKD2X); si no la puedes abrir, pide acceso en el canal. La fuente de verdad es este archivo. Si respetas el contrato, puedes trabajar en tu parte sin tocar las demás. **Cambiar un contrato** es la única cosa que se avisa al equipo antes de mergear.

```
Web ──► POST /chat ─────┐
Kapso ─► POST /whatsapp ┼─► ask_prais() ─► tool buscar_ofertas ─┐
                        │                                        ├─► search_offers() ─┬─► Source × N (en paralelo)
Asistentes ─► /mcp ─────┴─► tool search_prices ──────────────────┘                    └─► get_rate()
```

El backend es Python (FastAPI). Las rutas y las formas JSON son las del contrato; los nombres internos van en `snake_case`.

| Contrato | Dónde | Forma |
|---|---|---|
| **Web → API** | `services/api/app/routes/chat.py` | `POST /chat` `{ sessionId, message }` → `{ reply }`. La web lo llama como `/api/chat`. Un body inválido responde 400 |
| **Kapso → API** | `services/api/app/routes/whatsapp.py` | `POST /whatsapp`, firmado con `X-Webhook-Signature`. Encola el mensaje, responde 200 y contesta por la API de Kapso: ver [kapso.md](kapso.md) |
| **Canal → agente** | `services/api/app/agent.py` | `ask_prais(user_id, message)` → texto. `user_id` lleva el canal delante (`web:…`, `whatsapp:…`), y cada uno tiene su conversación. Si el producto todavía cambia de precio según el modelo, si es nuevo o usado, o la capacidad, el texto es una sola pregunta y no hay búsqueda |
| **Agente / MCP → búsqueda** | `services/api/app/lib/search.py` | `search_offers(SearchQuery(text, zone?, needs_delivery?))` → `{ query, offers, failedSources, notice? }`, ordenadas por precio en USD. Las claves del resultado van en camelCase, igual que antes. El MCP usa `search_all(query, open_web_budget_s)`: la misma forma, con las ofertas de la web abierta (Firecrawl) sumadas. `failedSources` lleva el id de cada fuente que falló. De la web abierta, `firecrawl:<dominio>` aparece una vez por dominio cuando una página suya quedó bloqueada, dio error o no terminó a tiempo, y ese dominio no tiene ofertas en la respuesta; un link muerto (404 o 410) no cuenta. El aviso de datos de ejemplo sale solo si alguna oferta tiene `example: true` |
| **Búsqueda → fuente** | `services/api/app/lib/types.py` (`Source`) | `await search(query)` → `SourceResult(offers, merchants)`. Tiene 8 s (`asyncio.wait_for`) y se cancela si tarda más; si falla o tarda, la búsqueda sigue sin ella |
| **Web → catálogo** | `services/api/app/routes/catalogo.py` | `GET /catalogo/rutas`, `/sitemap`, `/categorias`, `/marcas`, `/producto/{slug}-{id}`, `/categoria/{cat}`, `/categoria/{cat}/{marca o faceta}`, `/marca/{slug}`. JSON en camelCase; cada página trae `indexable` y `datosDeEjemplo`, o `{ redirect }`; 404 si no existe. La web lo llama al construir y al revalidar, desde el servidor (`services/web/src/lib/catalogo.ts`) |
| **Búsqueda → tasa** | `services/api/app/lib/rate.py` | `get_rate()` → `ExchangeRate(source, usd_to_ves, observed_at)`. Es la tasa oficial del BCV, de [dolarapi.com](https://ve.dolarapi.com/v1/dolares/oficial), con media hora de caché. Siempre devuelve una tasa: si la API no responde, la última buena, y su `observed_at` dice de cuándo es |

Cada oferta de `offers` lleva `title`, `url`, `price` (como la publica el comercio), `priceUsd`, `rate` (si hubo conversión), `seenAt`, `source` y `merchant { name, channel, zone, delivers, trust }`.

**Ruta interna, fuera del contrato.** `POST /internal/whatsapp-task` (`app/routes/whatsapp.py`) la llama solo Cloud Tasks, con un token OIDC. No la uses desde la web ni desde Kapso, y su forma puede cambiar sin avisar: los contratos públicos de arriba no cambian.

Los tipos de la búsqueda son `dataclass` en `app/lib/types.py`, en `snake_case` (`merchant_id`, `usd_to_ves`, `response_time_min`). `Source` es un `Protocol`: `id`, `enabled` y `async search(query)`. `Channel` incluye `amazon` e `importacion`.

Una oferta de importación no sale de `search_offers`. La arma `find_listings_importacion`. Su `price_kind` es `estimado`, su `price_usd` es el total puesto en Venezuela y el desglose va en `landed`. `fulfiller_id` es el courier (`cur:zoom`, `cur:liberty`); en los demás canales es null. El precio de Amazon queda en `landed.product_usd`. Esto cambia el contrato: avisar en el canal antes de mergear.

`merchant.trust` en la respuesta de `search_offers` sigue siendo un entero de 0 a 100 (o null en la web abierta): es la fórmula provisional de `prices.trust_score`. El puntaje del contrato —señales, cobertura y veredicto— vive en `app/lib/contracts.py` y se calcula en `app/lib/trust.py`. No reemplaza esa respuesta hasta que cada fuente mande sus señales. Cambiar el `Merchant` de la búsqueda para guardarlas se avisa antes de mergear.

## Sumar una fuente

1. Crea `services/api/app/lib/sources/<fuente>.py` con un objeto que cumpla `Source`. Copia `sources/mock.py` como modelo.
2. `enabled` depende de su API key: `enabled = bool(os.environ.get("FIRECRAWL_API_KEY"))`. Agrega la variable a `services/api/.env.example`.
3. Agrégala a la lista de `sources/__init__.py`. Es la única línea que tocas fuera de tu archivo.
4. Los ids de comercio llevan el prefijo de tu fuente (`ig:bodegon`, `ml:12345`), para no chocar con otras fuentes.
5. Tu fuente solo trae datos. No filtres por zona, no conviertas monedas ni ordenes: eso lo hace `search_offers` para todas.

Las particularidades de cada fuente están en [sources.md](sources.md).

## Decisión pendiente: la forma de una oferta

Los componentes del design system (`RankedList`, `FichaOferta`, `MensajeCanal`) esperan el tipo `Oferta` de `docs/design-system/components/index.d.ts`: `tienda`, `canal`, `usd`, `envio`, `confianza` de 0 a 5. La API devuelve `OfferResult`, con otros nombres y la confianza de 0 a 100, y `/chat` solo devuelve texto.

La propuesta es que la API devuelva ofertas con la forma `Oferta` y que `/chat` responda `{ reply, producto, ofertas, tasa, actualizado }`. Así la web pinta `RankedList` sin traducir nada. Sigue abierta.
