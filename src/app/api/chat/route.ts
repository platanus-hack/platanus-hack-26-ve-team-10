import { z } from "zod";
import { askPrais } from "@/agent";

const Body = z.object({
  sessionId: z.string().min(1).max(100),
  message: z.string().min(1).max(1000),
});

export async function POST(request: Request) {
  const body = Body.safeParse(await request.json().catch(() => null));
  if (!body.success) return Response.json({ error: "Body inválido" }, { status: 400 });

  try {
    const reply = await askPrais({ userId: `web:${body.data.sessionId}`, message: body.data.message });
    return Response.json({ reply });
  } catch (error) {
    console.error("chat failed", error);
    return Response.json({ reply: "No pude responder ahora. Intenta de nuevo en un momento." }, { status: 502 });
  }
}
