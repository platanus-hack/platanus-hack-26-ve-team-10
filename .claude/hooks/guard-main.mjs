// Hook de Claude Code (PreToolUse, Bash): main está bloqueado, todo entra por PR.
// Frena un `git push` que apunte a main, o un `git push` sin rama estando en main.
// Hacia el mirror Pleo2/prais.com sí se permite: es lo que hace `pnpm sync`.
// También frena cualquier push por origin si el clon no sube en paralelo a los dos repos.
import { execSync } from "node:child_process";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const command = JSON.parse(input || "{}").tool_input?.command ?? "";

const pushes = command
  .split(/&&|\|\||;|\n/)
  .map((part) => part.trim())
  .filter((part) => /^git\s+push\b/.test(part));
if (pushes.length === 0) process.exit(0);

let current = "";
try {
  current = execSync("git branch --show-current", { encoding: "utf8" }).trim();
} catch {}

const toMain = pushes.some((push) => {
  const args = push.split(/\s+/).slice(2).filter((arg) => !arg.startsWith("-"));
  if (/^prais$|Pleo2\/prais\.com/.test(args[0] ?? "")) return false; // el mirror sí recibe main (pnpm sync)
  if (args.length <= 1) return current === "main"; // git push / git push origin
  return args
    .slice(1)
    .some((spec) => /(^|:)(refs\/heads\/)?main$/.test(spec) || (/(^|:)HEAD$/.test(spec) && current === "main"));
});
// Todo push por origin tiene que ir en paralelo a Platanus y a prais.com (pnpm setup:git).
let pushUrls = "";
try {
  pushUrls = execSync("git config --get-all remote.origin.pushurl", { encoding: "utf8" });
} catch {}
const viaOrigin = pushes.some((push) => /^git\s+push(\s+-\S+)*(\s+origin\b|\s*$)/.test(push));
if (viaOrigin && !(pushUrls.includes("platanus-hack-26-ve-team-10") && pushUrls.includes("Pleo2/prais.com"))) {
  deny("Este clon no sube en paralelo a Platanus y prais.com. Corre `pnpm setup:git` y vuelve a hacer el push.");
}

if (!toMain) process.exit(0);

deny("main está bloqueado: todo entra por PR. Crea una rama (git switch -c <tipo>/<tema>), haz push de la rama y abre el PR con gh pr create.");

function deny(reason) {
  console.log(JSON.stringify({ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: reason } }));
  process.exit(0);
}
