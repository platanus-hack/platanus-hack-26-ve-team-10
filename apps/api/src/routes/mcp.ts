import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { searchOffers } from "../lib/search.js";

// Las tools llaman directo a la búsqueda, sin el agente: quien pregunta ya es un asistente de IA.
function createServer() {
  const server = new McpServer({ name: "prais", version: "0.1.0" });

  server.registerTool(
    "search_prices",
    {
      title: "Search prices in Venezuela",
      description:
        "Find where a product is cheapest in Venezuela across the main sales channels. Returns offers sorted by USD price, with the original price, the exchange rate used, when the price was seen and a 0-100 trust score for each merchant.",
      inputSchema: {
        query: z.string().describe("Product with brand and size or model, e.g. 'Harina PAN 1 kg'"),
        zone: z.string().optional().describe("City or area in Venezuela"),
        needs_delivery: z.boolean().optional(),
      },
      annotations: { readOnlyHint: true },
    },
    async ({ query, zone, needs_delivery }) => {
      const result = searchOffers(query, { zone, needsDelivery: needs_delivery });
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  return server;
}

export async function mcpRoutes(app: FastifyInstance) {
  app.all("/mcp", async (request, reply) => {
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined, // sin sesiones: cada request es independiente
      enableJsonResponse: true,
    });
    const server = createServer();
    reply.raw.on("close", () => {
      void transport.close();
      void server.close();
    });
    await server.connect(transport);
    reply.hijack(); // la respuesta la escribe el transporte de MCP
    await transport.handleRequest(request.raw, reply.raw, request.body);
  });
}
