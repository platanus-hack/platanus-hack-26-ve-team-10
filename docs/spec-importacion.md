# Spec: traerlo de USA

Cuando alguien pregunta por un producto, Prais busca en Venezuela **y en paralelo** averigua cuánto costaría comprarlo en Amazon y traerlo con un courier. Si traerlo sale mejor, esa opción compite en la misma lista que las tiendas locales.

Este documento son **definiciones, no implementación**. Fija qué se construye y por qué; el cómo queda para los PRs. El puntaje de confianza está en [contrato-confianza.md](contrato-confianza.md).

## 1. El caso

```
persona: "iphone 15 128"

   ├─► fuentes locales (web abierta, IG, TikTok, ML, Marketplace)
   │      $720 Instagram · $789 web · $810 web
   │
   └─► importación
          Amazon: $589
          ¿se puede traer?  sí, electrónica, 0.8 lb
          ¿vale la pena?    sí, estimado ~$680 < $720 local
          cotiza couriers en paralelo
          mejor: Zoom $94 todo incluido
          → oferta: $683 puesto en Venezuela

ranking
  1. $683  Traerlo de USA · Zoom      (estimado, 7-12 días)
  2. $720  Bodegón La Esquina · IG
  3. $789  Soytechno · Web
```

## 2. Decisiones

| # | Decisión | Qué se eligió | Por qué, en una línea |
|---|---|---|---|
| 1 | Forma del resultado | Una oferta más en el ranking, con el costo puesto en Venezuela | La propuesta de valor es comparar; un bloque aparte obliga a la persona a comparar sola |
| 2 | Modelo de compra | Casillero en Miami: la persona compra en Amazon, el courier trae | Es lo que más se usa en Venezuela y las tarifas existen sin integrar con nadie |
| 3 | Tarifa del courier | Cotizador en vivo, en paralelo, y se guarda en la BD cuando exista | Una tabla fija se desactualiza y el precio de traerlo es la mitad de la cifra |
| 4 | Quién decide | El orquestador rutea; la **tool** decide factibilidad y conveniencia, con código | Rutear es su rol; calcular sobre plata no lo es (regla 6 de AGENTS.md) |
| 5 | Peso | Del listing de Amazon; tabla por categoría como respaldo, marcado como estimado | Cubre la cola larga sin inventar, y cuando el dato es flojo se declara |
| 6 | Impuestos | Manda el cotizador; la tabla solo si cotiza sin impuestos | Prais no modela la ley aduanera, que cambia y no es nuestra |
| 7 | Confianza | Fórmula propia `import-v1`; Amazon y courier entran como señales | Un solo puntaje por oferta, como ya fija el contrato de confianza |
| 8 | Piezas | Una tool `find_listings_importacion`, dueña de todo el flujo | La cotización depende de qué producto de Amazon se eligió: es una cadena, no dos búsquedas |
| 9 | Latencia | Se espera la cotización. **Provisional**, se ajusta con métricas | Primero medir; el roadmap fija los plazos con el log, no a ojo |
| 10 | `priceUsd` | El total puesto en Venezuela; el desglose va en `landed` | El campo que ya ordena el ranking tiene que llevar lo que de verdad se paga |
| 11 | `price_anomaly` | Compara **solo del lado de USA** (mediana del mismo ASIN) | Una importación barata no es sospechosa: es el hallazgo que buscamos |
| 12 | Actores | Dos merchants: `merchantId` (vendedor) + `fulfillerId` (courier) | Los dos tienen riesgo propio y el courier debe acumular reputación entre consultas |
| 13 | Juez | No cambia; se precisa que `referencia` es "producto correcto, en USA" | Separa "¿es el producto?" de "¿se puede traer?" y salva los evals ya medidos |
| 14 | Cuántas ofertas | Una sola, el mejor courier que pase el filtro | El ranking compara productos, no couriers |
| 15 | Campos propios | Todo en `landed`, salvo `priceKind: "estimado"` | Un valor nuevo en un campo que ya existe, cero campos nuevos para los demás canales |
| 16 | Catálogo SEO | Por ahora no; solo consultas de personas | El sitemap ya dispara ~147 búsquedas de golpe: cotizar ahí multiplica el fan-out |
| 17 | Tiendas de USA | Solo Amazon en la v1 | `amazon_trust_score.py` ya está escrito y el juez ya sabe evaluar amazon.com |

## 3. Cómo encaja en lo que hay hoy

Los especialistas **ya no son agentes**: desde el PR #56 son tools de Python que devuelven listados, y el orquestador las llama directo (`app/agents/specialists.py`). La importación entra con ese mismo molde.

```
orquestador (LlmAgent)
  decide si rutear: ¿bien físico comprable en USA?
        │
        ├──► find_listings_open_web          (activa hoy)
        ├──► find_listings_instagram …       (PAUSED_TOOLS)
        └──► find_listings_importacion       ← NUEVA
                 │
                 │  todo esto es código, sin LLM:
                 ├─ 1. buscar en Amazon
                 ├─ 2. filtrar: ¿se puede traer? ¿vale la pena?
                 ├─ 3. cotizar couriers en paralelo
                 └─ 4. componer la oferta
                 │
                 ▼
          { listings: [ListingCard], notice }
```

**La tool es la autoridad.** Si el orquestador llama de más, la tool declina en microsegundos y no cuesta nada. Si llamara de menos, se pierde la oferta y nadie se entera: por eso el filtro vive en la tool y no en el prompt.

El patrón de "tool que se declara no aplicable" ya existe: las tools pausadas devuelven `listings: []` con un `notice`.

## 4. El flujo, paso a paso

| # | Paso | Quién | Qué pasa |
|---|---|---|---|
| 1 | Ruteo | Orquestador (LLM) | ¿Es un bien físico que alguien compraría en USA? Si cree que sí, llama a la tool. Decisión cualitativa y barata |
| 2 | Buscar en Amazon | Tool | Producto, precio, ASIN, vendedor, `fulfillment`, peso y dimensiones del listing |
| 3 | Filtro duro | Tool | Tabla de restricciones por categoría. Si está prohibido, devuelve `listings: []` con el motivo y **no se cotiza** |
| 4 | Peso facturable | Tool | `max(peso real, volumétrico)`. Del listing; si falta, tabla por categoría y se marca `weightSource: "tabla"` |
| 5 | Filtro de conveniencia | Tool | Estimado grueso con una tarifa de referencia. Si no puede acercarse al mejor precio local, **no se cotiza** |
| 6 | Cotizar | Tool | Todos los couriers en paralelo. Los que no respondan se omiten |
| 7 | Componer | Tool | Se arma **una** oferta con el mejor courier. Las demás cotizaciones quedan en el registro |
| 8 | Cerrar la confianza | Agregador | Rellena `price_anomaly` contra la mediana del ASIN y pasa el trust a `stage: "final"` |

Los pasos 2 al 7 no tienen ningún LLM. El 1 es la única decisión de un modelo, y es reversible.

### El costo puesto en Venezuela

```
productUsd     precio del producto en Amazon
+ freightUsd   lo que cotizó el courier por el peso facturable
+ taxUsd       0 si el courier cotizó con impuestos incluidos;
               si no, la tabla configurable sobre el valor
+ insuranceUsd si el courier lo cobra aparte
─────────────
= priceUsd     lo que compite en el ranking
```

Cada sumando guarda de dónde salió. Una cifra sin origen no entra.

## 5. Schema

### La tarjeta que devuelve la tool

`ListingCard` (`app/agents/listing.py`) es la forma común de todos los listados. La importación suma lo suyo sin romper a nadie:

```python
class ListingCard(BaseModel):
    # … los campos de hoy: title, seller, channel, url, price, rate,
    #    reviews, image_url, ships, example, trust, price_usd

    # Nuevos, nulos en los demás canales:
    price_kind: Literal["publicado", "al_dm", "estimado"] = "publicado"
    fulfiller: str | None = None      # nombre del courier
    landed: Landed | None = None
```

### El desglose

```python
class Quote(Model):
    courier_id: str                  # "cur:zoom"
    courier_name: str
    freight_usd: float
    tax_usd: float                   # 0 si va incluido en el flete
    insurance_usd: float = 0
    includes_tax: bool               # qué dijo el cotizador
    eta_days_min: int | None = None
    eta_days_max: int | None = None
    quoted_at: datetime
    source: Literal["cotizador", "tabla"]


class Landed(Model):
    product_usd: float               # el precio en Amazon
    freight_usd: float               # del courier elegido
    tax_usd: float
    insurance_usd: float = 0
    total_usd: float                 # == Offer.price_usd

    billable_lb: float
    weight_source: Literal["listing", "tabla"]
    tax_source: Literal["cotizado", "tabla"]

    eta_days_min: int | None = None
    eta_days_max: int | None = None
    requirements: list[str] = []     # "tarjeta internacional", "casillero en Miami"

    asin: str
    asin_median_usd: float | None = None   # contra esto compara price_anomaly
    quotes: list[Quote] = []         # todas las cotizaciones, no solo la elegida
```

### La oferta completa

```python
Offer
  channel:     "importacion"         # valor nuevo de Channel
  merchant_id: "amz:A2X9K"           # el vendedor de Amazon
  fulfiller_id:"cur:zoom"            # el courier. None en los demás canales
  price_usd:   683                   # el total puesto en Venezuela
  price_kind:  "estimado"            # valor nuevo
  landed:      Landed
  trust:       TrustScore(formula="import-v1", stage="parcial")
  evidence_ids: [...]                # el listing de Amazon y la cotización
```

Los dos actores van en `merchants[]` como `Merchant` normales, cada uno con su `trust`. El courier vive en `merchants/{id}` del store y acumula reputación entre consultas.

**Lo que va en la tarjeta es el resumen.** El costo desglosado y las señales quedan en los datos de la oferta, no en el texto de la tarjeta. Es la misma separación de la decisión 3 del [contrato de confianza](contrato-confianza.md).

## 6. Confianza

### `import-v1`

Un canal más del [contrato](contrato-confianza.md), con su tabla de señales. Los puntajes del vendedor de Amazon y del courier entran como señales, igual que `linked_socials` usa el puntaje de Instagram dentro de una tienda web.

| `family` | `key` | Peso | De dónde sale |
|---|---|---|---|
| `reputacion` | `amazon_seller` | 25 | El `score` de `amazon-v1` del vendedor |
| `reputacion` | `courier_trust` | 20 | El `score` de `courier-v1` del courier elegido |
| `contenido` | `weight_source` | 10 | `listing` = 1 · `tabla` = 0.4 |
| `contenido` | `tax_source` | 10 | `cotizado` = 1 · `tabla` = 0.5 |
| `contenido` | `eta_spread` | 5 | Rango de entrega estrecho y declarado = 1; sin dato = `None` |
| `precio` | `price_anomaly` | 20 | **Contra la mediana del mismo ASIN**, nunca contra el mercado venezolano |
| `reportes` | `reports` | 10 | Hoy `None`: no hay forma de reportar |

Banderas rojas: vendedor de Amazon con bandera roja propia, courier con bandera roja propia, o producto más de 50 % bajo la mediana de su ASIN.

**`price_anomaly` nunca mira el precio venezolano.** Que el total salga mucho más barato que en Venezuela no es señal de fraude: es el resultado que la feature existe para encontrar, y ya se ve solo porque `priceUsd` compite en el ranking.

### `courier-v1` — propuesta, falta confirmar

Es el único hueco conceptual que quedó abierto. Esta tabla es una propuesta, no una decisión:

| `family` | `key` | Peso | De dónde sale |
|---|---|---|---|
| `identidad` | `years_operating` | 15 | Años operando la ruta Miami–Venezuela |
| `identidad` | `rif` | 10 | RIF publicado y oficinas en Venezuela |
| `reputacion` | `public_reviews` | 20 | Reseñas públicas (Google, redes) |
| `contenido` | `tracking` | 15 | Ofrece rastreo y seguro declarados |
| `contenido` | `rate_published` | 10 | Publica su tarifa, o solo cotiza por privado |
| `tecnico` | `quote_reliability` | 15 | Qué tan seguido responde el cotizador y en cuánto |
| `riesgo` | `risk_language` | 5 | Los mismos 3 patrones de los otros canales |
| `reportes` | `reports` | 10 | Hoy `None` |

Como los couriers son pocos y se repiten, su puntaje se calcula una vez y se guarda, no en cada consulta.

## 7. El filtro

### Factibilidad: qué no se trae

Tabla determinista por categoría. No se cotiza, y la tool devuelve el motivo. Punto de partida a confirmar con quien sepa de aduana:

| Motivo | Ejemplos |
|---|---|
| Restringido o prohibido | Medicamentos, alimentos perecederos, líquidos, baterías de litio sueltas, armas |
| No tiene sentido económico | Víveres, productos de limpieza, cualquier cosa que pese mucho y valga poco |
| Peso o volumen fuera de rango | Electrodomésticos grandes, cauchos, muebles |

### Conveniencia: cuándo vale la pena cotizar

Antes de gastar en el cotizador, un estimado grueso con una tarifa de referencia:

```
estimado ≈ productUsd + (billableLb × tarifa_referencia) + impuesto_referencia

si estimado > mejor_precio_local × (1 + margen):  no se cotiza
```

El `margen` y la `tarifa_referencia` son parámetros a fijar con datos reales. Si todavía no hay ofertas locales con qué comparar, **se cotiza igual**: importar puede ser la única opción.

## 8. Lo que queda abierto

| # | Qué falta | Quién decide |
|---|---|---|
| 1 | Confirmar las señales y pesos de `courier-v1` (sección 6) | Producto + quien implemente la confianza |
| 2 | El `margen` y la `tarifa_referencia` del filtro de conveniencia | Con datos reales de las primeras corridas |
| 3 | La lista concreta de couriers y cómo cotiza cada uno | Quien implemente la tool |
| 4 | La tabla de restricciones, validada con alguien que sepa de aduana | Producto |
| 5 | La tabla de impuestos, para cuando el courier cotice sin ellos | Producto |
| 6 | Revisar la decisión 9 (esperar la cotización) con métricas reales | Con el log de latencia |
| 7 | Reabrir el catálogo SEO (decisión 16) cuando exista la BD de cotizaciones | Producto |

## 9. Tareas

Ninguna depende de infraestructura nueva. Cada una entra en su propio PR.

| # | Tarea | Archivos | Listo cuando | Depende de |
|---|---|---|---|---|
| 1 | **Fuente Amazon**: buscar un producto y traer ASIN, precio, vendedor, `fulfillment`, peso y dimensiones | `lib/sources/amazon.py` | Devuelve el producto real con su peso | `APIFY_TOKEN` |
| 2 | **Tabla de factibilidad** y el filtro duro | `lib/importacion/factibilidad.py` | Medicinas y víveres nunca se cotizan | — |
| 3 | **Peso facturable**: del listing, con respaldo por categoría | `lib/importacion/peso.py` | Declara siempre de dónde salió el peso | 1 |
| 4 | **Cotizadores**: uno por courier, en paralelo, con su plazo | `lib/importacion/couriers/` | Al menos 2 couriers cotizan de verdad | — |
| 5 | **Costo puesto en Venezuela** y la composición de la oferta | `lib/importacion/landed.py` | Cada sumando guarda su origen | 1, 3, 4 |
| 6 | **Tool `find_listings_importacion`** con el flujo completo | `agents/specialists.py` | El orquestador la llama y recibe la tarjeta | 2, 5 |
| 7 | **`import-v1`** en el motor de confianza | `lib/trust.py` | La oferta trae su `TrustScore` en `parcial` | `lib/trust.py` |
| 8 | **`courier-v1`**, calculado una vez y guardado | `lib/trust.py` | Cada courier tiene su puntaje | 7, abierto 1 |
| 9 | **Campos nuevos**: `channel: "importacion"`, `price_kind: "estimado"`, `fulfiller_id`, `landed` | `lib/types.py`, `agents/listing.py` | **Cambia contrato: avisar antes de mergear** | — |
| 10 | **Guardar las cotizaciones** cuando exista la BD | — | Alimenta el catálogo y la cache | BD |

**Orden sugerido:** 1 y 2 primero, que son independientes y baratas. Después 3 → 4 → 5 → 6, que es la cadena. La confianza (7 y 8) puede ir en paralelo desde que exista `lib/trust.py`.

**Hito de la v1:** preguntas por un iPhone por WhatsApp y, si traerlo de USA sale mejor, esa opción aparece en el carrusel junto a las tiendas venezolanas, con su desglose y su puntaje.
