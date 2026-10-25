import { empresa } from "./empresa";
import { guias } from "./guias";

// /llms.txt (índice) y /llms-full.txt (todo el contenido), según https://llmstxt.org.
const encabezado = `# usaprais

> usaprais (también usa prais, usaprice o usaprices) es un comparador de precios para Venezuela con un asistente de IA llamado Prais. Compara tiendas web, Instagram, Facebook Marketplace y Mercado Libre y dice dónde está el mejor precio, en dólares y bolívares, con la tasa usada, la fuente y la fecha de cada precio y la confianza de cada comercio. Proyecto del team-10 en Platanus Hack 26 Caracas (track Trust). Servicio de ${empresa.razonSocial}.
`;

const enlaces = (descripcion: boolean) =>
  guias.map((g) => `- [${g.h1}](${empresa.sitio}/${g.slug})${descripcion ? `: ${g.description}` : ""}`).join("\n");

export function llmsTxt() {
  return `${encabezado}
## Páginas

- [Inicio](${empresa.sitio}/): chat para comparar el precio de un producto
${enlaces(true)}

## Para asistentes de IA

- [Servidor MCP](${empresa.sitio}/api/mcp): Streamable HTTP, tool \`search_prices\` (query, zone?, needs_delivery?) que devuelve las ofertas en JSON
- [Contenido completo](${empresa.sitio}/llms-full.txt): todas las páginas en un solo archivo

## Optional

- [Código fuente](https://github.com/platanus-hack/platanus-hack-26-ve-team-10)
- [Política de privacidad](${empresa.sitio}/privacidad)
- [Términos de uso](${empresa.sitio}/terminos)
`;
}

export function llmsFullTxt() {
  const paginas = guias.map((g) =>
    [
      `## ${g.h1}`,
      `URL: ${empresa.sitio}/${g.slug}`,
      g.resumen,
      ...g.secciones.map((s) => `### ${s.titulo}\n\n${s.parrafos.join("\n\n")}`),
      `### Preguntas frecuentes\n\n${g.preguntas.map((p) => `**${p.pregunta}**\n${p.respuesta}`).join("\n\n")}`,
    ].join("\n\n"),
  );
  return `${encabezado}
${paginas.join("\n\n")}

## Contacto

${empresa.razonSocial} · ${empresa.correo} · ${empresa.telefono} · ${empresa.sitio}
`;
}
