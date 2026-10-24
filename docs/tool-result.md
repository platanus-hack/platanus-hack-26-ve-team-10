# ToolResult y store de datos

Spec del contrato que devuelve cada tool y de dónde se guarda. Complementa la sección 6 de [handoff-orquestador.md](handoff-orquestador.md). Es una **propuesta**: cambia `types.py`, así que se avisa al equipo antes de mergear ([docs/plan.md](plan.md)).

## 1. Principios

1. **La tool trae datos; el código calcula.** La tool llena lo que vio (precio publicado, moneda, título, URL). El precio en USD y en Bs, la tasa, el veredicto del juez y la confianza los llena `app/lib`, nunca la tool ni un LLM.
2. **El LLM no copia precios.** El especialista guarda el `ToolResult` en el estado de la sesión de ADK y responde solo un resumen con los ids de las ofertas. `AgentTool` reenvía ese estado al orquestador (`tool_context.state.update(event.actions.state_delta)` en ADK 2.13), así que el orquestador lee los precios del estado, no del texto.
3. **Cada oferta se puede auditar:** apunta a su comercio y a su evidencia (URL, extracto, fecha).
4. **Mismo formato en el cable que en el store:** JSON en camelCase, como el resto de los contratos ([agents/contracts.md](../agents/contracts.md)). En Python, `snake_case`.

## 2. Quién llena cada campo

| Etapa | Llena | Ejemplo |
|---|---|---|
| `traer` + `extraer` (tool) | Lo que publica la fuente | `title`, `url`, `price`, `priceKind`, `imageUrl`, datos del comercio |
| `mapear` (tool, función pura) | Normaliza a las entidades | `product`, `condition`, `variant`, ids con prefijo |
| `juzgar` (`lib/judge.py`) | Si es el producto pedido | `judge` |
| `enriquecer` (`lib/prices.py`, `lib/rate.py`, `lib/location.py`) | Cuentas, confianza y claves de ubicación | `priceUsd`, `priceVes`, `rateUsed`, `merchant.trust`, `location.stateCode`, `location.cityKey` |
| `agregar` (por consulta) | Qué tan cerca está cada oferta de esta persona | `Match` |

Los campos de juzgar y enriquecer llegan vacíos (`null`) desde la tool.

## 3. Modelos (pydantic 2, `app/lib/contracts.py`)

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    # JSON en camelCase, Python en snake_case. extra="forbid": un campo mal escrito es un error, no un dato perdido.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


Channel = Literal["web", "mercadolibre", "instagram", "tiktok", "facebook", "amazon"]
Currency = Literal["USD", "VES"]
Condition = Literal["nuevo", "usado", "reacondicionado", "desconocida"]
ToolStatus = Literal["ok", "parcial", "fallo", "plazo_vencido"]
JudgeVerdict = Literal["producto_ve", "listado_ve", "referencia", "social", "descartar"]  # resources/queries.md
TrustVerdict = Literal["confiable", "precaucion", "riesgosa", "sin_datos"]  # resources/*-trust-score.ts
LocationOrigin = Literal["persona", "publicacion", "comercio", "inferida"]
Proximity = Literal["misma_zona", "misma_ciudad", "mismo_estado", "otro_estado", "desconocida"]


# ── Ubicación ────────────────────────────────────────────────────────────────
# Un solo tipo para la persona, el comercio y el artículo: así se comparan sin adivinar.

class Location(Model):
    raw: str | None = None           # el texto tal como llegó: "mcbo", "Maracaibo, Zulia · a 3 km"
    city: str | None = None          # "Maracaibo"
    state: str | None = None         # "Zulia"
    area: str | None = None          # sector o urbanización: "Las Mercedes"
    country: str = "VE"              # ISO 3166-1; "US" en una referencia de Amazon
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    origin: LocationOrigin           # de dónde salió el dato
    # Claves para comparar. Las llena el código (lib/location.py), nunca la tool ni un LLM:
    state_code: str | None = None    # ISO 3166-2: "VE-V" (Zulia), "VE-A" (Distrito Capital)
    city_key: str | None = None      # ciudad normalizada desde una lista de ciudades: "maracaibo"
    area_key: str | None = None      # sector normalizado, si se reconoce


# ── Consulta ─────────────────────────────────────────────────────────────────

class Variant(Model):
    capacity: str | None = None      # "128 GB"
    size: str | None = None          # "32 pulgadas", "175/70 R13"
    presentation: str | None = None  # "1 kg", "1 L"
    color: str | None = None


class CanonicalProduct(Model):
    key: str                         # slug estable: "apple-iphone-15-128gb". Clave de cache y de deduplicación
    brand: str | None = None
    model: str
    variant: Variant = Variant()
    category: str | None = None      # slug de catalogo.json si coincide
    unit_quantity: int = 1           # 20 para un bulto de 20 × 1 kg
    catalog_id: str | None = None    # id de catalogo.json, si el producto está en el catálogo


class NormalizedQuery(Model):
    raw_text: str                    # lo que escribió la persona
    input_kind: Literal["texto", "link", "imagen"] = "texto"
    source_url: str | None = None    # el link que mandó, si mandó uno
    product: CanonicalProduct
    condition: Condition = "nuevo"   # si la persona no dice nada, se asume nuevo
    user_location: Location | None = None  # dónde está la persona (origin "persona"). Reemplaza a zone
    needs_delivery: bool | None = None
    missing: list[Literal["producto", "zona", "envio"]] = []  # si no está vacío, se pregunta antes de buscar


class ToolRequest(Model):
    job_id: str
    tool: str                        # "firecrawl", "mercadolibre", "apify-instagram"…
    query: NormalizedQuery
    planned_queries: list[str]       # consultas propias del proveedor, del plan del orquestador
    deadline_ms: int = 8000
    max_credits: int | None = None
    attempt: int = 1


# ── Resultado ────────────────────────────────────────────────────────────────

class Money(Model):
    amount: float = Field(gt=0)
    currency: Currency


class RateRef(Model):
    source: str                      # "BCV", "paralelo", "tasa de ejemplo"
    usd_to_ves: float = Field(gt=0)
    observed_at: datetime


class TrustSignal(Model):
    key: str                         # "antiguedad_cuenta", "rif_publicado"…
    weight: float
    value: float | None = Field(default=None, ge=0, le=1)  # None = sin dato
    reason: str | None = None
    good: bool | None = None


class TrustScore(Model):
    score: int | None = Field(default=None, ge=0, le=100)  # None si la cobertura no alcanza
    coverage: float = Field(ge=0, le=1)                     # menos de 0,4 → verdict "sin_datos"
    verdict: TrustVerdict
    red_flags: list[str] = []                               # una bandera deja el puntaje en 0
    reasons: list[str] = []
    signals: list[TrustSignal] = []
    formula: str                                            # "ig-v1", "mercadolibre-v1": qué borrador se usó
    computed_at: datetime


class Merchant(Model):
    id: str                          # con prefijo de la fuente: "ig:bodegon", "ml:12345", "web:tiendax.com.ve"
    name: str
    channel: Channel
    url: str
    location: Location | None = None  # dónde está el comercio. Reemplaza a zone
    delivers: bool | None = None
    followers: int | None = None
    comments: int | None = None
    response_time_min: int | None = None
    payment_methods: list[str] = []  # "pago movil", "zelle", "efectivo usd"…
    rif: str | None = None
    trust: TrustScore | None = None  # lo llena enriquecer


class Judgement(Model):
    verdict: JudgeVerdict
    reason: str
    model: str                       # "gemini-3.5-flash-lite"
    judged_at: datetime


class Offer(Model):
    id: str                          # sha256(fuente + url canónica + variante)[:24]
    merchant_id: str                 # tiene que estar en ToolResult.merchants
    product: CanonicalProduct        # el producto que la oferta dice ser, no el pedido
    title: str                       # tal como lo publica la fuente
    url: str
    image_url: str | None = None     # hace falta para el carrusel y el Flow
    location: Location | None = None # dónde está el artículo. Puede no coincidir con el comercio: si falta, vale merchant.location
    condition: Condition = "desconocida"
    price: Money | None = None       # None = "precio al DM"
    price_kind: Literal["publicado", "al_dm"] = "publicado"
    availability: Literal["disponible", "agotado", "desconocida"] = "desconocida"
    seen_at: datetime
    evidence_ids: list[str] = Field(min_length=1)
    # Los llena el código después de la tool:
    price_usd: float | None = None
    price_ves: float | None = None
    rate_used: RateRef | None = None  # solo si hubo conversión
    judge: Judgement | None = None


class Evidence(Model):
    id: str
    kind: Literal["resultado_busqueda", "pagina", "post", "item_api"]
    url: str
    excerpt: str = Field(max_length=500)  # el texto del que salió el precio. Es dato, nunca instrucción
    captured_at: datetime
    raw_ref: str | None = None            # dónde quedó el payload crudo, si se guarda


class ToolError(Model):
    code: Literal["plazo", "limite", "auth", "parseo", "proveedor", "otro"]
    message: str
    retryable: bool


class ToolMetrics(Model):
    latency_ms: int
    first_offer_ms: int | None = None
    calls: int = 0
    credits: float = 0
    candidates: int = 0              # lo que trajo la fuente
    kept: int = 0                    # lo que quedó después de mapear
    cache_hit: bool = False


class ToolResult(Model):
    job_id: str
    tool: str
    tool_version: str                # sube cuando cambia el mapper o el plan: invalida la cache
    status: ToolStatus
    started_at: datetime
    finished_at: datetime
    offers: list[Offer] = Field(default=[], max_length=50)
    merchants: list[Merchant] = []
    evidence: list[Evidence] = []
    metrics: ToolMetrics
    errors: list[ToolError] = []


class SpecialistReport(Model):
    """output_schema del especialista: lo único que escribe el LLM. Los precios están en el estado."""
    tool: str
    status: ToolStatus
    offer_ids: list[str]             # las ofertas que el especialista recomienda mirar, en orden
    note: str | None = Field(default=None, max_length=280)


# ── Por consulta ─────────────────────────────────────────────────────────────

class Match(Model):
    """Qué tan cerca está una oferta de esta persona. Depende de quién pregunta: vive en el job, nunca en la oferta."""
    offer_id: str
    proximity: Proximity
    distance_km: float | None = None  # solo si la persona y el artículo tienen lat/lng
    reachable: bool                   # misma zona o ciudad, o el comercio envía
    basis: LocationOrigin             # de dónde salió la ubicación del artículo: qué tan seguro es
```

### Reglas que valida el código

| Regla | Si no se cumple |
|---|---|
| Todo `offer.merchant_id` está en `merchants` | La oferta se descarta y se anota un error `parseo` |
| Todo `evidence_ids` existe en `evidence` | Igual |
| `price` es `None` ⇔ `price_kind == "al_dm"` | Igual |
| `rate_used` existe solo si `price.currency == "VES"` | Error de programación: falla el test |
| `location.origin`: `persona` solo en `user_location`; `publicacion` solo si la fuente publicó dónde está el artículo (Marketplace, Mercado Libre); `comercio` si se copió la del comercio; `inferida` si la dedujo el texto o un LLM | Se marca `inferida` |
| `state_code`, `city_key` y `area_key` los llena solo `lib/location.py` | Se ignoran y se recalculan |
| Un `Match` por oferta y por consulta, guardado en el job | Nunca se guarda en `offers/{offerId}`: la misma oferta está cerca de una persona y lejos de otra |

### Cómo se calcula `Match`

Se compara `query.user_location` con `offer.location` (o, si falta, `merchant.location`), siempre por las claves, nunca por el texto:

| `proximity` | Cuándo |
|---|---|
| `misma_zona` | Mismo `city_key` y mismo `area_key` |
| `misma_ciudad` | Mismo `city_key` |
| `mismo_estado` | Mismo `state_code` |
| `otro_estado` | Los dos `state_code` existen y son distintos |
| `desconocida` | Falta la clave en algún lado |

`reachable` es verdadero si `proximity` es `misma_zona` o `misma_ciudad`, o si `merchant.delivers` es verdadero. Es una regla inicial: cuando el comercio diga hasta dónde envía (local, estado o nacional), `reachable` la usa. `distance_km` solo se calcula si los dos lados tienen latitud y longitud.
| `status` cuadra con lo que pasó | `ok`: sin errores. `parcial`: hay ofertas y errores, o se venció el plazo con ofertas. `fallo`: sin ofertas y con errores. `plazo_vencido`: sin ofertas y se venció el plazo |
| Máximo 50 ofertas y extractos de 500 caracteres | Se recorta: así el `ToolResult` cabe holgado en un documento del store (límite de 1 MiB) |

### Ejemplo (JSON)

```json
{
  "jobId": "9f2c…",
  "tool": "firecrawl",
  "toolVersion": "firecrawl-c-1",
  "status": "parcial",
  "startedAt": "2026-10-24T20:10:02Z",
  "finishedAt": "2026-10-24T20:10:16Z",
  "offers": [
    {
      "id": "a41e…",
      "merchantId": "web:soytechno.com",
      "product": { "key": "apple-iphone-15-128gb", "brand": "Apple", "model": "iPhone 15", "variant": { "capacity": "128 GB" }, "unitQuantity": 1 },
      "title": "iPhone 15 128GB Nuevo Sellado",
      "url": "https://…",
      "condition": "nuevo",
      "location": { "city": "Caracas", "state": "Distrito Capital", "country": "VE", "origin": "comercio", "stateCode": "VE-A", "cityKey": "caracas" },
      "price": { "amount": 789, "currency": "USD" },
      "priceKind": "publicado",
      "availability": "disponible",
      "seenAt": "2026-10-24T20:10:09Z",
      "evidenceIds": ["e1"],
      "priceUsd": null, "priceVes": null, "rateUsed": null, "judge": null
    }
  ],
  "merchants": [{ "id": "web:soytechno.com", "name": "Soytechno", "channel": "web", "url": "https://…", "trust": null }],
  "evidence": [{ "id": "e1", "kind": "pagina", "url": "https://…", "excerpt": "iPhone 15 128GB … $789", "capturedAt": "2026-10-24T20:10:09Z" }],
  "metrics": { "latencyMs": 14100, "firstOfferMs": 3600, "calls": 6, "credits": 37, "candidates": 18, "kept": 5, "cacheHit": false },
  "errors": [{ "code": "plazo", "message": "2 páginas no respondieron a tiempo", "retryable": true }]
}
```

El precio de 789 es el observado el 24 de octubre en `resources/queries.md`; las URLs se omiten.

## 4. Cómo encaja con lo que hay

| Hoy (`app/lib/types.py`) | Pasa a | Cambio |
|---|---|---|
| `SourceResult(offers, merchants)` | `ToolResult` | Suma estado, evidencia, métricas y errores |
| `Offer(merchant_id, title, url, price, seen_at)` | `Offer` | Suma id, producto, condición, imagen, evidencia y los campos de enriquecer |
| `Merchant` | `Merchant` | Suma métodos de pago, RIF y `trust`. `zone: str` pasa a `location: Location`. Los datos que pide el puntaje de cada fuente (antigüedad de la cuenta, calificaciones, likes por video…) se suman como campos opcionales, según [Datos que el puntaje necesita](../agents/sources.md#datos-que-el-puntaje-necesita) |
| `SearchQuery.zone` | `NormalizedQuery.user_location` | El texto queda en `raw`; las claves las llena `lib/location.py` |
| `_same_zone` en `lib/search.py` (busca un texto dentro de otro) | `Match` | Compara `state_code` y `city_key`. Mientras se migra, `zone` y el filtro actual siguen andando |
| `Money`, `ExchangeRate`, `SearchQuery` | `Money`, `RateRef`, `NormalizedQuery` | Mismo significado, más campos |
| Salida de `search_offers` (`{query, offers, failedSources, notice}`) | Se arma desde los `ToolResult` | El contrato público de `/chat` y `/mcp` no cambia hasta que se decida la forma `Oferta` ([contracts.md](../agents/contracts.md#decisión-pendiente-la-forma-de-una-oferta)) |

Migración sin romper nada: `Source.search` sigue devolviendo `SourceResult` y un adaptador lo envuelve en `ToolResult`. Cada fuente se pasa al formato nuevo en su propio PR.

## 5. Store de datos (Firestore)

Firestore es la recomendación de la decisión abierta 4: serverless, en el mismo proyecto de GCP, sin servidor que mantener. Según el roadmap entra **después de la fase 1**. Hasta entonces, el `ToolResult` vive en el estado de la sesión de ADK y sus métricas van al log (tarea 1.9).

```
jobs/{jobId}                       una consulta de una persona
  └─ results/{tool}                un ToolResult por tool (cada tool escribe el suyo)
offers/{offerId}                   última versión vista de cada oferta, entre consultas
  └─ history/{yyyymmddHH}          precio por hora, para el historial del catálogo
merchants/{merchantId}             comercio y su último TrustScore
products/{productKey}              producto canónico, alias y mejor oferta
cache/{tool}__{queryHash}          puntero a un results/{tool} reciente, con vencimiento
rates/{yyyy-mm-dd}__{source}       tasa del día
```

### `jobs/{jobId}`

`jobId = sha256(canal + message.id)[:32]`: el mismo hash que ya nombra la tarea de Cloud Tasks, así un reintento cae en el mismo job.

| Campo | Tipo | Nota |
|---|---|---|
| `channel` | `"whatsapp" \| "web" \| "mcp"` | |
| `userRef` | string | HMAC-SHA256 del número con `USER_REF_SALT`. **Nunca el número en claro** |
| `query` | `NormalizedQuery` | De `user_location` se guardan ciudad, estado y claves. **Latitud y longitud no se guardan**: se usan para `distance_km` y se descartan |
| `status` | `recibido \| acuse_enviado \| buscando \| esperando_datos \| respondido \| fallo` | |
| `toolsPlanned` / `toolsDone` | string[] | El agregador cierra cuando son iguales o se vence `deadlineAt` |
| `createdAt`, `ackedAt`, `answeredAt`, `deadlineAt` | timestamp | |
| `replyMessageId` | string \| null | El `wamid` de la respuesta final. **Si existe, no se vuelve a enviar** (tarea 1.7) |
| `matches` | `Match[]` | Uno por oferta, para esta persona. Máximo 200 |
| `best` | `{ offerId, priceUsd, merchantId }` \| null | Lo que se le dijo a la persona |
| `totals` | `{ latencyMs, credits, offers }` | Suma de las métricas de cada tool |
| `expireAt` | timestamp | `createdAt` + 30 días. Política de TTL de Firestore |

### `jobs/{jobId}/results/{tool}`

El `ToolResult` completo (sección 3), ya enriquecido. Va en una subcolección y no dentro del job para que cada tool escriba en su propio documento: Firestore limita las escrituras seguidas al mismo documento, y así las tools en paralelo no compiten.

### `offers/{offerId}`

| Campo | Tipo | Nota |
|---|---|---|
| todos los de `Offer` | | La última vez que se vio |
| `productKey` | string | Copia de `product.key`, para consultar por índice |
| `firstSeenAt`, `lastSeenAt` | timestamp | |
| `lastJobId` | string | |
| `active` | bool | `false` si en la última búsqueda ya no apareció |

`offers/{offerId}/history/{yyyymmddHH}`: `{ priceUsd, priceVes, rateUsed, seenAt }`. Alimenta el historial de precios que el catálogo tiene pendiente ([agents/seo-geo.md](../agents/seo-geo.md)).

### `merchants/{merchantId}`

El `Merchant` con su último `trust`. El id ya trae el prefijo de la fuente (`ig:bodegon`). Firestore no acepta `/` en un id: `web:` usa el dominio, sin barras.

### `products/{productKey}`

| Campo | Tipo | Nota |
|---|---|---|
| `product` | `CanonicalProduct` | |
| `aliases` | string[] | Cómo lo escribe la gente: "iphone 15 128", "ip15 128gb" |
| `catalogId` | string \| null | Une con `catalogo.json` y las páginas `/ve/p/...` |
| `best` | `{ offerId, priceUsd, seenAt }` | Mejor oferta nueva con veredicto `producto_ve` |

### `cache/{tool}__{queryHash}`

`queryHash = sha256(product.key + condition + toolVersion)`, más `userLocation.cityKey` solo para las tools que buscan por zona (Marketplace). Para las demás, la ubicación no cambia lo que trae la tool: la cercanía se calcula después, en `Match`, así que dos personas de ciudades distintas reusan el mismo resultado. Guarda `{ jobId, tool, status, createdAt, expireAt }` y apunta al `results/{tool}` de ese job.

| Tool | Vence en (inicial, ajustar con métricas) |
|---|---|
| Firecrawl | 1 h |
| Mercado Libre | 30 min |
| Apify (lee el último dataset) | Lo que tarde el actor en volver a correr |

Un resultado `fallo` o `plazo_vencido` **no se cachea**. Uno `ok` sin ofertas vence a los 10 minutos.

### `rates/{yyyy-mm-dd}__{source}`

`RateRef`. Se escribe una vez al día y lo leen todos.

### Índices

| Colección | Campos | Para qué |
|---|---|---|
| `offers` | `productKey` ↑, `active` ↑, `priceUsd` ↑ | Las más baratas de un producto: fichas y respuesta |
| `offers` | `productKey` ↑, `lastSeenAt` ↓ | Lo más reciente |
| `offers` | `productKey` ↑, `location.stateCode` ↑, `priceUsd` ↑ | Las más baratas de un producto en un estado ("iphone 15 en Zulia") |
| `jobs` | `userRef` ↑, `createdAt` ↓ | Historial de una persona |
| `merchants` | `channel` ↑, `trust.score` ↓ | Ranking de comercios por canal |

### Qué no se guarda

- El número de teléfono ni el texto de la conversación fuera del job (que vence a los 30 días).
- El HTML o el JSON crudo de las fuentes: solo el extracto de 500 caracteres. Si hace falta auditar más, `raw_ref` apunta a un bucket que se agrega cuando haga falta.
- Las sesiones de ADK siguen en memoria. Pasarlas a un store es otra decisión.

## 6. Orden para llevarlo al código

1. `app/lib/contracts.py` con los modelos y sus tests de las reglas de la sección 3 (va con la tarea 1.5 del roadmap).
2. Adaptador `SourceResult` → `ToolResult`, para no tocar las fuentes de golpe.
3. El especialista guarda el `ToolResult` en `tool_context.state["resultado:<tool>"]` y responde un `SpecialistReport`.
4. Firestore, cuando el roadmap lo pida: `jobs` y `results` primero (envío único y métricas), después `cache`, y al final `offers`, `merchants` y `products` para el catálogo.
