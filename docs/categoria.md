# Página de categoría

El listado de modelos de una categoría (`/ve/telefonos/`), de una categoría con marca (`/ve/telefonos/xiaomi/`) o de una faceta con demanda (`/ve/zapatos-deportivos/dama/`). Reparte autoridad hacia las fichas, que son las que más tráfico traen ([ficha-producto.md](ficha-producto.md)), y compite por búsquedas como "motos bera" (12.100/mes) o "televisores de 32 pulgadas" (2.400/mes). Los datos están en [resources/keywords-ve.md](../resources/keywords-ve.md).

Este doc es la referencia viva de la categoría: si cambia una decisión, se cambia aquí por PR.

## Taxonomía

- **Lista propia y cerrada**, de ~150 categorías, con el nombre que más se busca en Venezuela: `neveras` (no refrigeradores), `cornetas` (no parlantes), `cauchos`, `franelas`, `perrarina`, `zapatos-deportivos` (no tenis, que trae el deporte), `telefonos`.
- **Un solo nivel.** No hay páginas de departamento: el menú agrupa las categorías (Tecnología, Hogar…), pero esos grupos no tienen URL.
- Cada producto (`productId`) pertenece a una sola categoría. Las categorías de las fuentes no se copian: cada oferta se asigna a una de la lista.
- Cada categoría guarda sus sinónimos (`zapatos-deportivos`: tenis, gomas, zapatillas). Se usan en el texto y en el buscador, no en URLs.

## URLs

```
/ve/telefonos/                       categoría
/ve/telefonos/xiaomi/                categoría + marca
/ve/zapatos-deportivos/dama/         categoría + faceta
/ve/telefonos/?pagina=2              paginación
/ve/telefonos/?precio=100-300        filtro: noindex, canonical a la página sin filtro
```

- Una sola faceta por URL indexable: no hay `/ve/zapatos-deportivos/nike/dama/`. Las combinaciones van como parámetros en `noindex`.
- Lo que no es categoría, marca ni faceta abierta (precio, condición, ciudad, pago, orden) va en parámetros, con `noindex` y canonical a la página base.

## Cuándo se indexa

| Página | Se indexa si |
|---|---|
| Categoría | Tiene al menos un modelo con oferta |
| Categoría + marca | Tiene 5 o más modelos con oferta |
| Faceta | Tiene búsquedas en el CSV de keywords **y** 5 o más modelos con oferta |

- **La regla es automática** y se recalcula cada semana. No hay lista manual.
- **Para que no parpadee:** una página se abre al llegar a 5 modelos y se cierra solo si queda por debajo de 3 durante dos semanas seguidas.
- Una página cerrada no da 404: queda en `noindex, follow` y sale del sitemap, así los enlaces siguen pasando hacia las fichas.

## Title y H1

```
Categoría:   Teléfonos en Venezuela: precios hoy desde $89 | Prais
Cat + marca: Teléfonos Xiaomi en Venezuela: precios desde $109 (Redmi, Poco) | Prais
Faceta:      Zapatos deportivos de dama: precios en Venezuela desde $25 | Prais
Página 2+:   … | Página 2 | Prais
H1:          Teléfonos · Teléfonos Xiaomi · Zapatos deportivos de dama
```

## Bloques, en orden

1. **Resumen con datos (solo en la página 1).** Un párrafo generado: "Hay 124 teléfonos en 18 comercios de Venezuela, desde $89 (Bs 3.565). El más buscado es el iPhone 17; el más barato, el Redmi A5. Precios vistos el 24 de octubre". Responde primero, como pide [agents/seo-geo.md](../agents/seo-geo.md).
2. **Filtros.** Marca, rango de precio, condición, ciudad y método de pago. Las marcas y facetas que tienen página abierta son **enlaces normales** a su URL; el resto son parámetros.
3. **Listado.** Ordenado por **popularidad**: primero los modelos más buscados (volumen del CSV) y con más ofertas. Cuando haya datos de clics propios, entran en el cálculo. Cada tarjeta lleva:
   - Foto y nombre del modelo.
   - **Desde $1.299 · Bs 52.025**: el precio nuevo más bajo, como en la ficha. Si solo tiene usados, dice "usado desde".
   - **En 7 comercios.**
4. **Paginación numerada.** 24 modelos por página, con enlaces `<a href>` reales a `?pagina=2`, `?pagina=3`… Cada página tiene su propio canonical (no apunta a la página 1), para que Google llegue a todas las fichas.
5. **Enlaces relacionados.** En una categoría: sus marcas y facetas abiertas. En una categoría + marca: las series de la marca (Redmi, Poco) y la categoría madre.
6. **Preguntas frecuentes con datos (solo en la página 1).** "¿Cuál es el teléfono más barato en Venezuela?", "¿Cuál es el más buscado?", "¿Cuánto cuesta un teléfono Xiaomi?", "¿Dónde comprar teléfonos en Caracas?". Las respuestas salen de los datos del momento.
7. **Breadcrumbs.** Inicio › Teléfonos › Xiaomi.

## Categoría + marca

Usa la misma plantilla, pero con identidad propia: su title, su resumen ("Xiaomi tiene 31 modelos en Venezuela, desde $109; el más buscado es el Redmi 15C"), sus preguntas ("¿Cuál es el Xiaomi más barato?") y enlaces a sus series. No es la categoría con un filtro marcado.

## Schema

- `BreadcrumbList`.
- `ItemList` con la URL de cada ficha listada, en orden.
- Sin `Product` ni `AggregateOffer` en la categoría: eso va en cada ficha.

## Qué datos necesita

Además de lo que pide la [ficha](ficha-producto.md#qué-datos-necesita-cambios-de-contrato):

| Dato | Para qué |
|---|---|
| `categoryId` del producto, de la lista propia | Armar la categoría |
| `brand` y `series` normalizadas del producto | Páginas categoría + marca y sus enlaces a series |
| Atributos de faceta (género, pulgadas, capacidad…) | Páginas de faceta |
| Puntaje de popularidad por producto: volumen de búsqueda del modelo + cantidad de ofertas | Orden del listado |
| Estado semanal de cada página (abierta o cerrada, y desde cuándo) | La regla de indexación sin parpadeo |
