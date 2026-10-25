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
| **Canal → agente** | `services/api/app/agent.py` | `ask_prais(user_id, message)` → texto. `user_id` lleva el canal delante (`web:…`, `whatsapp:…`), y cada uno tiene su conversación. El mensaje llega al agente tal cual: no se reescribe con un catálogo de modelos. El producto ya dicho queda en el estado de la sesión |
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
6. Si sabes puntuar tu canal, devuelve también `SourceResult.trust[merchant_id]`. Ver abajo.

Las particularidades de cada fuente están en [sources.md](sources.md).

## El puntaje de confianza de una fuente

Un especialista **mide solo lo que ve su canal y nunca cierra**. Devuelve un `TrustScore` en etapa
`parcial` (sin puntaje y con veredicto `sin_datos`) y el agregador lo cierra al final del turno,
porque `price_anomaly` necesita la mediana de todas las fuentes y eso ninguna fuente lo sabe sola.

Tres cosas impiden que cada fuente invente su propio puntaje:

1. **El catálogo es el contrato.** `CATALOGS` en `contracts.py` declara las señales de cada canal,
   su peso y quién la llena. `build_signals` rechaza una clave que no esté en el catálogo, y el
   validador de `TrustScore` rechaza una lista que no cuadre con él, pesos que no sumen 100, una
   cobertura mal calculada o una etapa `final` con señales en `pending`. No es una convención: no
   compila.
2. **El especialista no cierra.** Siempre `stage="parcial"`. Cerrar es del agregador.
3. **Lo que es igual en todos los canales vive en `trust.py`**, no en cada fuente: `risk_language`
   es el mismo en una bio de Instagram y en una descripción de Mercado Libre.

El camino, de punta a punta:

```
fuente            search_offers              agente
build_signals  →  contractOffer/Merchant  →  close_listings  →  tarjeta
compute_trust     (precio, tasa, USD)        aggregate + finalize
stage="parcial"                              stage="final", veredicto y estrellas
```

Lo que mide cada canal está en el borrador de `resources/<canal>_trust_score.py`: las fórmulas y
los umbrales se portan de ahí, no se inventan. Lo que la fuente no trae queda en `None`: no cuenta
y su peso se reparte entre las señales que sí hay. Con menos del 40 % del peso medido el veredicto
es `sin_datos`, que es la respuesta honesta cuando no se sabe.

El armador del contrato (`app/lib/contract_build.py`) es uno solo para todas: una fuente del
registro lo usa desde `search_offers` y la web abierta desde `open_web_trust.py`, que no pasa por
el registro. Ahí viven también la clave del producto, que agrupa las ofertas comparables para la
mediana, y la condición.

Una fuente que todavía no puntúa su canal deja `trust` vacío y su oferta sigue mostrando el entero
provisional de `prices.py`. Las dos formas conviven: `close_listings` cierra lo que trae contrato y
deja pasar el resto.

## Decisión pendiente: la forma de una oferta

Los componentes del design system (`RankedList`, `FichaOferta`, `MensajeCanal`) esperan el tipo `Oferta` de `docs/design-system/components/index.d.ts`: `tienda`, `canal`, `usd`, `envio`, `confianza` de 0 a 5. La API devuelve `OfferResult`, con otros nombres y la confianza de 0 a 100, y `/chat` solo devuelve texto.

La propuesta es que la API devuelva ofertas con la forma `Oferta` y que `/chat` responda `{ reply, producto, ofertas, tasa, actualizado }`. Así la web pinta `RankedList` sin traducir nada. Sigue abierta.
