/*
 * harness.mjs -- run the page in a real browser and collect its answer.
 *
 * No automation protocol. A static server, a browser pointed at it, and the
 * page posting its result back. That works identically in Chromium and in
 * Firefox, which their respective remote-debugging protocols do not, and it
 * leaves nothing installed to go stale.
 *
 * A fresh profile is used every time. Reusing the developer's own profile
 * would risk hijacking a running browser, and would let extensions and caches
 * into a measurement.
 *
 *   node wasm/harness.mjs --browser chromium --mode bench --build simd
 *
 * SPDX-License-Identifier: MIT
 */

import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { readFile, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join, normalize } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");

const args = new Map();
for (let i = 2; i < process.argv.length; i += 2) {
  args.set(process.argv[i].replace(/^--/, ""), process.argv[i + 1]);
}
const browser = args.get("browser") || "chromium";
const mode = args.get("mode") || "parity";
const build = args.get("build") || "scalar";
const reps = args.get("reps") || "5";
const headless = args.get("headless") !== "0";
const timeoutMs = Number(args.get("timeout") || 120_000);

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  // Le type MIME du .wasm n'est pas cosmétique : `instantiateStreaming`
  // refuse tout ce qui n'est pas application/wasm.
  ".wasm": "application/wasm",
  ".bin": "application/octet-stream",
};

let resolveReport;
const reported = new Promise((resolve) => { resolveReport = resolve; });

const server = createServer(async (request, response) => {
  if (request.method === "POST" && request.url === "/report") {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    response.writeHead(204).end();
    resolveReport(JSON.parse(Buffer.concat(chunks).toString()));
    return;
  }

  // La query est retirée AVANT de reconnaître la racine : `/?mode=bench` n'est
  // pas `/`, et la page se serait servi un 404 à elle-même.
  const requested = request.url.split("?")[0];
  const path = requested === "/" ? "/wasm/page.html" : requested;
  // Le serveur ne sert que l'arbre du dépôt : une traversée par `..` ne doit
  // pas transformer un banc de mesure en lecteur de système de fichiers.
  const resolved = normalize(join(ROOT, decodeURIComponent(path)));
  if (!resolved.startsWith(ROOT)) {
    response.writeHead(403).end("hors du dépôt");
    return;
  }

  try {
    const body = await readFile(resolved);
    const extension = resolved.slice(resolved.lastIndexOf("."));
    response.writeHead(200, {
      "content-type": TYPES[extension] || "application/octet-stream",
      // Une mesure ne doit jamais lire une réponse mise en cache.
      "cache-control": "no-store",
    });
    response.end(body);
  } catch {
    response.writeHead(404).end("absent");
  }
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const { port } = server.address();
const url = `http://127.0.0.1:${port}/?mode=${mode}&build=${build}&reps=${reps}`;

const profile = await mkdtemp(join(tmpdir(), "gammonnet-profile-"));

const COMMANDS = {
  chromium: [
    "chromium",
    [
      ...(headless ? ["--headless=new"] : []),
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      `--user-data-dir=${profile}`,
      url,
    ],
  ],
  firefox: [
    "firefox",
    [...(headless ? ["--headless"] : []), "--new-instance", "--profile", profile, url],
  ],
};

if (!COMMANDS[browser]) {
  console.error(`navigateur inconnu : ${browser} (chromium | firefox)`);
  process.exit(2);
}

const [command, commandArgs] = COMMANDS[browser];
const child = spawn(command, commandArgs, { stdio: args.get("debug") ? "inherit" : "ignore" });

let failed = false;
const timer = setTimeout(() => {
  console.error(`❌ ${browser} : aucun résultat après ${timeoutMs} ms`);
  failed = true;
  resolveReport(null);
}, timeoutMs);

const report = await reported;
clearTimeout(timer);

child.kill("SIGTERM");
server.close();

// Laisser le navigateur relâcher son profil avant de l'effacer : il écrit
// encore, et `rm` échouerait sur ENOTEMPTY en emportant le résultat avec lui.
await new Promise((resolve) => {
  const done = setTimeout(resolve, 3_000);
  child.once("exit", () => { clearTimeout(done); resolve(); });
});
await rm(profile, { recursive: true, force: true }).catch(() => {});

if (!report) process.exit(1);

console.log(JSON.stringify({ browser, headless, ...report }, null, 2));
if (report.error || report.parityOk === false) failed = true;
process.exit(failed ? 1 : 0);
