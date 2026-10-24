// Hook de Claude Code (PreToolUse, Bash): antes de un `git commit`, si el commit cambia
// código o configuración y no toca los docs, pide revisar si la arquitectura cambió.
// Si no hace falta tocar docs, el agente repite el commit con DOCS_REVIEWED=1 delante.
import { execSync } from "node:child_process";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const command = JSON.parse(input || "{}").tool_input?.command ?? "";

if (!/\bgit\s+commit\b/.test(command) || command.includes("DOCS_REVIEWED=1")) process.exit(0);

let staged = [];
try {
  staged = execSync("git diff --cached --name-only", { encoding: "utf8" }).split("\n").filter(Boolean);
} catch {
  process.exit(0); // fuera de un repo git: no opinamos
}
// `git commit -a` o un `git add` en el mismo comando: el hook corre antes, así que también
// cuentan los cambios que todavía no están en stage.
if (/(^|\s)-a\b|--all\b|\bgit\s+add\b/.test(command)) {
  const pending = "git diff --name-only && git ls-files --others --exclude-standard";
  staged.push(...execSync(pending, { encoding: "utf8" }).split("\n").filter(Boolean));
}

const code = staged.filter((f) => /^(src\/|package\.json$|next\.config\.ts$|Dockerfile$|\.env\.example$|\.github\/)/.test(f));
const docs = staged.filter((f) => /^(agents\/|AGENTS\.md$|docs\/)/.test(f));
if (code.length === 0 || docs.length > 0) process.exit(0);

console.log(
  JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason:
        `Este commit cambia ${code.join(", ")} sin tocar la documentación. ` +
        "Revisa si cambia la arquitectura, una ruta, una variable de entorno, una dependencia o cómo se despliega. " +
        "Si cambia, actualiza AGENTS.md y el doc que corresponda de agents/ (ver la tabla \"Qué doc leer\" en AGENTS.md), " +
        "agrégalos con git add y vuelve a hacer el commit. " +
        "Si no hace falta tocar docs, repite el mismo comando con DOCS_REVIEWED=1 delante: `DOCS_REVIEWED=1 git commit ...`.",
    },
  }),
);
