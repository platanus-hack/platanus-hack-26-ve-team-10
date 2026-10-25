// Frena un commit que cambia código o configuración y no toca docs.
// Lo llama el hook de git (.githooks/pre-commit) y el de Cursor (.cursor/hooks/check-docs).
// Si el cambio no afecta la documentación, se repite con DOCS_REVIEWED=1 delante del commit.
import { execSync } from "node:child_process";

const CODE = /^(apps\/[^/]+\/(src\/|app\/|requirements\.txt$|package\.json$|next\.config\.ts$|Dockerfile$|\.env\.example$)|package\.json$|pnpm-workspace\.yaml$|\.github\/|infra\/|cloudbuild\.[a-z]+\.yaml$)/;
const DOCS = /^(AGENTS\.md$|docs\/)/;

const REASON =
  "Revisa si el cambio afecta la arquitectura, una ruta, una variable de entorno, una dependencia o el deploy. " +
  "Si la afecta, actualiza AGENTS.md y el doc de docs/ que corresponda (la tabla está en AGENTS.md) y agrégalos al commit. " +
  "Si no hace falta tocar docs, repite el commit con DOCS_REVIEWED=1 delante.";

export function review(files) {
  const code = files.filter((file) => CODE.test(file));
  const docs = files.filter((file) => DOCS.test(file));
  if (code.length === 0 || docs.length > 0) return null;
  return `Este commit cambia ${code.join(", ")} sin tocar la documentación. ${REASON}`;
}

function gitLines(command) {
  return execSync(command, { encoding: "utf8" }).split("\n").filter(Boolean);
}

function filesForCommit(command) {
  const files = gitLines("git diff --cached --name-only");
  if (/(^|\s)-a\b|--all\b|\bgit\s+add\b/.test(command)) {
    files.push(...gitLines("git diff --name-only && git ls-files --others --exclude-standard"));
  }
  return files;
}

function fail(message, cursor) {
  if (!cursor) {
    console.error(message);
    process.exit(1);
  }
  console.log(JSON.stringify({ permission: "deny", user_message: message, agent_message: message }));
}

const cursor = process.argv.includes("--cursor");
let command = "";
if (cursor) {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  try {
    command = JSON.parse(input || "{}").command ?? "";
  } catch {
    command = "";
  }
  if (typeof command !== "string") command = "";
  if (!/\bgit\s+commit\b/.test(command)) {
    console.log(JSON.stringify({ permission: "allow" }));
    process.exit(0);
  }
}

if (command.includes("DOCS_REVIEWED=1") || process.env.DOCS_REVIEWED === "1") {
  if (cursor) console.log(JSON.stringify({ permission: "allow" }));
  process.exit(0);
}

let files = [];
try {
  files = filesForCommit(command);
} catch {
  if (cursor) console.log(JSON.stringify({ permission: "allow" }));
  process.exit(0);
}

const message = review(files);
if (message) fail(message, cursor);
else if (cursor) console.log(JSON.stringify({ permission: "allow" }));
