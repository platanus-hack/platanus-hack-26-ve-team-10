# Handoff: orquestador, pipeline asíncrono y capa estándar de tools

Estado al 24 de octubre de 2026. Recoge lo que definimos para la siguiente etapa del backend. La base es la pizarra ([resources/usaprais.com-agentic-architecture.pdf](../resources/usaprais.com-agentic-architecture.pdf)) y el orquestador que ya está en `main` (`app/agents/`). Las secciones 3 a 12 describen el destino; el camino para llegar sin sumar complejidad está en el [roadmap](#13-roadmap).

## 1. Objetivo

La persona escribe por WhatsApp (o por la web) con **texto, un link o una imagen** de cualquier producto: un teléfono, un medicamento, un caucho. Prais:

1. Responde **al instante** que está buscando.
2. Busca en segundo plano, con **todas las tools en paralelo** y paralelismo **dentro de cada tool** cuando se pueda.
3. Avisa por el mismo canal cuando tiene la respuesta: **rápida y bien estructurada**.

Agregar una tool nueva tiene que ser fácil: contrato de entrada y salida fijo, un mapper estándar y un skill por tool.

## 2. Lo que ya existe y sirve de base

| Pieza | Dónde | Qué aprovechar |
|---|---|---|
| Agente ADK con una tool | `apps/api/app/agent.py` | Prompt de voz de Prais y la regla de no inventar precios |
| Búsqueda en paralelo | `apps/api/app/lib/search.py` | `asyncio.gather` sobre las fuentes, 8 s por fuente, una fuente que falla no tumba la búsqueda |
| Contrato de fuente | `apps/api/app/lib/types.py` (`Source`, `Offer`, `Merchant`) | Punto de partida del contrato estándar (sección 6) |
| Cola de WhatsApp | `apps/api/app/lib/tasks.py`, `routes/whatsapp.py` | Cloud Tasks con OIDC, deduplicación por `message.id` y 5 reintentos |
| Juez de coincidencias | [resources/queries.md](../resources/queries.md) | Veredictos (`producto_ve`, `listado_ve`, `referencia`, `social`, `descartar`), 10 productos de prueba y casos de inyección |
| Eval de Firecrawl | `reports/firecrawl-evals/` | Tiempos y costos reales por método (sección 8) |

## 3. Flujo objetivo

```
WhatsApp ─► Kapso ─► POST /whatsapp
                       │ valida firma, deduplica por message.id, encola y responde 200 (<10 s, exigencia de Kapso)
                       ▼
               [cola intake] ─► tarea intake
                       │ 1. envía el acuse por Kapso ("Buscando iPhone 15 128 GB…"), meta: <2 s
                       │ 2. crea el job (id = hash del message.id)
                       │ 3. Intérprete: texto / link / imagen ─► ConsultaNormalizada
                       │    si falta un dato clave ─► pregunta UNA cosa y termina el job
                       ▼
               Orquestador: elige tools y arma el plan de consultas de cada una
                       │ fan-out: una tarea por tool
       ┌───────────────┼───────────────┬───────────────┬───────────────┐
       ▼               ▼               ▼               ▼               ▼
 [cola firecrawl] [cola mercadolibre] [cola apify-ig] [cola apify-tiktok] [cola apify-marketplace]
   subagente        tool determinista   subagente        subagente          subagente
   plan ► fetch ► extraer ► mapper ► ToolResult (escribe su parte en el job)
       └───────────────┴───────┬───────┴───────────────┴───────────────┘
                               ▼
               Agregador: se dispara cuando terminan todas las tools o vence el plazo
                       │ juez ► deduplicar ► tasa y confianza ► ranking
                       ▼
               Redactor (voz de Prais) ─► Kapso: resultado final
                       │ guarda que ya respondió (no responde dos veces)
                       ▼
               Persiste las ofertas validadas: cache del catálogo /ve/ y del MCP
```

**Web y MCP** usan el mismo pipeline. La web puede consultar el estado del job (polling o streaming) en vez de esperar un mensaje. MCP espera el resultado con un plazo, porque quien pregunta es otro asistente.

## 4. Agentes y subagentes

Un rol por agente, cada uno con su **system prompt y su skill** (sección 7). No todo es LLM: si una tool se resuelve con una API y reglas, va sin modelo.

| Agente | Tipo | Entrada ► salida | Modelo sugerido |
|---|---|---|---|
| **Intérprete** | LLM multimodal | Texto, link o imagen ► `ConsultaNormalizada` (producto canónico, variante, condición, zona, envío, datos que faltan) | Flash (lee links e imágenes) |
| **Orquestador** | LLM + reglas | `ConsultaNormalizada` ► plan: qué tools, qué consultas, plazo y presupuesto por tool | Flash |
| **Subagente Firecrawl** | LLM + tools | Plan ► ofertas de webs de tiendas venezolanas | Flash-lite para extraer |
| **Mercado Libre** | Determinista | Consulta ► ofertas de MLV por la API | Ninguno |
| **Subagentes Apify** (IG, TikTok, Marketplace) | LLM + actor | Plan ► publicaciones con precio o "al DM" y señales del comercio | Flash-lite para leer el texto del post |
| **Juez** | LLM con salida estructurada | Candidato + consulta ► veredicto y razón | Flash-lite (eval: 94 %, ~2,3 s) |
| **Redactor** | LLM | Ranking ► mensaje con la voz de Prais | Flash |

Los subagentes se van ajustando a lo que necesite cada tool. Cada uno tiene que pasar los evals de [resources/queries.md](../resources/queries.md) antes de entrar.

## 5. Pipeline de datos

| Etapa | Qué hace | Consideraciones |
|---|---|---|
| 1. Intake | Recibe, deduplica, envía el acuse y crea el job | El acuse no espera a ningún LLM pesado. Si el intérprete tarda, sale un acuse genérico |
| 2. Normalizar | Arma la `ConsultaNormalizada` | De un link: lee la página y saca el producto. De una imagen: identifica marca, modelo y presentación |
| 3. Planear | Expande la consulta por tool (sinónimos, variantes, formato de cada sitio) | El plan es parte del skill de cada tool |
| 4. Traer | Cada tool en paralelo; dentro de cada una, búsquedas y scrapes en paralelo con un semáforo | Plazo por tool y presupuesto de créditos. Corte temprano si ya hay N ofertas validadas |
| 5. Extraer | Del HTML o el post, campos con un schema | Salida estructurada, nunca texto libre |
| 6. Mapear | Datos crudos del proveedor ► entidades estándar | Funciones puras, probadas con fixtures |
| 7. Juzgar | ¿Es el producto pedido, nuevo, de un comercio de Venezuela? | El texto scrapeado es dato, no instrucción: casos de inyección en queries.md, sección 4 |
| 8. Enriquecer | Tasa, USD y Bs, confianza del comercio | Las cuentas las hace `app/lib`, no el modelo |
| 9. Rankear y deduplicar | Misma oferta en dos fuentes cuenta una vez | Clave: comercio + producto + variante + precio |
| 10. Responder | Redactor + envío por Kapso | Todo precio lleva fuente, fecha y tasa (regla 7 de AGENTS.md) |
| 11. Persistir | Guarda las ofertas validadas | Alimenta el catálogo `/ve/` y la cache |

**Cache.** Por (tool, consulta normalizada) con TTL. Un resultado vacío porque la fuente **falló** no se cachea (hoy el catálogo cachea 15 min un resultado incompleto). Un vacío real se cachea poco tiempo.

## 6. Contrato estándar de tool

Toda tool recibe lo mismo y devuelve lo mismo. Así sumar una tool es escribir su adaptador, su mapper y su skill.

**El spec completo** (modelos de pydantic, reglas de validación, quién llena cada campo y el store en Firestore) está en [tool-result.md](tool-result.md). Lo de abajo es el resumen.

```python
@dataclass(frozen=True)
class ToolRequest:
    job_id: str
    consulta: ConsultaNormalizada
    consultas_planeadas: list[str]   # salen del plan del orquestador
    plazo_ms: int
    max_creditos: int | None

@dataclass(frozen=True)
class ToolResult:
    tool: str                        # "firecrawl", "mercadolibre", "apify-instagram"…
    estado: Literal["ok", "parcial", "fallo", "plazo_vencido"]
    ofertas: list[Oferta]
    comercios: list[Comercio]
    evidencias: list[Evidencia]
    metricas: Metricas               # latencia_ms, creditos, llamadas, candidatos, descartados
    errores: list[str]
```

Cada tool implementa cuatro pasos, en una clase base común (`ToolAdapter`):

| Paso | Responsabilidad |
|---|---|
| `planear(request)` | Consultas propias del proveedor |
| `traer(plan)` | Llamadas en paralelo, con semáforo, plazo y presupuesto |
| `extraer(crudo)` | Campos con schema |
| `mapear(extraido)` | Entidades estándar, función pura |

Un registro (como hoy `sources/__init__.py`) lista las tools activas. `enabled` depende de su credencial.

### Entidades a estandarizar (propuesta, falta confirmarla)

| Entidad | Campos |
|---|---|
| **ProductoCanonico** | marca, modelo, variante (capacidad, tamaño, presentación), condición (nuevo, usado, reacondicionado), categoría, unidad y cantidad (para packs y bultos) |
| **Oferta** | precio publicado, moneda, precio en USD y en Bs, tasa usada, fecha vista, URL, disponibilidad, `precio_al_dm` |
| **Comercio** | id con prefijo de la fuente, nombre, canal, zona, envía, seguidores, comentarios, tiempo de respuesta, métodos de pago |
| **Evidencia** | fuente, URL exacta, extracto o captura, veredicto del juez y su razón |

Cambiar `Offer` y `Merchant` de `types.py` es **cambiar un contrato**: se avisa al equipo antes de mergear ([docs/plan.md](plan.md)).

## 7. Skill estándar por tool

Cada tool trae una carpeta con su skill, que es también el system prompt de su subagente:

```
apps/api/app/tools/<tool>/
  adapter.py     # planear, traer, extraer
  mapper.py      # crudo ► entidades estándar
  skill.md       # la guía del subagente (abajo)
  fixtures/      # respuestas reales para probar el mapper
```

Secciones fijas de `skill.md`:

1. **Propósito y cuándo usarla**: qué canales cubre y qué productos encuentra bien.
2. **Entradas y salida**: `ToolRequest` ► `ToolResult`.
3. **Plan de consultas**: cómo expandir la consulta para ese proveedor.
4. **Parámetros óptimos**: país, idioma, límites, formatos y cache.
5. **Paralelismo interno**: qué se puede hacer a la vez y con qué tope.
6. **Límites**: rate limit, créditos, plazo y qué hacer al vencerse.
7. **Extracción**: el schema y ejemplos.
8. **Trampas**: accesorios, variantes, otro país, reacondicionados, packs, "precio al DM".
9. **Evals**: qué productos de queries.md tiene que acertar.

## 8. Optimización por proveedor

| Proveedor | Cómo | Paralelismo | Números y ojo |
|---|---|---|---|
| **Firecrawl** | Método C del eval: search + escalación (scrape solo de lo que promete) | Búsqueda en Venezuela y scrape del top N en paralelo, con semáforo | Primera oferta válida en ~3,6 s, total ~15 s, ~37 créditos (~USD 0,036) por consulta. El método Agent tarda ~94 s: no sirve en vivo |
| **Mercado Libre** | API oficial de MLV, sin LLM | Varias consultas a la vez | Responde 403 sin token: hay que registrar una app. El método directo del eval no validó ninguna oferta: hay que revisarlo |
| **Apify (IG, TikTok, Marketplace)** | Actores precalentados para los productos más buscados del catálogo (Cloud Scheduler); en vivo, solo la cola larga | Un actor por canal, en paralelo | Tardan de segundos a minutos. Si no llega en plazo, se responde sin esa fuente. Muchos posts dicen "precio al DM" |
| **Tasa** | Una vez por día, en cache | | |

**Reglas globales**

- Un **semáforo por proveedor** y una cola de Cloud Tasks por proveedor (`max-concurrent-dispatches`) para no pasar sus límites.
- **Plazo del job**: blando de ~20 s (se responde con lo que haya) y duro de ~60 s. Los números se ajustan con métricas.
- **Corte temprano** cuando hay suficientes ofertas validadas.
- **Fan-out acotado.** El sitemap del catálogo y las alternativas de cada ficha disparan ~147 búsquedas a la vez: con fuentes reales eso gasta créditos y choca con los límites. Tienen que pasar por el mismo semáforo y la misma cache.

## 9. UX de la respuesta

- **Acuse inmediato** con lo que entendió: "Buscando *iPhone 15 128 GB nuevo* en webs, Mercado Libre e Instagram. Te aviso en un momento."
- **Resultado final** estructurado: primero la cifra y el veredicto, después como mucho dos alternativas, cada precio con su fuente, fecha y tasa.
- Si se vence el plazo blando: se manda lo que hay y se dice qué fuente faltó.
- **Una sola respuesta final por job**: se marca en el estado del job antes de enviar. Arregla el pendiente de [kapso.md](../agents/kapso.md): hoy un reintento puede guardar el turno dos veces.
- La respuesta final cae dentro de la ventana de 24 horas de WhatsApp, porque responde a un mensaje de la persona.

**Todo dentro de un WhatsApp Flow nativo, por Kapso** (verificado en su documentación):

| Momento | Qué se envía | Cómo |
|---|---|---|
| Al recibir | "Escribiendo…" y el acuse | Se marca leído con `typing_indicator`. Se borra al enviar o a los ~25 s |
| Falta un dato | Flow "Afinar" con solo los campos que faltan (zona, envío, condición) | Mensaje `interactive` de tipo `flow`. Al enviarlo, el webhook recibe un `interactive.type: nfm_reply` y arranca la búsqueda |
| Resultado | Una línea con la mejor oferta y el botón "Ver ofertas" (1 a 20 caracteres) | Mensaje `flow` con `flow_token` = id del job y los resultados en `flow_action_payload` |
| Dentro del Flow | Pantallas Ofertas → Detalle (precio, comercio, confianza, fuente, fecha, tasa, link) → Afinar | Los datos van en el payload inicial. Para paginar o filtrar, una función de datos los lee del job guardado |

- **Kapso hace** el registro y la publicación en Meta, las versiones, el cifrado, la URL y el secreto del endpoint de datos, la verificación de firma y el log de cada llamada.
- **Nosotros hacemos** el Flow JSON y, si es dinámico, la función de datos: JavaScript en Cloudflare Workers dentro de Kapso (`handler(request, env)`), que llama a nuestra API.
- **Límites del endpoint de datos:** responde en 15 s como máximo y recibe hasta 100 pedidos por minuto por Flow. Por eso solo lee resultados guardados y nunca lanza una búsqueda.
- **Bloqueante:** los Flows exigen un Portafolio de Meta Business verificado y activar el cifrado de Flows en el número (una vez). Hay que pedirlo ya.
- **Plan B:** fuera de la ventana de 24 h, el Flow va dentro de una plantilla aprobada con botón FLOW. Sin Flow, un carrusel interactivo de 2 a 10 tarjetas con foto y botón con link.
- El Flow "Afinar" respeta la regla de "una pregunta a la vez" del agente en espíritu: pide solo lo que falta.

## 10. Modelo

- **Gemini 3.8 Flash**, porque lee links y responde rápido. Ya está confirmado: es el Flash más nuevo que responde en Vertex (`global`) y el que fija Cloud Run ([agents/adk.md](../agents/adk.md#modelos)).
- Eval del juez: `gemini-3.5-flash-lite` acierta 94 % en ~2,3 s y `gemini-3.5-flash` 97 % en ~10,5 s.
- Propuesta: **un modelo por rol**, con una variable de entorno por rol (`PRAIS_MODEL_INTERPRETE`, `PRAIS_MODEL_JUEZ`, `PRAIS_MODEL_REDACTOR`…), para cambiarlos sin tocar código.
- ADK trae agentes de flujo (`SequentialAgent`, `ParallelAgent`). Antes de usarlos, confirma la API en `https://adk.dev/llms.txt` (regla 5 de AGENTS.md). El paralelismo entre tools va por Cloud Tasks; dentro de un proceso, por `asyncio`.

## 11. Decisiones abiertas

| # | Decisión | Recomendación |
|---|---|---|
| 1 | El doc de arquitectura base de agentes **no está en `resources/` ni en ninguna rama** | Subirlo, y ajustar este handoff si cambia algo |
| 2 | Entidades estándar (sección 6) | Las cuatro: producto canónico, oferta, comercio y evidencia |
| 3 | Mensajes intermedios por WhatsApp | Acuse + final. Un avance intermedio solo si el plazo pasa de ~20 s |
| 4 | Dónde vive el estado del job, de los resultados parciales y de la sesión | Firestore: serverless, en el mismo proyecto de GCP. Las sesiones en memoria no sobreviven al fan-out entre instancias |
| 5 | Plazos y presupuesto por consulta | Blando de 20 s, duro de 60 s, tope de créditos de Firecrawl por consulta |
| 6 | Políticas del juez: packs, webs de marca, listados | Las 4 abiertas en queries.md, sección 6 |
| 7 | Registrar el cambio a orquestador + subagentes | En `agents/architecture.md` y `docs/decisions/` |

## 12. Riesgos y consideraciones

- **Costo:** cada consulta llama a varios proveedores pagos. Hay que medir los créditos por job desde el día uno (`Metricas`).
- **Inyección de prompts:** el contenido scrapeado nunca se trata como instrucciones. El juez tiene que pasar el 100 % de los casos de seguridad.
- **Cloud Run:** el trabajo en segundo plano va siempre en tareas de la cola, no en `BackgroundTasks`, porque Cloud Run limita la CPU después de responder.
- **Observabilidad:** un trace por job, con la latencia, los créditos y el estado de cada tool, para afinar plazos y presupuestos.
- **Contratos:** `/chat`, `/whatsapp`, `/mcp` y `search_offers` cambian de forma. Se avisa al equipo y se actualizan `agents/contracts.md` y la propuesta `{ reply, producto, ofertas, tasa, actualizado }`.

## 13. Roadmap

Parte de lo que ya está en `main`: el orquestador `root_agent` con seis especialistas (`app/agents/`), `search_offers` en paralelo y la cola de Cloud Tasks de WhatsApp. **Solo hay tareas que no suman piezas nuevas de infraestructura**: cada una cambia uno o dos archivos y entra en su propio PR. Lo que agrega complejidad (Firestore, una cola por proveedor, agregador, endpoint de datos del Flow) queda al final, para cuando las métricas lo pidan.

### Fase 0: pedirlo ya (sin código, tarda en llegar)

| # | Tarea | Listo cuando |
|---|---|---|
| 0.1 | Verificar el Portafolio de Meta Business y activar el cifrado de Flows en el número | Kapso deja publicar un Flow |
| 0.2 | Keys de Firecrawl y Apify, y registrar la app de Mercado Libre (`ML_ACCESS_TOKEN`) | Están en `apps/api/.env` de quien las usa y en `prais-api-secrets` |
| 0.3 | ~~Confirmar el modelo~~ **Hecho:** `gemini-3.8-flash` responde en Vertex y es el de Cloud Run | `PRAIS_MODEL` apunta a un modelo que responde |

### Fase 1: el agente corre con datos reales

| # | Tarea | Archivos | Listo cuando | Depende de |
|---|---|---|---|---|
| 1.1 | **Cada especialista consulta solo su fuente.** `search_offers` acepta una lista opcional de ids de fuente | `lib/search.py`, `agents/specialists.py` | Una consulta llama una sola vez a cada fuente, no cinco | — |
| 1.2 | **Plazo por fuente** (opcional). `Source` suma `timeout_s` (8 s por defecto). Firecrawl ya no lo necesita: `open_web` la llama directo, fuera de `search_offers`, con 45 s de presupuesto | `lib/types.py`, `lib/search.py` | Una fuente lenta del registro puede usar más tiempo sin cambiar las demás | — |
| 1.3 | **Fuente Firecrawl.** **Primera versión hecha** (PR #46): `open_web` busca en Venezuela y lee el precio de hasta 3 páginas. Falta medirla contra el método C del eval y devolver `ToolResult` | `lib/sources/firecrawl.py` | Ofertas reales de al menos 2 tiendas, con métricas de tiempo y créditos | 0.2 |
| 1.4 | **Juez de coincidencias** como función: candidato + consulta → veredicto, con salida estructurada | `lib/judge.py`, `lib/search.py` | Pasa los 10 productos y los 3 casos de seguridad de `resources/queries.md` | 1.3 |
| 1.5 | **Salida estructurada de los especialistas** según [tool-result.md](tool-result.md): la tool guarda el `ToolResult` en el estado de la sesión y el especialista responde un `SpecialistReport` con `output_schema` (ADK 2.13 lo permite junto con tools) | `lib/contracts.py`, `agents/specialists.py` | El orquestador recibe datos, no texto, y cada precio llega con su fuente | 1.1 |
| 1.6 | **Acuse inmediato:** marcar leído con "escribiendo…" y mandar el acuse antes de correr el agente | `routes/whatsapp.py` | Por WhatsApp, el acuse llega en ~2 s | — |
| 1.7 | **No responder dos veces:** si el agente ya respondió y solo falló el envío, el reintento no vuelve a correr el agente | `routes/whatsapp.py` | Arregla el pendiente de [kapso.md](../agents/kapso.md#pendiente) | — |
| 1.8 | **Modelo por rol:** `PRAIS_MODEL_ORQUESTADOR` y `PRAIS_MODEL_ESPECIALISTA`, con `PRAIS_MODEL` de respaldo | `agents/*.py`, `.env.example` | Los especialistas usan flash-lite sin tocar código | 0.3 |
| 1.9 | **Una línea de log por consulta:** latencia y ofertas por fuente, y créditos de Firecrawl | `lib/search.py` | Se ven en Cloud Logging y sirven para fijar los plazos | — |

**Hito:** le escribes al número, recibes el acuse al instante y después el mejor precio real de la web, con fuente, fecha y tasa.

### Fase 2: más fuentes, mismo molde

| # | Tarea | Archivos | Listo cuando | Depende de |
|---|---|---|---|---|
| 2.1 | **Fuente Instagram:** lee el último dataset de un actor de Apify programado, no lo dispara en vivo | `lib/sources/apify_instagram.py` | Ofertas reales con seguidores y comentarios, en menos de 2 s | 0.2 |
| 2.2 | **Fuentes TikTok y Marketplace** con el mismo molde. Decidir el actor de Marketplace (la pizarra y `sources.md` proponen distintos) | `lib/sources/apify_*.py` | Igual que 2.1 | 2.1 |
| 2.3 | **Fuente Mercado Libre** con la API oficial | `lib/sources/mercadolibre.py` | Ofertas reales de MLV | 0.2 |
| 2.4 | **Confianza por fuente:** portar un borrador de `resources/*_trust_score.py` por PR, con la salida común (puntaje, cobertura, veredicto, banderas, razones) | `lib/prices.py` | El especialista reporta la confianza con su veredicto y sus razones | 2.1–2.3 |
| 2.5 | **Proteger el catálogo** antes de apagar la fuente de ejemplo: el sitemap y las alternativas leen la cache y respetan un tope de búsquedas a la vez | `lib/catalogo.py` | Con `USE_MOCK_SOURCE=false`, el sitemap no dispara ~147 búsquedas de golpe | 1.3 |
| 2.6 | **Meta Ads como ajuste de confianza**, no como fuente de ofertas | `lib/prices.py`, `agents/specialists.py` | El especialista de Meta Ad Library ajusta puntajes en vez de devolver 0 ofertas | 2.4 |

### Fase 3: la experiencia en WhatsApp

| # | Tarea | Archivos | Listo cuando | Depende de |
|---|---|---|---|---|
| 3.1 | **Imágenes y links:** el webhook acepta mensajes con imagen y le pasa al agente la foto (`message.kapso.media_url`) | `routes/whatsapp.py`, `agent.py` | Mandas la foto de un producto y Prais lo busca | — |
| 3.2 | **Flow de resultados estático:** las ofertas viajan en el payload inicial, sin endpoint de datos | Flow JSON en Kapso, `routes/whatsapp.py` | El botón "Ver ofertas" abre la lista y el detalle dentro de WhatsApp | 0.1, 1.5 |
| 3.3 | **Flow "Afinar"** para los datos que faltan; su `nfm_reply` arranca la búsqueda | Flow JSON en Kapso, `routes/whatsapp.py` | Si falta la zona, se abre el formulario en vez de preguntar por texto | 0.1 |

### Después, solo si las métricas lo piden

Firestore para el estado del job, una cola por proveedor con agregador, el endpoint de datos del Flow para paginar y filtrar, y el plazo blando con respuesta parcial. Cada una entra cuando el log de 1.9 muestre que hace falta.
