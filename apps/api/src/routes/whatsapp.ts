import { createHmac, timingSafeEqual } from "node:crypto";
import { WhatsAppClient } from "@kapso/whatsapp-cloud-api";
import type { FastifyBaseLogger, FastifyInstance } from "fastify";
import { askPrais } from "../agent.js";

type MessageReceived = {
  phone_number_id?: string;
  message?: { id?: string; type?: string; from?: string; text?: { body?: string } };
};

function validSignature(rawBody: string, signature: string | undefined) {
  const secret = process.env.KAPSO_WEBHOOK_SECRET;
  if (!secret || !signature) return false;
  const expected = createHmac("sha256", secret).update(rawBody).digest("hex");
  return expected.length === signature.length && timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}

async function reply({ phone_number_id, message }: MessageReceived) {
  const text = message?.text?.body?.trim();
  if (message?.type !== "text" || !text || !message.from || !phone_number_id) return;

  const answer = await askPrais({ userId: `whatsapp:${message.from}`, message: text });
  const client = new WhatsAppClient({
    baseUrl: "https://app.kapso.ai/api/meta/",
    kapsoApiKey: process.env.KAPSO_API_KEY!,
  });
  await client.messages.sendText({ phoneNumberId: phone_number_id, to: message.from, body: answer });
}

async function replyAll(events: MessageReceived[], log: FastifyBaseLogger) {
  for (const event of events) {
    await reply(event).catch((error) => log.error(error, "whatsapp reply failed"));
  }
}

// Webhook de Kapso. La firma se calcula sobre el cuerpo crudo, así que en este plugin
// el JSON llega como texto.
export async function whatsappRoutes(app: FastifyInstance) {
  app.addContentTypeParser("application/json", { parseAs: "string" }, (_request, body, done) => done(null, body));

  app.post("/whatsapp", async (request, reply) => {
    const rawBody = request.body as string;
    if (!validSignature(rawBody, request.headers["x-webhook-signature"] as string | undefined)) {
      return reply.code(401).send("Firma inválida");
    }
    if (request.headers["x-webhook-event"] !== "whatsapp.message.received") return reply.code(200).send();

    const payload = JSON.parse(rawBody);
    const events: MessageReceived[] = payload.batch ? payload.data : [payload];
    // Kapso exige un 200 en menos de 10 segundos: respondemos y el agente trabaja después.
    // En Cloud Run esto necesita CPU siempre asignada (--no-cpu-throttling).
    void replyAll(events, request.log);
    return reply.code(200).send();
  });
}
