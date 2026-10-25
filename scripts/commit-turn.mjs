// Al terminar un turno de Cursor, si quedaron archivos cambiados, pide un commit.
// Así el trabajo de un turno no se mezcla con el del siguiente.
import { execSync } from "node:child_process";

let input = "";
for await (const chunk of process.stdin) input += chunk;

let payload = {};
try {
  payload = JSON.parse(input || "{}");
} catch {
  payload = {};
}

if (payload.status !== "completed") process.exit(0);

let porcelain = "";
try {
  porcelain = execSync("git status --porcelain", { encoding: "utf8" });
} catch {
  process.exit(0);
}

const lines = porcelain.split("\n").filter(Boolean).filter((line) => {
  const path = line.slice(3).split(" -> ").pop().trim();
  if (path === ".env" || path.endsWith("/.env")) return false;
  if (path.endsWith(".env") && !path.endsWith(".env.example")) return false;
  if (path.includes("credentials")) return false;
  return true;
});

if (lines.length === 0) process.exit(0);

const listed = lines.slice(0, 40).join("\n");
const message = [
  "Este turno cambió archivos y no los dejó en un commit.",
  "Haz un solo commit con esos cambios y para. No empieces otra tarea.",
  "El mensaje va en inglés, en Conventional Commits, y dice por qué en una o dos frases.",
  "No incluyas secretos (.env, credenciales) y no hagas push.",
  "Si el cambio toca código o configuración, incluye AGENTS.md o docs/ en el mismo commit. Si no hace falta actualizar docs, pon DOCS_REVIEWED=1 delante del commit.",
  "Archivos:",
  listed,
].join("\n");

console.log(JSON.stringify({ followup_message: message }));
