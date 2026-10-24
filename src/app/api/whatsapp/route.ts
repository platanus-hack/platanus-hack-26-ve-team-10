import { createHmac, timingSafeEqual } from "node:crypto";
import { WhatsAppClient } from "@kapso/whatsapp-cloud-api";
import { after } from "next/server";
import { askPrais } from "@/agent";

type MessageReceived = {
  phone_number_id?: string;
  message?: { id?: string; type?: string; from?: string; text?: { body?: string } };
};

function validSignature(rawBody: string, signature: string | null) {
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

// Kapso exige un 200 en menos de 10 segundos: respondemos y el agente trabaja después con after().
// En Cloud Run esto necesita CPU siempre asignada (--no-cpu-throttling).
export async function POST(request: Request) {
  const rawBody = await request.text();
  if (!validSignature(rawBody, request.headers.get("x-webhook-signature"))) {
    return new Response("Firma inválida", { status: 401 });
  }
  if (request.headers.get("x-webhook-event") !== "whatsapp.message.received") {
    return new Response(null, { status: 200 });
  }

  const payload = JSON.parse(rawBody);
  const events: MessageReceived[] = payload.batch ? payload.data : [payload];
  after(async () => {
    for (const event of events) {
      await reply(event).catch((error) => console.error("whatsapp reply failed", error));
    }
  });
  return new Response(null, { status: 200 });
}
