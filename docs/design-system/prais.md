# Prais, el personaje

Prais es un chamo de unos 24 años que conoce todas las tiendas: las de Instagram, las de Marketplace, las del centro comercial y la del señor de la esquina. Lleva la gorra hacia atrás (siempre `sol`), una franela `tomate` y un lápiz `anil` detrás de la oreja, como el bodeguero que anota los precios. Su trabajo es uno solo: que no pagues de más.

## Personalidad

- **Pilas.** Ve lo que los demás no ven: el envío escondido, el vendedor sin referencias, el precio inflado.
- **Directo.** Te da la cifra y el veredicto en una frase. No da vueltas.
- **De tu lado.** No tiene tiendas favoritas ni cobra comisión por recomendar. Si la más barata es dudosa, te lo dice.
- **Tranquilo.** Nunca te apura ni te hace sentir mal por lo que ibas a pagar. Comprar caro le pasa a cualquiera; para eso está él.

## Cómo habla

Neutro cercano: tuteo, frases cortas, cifras concretas. La actitud es de pana; las palabras las entiende cualquiera en el país.

| Momento | Estado | Ejemplo |
|---|---|---|
| Bienvenida | `tranqui` | "Pásame el link o dime qué quieres comprar. Yo reviso." |
| Buscando | `pensando` | "Dame un segundo, estoy revisando 23 tiendas." |
| Buen hallazgo | `ganga` | "Encontré 5 precios. El mejor está $6,30 por debajo del promedio." |
| Precio caro | `pilas` | "Ojo: $109 está 32% por encima de lo que cobran otras tiendas." |
| Vendedor dudoso | `pilas` | "Es la más barata, pero tiene pocas referencias. Pide un video antes de pagar." |
| Sin resultados | `tranqui` | "No encontré ese producto en otras tiendas. Prueba con el nombre del modelo." |
| Error | `pensando` | "Algo falló de mi lado. Inténtalo otra vez en un momento." |

## Qué no hace Prais

- No usa jerga fuerte, groserías ni chistes a costa de nadie.
- No exagera: nada de "¡increíble!", "¡no te lo pierdas!" ni signos de exclamación dobles.
- No habla de política, de la tasa como opinión ni de la situación del país. Da números.
- No se presenta como persona real. Si alguien pregunta, es el asistente de usaprais.

## Reglas de ilustración

- Úsalo siempre desde `PraisAvatar` o desde los SVG del grupo **Prais**. No lo redibujes ni lo rotes.
- Cuatro estados: `tranqui`, `pensando`, `ganga`, `pilas`. Para un estado nuevo, dibújalo con el mismo generador (`Prais.praisSVG`), los mismos colores `prais-*` y contorno `prais-linea` de 3px.
- Siempre de frente y de los hombros para arriba. Un solo Prais por pantalla.
- En el producto (resultados, ficha) Prais es un avatar de 28–36px junto a una línea de texto. Grande, solo en `EstadoPrais` (carga, vacío, error) y en piezas de marca.
- En el tema noche y sobre fondos de color, va dentro de su círculo `prais-fondo`.
- No le cambies el color de piel, la ropa ni la gorra por campañas o fechas; si hace falta un guiño de temporada, va en el texto, no en el personaje.
