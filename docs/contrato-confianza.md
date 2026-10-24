# Contrato de confianza: qué entrega cada especialista

Kickoff de la feature de *trust scoring*. Define **un solo schema** que todos los especialistas llenan, aunque cada fuente mida cosas distintas, y qué hace el orquestador con eso.

Complementa [tool-result.md](tool-result.md) (el `ToolResult` completo) y [handoff-orquestador.md](handoff-orquestador.md) (el pipeline). Las señales, los pesos y las fórmulas de cada canal **no se repiten aquí**: viven en `resources/*_trust_score.py`, para que no se desincronicen.

Es una **propuesta de contrato**: cambia `app/lib/types.py`, así que se avisa al equipo antes de mergear ([plan.md](plan.md)).

## 1. El problema que resuelve

Instagram mide likes por seguidor. Mercado Libre mide el termómetro del vendedor. Una tienda web mide la antigüedad del dominio. **No comparten ni una sola señal.** Aun así, el orquestador tiene que poder ordenar siete fuentes en una sola respuesta y decir "este vendedor es confiable y este no".

La solución no es obligar a todos a medir lo mismo. Es que todos entreguen **la misma caja con los mismos compartimientos**, y que `coverage` se encargue de que venir con compartimientos vacíos no castigue a nadie.

## 2. Decisiones tomadas

| # | Decisión | Qué se eligió | Qué se descartó |
|---|---|---|---|
| 1 | Quién calcula el puntaje | **El especialista calcula sus señales; el orquestador rellena las que requieren ver todo junto y cierra el puntaje** | Que el especialista cierre (no conoce la mediana) o que el orquestador haga todo (7 canales en un solo lugar) |
| 2 | Señales exclusivas de cada fuente | **`family` (enum cerrado de 8) + `key` libre por canal** | Claves libres (incomparables) o un enum global con las ~60 claves (rígido) |
| 3 | Quién recibe qué | **El agregador recibe todo; el redactor solo lo necesario para contestar; el registro completo queda listo para el agente de almacenamiento** | Un solo payload para todos |
| 4 | Señales sin dato | **`value: "pending"`** si la va a llenar el orquestador, **`value: null`** si nadie la va a llenar | Omitirlas, o un solo `null` para los dos casos |
| 5 | Dónde vive el puntaje | **En la oferta** (`Offer.trust`) | En el comercio: Facebook perdería 45 de 100 puntos, que son del anuncio |
| 6 | Vendedor en varios canales | **Se resuelve la identidad** (`MerchantIdentity`) y los canales quedan enlazados | Tratarlos como vendedores distintos sin relación |
| 7 | Escala | **0–100 interno, 0–5 de cara a la persona** | Una sola escala para los dos lados |
| 8 | Evidencia | **Obligatoria para el precio; opcional por señal** | Obligatoria en todo (infla) o en nada (no se audita) |

**Fuera de alcance:** cómo viajan los datos del especialista al orquestador (estado de ADK, retorno directo…). Este contrato define **qué** datos, no por dónde pasan. Lo resuelve quien implemente.

## 3. El recorrido

El orquestador son dos mitades, y confundirlas es el error más fácil de cometer:

```
Especialista IG  ──► ToolResult ──┐
Especialista ML  ──► ToolResult ──┤
Especialista web ──► ToolResult ──┤
  (trust stage="parcial")         │
                                  ▼
                        AGREGADOR  (código, no LLM)
                        lee TODO, hace 4 pasadas
                                  │
                                  ├──► AnswerPayload ──► REDACTOR (LLM)
                                  │    solo lo que hace falta    responde
                                  │    para contestar
                                  │
                                  └──► ToolResult completo ──► agente de
                                       (trust stage="final")    almacenamiento
                                                                (todavía no se implementa)
```

### Las 4 pasadas del agregador

El orden importa: **no es una pasada plana**.

| # | Pasada | Por qué va en ese orden |
|---|---|---|
| 1 | Mediana de precio, grupos de fotos repetidas, identidad del comercio | Necesita **todas** las tools de vuelta |
| 2 | Cierra `instagram`, `tiktok`, `facebook`, `mercadolibre`, `amazon` | Ya tiene todo lo que necesitan |
| 3 | Cierra `web` | Su señal `linked_socials` usa los puntajes de IG y TikTok de la pasada 2 |
| 4 | Aplica los ajustes de Meta Ads sobre IG, Facebook y TikTok | Meta Ads no da puntaje propio: suma o resta sobre uno ya cerrado |

## 4. Modelos

Pydantic 2, en `app/lib/contracts.py`, con la clase `Model` de [tool-result.md](tool-result.md) (JSON en camelCase, Python en `snake_case`, `extra="forbid"`).

```python
SignalFamily = Literal[
    "identidad",    # ¿existe hace rato y es quien dice ser?
    "reputacion",   # ¿qué dice la plataforma de él?
    "interaccion",  # ¿su audiencia es real?
    "contenido",    # ¿el anuncio está bien hecho?
    "tecnico",      # infraestructura: HTTPS, correo del dominio, listas negras
    "riesgo",       # lenguaje sospechoso
    "precio",       # ¿es demasiado bueno para ser verdad?
    "reportes",     # lo que Prais sabe de él
]

TrustVerdict = Literal["confiable", "precaucion", "riesgosa", "sin_datos"]
TrustStage = Literal["parcial", "final"]
SignalValue = float | Literal["pending"] | None


class TrustSignal(Model):
    """Un ladrillo del puntaje. Todas las señales del canal van en la lista,
    midan o no: el orquestador necesita saber cuánto peso quedó sin medir."""
    family: SignalFamily
    key: str                      # "age", "thermometer": propia del canal, única dentro de él
    weight: float                 # fijo por canal; los pesos de un canal suman 100
    value: SignalValue            # 0..1 medido · "pending" lo llena el orquestador · None nadie lo llenará
    reason: str | None = None     # texto citable: "Cuenta con 2.5 años"
    good: bool | None = None      # para pintarlo en verde o en rojo
    evidence_id: str | None = None


class Adjustment(Model):
    """Una capa que no puntúa sola: corrige un puntaje ya calculado. Hoy, Meta Ads."""
    source: str                   # "meta-ads"
    bonus: float = Field(ge=0, le=5)
    penalty: float = Field(ge=0, le=15)
    reasons: list[str] = []
    red_flags: list[str] = []


class TrustScore(Model):
    score: int | None = Field(default=None, ge=0, le=100)   # None si no alcanza la cobertura
    coverage: float = Field(ge=0, le=1)                     # peso medido / peso total del canal
    verdict: TrustVerdict
    stage: TrustStage                                       # "parcial" sale del especialista
    red_flags: list[str] = []                               # una sola deja el puntaje en 0
    reasons: list[str] = []                                 # ordenadas por gravedad
    signals: list[TrustSignal] = []                         # SIEMPRE la lista completa del canal
    adjustments: list[Adjustment] = []
    formula: str                                            # "ig-v1": qué borrador corrió
    computed_at: datetime


class MerchantLink(Model):
    """Una red o dominio que el propio comercio declara. Insumo de la identidad."""
    kind: Literal["instagram", "tiktok", "facebook", "whatsapp", "dominio", "rif"]
    value: str                    # normalizado: sin @, sin https://, solo dígitos en teléfonos


class Merchant(Model):
    id: str                       # con prefijo de fuente: "ig:bodegon", "ml:12345", "web:tiendax.com.ve"
    entity_id: str | None = None  # el vendedor real detrás; lo llena el agregador
    name: str
    channel: Channel
    url: str
    location: Location | None = None
    delivers: bool | None = None
    links: list[MerchantLink] = []
    facebook_page_id: str | None = None   # habilita el ajuste de Meta Ads
    source_data: dict = {}        # lo crudo y exclusivo de la fuente. NUNCA entra al cálculo
    trust: TrustScore | None = None       # opcional: el puntaje que manda está en la oferta


class Offer(Model):
    id: str                       # sha256(fuente + url canónica + variante)[:24]
    merchant_id: str
    product: CanonicalProduct     # product.key agrupa las ofertas para sacar la mediana
    condition: Condition          # un usado barato NO es anomalía de precio
    title: str
    url: str
    image_url: str | None = None  # insumo del hash de fotos repetidas
    price: Money | None = None    # None ⇔ price_kind == "al_dm"
    price_kind: Literal["publicado", "al_dm"] = "publicado"
    seen_at: datetime
    evidence_ids: list[str] = Field(min_length=1)   # al menos la del precio
    trust: TrustScore             # "parcial" al salir del especialista
    # Los llena el agregador:
    price_usd: float | None = None
    price_ves: float | None = None
    rate_used: RateRef | None = None
    judge: Judgement | None = None


class MerchantIdentity(Model):
    """El vendedor real detrás de varios merchant_id. Lo arma el agregador."""
    entity_id: str                # sha256 de la evidencia más fuerte disponible
    members: list[str]            # los merchant_id que se unieron
    method: Literal["rif", "dominio", "declarado", "telefono", "handle", "manual"]
    confidence: float = Field(ge=0, le=1)


class PriceStat(Model):
    product_key: str
    condition: Condition          # un usado no se compara contra nuevos
    median_usd: float
    comparables: int              # mínimo 5; con menos, price_anomaly baja a None
    sources: list[str]


# ── Lo que lee el redactor: solo para contestar ──────────────────────────────

class OfferCard(Model):
    offer_id: str
    title: str
    url: str
    price_display: str | None     # "USD 789" o "Bs.S 31.560,00", ya formateado
    price_usd: float | None
    rate_note: str | None         # "200 Bs/USD (BCV, 2026-10-24)" si hubo conversión
    seen_at: datetime
    merchant_name: str
    channel: Channel
    city: str | None
    delivers: bool | None
    trust_score: int | None       # 0..100. None = sin datos
    trust_stars: int | None       # 0..5, lo que se le dice a la persona
    trust_verdict: TrustVerdict
    trust_reasons: list[str] = Field(max_length=3)   # las 3 más graves
    trust_red_flags: list[str] = []
    is_example: bool              # viene de datos de ejemplo: hay que decirlo
    rank: int


class AnswerPayload(Model):
    job_id: str
    product_label: str            # "iPhone 15 128 GB nuevo"
    cards: list[OfferCard] = Field(max_length=5)
    best: OfferCard | None
    median_usd: float | None      # para decir "está 12% bajo el promedio"
    comparables: int
    failed_tools: list[str]
    notice: str | None
```

El `source_data` y la lista completa de `signals` **no viajan** en el `AnswerPayload`. El redactor no los necesita y, si los tuviera, los copiaría mal. Quedan en el `ToolResult`, listos para el agente de almacenamiento.

## 5. El catálogo de señales

Las 8 familias cubren las ~60 claves de los 7 canales. **Instagram y Mercado Libre no comparten ni una clave, pero los dos reportan `identidad` y `reputacion`**: eso es lo que hace comparable el schema.

| `family` | Instagram | TikTok | Facebook Mktp | Mercado Libre | Tienda web | Amazon |
|---|---|---|---|---|---|---|
| `identidad` | `age` 15 · `username_changes` 5 · `country` 5 | `age` 15 · `region` 5 | `fb_age` 15 · `location` 5 | `account_age` 10 · `location` 5 | `domain_age` 15 | — |
| `reputacion` | — | — | *(bonus +10)* | `thermometer` 15 · `power_seller` 5 · `sales_volume` 10 · `negative_ratings` 10 | — | `fulfillment` 15 · `positive_feedback` 20 · `ratings_volume` 10 · `recent_activity` 10 |
| `interaccion` | `engagement` 15 · `consistency` 10 · `comment_like_ratio` 5 · `comment_quality` 10 · `posting_rhythm` 5 | `like_view_ratio` 15 · `ratio_consistency` 5 · `hearts_per_follower` 5 · `comment_quality` 10 · `shares_saves` 5 · `posting_rhythm` 5 | — | — | — | — |
| `contenido` | — | — | `history` 20 · `photos_original` 20 · `completeness` 5 | `completeness` 5 · `warranty` 5 | `contact` 10 · `policies` 10 · `catalog` 5 | `alert_reviews` 10 · `product_history` 5 |
| `tecnico` | — | — | — | — | `https` 5 · `mx` 5 · `safe_browsing` 5 · `linked_socials` 10 | — |
| `riesgo` | `risk_language` 10 | `risk_language` 5 | `risk_language` 5 | `risk_language` 5 | `risk_language` 5 | — |
| `precio` | `price_anomaly` 15 | `price_anomaly` 20 | `price_anomaly` 20 | `price_anomaly` 20 | `price_anomaly` 20 | `price_anomaly` 20 |
| `reportes` | `reports` 5 | `reports` 10 | `reports` 10 | `reports` 10 | `reports` 10 | `reports` 10 |
| | **`ig-v1`** | **`tiktok-v1`** | **`fb-v1`** | **`ml-v1`** | **`web-v1`** | **`amazon-v1`** |

Meta Ads no aparece: no tiene `formula` ni señales propias. Produce un `Adjustment` (`meta-ads`) que se aplica sobre IG, Facebook o TikTok.

### Quién llena qué

| Señal | La llena | Cómo |
|---|---|---|
| Todas menos las de abajo | **el especialista** | Con lo que trajo su fuente ([sources.md § Datos que el puntaje necesita](../agents/sources.md#datos-que-el-puntaje-necesita)) |
| `price_anomaly` | **el agregador**, pasada 1–2 | `(precio − mediana) / mediana` del mismo `product_key` + `condition`, con **≥5 comparables** |
| `photos_original` (Facebook) | **el agregador**, pasada 1–2 | Hash perceptual de `image_url`: en cuántos `entity_id` distintos aparece la misma foto |
| `linked_socials` (web) | **el agregador**, pasada 3 | El mejor puntaje de las redes enlazadas del mismo `entity_id` |
| `reports` | **nadie, hoy** | No hay forma de reportar todavía: sale `None`, no `"pending"` |

Si el especialista no sabe llenar una señal que le toca, va `None`. Si le toca al agregador, va `"pending"`.

## 6. Reglas de cálculo

Son las de `resources/*_trust_score.py`, sin cambios. Se escriben una sola vez en `app/lib/trust.py` y sirven para los siete canales.

### Cobertura

```
medido   = suma de los weight de las señales con value float
total    = suma de todos los weight del canal  (siempre 100)
coverage = medido / total
```

`"pending"` y `None` **no cuentan como medidas**. El denominador es siempre el total del canal, así que en `stage="parcial"` la cobertura se ve baja: es esperado y es informativo.

### Puntaje

```
score = 100 × Σ(weight × value) / Σ(weight)     ← solo las señales con value float
```

Las señales sin dato **no restan**: se dividen entre el peso medido, no entre 100. Quien no tiene datos no es castigado, solo medido con menos certeza. Después se aplican los ajustes:

```
score_final = clamp(score + Σbonus − Σpenalty, 0, 100)
```

### Banderas rojas

Cortocircuitan todo: `score = 0`, `verdict = "riesgosa"`, sin promediar. Las de cada canal están en su borrador. Un `red_flag` que venga en un `Adjustment` también cortocircuita.

### Veredicto

| Condición | `verdict` |
|---|---|
| Hay bandera roja | `riesgosa` (score 0) |
| `coverage < 0.40` | `sin_datos` (score `null`) |
| `score >= 75` | `confiable` |
| `score >= 50` | `precaucion` |
| resto | `riesgosa` |

**La puerta de 0,40 solo se evalúa en `stage="final"`.** En `parcial` el puntaje siempre sale `null` y el veredicto `sin_datos`: el especialista no cierra nada.

### Atajos

| Caso | Qué pasa |
|---|---|
| Amazon vende y envía el propio Amazon | `score = 95`, `coverage = 1`, `confiable`, sin calcular señales |
| Facebook Marketplace con calificaciones o insignias | Bonus de hasta **+10** sobre el puntaje base. Nunca resta: quien no tiene calificaciones (casi todos en Venezuela) no pierde nada |

### Cerrar el puntaje

Al pasar a `stage="final"`:

1. Toda señal `"pending"` que el agregador **sí** pudo llenar pasa a `float`.
2. Toda señal `"pending"` que **no** pudo llenar (menos de 5 comparables, no hubo fotos…) **baja a `None`**.
3. Se recalcula cobertura, puntaje, banderas y veredicto.
4. **Un `TrustScore` con `stage="final"` no puede tener ni un `"pending"`.** Es un error de programación: falla el test.

## 7. Identidad del comercio

Un bodegón con Instagram y tienda web son dos `merchant_id` y dos puntajes. Son el mismo vendedor. El agregador los une en un `entity_id`.

| `method` | Evidencia | `confidence` |
|---|---|---|
| `rif` | Mismo RIF publicado | 1.00 |
| `dominio` | Mismo dominio registrable | 0.90 |
| `declarado` | A enlaza a B **y** B enlaza a A | 0.90 |
| `telefono` | Mismo teléfono normalizado | 0.80 |
| `declarado` | Solo una dirección (A enlaza a B) | 0.60 |
| `handle` | Mismo @ en dos plataformas | 0.50 |

- **Se unen desde `confidence >= 0.70`.** Por debajo quedan separados y el candidato se registra, sin efecto en el puntaje.
- `handle` solo nunca alcanza para unir: `@ventasve` existe en todas las plataformas y es de gente distinta.
- **Los puntajes de canales unidos no se promedian.** Cada canal conserva el suyo; la identidad solo habilita `linked_socials` y poder decirle a la persona "el mismo vendedor también está en Instagram con 82".
- Un comercio sin pareja es un `entity_id` de un solo miembro. No hay caso especial.

## 8. De cara a la persona: 0–5

Interno es 0–100. Lo que se muestra son estrellas, porque es lo que espera el design system (`Oferta.confianza`, 0 a 5). La conversión vive en **una sola función**, `app/lib/trust.py: to_stars()`:

| `score` | Estrellas | `verdict` |
|---|---|---|
| 90–100 | 5 | `confiable` |
| 75–89 | 4 | `confiable` |
| 60–74 | 3 | `precaucion` |
| 50–59 | 2 | `precaucion` |
| 1–49 | 1 | `riesgosa` |
| 0 (bandera roja) | 0 | `riesgosa` |
| `null` | sin estrellas (`undefined`) | `sin_datos` |

Los cortes caen en 75 y 50, los mismos del veredicto: las estrellas nunca contradicen el texto.

**Hay que corregir `_confianza_texto()` en `app/lib/catalogo.py`**, que hoy corta en 70/50 en vez de 75/50.

El orquestador le habla a la persona con el **número de 0 a 100** (así lo pide su instrucción actual) y la web pinta estrellas. Las dos cosas salen del mismo `score`.

## 9. Validaciones

| Regla | Si no se cumple |
|---|---|
| Los `weight` de un canal suman 100 | Error de programación: falla el test |
| Toda señal tiene `family` del enum y `key` único dentro del canal | Igual |
| `stage="final"` no tiene ninguna señal en `"pending"` | Igual |
| `score is None` ⇔ `verdict == "sin_datos"` ⇔ `coverage < 0.40` (salvo bandera roja) | Igual |
| `red_flags` no vacío ⇒ `score == 0` y `verdict == "riesgosa"` | Igual |
| `evidence_ids` tiene al menos la evidencia del precio | La oferta se descarta y se anota un error `parseo` |
| `signal.evidence_id`, si existe, está en `evidence` | Igual |
| `source_data` no se lee en ningún cálculo | Revisión de código |
| `price_anomaly` solo compara contra la mediana de la misma `condition` | Igual |

## 10. Ejemplo

Dos especialistas que no comparten ni una clave, y el agregador cerrando los dos.

```jsonc
// Instagram, stage "parcial"
{ "offerId": "a41e…", "merchantId": "ig:bodegon",
  "trust": {
    "stage": "parcial", "score": null, "verdict": "sin_datos",
    "coverage": 0.70, "formula": "ig-v1",
    "signals": [
      { "family": "identidad",   "key": "age",           "weight": 15, "value": 0.93,
        "good": true,  "reason": "Cuenta con 2.5 años" },
      { "family": "interaccion", "key": "engagement",    "weight": 15, "value": 0.00,
        "good": false, "reason": "Muy poca interacción para 18.500 seguidores" },
      { "family": "identidad",   "key": "country",       "weight": 5,  "value": null },
      { "family": "precio",      "key": "price_anomaly", "weight": 15, "value": "pending" },
      { "family": "reportes",    "key": "reports",       "weight": 5,  "value": null }
      // … el resto del canal
    ]
  }
}

// Mercado Libre, stage "parcial" — ni una clave en común, mismas familias
{ "offerId": "b77c…", "merchantId": "ml:12345",
  "trust": {
    "stage": "parcial", "score": null, "verdict": "sin_datos",
    "coverage": 0.65, "formula": "ml-v1",
    "signals": [
      { "family": "reputacion", "key": "thermometer",   "weight": 15, "value": 1.00,
        "good": true, "reason": "Reputación verde con 340 ventas" },
      { "family": "identidad",  "key": "account_age",   "weight": 10, "value": 0.88 },
      { "family": "precio",     "key": "price_anomaly", "weight": 20, "value": "pending" },
      { "family": "reportes",   "key": "reports",       "weight": 10, "value": null }
      // … el resto del canal
    ]
  }
}
```

El agregador saca la mediana (`$789` con 6 comparables), llena los dos `price_anomaly`, recalcula y cierra:

```jsonc
{ "offerId": "b77c…", "trustScore": 82, "trustStars": 4, "trustVerdict": "confiable" }
{ "offerId": "a41e…", "trustScore": 49, "trustStars": 1, "trustVerdict": "riesgosa",
  "trustReasons": ["Precio 43% bajo el mercado",
                   "Muy poca interacción para 18.500 seguidores"] }
```

## 11. Qué falta para implementar

| # | Tarea | Archivos | Listo cuando |
|---|---|---|---|
| 1 | **`app/lib/trust.py`**: el motor común (cobertura, banderas, veredicto, ajustes, `to_stars`) y sus tests | `lib/trust.py` | Los siete canales lo usan sin ramificaciones |
| 2 | **`app/lib/contracts.py`**: los modelos de la sección 4 y las validaciones de la 9 | `lib/contracts.py` | Los tests de las reglas pasan |
| 3 | **Un paso determinista entre los especialistas y la respuesta.** Hoy no existe: el orquestador es un `LlmAgent` con `AgentTool` y entre que vuelven los especialistas y que habla no corre código nuestro | `app/agents/` | Las 4 pasadas de la sección 3 corren sobre datos reales |
| 4 | **Portar un canal de punta a punta** (sugerido: Mercado Libre, que no depende de otros) | `lib/sources/`, `lib/trust.py` | Una oferta real llega con `stage="final"` y su veredicto |
| 5 | **Campos nuevos en `Merchant`** para los datos crudos de cada fuente | `lib/types.py` | **Cambia contrato: avisar antes de mergear** |
| 6 | **Hash perceptual de fotos** | `lib/trust.py`, `requirements.txt` | `photos_original` se puede llenar. Son 20 de los 100 puntos de Facebook |
| 7 | **Corregir los umbrales del catálogo** de 70/50 a 75/50 | `lib/catalogo.py` | El texto no contradice al veredicto |
| 8 | **`amazon` como `Channel`** | `lib/types.py` | `tool-result.md` ya lo incluye; `types.py` todavía no |
| 9 | **Resolución de identidad** (sección 7) | `lib/trust.py` | `linked_socials` se puede calcular |

**Orden sugerido:** 1 y 2 primero (son la base y no dependen de nadie), después 3, y recién ahí 4. Los demás, por PR, cuando su canal lo pida.

### Lo que este contrato no cubre

- **Cómo viajan los datos** al orquestador: lo decide quien implemente.
- **El agente de almacenamiento.** El `ToolResult` completo queda listo para él, pero no se implementa todavía.
- **`reports`.** No hay forma de reportar un vendedor: la señal existe en el schema y sale `None`.
- **La persistencia** entre consultas, que es lo que haría posible `reports` y las fotos repetidas históricas. Según el [roadmap](handoff-orquestador.md#13-roadmap), entra cuando las métricas la pidan.
