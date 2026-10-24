import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { askPrais } from "../agent.js";

const Body = z.object({
  sessionId: z.string().min(1).max(100),
  message: z.string().min(1).max(1000),
});

// Chat de la web: la página llama a /api/chat y Next lo reenvía aquí.
export async function chatRoutes(app: FastifyInstance) {
  app.post("/chat", async (request, reply) => {
    const body = Body.safeParse(request.body);
    if (!body.success) return reply.code(400).send({ error: "Body inválido" });

    try {
      const answer = await askPrais({ userId: `web:${body.data.sessionId}`, message: body.data.message });
      return { reply: answer };
    } catch (error) {
      request.log.error(error, "chat failed");
      return reply.code(502).send({ reply: "Algo falló de mi lado. Inténtalo otra vez en un momento." });
    }
  });
}
