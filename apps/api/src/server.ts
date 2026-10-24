import Fastify from "fastify";
import { chatRoutes } from "./routes/chat.js";
import { mcpRoutes } from "./routes/mcp.js";
import { whatsappRoutes } from "./routes/whatsapp.js";

const app = Fastify({ logger: true });

app.get("/health", async () => ({ ok: true }));
await app.register(chatRoutes);
await app.register(whatsappRoutes);
await app.register(mcpRoutes);

await app.listen({ host: "0.0.0.0", port: Number(process.env.PORT ?? 4000) });
