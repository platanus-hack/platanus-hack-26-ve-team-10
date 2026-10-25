# Fuentes

Cada fuente del registro es un archivo en `apps/api/app/lib/sources/` que cumple el contrato `Source`. Los pasos para sumar una están en [contracts.md](contracts.md#sumar-una-fuente). En el registro están la de ejemplo (`mock.py`), que se apaga con `USE_MOCK_SOURCE=false`, e Instagram y TikTok por Apify (`apify.py`), que se encienden con `APIFY_TOKEN`. Además de sus ofertas fijas, responde por cada modelo del catálogo (`catalogo.json`) con comercios marcados "(ejemplo)" y precios generados desde `precioEjemplo`. Apagarla deja el catálogo con solo ofertas reales: ver [seo-geo.md](seo-geo.md#catálogo-el-interruptor-de-indexación). Firecrawl no está en ese registro: `search_offers` cancela a los 8 s, y la web abierta se llama directo desde la tool y desde el MCP.

## Cadenas con tienda propia

La lista curada está en `apps/api/app/lib/cadenas.py`. Son comercios que venden ellos mismos, tienen sucursales y su web es el canal oficial. Es una señal de respaldo comercial del comercio, no del precio y no de que la oferta sea el producto buscado. `trust_score` todavía no suma puntos por ella: quien calcule la confianza compara el dominio con `chain_for_host`.

La comparación es por dominio exacto. Se ignora un `www` al principio. No se compara por nombre: `tiendas-daka.com` no hereda la confianza de `tiendasdaka.com`. Otro subdominio tampoco. `ve.epaenlinea.com` es EPA Venezuela; `epaenlinea.com` solo elige país, y Costa Rica, Guatemala y El Salvador no entran.

Cada fila trae categoría (`farmacia`, `supermercado`, `tecnologia`, `hogar`), `tienda_propia: true`, si vimos tienda en línea y si un cliente HTTP simple recibe un bloqueo. La revisión del archivo es del 2026-10-24. Hay que volver a mirarla antes de la demo: la lista envejece.

Cuatro tiendas en línea que respondieron con catálogo quedan marcadas `price_source`, para conectarlas después: Gama (`gamaenlinea.com`), IVOO (`ivoo.com`), Daka (`tiendasdaka.com`) y EPA Venezuela (`ve.epaenlinea.com`). No hay adapter en `lib/sources/`: esta lista no abre una fuente nueva. Cuando se conecten, el adapter lee estos dominios y no los copia a otro archivo.

Quedó fuera Farmavenezuela (`farmavenezuela.com`): un cliente HTTP y el navegador solo reciben un 403 genérico de Apache, sin la farmacia. Estos hosts respondieron, pero no son la tienda de la fila: `xiaomivenezuela.com` (un lander; Xiaomi Latin está en `xio-online.com`), `multimax.net` (Panamá; Venezuela es `multimax.com.ve`), `beco.com.ve` (no completó HTTP; Beco está en `becoenlinea.com`), `makro.com.ve` (no completó HTTP; Makro está en `makrove.com`), `mitiendadamasco.com` (respondió vacío) y `corporaciondamasco.com` (no resuelve). Damasco está en `www.damascovzla.com`.

## Qué hay que saber de cada una

| Fuente | Cómo se consulta | Ojo |
|---|---|---|
| **Firecrawl** | `search_open_web` en `app/lib/sources/firecrawl.py`. La llaman la tool de la web abierta y `search_prices` del MCP. Cómo distingue un listado de una ficha, abajo | La web abierta sigue sin puntaje (`trust` null). El motor ya puede cerrar una tienda si llegan sus señales; RDAP, DNS y Safe Browsing no están conectados |
| **Apify: Instagram** | Conectada: `instagram_source` en `app/lib/sources/apify.py`, actor `apify/instagram-scraper` | Se entra por la página del hashtag del producto. Muchas tiendas ponen "precio al DM": la oferta va con `price=None` |
| **Apify: TikTok** | Conectada: `tiktok_source` en el mismo archivo, actor `clockworks/tiktok-scraper` | Busca por palabras, con proxy venezolano. El puntaje de confianza usa `clockworks/tiktok-profile-scraper` y `clockworks/tiktok-comments-scraper` (ver [resources/tiktok_trust_score.py](../resources/tiktok_trust_score.py)) |
| **Apify: Facebook Marketplace** | Cliente de Python de Apify + un actor de Marketplace de la Apify Store | Facebook no tiene API oficial. Candidato: `deepmine/facebook-marketplace-scraper`, con proxy residencial (ver [resources/fb_marketplace_trust_score.py](../resources/fb_marketplace_trust_score.py)) |
| **Mercado Libre** | API oficial, sitio `MLV` | Sigue **403 sin token**: no hay cliente en vivo. `score_mercadolibre` en `app/lib/trust.py` puntúa el JSON de `/items` y `/users` sin llamar a la red |
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
| Entrada | `directUrls` con `https://www.instagram.com/explore/tags/<hashtag>/` y `resultsType: posts` | `searchQueries` con el producto, `searchSection: /video` |
| Hashtag | `_hashtag()` arma el tag del producto: "Harina PAN 1 kg" es `#harinapan`, "iPhone 15 128 GB" es `#iphone15`. Una cifra seguida de su unidad se cae: es la presentación, no el modelo | — |
| Zona | `proxyCountryCode` no aplica: el hashtag es global y se filtra por el caption | `proxyCountryCode: "VE"` |
| Seguidores | No vienen en una publicación: `followers` va en `None` | `authorMeta.fans` |

`searchType: "hashtag"` **no** sirve para esto: devuelve el volumen del hashtag y los relacionados, no sus publicaciones. Por eso se usa la URL del hashtag.

**El precio sale del caption**, con las mismas funciones que la web abierta (`published_prices` y `matches_product`, en `firecrawl.py`: esa lógica vive en un solo lugar). Las reglas:

- El monto tiene que estar escrito **con su moneda** ($, USD, Bs). Un número suelto, como un teléfono, no es un precio.
- Si la publicación nombra el precio en dólares y en bolívares, manda el de dólares.
- Si nombra **varios precios** en la misma moneda (un post con tres modelos), no se usa ninguno.
- Sin precio, la oferta solo se guarda si el caption dice "precio al DM" (o inbox, interno, privado, whatsapp), y va con `price=None`.
- La publicación tiene que nombrar el producto pedido (`matches_product` sobre el caption), si no, se descarta.

**Lo que cuesta.** Los dos actores cobran por publicación (Instagram, unos USD 2,70 por 1.000 en el plan gratis). Cada corrida pide `RESULTS` (20) y además lo limita con `max_items`, así que son unos 5 centavos. La caché es lo que evita repetirlas.

**Lo que falta.** El hashtag de Instagram es global: para "iPhone 15" trae publicaciones de todo el mundo y solo quedan las que nombran precio y producto. Una lista de cuentas de comercios venezolanos (`directUrls` de perfiles) daría mucha mejor cobertura, y es el siguiente paso. Tampoco se guarda todavía lo que pide el puntaje de confianza: para eso hay que sumar campos a `Merchant` (ver [Datos que el puntaje necesita](#datos-que-el-puntaje-necesita)).

**Probar que el token sirve**, con una corrida de verdad (gasta créditos), desde `apps/api`:

```bash
.venv/bin/python scripts/apify_prueba.py "iPhone 15 128 GB" instagram
```

Muestra el input que recibe el actor, la primera publicación entera (para confirmar los nombres de los campos) y las ofertas que salen de ahí.

## Puntaje de confianza por fuente

Cada canal mide cosas distintas. Para poder compararlos, todos entregan la misma caja: una lista de señales. Cada señal tiene un peso fijo (los de un canal suman 100) y un valor de 0 a 1.

El motor está en `apps/api/app/lib/trust.py`. Los modelos (`TrustSignal`, `TrustScore`, `Adjustment`, `MerchantIdentity`) están en `apps/api/app/lib/contracts.py`. Los borradores de `resources/` no se importan: son la referencia de las fórmulas y de los nombres de campo. Antes de escribir un adapter, corre el actor con casos reales y confirma esos nombres.

Cómo se calcula:

- **Sin dato no es cero.** `null` significa que no hay dato y esa señal no entra en la cuenta. `0` significa que el dato está y es malo. `"pending"` es un hueco que el agregador va a llenar; al cerrar, si no pudo, lo baja a `null`. Un puntaje `final` no puede conservar un `"pending"`.
- **Cobertura.** Es el peso medido dividido entre 100. El puntaje divide solo entre el peso medido: quien tiene menos datos no es castigado, solo se mide con menos certeza.
- **Veredicto.** En `stage="parcial"` el puntaje queda en `null` y el veredicto en `sin_datos`: el especialista no cierra. Al pasar a `final`, una bandera roja deja el puntaje en 0 y el veredicto en `riesgosa`. Si se midió menos del 40 % del peso, no hay puntaje (`sin_datos`). De 75 para arriba es `confiable`; de 50 a 74, `precaucion`; por debajo, `riesgosa`.
- **Estrellas.** `to_stars()` convierte el 0–100 a 0–5. Los cortes coinciden con el veredicto (90, 75, 60 y 50). Sin puntaje, no hay estrellas. El texto del catálogo usa los mismos 75 y 50.
- **Agregador.** `ask_prais` junta el JSON de cada tool y llama a `close_listings`. Ahí corren cuatro pasadas: mediana de precio e identidad del comercio, cierre de Instagram, TikTok, Facebook, Mercado Libre y Amazon, cierre de la tienda web (su señal `linked_socials` usa los puntajes de Instagram y TikTok del mismo vendedor) y los ajustes de Meta Ads. Hace falta un grupo de al menos 5 precios publicados del mismo producto y la misma condición (nuevo, usado o reacondicionado). Una oferta cuyo `evidence_id` no está en la oferta se descarta con error `parseo`.

La búsqueda (`search_offers`) sigue devolviendo `merchant.trust` como un entero. Esa fórmula provisional está en `prices.trust_score` (seguidores, comentarios y tiempo de respuesta, con piso de 40). Cambiar el `Merchant` de `types.py` para guardar los datos crudos de cada fuente cambia el contrato de la búsqueda: hay que avisarlo antes de mergear. Hasta entonces, las pasadas solo actúan si el listado trae `contractOffer` y `contractMerchant`.

Mercado Libre, de punta a punta en este código: el JSON de la publicación y del vendedor entra a `score_mercadolibre` y sale un `TrustScore`. Con la mediana, el agregador llena `price_anomaly` y deja `stage="final"`. No llama a la API.

Todavía no: el hash perceptual de las fotos de Facebook (si nadie pasa el conteo, `photos_original` queda sin dato), los campos crudos en el `Merchant` de la búsqueda, y el fetch de los otros canales. El atajo de Amazon (vende y envía Amazon → 95) y el bonus de hasta +10 de Marketplace sí están en el motor. `amazon` ya es un canal en `types.py`.

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

`FIRECRAWL_API_KEY` y `APIFY_TOKEN`. El puntaje de tiendas web puede usar además `GOOGLE_SAFE_BROWSING_KEY`, que es opcional, y el de Mercado Libre, `ML_ACCESS_TOKEN`, el token de la app. Amazon usa `APIFY_TOKEN`. `APIFY_TOKEN` sale de [Apify Console → Settings → API & Integrations](https://console.apify.com/settings/integrations) y va en `apps/api/.env`. Sin él, Instagram y TikTok quedan apagadas y la búsqueda sigue igual que antes. Las demás variables, agrégalas a `apps/api/.env.example` cuando conectes la fuente. En producción ya tienen lugar en el secreto `prais-api-secrets` ([gcp.md](gcp.md)).

## Docs

- Firecrawl: [llms.txt](https://docs.firecrawl.dev/llms.txt), para el SDK de Python
- Apify: [llms.txt](https://docs.apify.com/llms.txt), para el cliente de Python
- [Mercado Libre Developers](https://developers.mercadolibre.com.ve)
