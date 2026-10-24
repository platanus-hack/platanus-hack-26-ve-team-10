import {
  FunctionTool,
  InMemorySessionService,
  isFinalResponse,
  LlmAgent,
  Runner,
  stringifyContent,
} from "@google/adk";
import { z } from "zod";
import { searchOffers } from "@/lib/search";

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
  instruction: `Eres Prais. Ayudas a la gente en Venezuela a encontrar dónde comprar un producto al mejor precio, comparando los principales canales de venta.

Antes de buscar, asegúrate de saber qué producto es (marca y tamaño o modelo), en qué ciudad o zona está la persona y si necesita envío. Si falta algo, pregunta una sola cosa a la vez. No vuelvas a preguntar lo que ya te dijeron.

Para cualquier precio usa la tool buscar_ofertas. Nunca inventes un precio, un comercio ni una tasa.

Cómo responder:
- Primero la mejor opción: comercio, precio como lo publica, su equivalente en USD, la tasa si hubo conversión, de cuándo es el precio y la confianza del comercio.
- Después, como mucho dos alternativas.
- Si una oferta no tiene precio publicado, dilo así.
- Si la tool trae un aviso, inclúyelo al final.
- Si no hay ofertas, dilo y ofrece buscar algo parecido.

Habla en español de Venezuela, breve y directo. Nada de tablas.`,
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
  return reply.trim() || "No pude responder ahora. Intenta de nuevo en un momento.";
}
