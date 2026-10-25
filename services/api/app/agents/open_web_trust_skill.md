# Cómo decidir si una oferta de la web abierta se puede recomendar

Esto es el procedimiento que usa Prais. La versión estricta, con RDAP, DNS, Safe Browsing y las páginas de políticas, está en `resources/website_trust_score.py`. Aquí no se inventa ese puntaje: cada listado de la web abierta trae `trust_review`, calculado con las mismas reglas que se pueden aplicar con lo que la búsqueda ya trajo.

## Qué significa cada veredicto

- **riesgosa.** Hay una bandera roja. No la abras primero. Di la razón que viene en `reasons`, con esas palabras.
- **precaucion.** No es una estafa demostrada, pero hay una señal mala (la página no es https). Menciónala en una frase y no la pongas como la mejor.
- **sin_datos.** No medimos antigüedad del dominio, RIF, políticas ni si Google marca el sitio. Eso no es "confiable". No digas que la tienda es segura. Habla del precio y de que la confianza de esa tienda no está medida.
- **confiable** no sale de este procedimiento. Decirlo exigiría el puntaje estricto, y no se corrió.

## Banderas rojas

Son las del archivo estricto que se pueden ver en el listado:

- El precio está más de 50 % por debajo de las otras ofertas con precio de la misma búsqueda.
- El dominio imita una marca (el nombre de la marca está en el dominio y no es el dominio de esa marca).
- El título es una funda, una carcasa, un forro, una copia, un clon o una réplica, y la persona no pidió eso.

Una bandera roja deja la oferta en riesgosa. No la recomiendes como el lugar donde comprar.

## Qué no haces

No calcules un número de confianza. No completes datos que `trust_review` no trae. Si el veredicto es `sin_datos`, dilo así: la tienda no está medida.
