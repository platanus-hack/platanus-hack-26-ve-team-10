# Fuentes

Cada fuente del registro es un archivo en `services/api/app/lib/sources/` que cumple el contrato `Source`. Los pasos para sumar una están en [contracts.md](contracts.md#sumar-una-fuente). En el registro están la de ejemplo (`mock.py`), que se apaga con `USE_MOCK_SOURCE=false`, e Instagram y TikTok por Apify (`apify.py`), que se encienden con `APIFY_TOKEN`. Además de sus ofertas fijas, responde por cada modelo del catálogo (`catalogo.json`) con comercios marcados "(ejemplo)" y precios generados desde `precioEjemplo`. Apagarla deja el catálogo con solo ofertas reales: ver [seo-geo.md](seo-geo.md#catálogo-el-interruptor-de-indexación). Firecrawl no está en ese registro: `search_offers` cancela a los 8 s, y la web abierta se llama directo desde la tool y desde el MCP. Amazon tampoco está: si entrara en esa búsqueda, el precio de la ficha competiría sin el flete. Lo llama la tool `find_listings_importacion`.

## Cadenas con tienda propia

La lista curada está en `services/api/app/lib/cadenas.py`. Son comercios que venden ellos mismos, tienen sucursales y su web es el canal oficial. Es una señal de respaldo comercial del comercio, no del precio y no de que la oferta sea el producto buscado. `trust_score` todavía no suma puntos por ella: quien calcule la confianza compara el dominio con `chain_for_host`.

La comparación es por dominio exacto. Se ignora un `www` al principio. No se compara por nombre: `tiendas-daka.com` no hereda la confianza de `tiendasdaka.com`. Otro subdominio tampoco. `ve.epaenlinea.com` es EPA Venezuela; `epaenlinea.com` solo elige país, y Costa Rica, Guatemala y El Salvador no entran.

Cada fila trae categoría (`farmacia`, `supermercado`, `tecnologia`, `hogar`), `tienda_propia: true`, si vimos tienda en línea y si un cliente HTTP simple recibe un bloqueo. La revisión del archivo es del 2026-10-24. Hay que volver a mirarla antes de la demo: la lista envejece.

Cuatro tiendas en línea que respondieron con catálogo quedan marcadas `price_source`, para conectarlas después: Gama (`gamaenlinea.com`), IVOO (`ivoo.com`), Daka (`tiendasdaka.com`) y EPA Venezuela (`ve.epaenlinea.com`). No hay adapter en `lib/sources/`: esta lista no abre una fuente nueva. Cuando se conecten, el adapter lee estos dominios y no los copia a otro archivo.

Quedó fuera Farmavenezuela (`farmavenezuela.com`): un cliente HTTP y el navegador solo reciben un 403 genérico de Apache, sin la farmacia. Estos hosts respondieron, pero no son la tienda de la fila: `xiaomivenezuela.com` (un lander; Xiaomi Latin está en `xio-online.com`), `multimax.net` (Panamá; Venezuela es `multimax.com.ve`), `beco.com.ve` (no completó HTTP; Beco está en `becoenlinea.com`), `makro.com.ve` (no completó HTTP; Makro está en `makrove.com`), `mitiendadamasco.com` (respondió vacío) y `corporaciondamasco.com` (no resuelve). Damasco está en `www.damascovzla.com`.

## Qué hay que saber de cada una

| Fuente | Cómo se consulta | Ojo |
|---|---|---|
| **Firecrawl** | `search_open_web` en `app/lib/sources/firecrawl.py`. La llaman la tool de la web abierta y `search_prices` del MCP. Cómo distingue un listado de una ficha, abajo | Su puntaje (`web-v1`) lo arma `app/lib/sources/web_trust.py` con RDAP y DNS: ver [abajo](#la-confianza-de-una-tienda-web). Safe Browsing sigue sin conectar |
| **Apify: Instagram** | Conectada: `instagram_source` en `app/lib/sources/apify.py`, actor `apify/instagram-scraper` | Se entra por la página del hashtag del producto. Muchas tiendas ponen "precio al DM": la oferta va con `price=None` |
| **Apify: TikTok** | Conectada: `tiktok_source` en el mismo archivo, actor `clockworks/tiktok-scraper` | Busca por palabras, con proxy venezolano. El puntaje de confianza usa `clockworks/tiktok-profile-scraper` y `clockworks/tiktok-comments-scraper` (ver [resources/tiktok_trust_score.py](../resources/tiktok_trust_score.py)) |
| **Facebook Marketplace** | Conectada: `facebook_source` en `app/lib/sources/facebook.py`, actor `curious_coder/facebook-marketplace` | Marketplace está detrás de un login, no de un anti-bots: ver [abajo](#facebook-marketplace-y-la-moneda-que-miente) |
| **Mercado Libre** | Conectada: `mercadolibre_source` en `app/lib/sources/mercadolibre.py`, actor `sourabhbgp/mercadolibre-scraper` con `country: "VE"` | Es un puente hasta tener la API oficial: ver [abajo](#mercado-libre-por-ahora-con-un-actor) |
| **Amazon + courier** | Actor `junglee/Amazon-crawler` y el cotizador de cada courier. Ver [Traerlo de USA](#traerlo-de-usa) | Sin `APIFY_TOKEN` la tool no llama a Amazon. El precio que compite es el total puesto en Venezuela |
| **Meta Ads** | API de la Ad Library | Solo devuelve anuncios comerciales que se mostraron en la UE o el Reino Unido. Para Venezuela no sirve. Candidato: el actor `curious_coder/facebook-ads-library-scraper`, que se usa para ajustar el puntaje de confianza (ver [resources/meta_ads_signals.py](../resources/meta_ads_signals.py)) |

## Reglas

- **Lento no va en vivo.** Cada fuente tiene 8 segundos (`asyncio.wait_for` la cancela). Si tarda más (Apify), la búsqueda arranca el actor, lo espera un poco y sigue sin él: la corrida queda andando y la siguiente búsqueda del mismo producto lee su resultado. Ver [Apify](#apify-instagram-y-tiktok).
- **Sin precio no hay inventos.** Si la publicación no tiene precio, `price` va en `None`.
- **Una fuente que falla no tumba la búsqueda.** `search_offers` ya la deja fuera y la anota en `failedSources`.
- **Async de verdad.** `search` es `async`: usa clientes asíncronos (`httpx.AsyncClient`) para no bloquear a las demás fuentes.
- **Guarda los datos del comercio** (seguidores, comentarios, reputación), porque los usa el puntaje de confianza. Qué traer de cada fuente está en [Datos que el puntaje necesita](#datos-que-el-puntaje-necesita).

## Cómo Firecrawl lee un listado

`search_open_web` busca el producto y después lee las páginas que salieron. Hay dos clases de página:

- **Listado, categoría o portal de anuncios.** La ruta trae un tramo como `collections`, `categoria`, `category`, `departamento`, `laptops-gamer` o `listado`, o el dominio empieza por `listado.`. Un portal de anuncios (carros usados, motos, inmuebles) también: un tramo de la ruta es la palabra sola `usado`, `usados`, `auto`, `autos`, `carro`, `carros`, `moto`, `motos`, `vehiculo`, `vehiculos`, `inmueble`, `inmuebles`, `clasificado`, `clasificados`, `anuncio` o `anuncios`. Por ejemplo `/auto/usado/chevrolet/aveo`. Esa página tiene varios avisos, no un solo producto: el formato `product` devolvería uno, a menudo sin precio. Se lee **una sola vez**, pidiendo juntos `json` (la lista de ofertas) y `markdown` (para comprobar que cada precio está escrito en la página). Si el aviso trae su enlace, la oferta apunta a ese anuncio; si no, apunta a la página leída. Una ficha suelta como `/iphone-15-usado` no entra aquí: `usado` no es un tramo aparte. Firecrawl acepta varios formatos en la misma llamada a `/scrape`. El scrape base cuesta 1 crédito y el JSON suma 4: 5 en total. El markdown no suma. El formato `product` tampoco suma, pero en un listado no devuelve precio; si se pide antes, la segunda lectura ya no cabe en el plazo del MCP.
- **Ficha de un producto.** Se pide primero `product` (1 crédito, sin modelo de lenguaje). Si trae precio, no se pide el JSON. Si no trae precio y todavía queda tiempo, recién ahí se pide el JSON. Si no queda tiempo, esa segunda lectura no se lanza.

`u$s` y `U$S` se leen como dólares (USD). TuCarro (`tucarro.`), Trovit y eBay no se leen: TuCarro es Mercado Libre y la página cae en su verificación anti-bots; no se intenta saltarla. Una página bloqueada, con error o cortada por el tiempo va a `failedSources` como `firecrawl:<dominio>` y queda en una línea de log con el dominio, el resultado (`bloqueada` o `error`) y los segundos. Un link muerto (404 o 410) no cuenta. El aviso de datos de ejemplo sale solo cuando alguna oferta de la respuesta tiene `example: true`.

El tiempo de cada lectura es el que le queda al plazo (25 s en el MCP, 45 s en el agente), no 15 s fijos y después 20 s. La búsqueda deja al menos unos 10 s de ese plazo para las lecturas: si se come los 20 s de su propio tope, las páginas no llegan a leerse.

Antes de leer se descartan los dominios de otros países (`.mx`, `.pe`, `.co`, `.com.ar` y similares) y las webs de marca que no venden en Venezuela (`lenovo.com`, `nvidia.com`, `apple.com`…). Una ruta `/ve/` o un dominio `.ve` sí se lee (`apple.com/ve`). Las tiendas conocidas (`sigmatiendas.com`, `soytechno.com`, `tiendasdaka.com`, `elplazas.com`) y los dominios `.ve` van primero. De lo que queda se leen hasta 8 páginas. La búsqueda pide 15 resultados —4 créditos, porque son 2 por cada 10, redondeando hacia arriba— para que, al botar los de afuera, todavía queden tiendas de Venezuela.

Si esas primeras páginas no traen ningún precio publicado, la búsqueda no se cierra ahí. Sigue, y se detiene en cuanto aparece una oferta con precio. No inventa el monto: sigue valiendo solo un precio que está escrito en la página.

- **Más resultados.** Lee las páginas de esa misma búsqueda que no entraron en las primeras 8.
- **El listado.** Si todavía no hay precio, lee las páginas de categoría o de anuncios que esa búsqueda trajo y que aún no se abrieron. Cada una sigue siendo una sola lectura, con JSON y markdown juntos.
- **Una consulta más cerrada.** Si sigue sin precio y queda tiempo, busca `comprar "{producto}" precio`, otra vez desde Caracas y en Venezuela. De esos resultados abre primero los listados. Es otra búsqueda de Firecrawl y solo se paga cuando la primera tanda no trajo precio (los mismos 2 créditos por cada 10 resultados).

Un aviso sin precio no entra como opción. Si esta pasada tampoco encuentra un precio publicado, la tool lo dice en una frase y no pide revisar cada opción. El orquestador repite eso y no completa el hueco con un consejo.

Si una página se leyó y otra se cortó por el tiempo, la que sí se leyó se guarda (una hora si trajo ofertas, 10 minutos si no). La consulta siguiente no vuelve a pagarla. El resultado entero no se guarda cuando alguna página quedó a medias, ni cuando se acabó el tiempo antes de esa pasada que sigue buscando un precio: la próxima búsqueda puede abrir lo que esta no alcanzó. El MCP sigue en 25 s y el agente en 45 s. Con una sola lectura por listado, 25 s alcanza para la búsqueda y para leer la página.

## El reloj de una búsqueda

**Las páginas se leen en paralelo, así que el reloj lo fija la más lenta, no cuántas son.** Medido sobre 119 páginas reales: «apple watch se» leyó 8 páginas que sumaban 185 s de trabajo y terminó en 33,8 s; «una macbook air m4» leyó 13 que sumaban 113,9 s y terminó en 22,8 s. Leer menos tiendas no acorta la búsqueda: solo trae menos precios.

Lo que sí la acorta es cortar la cola, y hay un punto donde eso deja de costar datos:

| Tope por página | Ofertas que se conservan |
|---|---|
| 15 s | 40 % |
| 20 s | 70 % |
| 25 s | 93 % |
| 30 s | 97 % |

Por eso `PAGE_BUDGET_S` son 28 s. Bajarlo a 15 s tiraría el 60 % de los precios: la página pesada de renderizar suele ser justo la que trae producto y precio, y las rápidas son en su mayoría las que no sirven.

### El cupo del plan

Firecrawl limita **por equipo y por plan**: Hobby da 5 navegadores concurrentes y 100 scrapes por minuto; Standard, 25 y 500 ([rate limits](https://docs.firecrawl.dev/rate-limits)). Pedir más de lo que da el plan no trae más datos: lo que sobra vuelve como `RateLimitError` y esa página se pierde entera, después de haber gastado unos 5 s. De 119 páginas medidas, 56 fueron error y **39 de esas fueron rate limit**.

`SCRAPE_CONCURRENCY` (variable `FIRECRAWL_CONCURRENCY`, 5 por defecto) mantiene los scrapes a la vez dentro de ese cupo: las páginas que sobran esperan su turno en vez de que Firecrawl las rechace. Como el límite es del equipo, el MCP y otra búsqueda en paralelo también lo gastan, así que un 429 se reintenta una vez tras `RATE_RETRY_S`.

**Subir el paralelismo es un cambio de plan, no de código.** Con el plan actual, el techo ya está tocado: `SCRAPE_LIMIT` son 8 páginas y el cupo son 5. Al contratar más, se sube `FIRECRAWL_CONCURRENCY` y es lo único que hay que tocar.

## El precio tiene que ser del producto pedido

Una oferta entra solo si el artículo que trae el precio es el que se buscó. Eso se decide al leer la página, antes de armar las tarjetas. El texto con el que el asistente resume la búsqueda no agrega ni quita ofertas.

El título de ese artículo tiene que decir la marca, el modelo y las cifras de la búsqueda. Un iPhone 14 no es un Samsung, ni un iPhone 15, ni un iPhone 14 Pro, Plus, mini o slim. Si la ficha (`product`) trae el precio de otro artículo, la página queda fuera y no se pide el listado en JSON: ya se vio qué está a la venta. Si la ficha no trae precio, recién ahí se lee el listado, igual que antes.

Una comparación que nombra los dos no cuenta por mencionar el producto buscado. Cuenta el artículo al que corresponde el precio. En un listado se botan los otros avisos y se queda el que sí coincide. Si la ficha dice "iPhone 14 vs Samsung" y la marca del precio es Samsung, esa oferta no entra. Si la marca del precio es Apple, entra el lado del iPhone, no el Samsung.

## Apify: Instagram y TikTok

Las dos están en `app/lib/sources/apify.py`: comparten el cliente, la caché y la lectura de captions.

**El plazo.** Una corrida de actor tarda de segundos a minutos y `search_offers` corta a los 8 s. La fuente arranca el actor, lo espera `LIVE_WAIT_S` (6 s) y devuelve lo que tenga. La corrida **no se cancela**: termina en segundo plano y deja sus publicaciones en la caché, así que la siguiente búsqueda del mismo producto sí las ve. Un resultado dura 6 horas; uno vacío o fallido, 15 minutos, para no pagar dos veces lo mismo. **Precalentar antes de una demo es buscar el producto una vez.** La corrida vive en el proceso del API: si Cloud Run apaga la instancia, se pierde y la próxima búsqueda vuelve a arrancarla.

**Por dónde entra cada una.**

| | Instagram | TikTok |
|---|---|---|
| Entrada | **Dos puertas en paralelo**: la búsqueda por publicaciones (`scraping_solutions/instagram-boolean-search-scraper-posts-reels`, con `searchQuery` booleana) y la página del hashtag (`directUrls`, `resultsType: posts`) | `searchQueries` con el producto, `searchSection: /video` |
| Hashtag | `_hashtag()` arma el tag del producto: "Harina PAN 1 kg" es `#harinapan`, "iPhone 15 128 GB" es `#iphone15`. Una cifra seguida de su unidad se cae: es la presentación, no el modelo | — |
| Zona | `proxyCountryCode` no aplica: el hashtag es global y se filtra por el caption | `proxyCountryCode: "VE"` |
| Seguidores | No vienen en una publicación: `followers` va en `None` | `authorMeta.fans` |

`searchType: "hashtag"` del actor oficial **no** sirve para esto: devuelve el volumen del hashtag y los relacionados, no sus publicaciones. Por eso esa puerta usa la URL del hashtag.

**Por qué dos puertas.** El actor oficial no busca publicaciones por frase, y la página de un hashtag es global: una corrida real de `#iphone15` trajo 18 publicaciones de India, Tailandia, Brasil y Japón, y **ninguna** de un vendedor venezolano. El buscador booleano sí acepta `"iPhone 15" AND (Venezuela OR Caracas OR ...)`, así que el país entra en la consulta en vez de filtrarse después de pagar los resultados: la misma prueba devolvió 10 publicaciones y las 10 eran de tiendas venezolanas, 8 con su ciudad. El hashtag se queda porque alcanza publicaciones que el buscador no indexa. Las dos corren a la vez y son independientes: si una falla, la otra sigue, y sus publicaciones se leen igual porque `_from_search` les pone los nombres de campo del actor oficial.

**La ciudad.** La búsqueda por publicaciones trae `locationName`, así que `merchant.zone` deja de ser "Venezuela" a secas y pasa a ser la ciudad real cuando la publicación la tiene.

**Dos corridas, no una.** La búsqueda devuelve una publicación por cuenta, y con una sola no se
pueden medir proporciones ni ritmo: el puntaje se quedaría bajo el 40 % de cobertura. Por eso, con
los comercios que **sí dieron oferta**, el especialista hace una segunda corrida sobre sus perfiles
(`profiles` en TikTok, `directUrls` de perfil en Instagram) y pide `PROFILE_POSTS` publicaciones de
cada uno. Solo se paga por quien ya aportó algo, y las dos corridas caben en la misma tarea de
fondo: la búsqueda sigue sin esperarlas.

**El puntaje de confianza.** `apify_trust.py` arma el `TrustScore` `parcial` de cada comercio con
los catálogos `ig-v1` y `tiktok-v1`, portando las fórmulas de los borradores. Lo cierra el
agregador al final del turno. El contrato y por qué funciona así están en
[contracts.md](contracts.md#el-puntaje-de-confianza-de-una-fuente). Qué alcanza a medir hoy:

| | Mide | Le falta |
|---|---|---|
| TikTok | Antigüedad (del id numérico), región, likes/vistas, consistencia, corazones por seguidor, compartidos y guardados, ritmo, lenguaje de riesgo | `comment_quality`, que necesita `clockworks/tiktok-comments-scraper` |
| Instagram | Consistencia de likes, comentarios/likes, ritmo, calidad de comentarios, lenguaje de riesgo | `engagement` (necesita seguidores, que una publicación no trae) y antigüedad, cambios de usuario y país, que están en el bloque "about", una opción de pago del actor |

**El precio sale del caption**, con las mismas funciones que la web abierta (`published_prices` y `matches_product`, en `firecrawl.py`: esa lógica vive en un solo lugar). Las reglas:

- El monto tiene que estar escrito **con su moneda** ($, USD, Bs). Un número suelto, como un teléfono, no es un precio.
- Si la publicación nombra el precio en dólares y en bolívares, manda el de dólares.
- Si nombra **varios precios** en la misma moneda (un post con tres modelos), no se usa ninguno.
- **Una cuota o una inicial no es un precio.** Media tienda venezolana publica "Con Cashea desde 230$ de inicial" de un equipo que cuesta el triple. Antes de buscar montos se cae toda línea que hable de pagar a plazos (`inicial`, `cuota`, `crédito`, `financia`, `abono`, `reserva`, `desde`, `Cashea`). Leer esa cifra como el precio es peor que no mostrar nada.
- **La condición la declara la fuente**, porque ve el caption entero y a la búsqueda solo le llega el título: `Pre-Owned`, `preowned`, `seminuevo` y `usado` son usado; `reacondicionado` y `refurbished`, reacondicionado.
- Sin precio, la oferta solo se guarda si el caption dice "precio al DM" (o inbox, interno, privado, whatsapp), y va con `price=None`.
- La publicación tiene que nombrar el producto pedido (`matches_product` sobre el caption), si no, se descarta.

**Lo que cuesta.** Los dos actores cobran por publicación (Instagram, unos USD 2,70 por 1.000 en el plan gratis). Cada corrida pide `RESULTS` (20) y además lo limita con `max_items`, así que son unos 5 centavos. La caché es lo que evita repetirlas.

**Lo que falta.** El hashtag de Instagram es global: para "iPhone 15" trae publicaciones de todo el mundo y solo quedan las que nombran precio y producto. Una lista de cuentas de comercios venezolanos (`directUrls` de perfiles) daría mucha mejor cobertura, y es el siguiente paso. Tampoco se guarda todavía lo que pide el puntaje de confianza: para eso hay que sumar campos a `Merchant` (ver [Datos que el puntaje necesita](#datos-que-el-puntaje-necesita)).

**Probar que el token sirve**, con una corrida de verdad (gasta créditos), desde `services/api`:

```bash
.venv/bin/python scripts/apify_prueba.py "iPhone 15 128 GB" instagram
```

Muestra el input que recibe el actor, la primera publicación entera (para confirmar los nombres de los campos) y las ofertas que salen de ahí.

## Traerlo de USA

Cuando alguien pide un producto, el orquestador también llama a `find_listings_importacion`. La tool decide. Si el producto no se puede traer, responde sin ofertas y no llama a Amazon.

No se cotiza un medicamento, un perecedero, una batería suelta, un vívere, un líquido, un arma ni un bulto que no entra en un casillero aéreo (más de 50 lb, o una nevera, un caucho, un mueble). Un teléfono no es una batería suelta.

### Amazon

El archivo es `app/lib/sources/amazon.py`. El actor es `junglee/Amazon-crawler`, el mismo que nombra el borrador de confianza. La búsqueda es una URL de amazon.com (`categoryOrProductUrls`). Se piden el detalle del producto y el vendedor de la oferta principal (`scrapeProductDetails`, `scrapeSellers`, `maxOffers: 0`). `useCaptchaSolver` queda en false: no saltamos el bloqueo de Amazon, y con el captcha el actor no devuelve el peso.

De cada resultado se leen ASIN, precio en dólares, vendedor, quién envía (Amazon, FBA o el vendedor) y, si vienen, peso y medidas. Esos últimos están en `attributes`, `productOverview` o `manufacturerAttributes`. Un resultado de otro producto se bota con la misma regla que la web abierta. Sin precio en dólares no entra.

La tool espera hasta 35 s. Si el actor no alcanzó, la corrida sigue y la próxima pregunta del mismo producto lee lo que dejó. Sin `APIFY_TOKEN` no arranca.

### Peso

`app/lib/importacion/peso.py`. El peso facturable es el mayor entre el real y el volumétrico. El volumétrico usa 166 pulgadas cúbicas por libra, que es la cuenta habitual de la carga aérea, porque Zoom publica kilos físicos y Liberty calcula el volumen en su propio cotizador. Si el listing no trae peso, se usa una tabla por categoría (un iPhone, 0.8 lb) y la oferta dice `weightSource: "tabla"`.

### Couriers

Los dos cotizan en paralelo. El que no responde se omite. Queda una sola oferta: el courier más barato. Las otras cotizaciones viajan en `landed.quotes`.

| Courier | De dónde sale el número |
|---|---|
| **Zoom** (`cur:zoom`) | La página pública [consulta de precios](https://casilleros.zoom.red/consulta-de-precios/). El aéreo se cobra por cada ½ kg o fracción, más la protección que la misma página escribe ($1 bajo $100, o el 1 % si vale más). No se llama a `CalcularTarifa`: esa API es de envíos nacionales y el casillero no tiene el contrato publicado |
| **Liberty Express** (`cur:liberty`) | El cotizador de su calculadora, `POST https://api.iqpackoffice.com/Cotizar`. El código de flete, la ruta Miami–Venezuela y el host salen del HTML de [la calculadora](https://iqpack.libertyexpress.com/Calculator). El token sale del script que esa página carga: es el de la calculadora pública, no una clave nuestra. Se usa el flete de casillero aéreo (`termino` COL, paquete, sin condición) |

El impuesto de Liberty es el que el cotizador devuelve (`taxSource: "cotizado"`). Zoom no lo incluye. La tabla de arancel está en cero hasta confirmarla: ese cero es la tabla, no un impuesto inventado. Ninguna de las dos páginas publica un rango de días, así que la tarjeta no inventa "7-12 días".

`priceUsd` es el total puesto en Venezuela: precio de Amazon + flete + impuesto + seguro. El precio de Amazon queda en `landed.productUsd`.

### Confianza

La oferta sale con `import-v1` en `stage: "parcial"`. Al cerrar, `price_anomaly` compara el precio de Amazon con la mediana del mismo ASIN. No mira el precio venezolano: si lo mirara, una importación más barata que las tiendas de aquí saldría con puntaje 0. Con un solo precio de ese ASIN no hay mediana y la señal queda sin dato. Vendido y enviado por Amazon usa el atajo de 95. El puntaje del courier (`courier_trust`) queda vacío: `courier-v1` no se calculó porque sus pesos siguen sin confirmar. Vacío no es cero.

No se guardan las cotizaciones. Postgres hoy guarda la conversación del agente, no esta tarifa.

## La confianza de una tienda web

`app/lib/sources/web_trust.py` arma el puntaje parcial `web-v1` de cada oferta de la web abierta, y
`app/agents/open_web_trust.py` se lo pega a la oferta como contrato. Lo cierra el agregador, igual
que en los demás canales ([contracts.md](contracts.md#el-puntaje-de-confianza-de-una-fuente)).

Mide lo que se sabe del dominio **sin pagar otra lectura de la página**:

| Señal | Peso | De dónde sale | Cuesta |
|---|---|---|---|
| `domain_age` | 15 | RDAP (`rdap.org/domain/<dominio>`) | Gratis, sin API key |
| `contact` | 10 | Si el host está en `cadenas.py`: una cadena revisada a mano es una empresa con contacto verificable | Gratis |
| `https` | 5 | La URL | Gratis |
| `mx` | 5 | DNS sobre HTTPS (`dns.google`) | Gratis, sin API key |
| `risk_language` | 5 | El helper compartido de `trust.py` | Gratis |

Las dos consultas de red se hacen **una vez por host**, en paralelo y con 4 segundos de tope, y se
recuerdan un día. Lo que no se pudo averiguar queda en `None`: no cuenta y su peso se reparte.

Una cadena conocida llega a 0,40 de cobertura sola; una tienda que no está en `cadenas.py` llega a
0,30 y necesita que el agregador llene `price_anomaly` (20) para pasar el mínimo. `linked_socials`
(10) lo llena el agregador con el puntaje ya cerrado de las redes del mismo comercio, que existe
desde que Instagram y TikTok emiten el contrato.

**Lo que falta**: `contact` completo (RIF, dirección), `policies` y `catalog` piden otra extracción
con Firecrawl, y `safe_browsing` una `GOOGLE_SAFE_BROWSING_KEY`.

**Dos banderas rojas** se conservan de la revisión anterior, ahora dentro del puntaje: un dominio
que imita a una marca sin serlo (`iphone-venezuela.com`) y un anuncio que en realidad vende un
accesorio. La tercera que había —precio más de 50 % bajo el resto— **no se repite aquí**: es
`price_anomaly`, y el agregador ya la aplica con ese mismo umbral.

## Mercado Libre: por ahora, con un actor

La API oficial responde **403 hasta en `/sites/MLV`**: hay que registrar una app gratis en
developers.mercadolibre.com.ve para tener `client_id` y `client_secret`. El endpoint de token
acepta `client_credentials`, así que no haría falta OAuth con navegador.

Mientras eso no exista, el canal entra por `sourabhbgp/mercadolibre-scraper` con `country: "VE"`.
Leer el sitio directo no es opción: `listado.mercadolibre.com.ve` devuelve su verificación
anti-bots, y no se intenta saltarla (por eso `mercadolibre.` y `tucarro.` están en `_SKIP_HOSTS`
de la web abierta).

**MLV tiene catálogo**, contra lo que se podía suponer: una corrida real de "iPhone 15" devolvió 15
avisos, los 15 de Venezuela y todos con precio en dólares. Pero su relevancia es floja —entre los 15
había varios Xiaomi Redmi—, así que el filtro `matches_product` no es opcional.

**`scrapeProductDetails` es obligatorio.** Sin abrir la ficha no vienen la reputación del vendedor
ni la garantía, y el puntaje se queda en 15 % de cobertura. Con detalle, 15 resultados salieron por
unos 3 céntimos.

**El puntaje.** `score_mercadolibre` ya existía y lee la forma de la API oficial, así que la fuente
le traduce la del actor (`sellerReputation` → `seller_reputation.level_id`, `sellerPowerStatus` →
`power_seller_status`). Lo que el actor no trae queda en `None`, no cuenta y su peso se reparte:

| Señal | Peso | ¿La trae el actor? |
|---|---|---|
| `thermometer` | 15 | Sí (`5_green`, `2_orange`…) |
| `power_seller` | 5 | Sí (`silver`, `gold`…) |
| `completeness`, `warranty`, `risk_language` | 15 | Sí |
| `sales_volume`, `negative_ratings`, `account_age`, `location` | 35 | **No**: solo la API oficial |

Un vendedor con reputación llega a 35 % de cobertura, y a 55 % cuando el agregador llena
`price_anomaly`. Cuando exista el token, la fuente se reemplaza y `score_mercadolibre` no cambia.

**Los términos de servicio.** Scrapear Mercado Libre va contra sus términos, y que lo haga un actor
de terceros no cambia eso. La API es la vía sancionada: para una demo el riesgo es bajo, pero si
esto va a producción de verdad, registrar la app deja de ser opcional.

No necesita variable nueva: usa `APIFY_TOKEN`, el mismo de Instagram y TikTok.

## Facebook Marketplace y la moneda que miente

Marketplace **no se puede leer directo**: la página redirige a `/login/`. No es un muro anti-bots
como el de Mercado Libre, es autenticación. Entrar con las cookies de una cuenta real queda
descartado: expone esa cuenta a bloqueo y va contra los términos de Meta. El canal entra por
`curious_coder/facebook-marketplace` (4,2 M de corridas), que **no pide sesión ni proxy
residencial**, acepta `searchKeyword` más `location` en formato "Ciudad, Estado, País" y cobra
USD 0,0005 por aviso. Una corrida real de Caracas: 21 avisos en 43 segundos por USD 0,013.

Se buscan tres ciudades (Caracas, Maracaibo y Valencia) con 60 km de radio, porque Marketplace
busca por ciudad y no por país. Las tres corridas se solapan y el deduplicado por link las junta.

### La trampa de la moneda

Facebook etiqueta como **VEF** —el bolívar anterior a 2018, que ya no circula— casi todos los
avisos venezolanos: 19 de 21 en esa corrida, con descripciones que decían "440$". Nadie pone
precios en una moneda muerta hace siete años: el aviso está en dólares.

El lector resuelve así, y el orden importa:

1. **Manda lo que escriba el vendedor en el texto.** Es la única fuente de verdad, y además
   reconoce un precio en bolívares de verdad ("Bs. 5.000").
2. Si el texto no dice nada, la etiqueta `VEF` se lee como dólares.

Lo segundo es lo seguro, aunque parezca lo contrario: equivocarse hacia el dólar **sobreestima** el
precio unas 900 veces, y esa oferta se hunde al fondo de la lista. Leerlo como bolívares volvería
440 en medio dólar y lo pondría primero, anunciado como el mejor precio del mercado. **El error
peligroso es el otro.**

### Qué mide

| Señal | Peso | ¿Se puede hoy? |
|---|---|---|
| `fb_age` | 15 | Sí, `joined_at` del vendedor |
| `location` | 5 | Sí |
| `completeness` | 5 | Sí: fotos y palabras de la descripción |
| `risk_language` | 5 | Sí |
| `history` | 20 | No: pide otra corrida sobre el perfil del vendedor, que trae su `url` |
| `photos_original` | 20 | No: es del agregador y el hash perceptual no está |

30 % de cobertura, 50 % con `price_anomaly`. Las calificaciones del vendedor no son una señal: van
como bonus de hasta +10 (`facebook_rating_bonus`), porque en Marketplace casi nadie califica y la
ausencia no debe restar. Dos banderas rojas propias: perfil creado hace menos de un mes y menos de
3★ con 5 calificaciones o más.

**Marketplace es entre personas, no tiendas.** Los vendedores son "Betty Rumbos", no "Daka". Son
los precios más bajos de todos los canales y donde más riesgo de estafa hay. En la corrida real
aparecieron un iPhone 15 a 45 dólares y otro a 5.000: al primero lo caza la bandera de "más de
50 % bajo el mercado" del agregador y el segundo se hunde solo.

## Puntaje de confianza por fuente

La web abierta no corre el puntaje estricto en cada búsqueda. El agente sigue [open_web_trust_skill.md](../services/api/app/agents/open_web_trust_skill.md): cada listado trae `trust_review` con las banderas que ya se ven (precio contra las otras ofertas, dominio que imita una marca, funda o copia). Antigüedad, RIF, políticas y Safe Browsing siguen en `resources/website_trust_score.py` y no se inventan.

Cada canal mide cosas distintas. Para poder compararlos, todos entregan la misma caja: una lista de señales. Cada señal tiene un peso fijo (los de un canal suman 100) y un valor de 0 a 1.

El motor está en `services/api/app/lib/trust.py`. Los modelos (`TrustSignal`, `TrustScore`, `Adjustment`, `MerchantIdentity`) están en `services/api/app/lib/contracts.py`. Los borradores de `resources/` no se importan: son la referencia de las fórmulas y de los nombres de campo. Antes de escribir un adapter, corre el actor con casos reales y confirma esos nombres.

Cómo se calcula:

- **Sin dato no es cero.** `null` significa que no hay dato y esa señal no entra en la cuenta. `0` significa que el dato está y es malo. `"pending"` es un hueco que el agregador va a llenar; al cerrar, si no pudo, lo baja a `null`. Un puntaje `final` no puede conservar un `"pending"`.
- **Cobertura.** Es el peso medido dividido entre 100. El puntaje divide solo entre el peso medido: quien tiene menos datos no es castigado, solo se mide con menos certeza.
- **Veredicto.** En `stage="parcial"` el puntaje queda en `null` y el veredicto en `sin_datos`: el especialista no cierra. Al pasar a `final`, una bandera roja deja el puntaje en 0 y el veredicto en `riesgosa`. Si se midió menos del 40 % del peso, no hay puntaje (`sin_datos`). De 75 para arriba es `confiable`; de 50 a 74, `precaucion`; por debajo, `riesgosa`.
- **Estrellas.** `to_stars()` convierte el 0–100 a 0–5. Los cortes coinciden con el veredicto (90, 75, 60 y 50). Sin puntaje, no hay estrellas. El texto del catálogo usa los mismos 75 y 50.
- **Agregador.** `ask_prais` junta el JSON de cada tool y llama a `close_listings`. Ahí corren cuatro pasadas: mediana de precio e identidad del comercio, cierre de Instagram, TikTok, Facebook, Mercado Libre y Amazon, cierre de la tienda web (su señal `linked_socials` usa los puntajes de Instagram y TikTok del mismo vendedor) y los ajustes de Meta Ads. Hace falta un grupo de al menos 5 precios publicados del mismo producto y la misma condición (nuevo, usado o reacondicionado). Una oferta cuyo `evidence_id` no está en la oferta se descarta con error `parseo`.

La búsqueda (`search_offers`) sigue devolviendo `merchant.trust` como un entero. Esa fórmula provisional está en `prices.trust_score` (seguidores, comentarios y tiempo de respuesta, con piso de 40). Cambiar el `Merchant` de `types.py` para guardar los datos crudos de cada fuente cambia el contrato de la búsqueda: hay que avisarlo antes de mergear. Hasta entonces, las pasadas solo actúan si el listado trae `contractOffer` y `contractMerchant`.

Mercado Libre, de punta a punta en este código: el JSON de la publicación y del vendedor entra a `score_mercadolibre` y sale un `TrustScore`. Con la mediana, el agregador llena `price_anomaly` y deja `stage="final"`. No llama a la API.

Todavía no: el hash perceptual de las fotos de Facebook (si nadie pasa el conteo, `photos_original` queda sin dato), los campos crudos en el `Merchant` de la búsqueda, y el fetch de los otros canales. El atajo de Amazon (vende y envía Amazon → 95) y el bonus de hasta +10 de Marketplace sí están en el motor. `amazon` e `importacion` ya son canales en `types.py`. En `import-v1`, `price_anomaly` no usa la mediana de Venezuela: usa la del mismo ASIN. `courier-v1` no está en el motor.

El contrato pedía comprobar que el estado del agente se propaga y que hubiera un paso determinista entre los especialistas y la respuesta. Eso ya no aplica: los especialistas son tools de Python y `ask_prais` lee el JSON de cada una.

| Fuente | Borrador | Qué pesa más |
|---|---|---|
| Instagram | [ig_trust_score.py](../resources/ig_trust_score.py) | Antigüedad de la cuenta, interacción acorde a los seguidores y comentarios reales |
| Facebook Marketplace | [fb_marketplace_trust_score.py](../resources/fb_marketplace_trust_score.py) | Historial del vendedor y fotos que no aparecen en anuncios de otros: en Venezuela casi nadie califica |
| TikTok | [tiktok_trust_score.py](../resources/tiktok_trust_score.py) | Proporción entre likes y vistas, no likes por seguidor: las vistas las reparte el algoritmo |
| Tiendas web | [website_trust_score.py](../resources/website_trust_score.py) | Antigüedad del dominio, RIF y contacto publicados, políticas de devolución |
| Mercado Libre | [mercadolibre_trust_score.py](../resources/mercadolibre_trust_score.py) | Reputación de la plataforma: termómetro, MercadoLíder y calificaciones |
| Amazon | [amazon_trust_score.py](../resources/amazon_trust_score.py) | Quién envía (Amazon, FBA o el vendedor) y el feedback del vendedor externo. Detecta cuentas inactivas que reaparecen con precios bajos |
| Meta Ads | [meta_ads_signals.py](../resources/meta_ads_signals.py) | No es un puntaje: ajusta el de Instagram, Marketplace o TikTok. Un vendedor que no anuncia no pierde nada |

Todos comparten la misma salida: puntaje de 0 a 100, cobertura, veredicto (`confiable`, `precaucion`, `riesgosa` o `sin_datos`), banderas rojas y razones. Una bandera roja deja el puntaje en 0. Si hay menos de 40 % del peso medido, el veredicto es `sin_datos`.

## Datos que el puntaje necesita

El `Merchant` de la búsqueda solo trae `followers`, `comments` y `response_time_min`. El puntaje del contrato no usa esos tres campos: cuenta las señales cuyo dato trae la fuente. Las demás no entran en la cuenta. El puntaje divide solo entre el peso medido, y la cobertura dice cuánto quedó afuera. **Cada dato de esta lista que traiga tu fuente suma una señal**, pero guardarlo en `types.py` cambia el contrato: avisa antes de mergear.

Cómo guardarlo:

- Como campo opcional de `Merchant` en `snake_case`, con `None` por defecto. Cambiar `types.py` es cambiar un contrato: avisa en el canal antes de mergear.
- Si la fuente no trae el dato, va `None`, nunca `0`. `None` no cuenta; `0` cuenta como dato malo.
- Fechas en ISO 8601, como `seen_at`. Listas de publicaciones: las más recientes primero, máximo 20.
- Lo lento (la sección "Información sobre esta cuenta" de Instagram, los comentarios, el historial del vendedor) va en el actor que corre antes, no en la consulta en vivo.

Los nombres de campo de origen son los de los borradores en `resources/`: confírmalos con una corrida real del actor antes de escribir el adapter. Los pesos de cada señal están en esos borradores, no aquí, para que no se desincronicen.

### Instagram

Actores: `apify/instagram-profile-scraper` y `apify/instagram-comment-scraper`.

| Dato | Campo de origen | Señal que alimenta |
|---|---|---|
| Fecha de creación de la cuenta | `about.dateJoined` (opción de pago "about" del actor) | Antigüedad; menos de 1 mes es bandera roja |
| Cambios de nombre de usuario | `about.formerUsernames` | Cambios de @; 4 o más es bandera roja |
| País de la cuenta | `about.country` | País coherente |
| Likes y comentarios por publicación | `latestPosts[].likesCount`, `commentsCount` | Interacción, consistencia y comentarios/likes |
| Fecha de cada publicación | `latestPosts[].timestamp` | Ritmo de publicación |
| Texto y autor de comentarios recientes (unos 30 de los 3 últimos posts) | `text`, `ownerUsername` del actor de comentarios | Calidad de comentarios |
| Bio y captions | `biography`, `latestPosts[].caption` | Lenguaje de riesgo |
| Cuenta privada | `private` | Se avisa al usuario |

### TikTok

Actores: `clockworks/tiktok-profile-scraper` y `clockworks/tiktok-comments-scraper`.

| Dato | Campo de origen | Señal que alimenta |
|---|---|---|
| ID numérico del usuario | `authorMeta.id` (la fecha de creación sale de sus 32 bits altos) | Antigüedad; menos de 1 mes es bandera roja |
| Región | `authorMeta.region` | Región coherente |
| Likes totales de la cuenta | `authorMeta.heart` | Likes totales / seguidores |
| Por video: vistas, likes, compartidos, guardados, fecha y si es anuncio | `playCount`, `diggCount`, `shareCount`, `collectCount`, `createTimeISO`, `isAd` | Likes/vistas, consistencia, compartidos + guardados, ritmo |
| Texto y autor de comentarios recientes | `text`, `uniqueId` del actor de comentarios | Calidad de comentarios |
| Bio y captions | `authorMeta.signature`, `text` | Lenguaje de riesgo |

### Facebook Marketplace

Actor: `deepmine/facebook-marketplace-scraper`, con "Add listing details" activo.

| Dato | Campo de origen | Señal que alimenta |
|---|---|---|
| Desde cuándo está en Facebook | `sellerJoinTime` | Antigüedad; menos de 1 mes es bandera roja |
| Otros anuncios del vendedor: fecha y ciudad de cada uno | Perfil del vendedor (`/marketplace/profile/<id>`) | Historial (detecta cuentas robadas) y coherencia de ubicación |
| URLs de las fotos del anuncio | `listingPhotos` | Fotos copiadas de otros vendedores (hash perceptual) |
| Título y descripción | `marketplaceListingTitle`, `redactedDescription` | Completitud y lenguaje de riesgo |
| Calificación promedio, cantidad e insignias | `sellerRatingAverage`, `sellerRatingCount`, `commerce_badges_info` | Bonus de hasta +10; menos de 3★ con 5+ calificaciones es bandera roja |

### Mercado Libre

API oficial: `/items/{id}`, `/items/{id}/description` y `/users/{id}`.

| Dato | Campo de origen | Señal que alimenta |
|---|---|---|
| Termómetro y MercadoLíder | `seller_reputation.level_id`, `power_seller_status` | Reputación; rojo con 10+ ventas es bandera roja |
| Ventas concretadas y totales | `seller_reputation.transactions.completed`, `total` | Volumen de ventas |
| Proporción de calificaciones negativas | `seller_reputation.transactions.ratings.negative` | Calificaciones negativas; 25 % o más es bandera roja |
| Fecha de registro | `registration_date` (confirmar que viene para terceros) | Antigüedad |
| Estado del vendedor y de la publicación | `address.state`, `seller_address.state.name` | Ubicación coherente |
| Estado de la cuenta | `status.site_status` | Cuenta suspendida es bandera roja |
| Fotos, descripción y garantía de la publicación | `pictures`, `plain_text`, `warranty` | Completitud, garantía y lenguaje de riesgo |

### Tiendas web

Firecrawl, RDAP, DNS y Google Safe Browsing.

| Dato | De dónde sale | Señal que alimenta |
|---|---|---|
| Fecha de registro del dominio | RDAP (`rdap.org/domain/<dominio>`) | Antigüedad; menos de 1 mes es bandera roja |
| RIF, dirección, teléfonos y correos | Extracción con schema de Firecrawl en portada, contacto y nosotros | Contacto verificable |
| Palabras de las páginas de términos, devoluciones, garantía y privacidad | Scrape de cada página | Políticas |
| Productos visibles | Extracción con schema | Catálogo |
| Redes enlazadas | Links del sitio | Enlaza redes |
| HTTPS, correo del dominio (MX) y si Google lo marca como peligroso | URL final, DNS, Safe Browsing | Técnico; marcado por Google es bandera roja |
| Texto de la portada | Markdown de Firecrawl | Lenguaje de riesgo |
| Si dice ser tienda oficial de una marca | Extracción con schema | Bandera roja si no está en el dominio de la marca |

### Amazon

Actores: `junglee/Amazon-crawler` y `reefapi/amazon-seller-scraper`.

| Dato | Campo de origen | Señal que alimenta |
|---|---|---|
| Quién vende y quién envía | `seller.name`, `shipsFrom` | Amazon, FBA o el vendedor. Si vende y envía Amazon, el puntaje es 95 directo |
| ID del vendedor | `seller.id` | Para pedir su perfil |
| Feedback positivo y calificaciones (de por vida y 12 meses) | `feedback_percent`, `lifetime_ratings`, `ratings_12m` | Feedback, volumen y actividad reciente (detecta cuentas robadas) |
| Texto y nota de reseñas de feedback recientes | `seller/reviews` | Reseñas de falsificación o envíos no recibidos |
| Nota y reseñas del producto | `stars`, `reviewsCount` | Historial del producto |

### Para todas las fuentes

- **Precio**: no lo trae la fuente. Lo calcula `search_offers` contra la mediana de las demás ofertas del mismo producto, con al menos 5 comparables.
- **Reportes de usuarios**: todavía no hay forma de reportar, así que no cuentan.
- **Meta Ads**: para ajustar el puntaje de Instagram, Marketplace o TikTok hace falta el ID de la página de Facebook vinculada. Si el actor de tu fuente lo trae, guárdalo.

## Variables

`FIRECRAWL_API_KEY` y `APIFY_TOKEN`. `FIRECRAWL_CONCURRENCY` (opcional, 5) fija los scrapes a la vez y tiene que seguir al cupo del plan: ver [el cupo del plan](#el-cupo-del-plan). El puntaje de tiendas web puede usar además `GOOGLE_SAFE_BROWSING_KEY`, que es opcional, y el de Mercado Libre, `ML_ACCESS_TOKEN`, el token de la app. Amazon usa el mismo `APIFY_TOKEN`. Sale de [Apify Console → Settings → API & Integrations](https://console.apify.com/settings/integrations) y va en `services/api/.env`. Sin él, Instagram, TikTok y la importación quedan apagadas y la búsqueda sigue igual que antes. Zoom y Liberty no piden clave: se leen sus páginas públicas. Las demás variables, agrégalas a `services/api/.env.example` cuando conectes la fuente. En producción ya tienen lugar en el secreto `prais-api-secrets` ([gcp.md](gcp.md)).

## Docs

- Firecrawl: [llms.txt](https://docs.firecrawl.dev/llms.txt), para el SDK de Python
- Apify: [llms.txt](https://docs.apify.com/llms.txt), para el cliente de Python
- [Mercado Libre Developers](https://developers.mercadolibre.com.ve)
