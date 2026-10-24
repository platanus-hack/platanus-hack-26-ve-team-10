# Página de marca

El hub de una marca (`/ve/marca/samsung/`) y el índice de todas las marcas (`/ve/marcas/`). Este doc es la referencia viva de ambas: si cambia una decisión, se cambia aquí por PR.

## Qué búsqueda ataca

La marca sola ("samsung", "nike", "apple": 40.500 búsquedas al mes cada una) la gana la web oficial: no es el objetivo. La página de marca apunta a **"[marca] venezuela"**: "adidas venezuela" 4.400/mes, "samsung venezuela" 1.600, "nike venezuela" 1.300, "xiaomi venezuela" 1.000. La demanda de compra ("motos bera" 12.100, "zapatos nike" 9.900, "teléfonos honor" 3.600) la captura la página categoría + marca ([categoria.md](categoria.md)), y la marca le pasa enlaces a ellas.

## URLs

```
/ve/marca/samsung/      marca con ofertas en 2 o más categorías
/ve/marca/bera/         301 a /ve/motos/bera/ (solo vende en una categoría)
/ve/marcas/             índice A–Z
```

- **Un slug por marca**, normalizado: "LG Electronics", "LG" y "lg" son `lg`. Los alias se guardan para asignar ofertas, no generan URLs.

## Marcas de una sola categoría

- Si una marca tiene ofertas en **una sola categoría** (Bera y Toro solo venden motos), `/ve/marca/bera/` **redirige con 301** a `/ve/motos/bera/`. Así no hay dos páginas que compitan por "motos bera".
- Si suma ofertas en una segunda categoría, la redirección se quita y la página de marca se activa sola.
- Usa la misma regla anti-parpadeo de [categoria.md](categoria.md#cuándo-se-indexa): se activa al llegar a 2 categorías y vuelve a redirigir solo si pasa dos semanas seguidas con una sola.
- Los enlaces internos (índice, fichas, breadcrumbs) apuntan siempre a la URL final, nunca a una que redirige.

## Title y H1

```
Title: Samsung en Venezuela: precios de teléfonos, neveras y más desde $29 | Prais
H1:    Samsung en Venezuela
```

Las categorías del title son las dos con más modelos de la marca.

## Bloques, en orden

1. **Resumen con datos.** "Samsung tiene 87 modelos en 6 categorías y 21 comercios de Venezuela, desde $29 (Bs 1.161). Lo más buscado: Galaxy A56 y neveras Samsung. Precios vistos el 24 de octubre."
2. **Categorías de la marca.** Una tarjeta por categoría: "Teléfonos Samsung · 42 modelos · desde $129", que enlaza a `/ve/telefonos/samsung/`. Es el núcleo del hub. Si la categoría + marca todavía no tiene página abierta, la tarjeta enlaza a la categoría con el filtro de marca.
3. **Modelos más buscados.** Los 8 a 12 modelos más populares de la marca (mismo puntaje que el orden de [categoria.md](categoria.md)), con la tarjeta de siempre: precio nuevo en USD + Bs y "en N comercios".
4. **Comercios que la venden.** Los comercios con más ofertas de la marca, con su puntaje de confianza. Sin enlace a un perfil: por ahora no hay página de comercio. No se dice "distribuidor oficial": ese dato no se tiene.
5. **Preguntas frecuentes con datos.** "¿Dónde comprar Samsung en Venezuela?", "¿Cuál es el Samsung más barato?", "¿Qué Samsung es el más buscado?". Las respuestas salen de los datos del momento.
6. **Breadcrumbs.** Inicio › Marcas › Samsung.

## Índice de marcas `/ve/marcas/`

- Lista A–Z de todas las marcas con al menos una oferta, con la cantidad de modelos de cada una.
- Las marcas de una sola categoría enlazan directo a su categoría + marca (`/ve/motos/bera/`), no a la URL que redirige.
- Poco tráfico propio: sirve para que Google llegue a todas las marcas.

## Schema

- `BreadcrumbList`.
- `ItemList` con las fichas del bloque "Modelos más buscados".
- Sin `Product`: eso va en cada ficha.

## Qué datos necesita

Además de lo que piden la [ficha](ficha-producto.md) y la [categoría](categoria.md):

| Dato | Para qué |
|---|---|
| Tabla de marcas: slug, nombre visible y alias | Normalizar y asignar ofertas |
| Cantidad de categorías con oferta por marca, y desde cuándo | Decidir si la página se activa o redirige |
| Ofertas por comercio y marca | Bloque "Comercios que la venden" |
