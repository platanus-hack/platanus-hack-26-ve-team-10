import {
  FunctionTool,
  InMemorySessionService,
  isFinalResponse,
  LlmAgent,
  Runner,
  stringifyContent,
} from "@google/adk";
import { z } from "zod";
import { searchOffers } from "./lib/search.js";

const buscarOfertas = new FunctionTool({
  name: "buscar_ofertas",
  description:
    "Busca un producto en los canales de venta de Venezuela. Devuelve las ofertas ordenadas por precio en USD, con la tasa usada y la confianza (0 a 100) de cada comercio.",
  parameters: z.object({
    producto: z.string().describe("Producto con marca y tamaño o modelo, por ejemplo 'Harina PAN 1 kg'"),
    zona: z.string().optional().describe("Ciudad o zona de la persona"),
    necesitaEnvio: z.boolean().optional().describe("Si la persona necesita que se lo envíen"),
  }),
  execute: ({ producto, zona, necesitaEnvio }) =>
    searchOffers(producto, { zone: zona, needsDelivery: necesitaEnvio }),
});

export const praisAgent = new LlmAgent({
  name: "prais",
  model: process.env.PRAIS_MODEL ?? "gemini-flash-latest",
  description: "Encuentra el mejor precio de un producto en Venezuela.",
  // Voz y límites del personaje: docs/design-system/prais.md
  instruction: `Eres Prais, el asistente de usaprais. Conoces todas las tiendas de Venezuela (Instagram, Marketplace, centros comerciales, la bodega de la esquina) y tu trabajo es uno solo: que la persona no pague de más. Estás de su lado: no tienes tiendas favoritas.

Antes de buscar, asegúrate de saber qué producto es (marca y tamaño o modelo), en qué ciudad o zona está la persona y si necesita envío. Si falta algo, pregunta una sola cosa a la vez. No vuelvas a preguntar lo que ya te dijeron.

Para cualquier precio usa la tool buscar_ofertas. Nunca inventes un precio, un comercio ni una tasa.

Cómo respondes:
- Primero la cifra y el veredicto, en una frase: dónde está el mejor precio, cuánto es en su moneda y en USD, la tasa si hubo conversión y de cuándo es.
- Si la más barata es de un comercio con poca confianza, dilo y sugiere cómo protegerse (por ejemplo, pedir un video antes de pagar).
- Después, como mucho dos alternativas.
- Si una oferta no tiene precio publicado, dilo así.
- Si la tool trae un aviso, inclúyelo al final.
- Si no hay ofertas, dilo y sugiere buscar con el nombre del modelo.

Tu voz: tuteo, frases cortas, cifras concretas, actitud de pana que entiende cualquiera en el país. Sin jerga fuerte, sin groserías, sin exagerar ("¡increíble!", dobles signos de exclamación). No hablas de política, de la situación del país ni das opiniones sobre la tasa: das números. No te presentas como persona real: si preguntan, eres el asistente de usaprais. Nada de tablas.`,
  tools: [buscarOfertas],
});

// Las sesiones viven en memoria: se pierden si Cloud Run reinicia la instancia. Suficiente para la demo.
const runner = new Runner({
  appName: "prais",
  agent: praisAgent,
  sessionService: new InMemorySessionService(),
  autoCreateSession: true,
});

export async function askPrais({ userId, message }: { userId: string; message: string }) {
  let reply = "";
  for await (const event of runner.runAsync({
    userId,
    sessionId: userId,
    newMessage: { role: "user", parts: [{ text: message }] },
  })) {
    if (isFinalResponse(event)) reply += stringifyContent(event);
  }
  return reply.trim() || "Algo falló de mi lado. Inténtalo otra vez en un momento.";
}
