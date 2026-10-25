import { empresa } from "./empresa";

// Páginas estáticas para SEO y GEO. De aquí salen las páginas, el sitemap, /llms.txt y /llms-full.txt:
// si cambias un texto, cambia en todos lados. Cada página responde primero y después da el detalle.
export type Guia = {
  slug: string;
  title: string; // <title>: lo que se busca, sin la marca (el layout le agrega "| usaprais")
  description: string;
  h1: string;
  resumen: string; // primer párrafo: la respuesta directa, la parte que citan los asistentes de IA
  secciones: { titulo: string; parrafos: string[] }[];
  preguntas: { pregunta: string; respuesta: string }[];
};

const nombres = "usaprais (también lo buscan como usa prais, usaprice o usaprices)";

export const guias: Guia[] = [
  {
    slug: "comparador-de-precios",
    title: "Comparador de precios en Venezuela",
    description:
      "usaprais es un comparador de precios para Venezuela: busca un producto en tiendas web, Instagram, Marketplace y Mercado Libre y te dice dónde está más barato, en dólares y en bolívares.",
    h1: "Comparador de precios en Venezuela",
    resumen: `${nombres} es un comparador de precios para Venezuela. Le dices qué quieres comprar y revisa los principales canales de venta del país, como tiendas web, Instagram, Facebook Marketplace y Mercado Libre. Te devuelve las ofertas ordenadas de la más barata a la más cara, en dólares y en bolívares, con la fuente y la fecha de cada precio y la confianza de cada comercio.`,
    secciones: [
      {
        titulo: "Por qué hace falta un comparador de precios en Venezuela",
        parrafos: [
          "En Venezuela el mismo producto puede costar muy distinto de un negocio a otro, incluso en la misma calle. Muchos precios se marcan en dólares y se cobran en bolívares, y cada negocio hace la conversión con la tasa que le conviene. A eso se suman el envío y los recargos según cómo pagues.",
          "Comparar a mano significa preguntar en varios negocios y revisar catálogos en redes sociales. usaprais hace esa comparación por ti en un solo mensaje.",
        ],
      },
      {
        titulo: "Cómo compara usaprais",
        parrafos: [
          "Ordena por precio total, con envío incluido, de menor a mayor. Un precio bajo con envío caro no gana.",
          "Cada precio en dólares lleva su equivalente en bolívares y la tasa usada. Cada oferta dice de dónde salió el precio y cuándo se revisó.",
          "Califica la confianza de cada comercio. Si la opción más barata tiene un vendedor con pocas referencias, te lo dice.",
        ],
      },
      {
        titulo: "Dónde usarlo",
        parrafos: [
          "En la web, en usaprais.com, con un chat. Por WhatsApp, escribiéndole a Prais, el asistente de usaprais. Y desde ChatGPT, Claude u otro asistente de IA, que pueden consultar los precios por MCP en usaprais.com/api/mcp.",
        ],
      },
    ],
    preguntas: [
      {
        pregunta: "¿Qué es un comparador de precios?",
        respuesta:
          "Es un servicio que busca el mismo producto en varias tiendas y te muestra los precios lado a lado, para que sepas dónde comprarlo más barato. usaprais lo hace para Venezuela.",
      },
      {
        pregunta: "¿usaprais cobra por comparar precios?",
        respuesta: "No. usaprais es gratis para quien compra y no cobra a las tiendas por aparecer.",
      },
      {
        pregunta: "¿usaprais vende productos?",
        respuesta:
          "No. Muestra precios públicos y enlaza a la publicación original. La compra es entre tú y la tienda.",
      },
      {
        pregunta: "¿Muestra los precios en bolívares?",
        respuesta: "Sí. Cada precio en dólares lleva su equivalente en bolívares y la tasa que se usó para convertirlo.",
      },
    ],
  },
  {
    slug: "comparador-de-celulares",
    title: "Comparador de celulares: precios de teléfonos en Venezuela",
    description:
      "Compara el precio de un celular en las tiendas de Venezuela antes de comprarlo. usaprais te dice dónde está más barato el mismo modelo, con envío, garantía y la confianza del vendedor.",
    h1: "Comparador de celulares en Venezuela",
    resumen:
      "Para comparar el precio de un celular en Venezuela, escríbele a usaprais el modelo exacto, por ejemplo \"Redmi Note 15 128 GB\" o \"iPhone 16\", y tu ciudad. usaprais busca ese mismo modelo en tiendas web, Instagram, Facebook Marketplace y Mercado Libre y te devuelve las ofertas de la más barata a la más cara, con el precio total en dólares y en bolívares, el envío, si es nuevo o usado, la garantía y la confianza del vendedor.",
    secciones: [
      {
        titulo: "Qué comparar además del precio",
        parrafos: [
          "Condición: un teléfono nuevo, uno usado como nuevo y uno reacondicionado no valen lo mismo. usaprais muestra la condición junto al precio.",
          "Garantía: la diferencia entre 0 y 12 meses de garantía puede valer más que la diferencia de precio.",
          "Vendedor: en Marketplace e Instagram hay vendedores con pocas referencias. Si la oferta más barata es de uno de ellos, usaprais te lo advierte y te sugiere pedir un video del equipo funcionando antes de pagar.",
          "Envío: el orden es por precio total con envío, no por el precio de la publicación.",
        ],
      },
      {
        titulo: "Cómo pedirlo para que la comparación sea exacta",
        parrafos: [
          "Escribe la marca, el modelo y la capacidad: \"Samsung Galaxy A56 256 GB\" compara mejor que \"Samsung barato\". Si no sabes el modelo, dile a Prais tu presupuesto y para qué lo quieres, y te pregunta lo que falte.",
        ],
      },
    ],
    preguntas: [
      {
        pregunta: "¿Cómo comparo celulares en Venezuela?",
        respuesta:
          "Escríbele a usaprais el modelo y tu ciudad, en usaprais.com o por WhatsApp. Te devuelve las ofertas del mismo modelo ordenadas por precio total, con envío, condición, garantía y confianza del vendedor.",
      },
      {
        pregunta: "¿usaprais compara especificaciones técnicas?",
        respuesta:
          "No. usaprais compara precios del mismo modelo entre tiendas. Para elegir entre modelos distintos, dile tu presupuesto y para qué lo quieres.",
      },
      {
        pregunta: "¿Incluye teléfonos usados?",
        respuesta: "Sí, cuando aparecen en Marketplace o en otras tiendas. La condición se muestra junto a cada precio.",
      },
    ],
  },
  {
    slug: "que-es-usaprais",
    title: "Qué es usaprais",
    description:
      "usaprais (también usaprice o usaprices) es un comparador de precios para Venezuela, creado por el team-10 en Platanus Hack 26 Caracas, en el track Trust.",
    h1: "Qué es usaprais",
    resumen: `${nombres} es un comparador de precios para Venezuela con un asistente de IA llamado Prais. Le dices qué quieres comprar y te dice dónde está el mejor precio, comparando tiendas web, Instagram, Facebook Marketplace y Mercado Libre, con precios en dólares y bolívares, la tasa usada y la confianza de cada comercio. Lo creó el team-10 en la hackathon Platanus Hack 26 Caracas, en el track Trust.`,
    secciones: [
      {
        titulo: "El problema que resuelve",
        parrafos: [
          "En Venezuela el mismo producto puede costar muy distinto según el negocio, y eso genera desconfianza al comprar. usaprais busca en los principales canales de venta y muestra los precios lado a lado, para que compres sabiendo cuánto cuesta el producto en cada lugar.",
        ],
      },
      {
        titulo: "Platanus Hack 26 Caracas",
        parrafos: [
          "usaprais es el proyecto del team-10 en Platanus Hack 26: Caracas ft. Yummy Project, en el track Trust. En la entrega aparece con el nombre Prais.",
          "Equipo: Jose Leonardo Moreno (@Pleo2), Enrique Uzcategui (@enriqueuz), Roybert Parada (@roybertparada), Diego Gallovich (@diegogallovich) y Genaro Villegas (@colarussozz).",
          "El código es público en github.com/platanus-hack/platanus-hack-26-ve-team-10.",
        ],
      },
      {
        titulo: "Cómo está hecho",
        parrafos: [
          "Una web en Next.js con un chat, y un backend en Python con FastAPI. El agente Prais usa Google ADK con Gemini y tiene una herramienta que busca ofertas en paralelo en todas las fuentes, las convierte a dólares y bolívares, las filtra y las ordena.",
          "Responde en tres canales: la web, WhatsApp (a través de Kapso) y un servidor MCP en usaprais.com/api/mcp con la herramienta search_prices, para que ChatGPT, Claude u otros asistentes de IA consulten precios directamente.",
        ],
      },
      {
        titulo: "Quién está detrás",
        parrafos: [
          `usaprais es un servicio de ${empresa.razonSocial}. Contacto: ${empresa.correo}, ${empresa.telefono}.`,
        ],
      },
    ],
    preguntas: [
      {
        pregunta: "¿Es lo mismo usaprais, usaprice y usaprices?",
        respuesta:
          "Sí. El nombre oficial es usaprais, en minúscula y junto. Prais es el nombre del asistente y el nombre del proyecto en la hackathon.",
      },
      {
        pregunta: "¿Quién hizo usaprais?",
        respuesta:
          "El team-10 de Platanus Hack 26 Caracas: Jose Leonardo Moreno, Enrique Uzcategui, Roybert Parada, Diego Gallovich y Genaro Villegas.",
      },
      {
        pregunta: "¿Cómo uso usaprais desde ChatGPT o Claude?",
        respuesta:
          "Agrega el servidor MCP https://usaprais.com/api/mcp a tu asistente. Tiene la herramienta search_prices, que recibe el producto, la zona y si necesitas envío.",
      },
    ],
  },
];

export function guia(slug: string): Guia {
  const encontrada = guias.find((g) => g.slug === slug);
  if (!encontrada) throw new Error(`No existe la guía ${slug}`);
  return encontrada;
}
