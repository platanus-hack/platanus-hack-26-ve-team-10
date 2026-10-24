import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { z } from "zod";
import { searchOffers } from "@/lib/search";

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

async function handle(request: Request) {
  const transport = new WebStandardStreamableHTTPServerTransport({
    sessionIdGenerator: undefined, // sin sesiones: cada request es independiente
    enableJsonResponse: true,
  });
  await createServer().connect(transport);
  return transport.handleRequest(request);
}

export { handle as DELETE, handle as GET, handle as POST };
