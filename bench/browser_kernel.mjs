/*
 * browser_kernel.mjs -- T84, volet navigateur : le même banc, dans un vrai
 * moteur de navigateur.
 *
 * POURQUOI, ALORS QUE NODE SUFFIRAIT PRESQUE
 *
 * Node embarque V8, donc `node build/wasm/bench_kernel_*.js` mesure déjà le
 * moteur de Chromium. Ce qu'il ne mesure pas, c'est le NAVIGATEUR : ses
 * réglages de compilation WebAssembly (tiering Liftoff → TurboFan), sa
 * politique d'horloge, et surtout Firefox, dont le moteur (SpiderMonkey) est
 * une implémentation entièrement différente de SIMD128. La règle 3 de
 * `CLAUDE.md` interdit de transposer l'un à l'autre sans mesurer.
 *
 * Aucun protocole d'automatisation : un serveur statique, un navigateur pointé
 * dessus, et la page qui renvoie son résultat -- le même dispositif que
 * `wasm/harness.mjs`, qui marche identiquement dans Chromium et dans Firefox là
 * où leurs protocoles de débogage respectifs ne marchent pas. Profil neuf à
 * chaque fois : le profil du développeur ferait entrer extensions et caches
 * dans une mesure.
 *
 *   node bench/browser_kernel.mjs --browser chromium --widths 8,16,32
 *
 * SPDX-License-Identifier: MIT
 */

import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { readFile, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join, normalize } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const WASM = join(ROOT, "build", "wasm");

const args = new Map();
for (let i = 2; i < process.argv.length; i += 2) {
  args.set(process.argv[i].replace(/^--/, ""), process.argv[i + 1]);
}
const browser = args.get("browser") || "chromium";
const widths = (args.get("widths") || "8,16,32").split(",").map(Number);
const kernels = (args.get("kernels") || "auto,intrin").split(",");
const reps = args.get("reps") || "2";
const decisions = args.get("decisions") || "3";
const timeoutMs = Number(args.get("timeout") || 600_000);

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".wasm": "application/wasm",
  ".data": "application/octet-stream",
};

/*
 * La page. Elle définit `Module` AVANT de charger le script émis par
 * Emscripten -- `arguments` doit exister au moment où `main` part, et `print`
 * doit être détourné avant la première ligne, sans quoi la sortie du banc va
 * dans la console et nulle part ailleurs.
 */
function page(kernel, width) {
  return `<!doctype html><meta charset="utf-8"><title>bench_kernel</title>
<pre id="out"></pre>
<script>
  const lines = [];
  var Module = {
    arguments: ["models/cubeless_prob5_512_512_256_128.bin",
                "models/prune_32.bin", "${reps}", "${decisions}"],
    print: (text) => {
      lines.push(text);
      document.getElementById("out").textContent += text + "\\n";
      /* La derniere ligne du banc, et non onExit : sans EXIT_RUNTIME le
         runtime survit a main et onExit n'est jamais appele. */
      if (text.indexOf("decision 2-ply") >= 0 || text.indexOf("cision 2-ply") >= 0) {
        fetch("/result", { method: "POST", body: JSON.stringify({ lines }) });
      }
    },
    printErr: (text) => { lines.push("ERR " + text); },
  };
</script>
<script src="/bench_kernel_${kernel}_${width}.js"></script>`;
}

async function measure(kernel, width) {
  let resolve;
  const answered = new Promise((r) => { resolve = r; });

  const server = createServer(async (request, response) => {
    if (request.method === "POST" && request.url === "/result") {
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      response.writeHead(204).end();
      resolve(JSON.parse(Buffer.concat(chunks).toString()).lines);
      return;
    }
    if (request.url === "/" || request.url.startsWith("/?")) {
      response.writeHead(200, { "content-type": TYPES[".html"] });
      response.end(page(kernel, width));
      return;
    }
    const path = normalize(join(WASM, decodeURIComponent(request.url.split("?")[0])));
    if (!path.startsWith(WASM)) { response.writeHead(403).end(); return; }
    try {
      const body = await readFile(path);
      const dot = path.lastIndexOf(".");
      response.writeHead(200, {
        "content-type": TYPES[path.slice(dot)] || "application/octet-stream",
      });
      response.end(body);
    } catch { response.writeHead(404).end(); }
  });

  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const port = server.address().port;
  const profile = await mkdtemp(join(tmpdir(), "gn-kernel-"));
  const flags = browser.includes("firefox")
    ? ["--headless", "--profile", profile, `http://127.0.0.1:${port}/`]
    : ["--headless=new", `--user-data-dir=${profile}`, "--no-first-run",
       "--disable-gpu", `http://127.0.0.1:${port}/`];
  const child = spawn(browser, flags, { stdio: "ignore" });

  const timer = setTimeout(() => resolve(null), timeoutMs);
  const lines = await answered;
  clearTimeout(timer);
  child.kill();
  server.close();
  /* Le navigateur écrit encore dans son profil quand il reçoit le signal ;
     effacer trop tôt lève ENOTEMPTY. On laisse partir, puis on nettoie sans
     faire échouer la mesure pour un répertoire temporaire. */
  await new Promise((r) => setTimeout(r, 500));
  await rm(profile, { recursive: true, force: true }).catch(() => {});
  if (lines === null) throw new Error(`${browser} n'a rien renvoyé en ${timeoutMs} ms`);
  return lines;
}

const RATE = /débit du noyau[^:]*:\s*([0-9.]+) éval\/s/;
const DECISION = /décision 2-ply[^:]*:\s*([0-9.]+) s/;
const EXACT = /max\|Δ\| = ([0-9.e+-]+)/;

const table = [];
for (const width of widths) {
  for (const kernel of kernels) {
    const lines = await measure(kernel, width);
    const text = lines.join("\n");
    const row = {
      browser, width, kernel,
      rate: Number(text.match(RATE)[1]),
      decision: Number(text.match(DECISION)[1]),
      maxDelta: Number(text.match(EXACT)[1]),
    };
    table.push(row);
    console.log(`${browser}  largeur ${String(width).padStart(2)}  ` +
                `${kernel.padEnd(7)}  ${row.rate.toFixed(1).padStart(9)} éval/s  ` +
                `${row.decision.toFixed(4)} s  max|Δ| ${row.maxDelta.toExponential(1)}`);
  }
}

/* La référence est la configuration LIVRÉE : largeur 32, auto-vectorisée. Si
   le balayage ne l'a pas incluse, la première ligne sert de repère et la
   colonne « gain » n'est plus comparable à l'artefact — le message le dit. */
const base = table.find((r) => r.width === 32 && r.kernel === "auto") || table[0];
if (base.width !== 32 || base.kernel !== "auto") {
  console.log(`\n(référence = ${base.width}/${base.kernel}, PAS la configuration livrée)`);
}
console.log(`\n── T84 — ${browser} : par largeur et par noyau ──`);
for (const row of table) {
  console.log(
    `${String(row.width).padStart(7)}  ${row.kernel.padEnd(8)}` +
    `${row.rate.toFixed(1).padStart(10)} éval/s  ${(row.rate / base.rate).toFixed(2)}x` +
    `   ${row.decision.toFixed(4)} s  ${(base.decision / row.decision).toFixed(2)}x`);
}
const out = args.get("json");
if (out) await writeFile(out, JSON.stringify(table, null, 2));
