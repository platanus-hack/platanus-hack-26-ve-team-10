# Componentes

Todos viven en `components/bundle.js` como `window.Prais` y necesitan React 18 en la página. Los tipos están en `components/index.d.ts`.

## Producto · Base

### Button

El botón del producto: relleno sólido, borde de 1px y sin sombras. La variante `cartel` es solo para piezas de marca.

**Props:** `variant` (`primario` · `secundario` · `fantasma` · `cartel`), `size` (`md` 44px · `lg` 52px), `icon` / `iconRight` (nombre de `Icon`), más cualquier prop de `<button>`.

- **Primario** (`accion`, negro en claro): una sola vez por pantalla, para la acción principal ("Buscar precios", "Ir al anuncio").
- **Secundario** (`papel-alto` con borde `borde`): acciones de apoyo ("Pegar link", compartir).
- **Fantasma**: acciones de navegación en barras y listas ("Historial", "Ver las 5 ofertas").
- **Cartel** (`sol`, borde grueso, sombra dura que se hunde): solo en la landing, campañas y slides. Nunca en pantallas con precios.
- Texto: verbo + objeto, con mayúscula solo al inicio.

### Badge

La etiqueta plana del producto para veredictos y datos cortos: "Más barato", "Buen precio", "Está caro", el canal de venta.

**Props:** `tone` (`destacado` · `barato` · `neutro` · `caro`), `icon` (nombre de `Icon`, opcional), `children`.

| Tono | Uso |
|---|---|
| `destacado` | "Más barato": solo la oferta #1, una vez por lista. Fondo `sol`. |
| `barato` | "Buen precio" (≤ 95% del promedio), con ícono `check`. |
| `neutro` | "Precio normal" y datos como el canal ("Marketplace"). |
| `caro` | "Está caro" (> 105% del promedio), con ícono `alerta`. |

- Máximo tres palabras, mayúscula solo al inicio.
- Derecho, sin borde ni sombra. La versión torcida de cartel es `Sticker` y vive solo en la capa de marca.

### Chip

Una píldora neutra para datos de contexto, como las plataformas que acepta el buscador.

**Props:** `icon` (opcional), `children`.

- Solo información, no es clickeable. Para filtros activables, usa `Button variant="secundario"`.
- Plataformas escritas como las conoce la gente ("Instagram", "Mercado Libre", "Marketplace"), sin sus logos.

### Icon

El set de íconos propio de usaprais: 24×24, trazo 2.25px, puntas redondas, color `currentColor`.

**Props:** `name` (`buscar` · `flecha` · `enlace` · `check` · `alerta` · `envio` · `escudo` · `tienda` · `compartir` · `reloj` · `volver` · `imagen` · `usuario` · `chevron`), `size` (px, por defecto 20), `label` (si el ícono es el único contenido, para lectores de pantalla).

- El trazo grueso combina con los bordes de cartel; no mezcles con sets de trazo fino.
- Siempre junto a una palabra salvo en botones de solo ícono, que llevan `label`.
- Si necesitas un ícono nuevo, dibújalo con la misma retícula y trazo y agrégalo a este set.

### PriceTag

Un precio en dólares con su equivalente en bolívares debajo, en Outfit 700 con números tabulares.

**Props:** `usd`, `tasa` (Bs. por dólar; si falta, no se muestra Bs.), `size` (`sm` 16 · `md` 20 · `lg` 32 · `xl` 44), `antes` (precio anterior tachado), `label`, `align` (`left` para alinear a la izquierda), `marca` (Bungee, solo capa de marca).

- Formato venezolano: punto de miles, coma decimal ("$1.249,99", "Bs. 21.810,15"). Sin ",00" en dólares.
- Dólares arriba y en `tinta`; bolívares debajo en `tinta-suave`. La tasa usada aparece en el tooltip y en el encabezado de la lista.
- Se compara el total con envío.
- `marca` solo en slides y campañas; nunca en listas de resultados ni fichas.

### TrustDots

Cinco puntos pequeños y una etiqueta que resumen qué tan confiable es un vendedor.

**Props:** `value` (0–5).

- 4–5: "Vendedor confiable" · 3: "Buenas referencias" · 1–2: "Pocas referencias" (en `caro-texto`) · 0: "Sin referencias".
- Va en la ficha de la oferta. En la lista de resultados la confianza se muestra solo como texto con ícono, dentro de `OfferRow`.

## Producto · Resultados

### SearchBox

El buscador: un campo con borde de 1px y el botón primario, donde la persona pega un link o escribe un producto.

**Props:** `onSubmit(valor)`, `label` (por defecto "¿Qué vas a comprar?"), `placeholder`, `cta` (texto del botón), `hint` (ayuda debajo), `defaultValue`.

- Un solo `SearchBox` por pantalla, arriba.
- El `hint` dice qué tipos de link acepta; nada de instrucciones largas.
- En móvil el botón pasa abajo a todo el ancho.

### PraisSays

Una línea de resumen con el avatar pequeño de Prais: así habla Prais dentro del producto.

**Props:** `mood` (estado del avatar), `children` (el mensaje; acepta `<b>` para la cifra clave), `avatarSize` (por defecto 36).

- Una sola por pantalla, arriba de los resultados, con el veredicto en una frase.
- Sin globo ni bordes: es texto junto a un avatar. El globo de cómic queda para piezas de marca.
- El estado del avatar coincide con el mensaje: `ganga` si hay ahorro, `pilas` si el precio está caro o el vendedor es dudoso.

### PriceRange

Una pista delgada que muestra dónde cae un precio entre el más bajo y el más alto del mercado, con el promedio marcado y el veredicto.

**Props:** `min`, `max`, `promedio`, `valor` (el precio que trajo la persona; opcional), `titulo`, `etiquetaValor` (por defecto "Tu precio"), `badge` (`false` oculta el veredicto).

- Zonas: `ahorro` hasta el 95% del promedio, neutra entre 95% y 105%, `caro` por encima. Las mismas reglas que `veredicto()`.
- Úsalo cuando la persona trae un precio concreto ("me lo venden en $109, ¿está bien?"). Si solo busca un producto, ve directo a `RankedList`.

### OfferRow

Una fila de la lista de resultados: puesto, tienda y canal, detalles, confianza, y a la derecha el total con su equivalente en Bs. y la diferencia frente al promedio.

**Props:** `rank`, `tienda`, `canal`, `usd`, `envio` (`0` = gratis, `null` = por confirmar), `tasa`, `condicion`, `garantia`, `confianza` (0–5), `promedio`, `destacado`, `flag`, `onAbrir` (vuelve toda la fila tocable y abre `FichaOferta`).

- Normalmente no se usa sola: `RankedList` la arma dentro de una lista con divisores.
- La fila destacada (#1) lleva el badge "Más barato" y fondo `sol-tinte`. Ninguna otra lleva color de fondo.
- Detalles en `tinta-suave`, separados por " · ": envío, condición, garantía. La ubicación y las notas largas van en la ficha.
- Confianza baja (≤ 2) en `caro-texto` con ícono `alerta`; el resto con `escudo` en gris.
- En contenedores de menos de 420px, tienda y canal se apilan y se oculta la flecha.

### RankedList

El resultado principal de usaprais: todas las ofertas en una sola lista, ordenadas de menor a mayor precio total con envío.

**Props:** `ofertas` (lista de `Oferta`; si traen `onAbrir`, cada fila es tocable), `tasa`, `producto` (título opcional), `promedio` (si no viene, se calcula), `actualizado`.

- El orden es siempre por total con envío; nunca por relevancia ni por quién paga publicidad.
- La #1 se destaca sola. Si la #1 tiene confianza ≤ 2, la línea de `PraisSays` de arriba debe decirlo.
- Muestra siempre cuándo se revisaron los precios y la tasa usada.
- Ponle arriba un `PraisSays` con el resumen en una frase.

### EstadoPrais

Prais ilustrado cuando no hay contenido que mostrar: buscando, sin resultados o error. Es el único lugar del producto donde el personaje aparece grande.

**Props:** `tipo` (`cargando` · `vacio` · `error`), `titulo` y `texto` (para reemplazar los textos por defecto), `mood`, `size` (por defecto 112), `accion` (texto de un botón secundario) y `onAccion`.

- `cargando` usa Prais `pensando` y una barra amarilla que se mueve; sin animación si la persona pidió reducir el movimiento.
- Los textos explican qué pasó y qué hacer, en la voz de Prais, sin culpar a la persona.
- Centrado en la pantalla, una sola vez. No lo uses como decoración en pantallas que ya tienen resultados.

## Pantallas

### FichaOferta

La pantalla de detalle de una oferta en móvil: lo que ve la persona cuando toca un anuncio de Marketplace, Mercado Libre, Instagram o una tienda dentro de los resultados.

**Props:** `oferta` (una `Oferta`, con `vendedor`, `publicado` y `foto` opcionales), `producto`, `tasa`, `rank`, `de`, `promedio`, `revisiones` (lista de `{tono: 'ok' | 'ojo', texto}`), `consejo`, `mejor` (la oferta #1), `masBaratas`, `onVolver`, `onIr`, `onCompartir`, `onVerMejor`.

Orden fijo, de arriba a abajo:

1. Barra con volver, producto y puesto ("3 de 5").
2. Foto del anuncio (o un marcador neutro).
3. Badges (veredicto, canal, hace cuánto se publicó), tienda, total con Bs., detalles y diferencia frente al promedio.
4. **Lo que revisó Prais:** 3 a 5 líneas con `check` o `alerta`, y el consejo en un recuadro gris si hace falta.
5. Vendedor: tipo, desde cuándo, referencias y `TrustDots`.
6. Si hay opciones más baratas, la #1 como atajo sobre `sol-tinte`.
7. Nota legal y barra fija con "Ir al anuncio" (primario) y compartir.

- Los anuncios se muestran con la estética de usaprais: nunca copies la interfaz ni los logos de Marketplace, Mercado Libre o Instagram. El canal va en un `Badge`.
- "Ir al anuncio" abre el anuncio original; usaprais no intermedia la compra.
- Si el vendedor tiene pocas referencias, al menos una revisión y el consejo dicen qué verificar antes de pagar.
- Diseñada para 360–480px; en desktop, como panel lateral de máximo 480px.

### PantallasMovil

El recorrido completo en el teléfono con la capa de producto: inicio, buscando, resultados y ficha de un anuncio de Marketplace.

- **Inicio:** barra con logo e historial, titular, `SearchBox` con botón primario negro, plataformas como `Chip` y búsquedas recientes en una lista.
- **Buscando:** `EstadoPrais tipo="cargando"`.
- **Resultados:** barra con volver y compartir, `PraisSays` con el resumen y `RankedList` con filas tocables.
- **Ficha:** `FichaOferta`, con la barra de acciones fija abajo.

Ancho de diseño: 390px. Márgenes laterales `space-4`.

## Marca

### Wordmark

El logotipo de usaprais: "usa" en tinta y "prais" dentro de una etiqueta de precio color `sol`, inclinada -4°.

**Props:** `size` (`sm` 18px · `md` 26px · `lg` 44px · `xl` 72px), `dotcom` (añade ".com" en `tinta-suave`).

- Usa `dotcom` solo donde la persona tiene que escribir la dirección: cierres de carrusel, pies de slide, materiales impresos. En la web y en la app, sin ".com".
- Dale al logo un espacio libre igual a la altura de la etiqueta por todos los lados.
- La etiqueta siempre lleva el contorno `prais-linea`, también en el tema noche.
- No: cambiar el color de la etiqueta, separar "usa" de "prais", escribirlo con mayúscula inicial ("Usaprais") ni como "UsaPrais".

### PraisAvatar

El personaje Prais en uno de sus cuatro estados de ánimo, dibujado en SVG.

**Props:** `mood` (`tranqui` · `pensando` · `ganga` · `pilas`), `size` (px, por defecto 96), `ground` (círculo `prais-fondo` detrás; por defecto `true`), `title` (texto alternativo; por defecto describe el estado).

Cada estado tiene un momento fijo en el producto:

| Estado | Cuándo |
|---|---|
| `tranqui` | Bienvenida, estados vacíos, ayuda. |
| `pensando` | Mientras busca precios (carga). |
| `ganga` | Encontró un precio por debajo del promedio. |
| `pilas` | El precio consultado está caro, o hay un vendedor con pocas referencias. |

- Siempre con `ground` sobre fondos de color o en el tema noche; sin círculo solo sobre `sol` o en ilustraciones grandes (slides).
- Tamaño mínimo 32px. Por debajo de 48px no muestra detalles: úsalo solo como firma de mensajes.
- No lo recortes, no lo voltees, no le cambies los colores ni le dibujes estados nuevos sin pasar por esta guía.

### Sticker

La etiqueta inclinada de cartel para la capa de marca: slides de Instagram, campañas, landing. No se usa en el producto.

**Props:** `tone` (`sol` · `barato` · `normal` · `caro` · `ojo`), `tilt` (grados, por defecto -3), `icon`, `children`.

- En pantallas con precios para comparar, usa `Badge`.
- Máximo tres palabras; Bungee las pone en mayúsculas.
- Alterna la inclinación entre -5° y 4° cuando hay varios cerca.
- El texto dice el veredicto y `barato`/`caro` llevan ícono: el color nunca es la única señal.
- Los tonos `normal` y `ojo` tienen colores fijos de papel kraft, porque el sticker siempre va sobre fondos de marca.

## Canales

### MensajeCanal

El mismo resultado escrito en el formato nativo de cada canal: WhatsApp (Flow o mensaje), una respuesta en un hilo de X o un DM de Instagram.

**Props:** `canal` (`whatsapp` · `x` · `instagram`), `producto`, `ofertas`, `tasa`, `enlace`, `mood` (avatar de la firma), `texto` (para mostrar un texto propio en vez del generado).

El texto sale de `Prais.textoParaCanal(canal, datos)`, que puedes usar directo en tus bots:

- **WhatsApp:** hasta 5 precios con negritas `*así*`, una línea de contexto por oferta y el enlace a la lista completa.
- **X:** una sola respuesta de máximo 280 caracteres: tienda, total, ahorro y enlace. El contador avisa si te pasas.
- **Instagram:** un DM corto que acompaña al carrusel (`IGSlide`).
- Sin emojis en las plantillas. Si un canal lo pide, máximo uno, y nunca en lugar de una palabra.

### IGSlide

Un slide de carrusel de Instagram de 1080 × 1350, mostrado a escala: portada, oferta o cierre.

**Props:** `tipo` (`portada` · `oferta` · `cierre`), `ancho` (px de la vista previa, por defecto 270). Portada: `producto`, `revisados`, `kicker`. Oferta: `oferta` (objeto de `OfferRow`), `rank`, `de`, `tasa`, `ahorro`. Cierre: `titulo`, `subtitulo`.

- El carrusel es: 1 portada + hasta 5 ofertas + 1 cierre.
- Los slides siempre usan el tema papel, aunque la app esté en noche: son imágenes que se exportan.
- Portada en `sol` con Prais `pilas`; ofertas en `papel` con marco `sol`; cierre en `tomate` con Prais `ganga`.
- Para exportar, renderiza con `ancho={1080}` y captura el nodo.
