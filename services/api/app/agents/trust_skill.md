# Cómo hablar de la confianza de una oferta

Lo usan el orquestador de WhatsApp y el MCP, para que la misma tienda se describa igual en los dos. El puntaje lo calcula el código (`app/lib/trust.py`), con las señales que cada fuente sí midió. Tú no lo calculas ni lo completas.

## Qué trae cada oferta

- **El puntaje del contrato:** `verdict`, `score` de 0 a 100, `redFlags` y `reasons`. En la tarjeta de WhatsApp se ve en estrellas de 0 a 5.
- **Solo un número**, sin veredicto: es el puntaje provisional de una fuente que todavía no emite el contrato. Puedes nombrarlo, pero no digas que la tienda es confiable por eso.
- **`stage` parcial:** la fuente midió lo suyo y falta el cierre con las demás fuentes. No lo uses para recomendar ni para descartar, salvo que ya traiga una bandera roja.
- **Nada:** la confianza de esa tienda no está medida.

## Qué significa cada veredicto

- **confiable.** Se puede abrir primero si el precio también conviene. Di por qué con lo que viene en `reasons`.
- **precaucion.** Hay una señal mala. Nómbrala en una frase y no la pongas como la mejor si hay otra confiable con un precio parecido.
- **riesgosa.** Hay una bandera roja y el puntaje queda en 0. No la recomiendes. Di la razón con las palabras de `redFlags`.
- **sin_datos.** Se midió menos del 40 % del peso de las señales. No es "confiable" ni "riesgosa": di que la confianza de esa tienda no está medida y habla del precio.

## Las banderas rojas

- El precio está más de 50 % por debajo de la mediana de las otras ofertas de la misma búsqueda.
- El dominio imita una marca: el nombre de la marca está en el dominio y no es el de esa marca.
- El anuncio es una funda, una copia o un accesorio, y la persona no pidió eso.
- Las fotos están copiadas de otros vendedores, o el precio de Amazon está muy por debajo del mismo producto.

## Qué no haces

- No inventas un número ni una señal.
- No dices que una tienda es "segura" o "verificada".
- No tratas `sin_datos` como algo bueno.
- No escondes una oferta poco confiable si es la más barata: la muestras con su advertencia.
