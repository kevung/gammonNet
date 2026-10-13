/*
 * browser_threads.mjs -- what the threaded WebAssembly module gives a 2-ply
 * decision, in a real browser.
 *
 * The same device as `bench/browser_kernel.mjs` (static server, fresh
 * headless profile, the page posts its result back), plus the two headers
 * without which a browser refuses shared memory: COOP `same-origin` and COEP
 * `require-corp`. Without them `crossOriginIsolated` is false and the
 * threaded module cannot start -- the worker then reports the error rather
 * than a single-threaded number dressed as a threaded one.
 *
 *   node bench/browser_threads.mjs --browser chromium --threads 1,2,4,8,16
 *   node bench/browser_threads.mjs --browser firefox --decisions 20
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
const threadCounts = (args.get("threads") || "1,2,4,8,16").split(",").map(Number);
const decisions = Number(args.get("decisions") || "20");
const level = args.get("level") || "normal";
const build = args.get("build") || "gammonnet-simd-mt.mjs";
const timeoutMs = Number(args.get("timeout") || "900000");

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".wasm": "application/wasm",
  ".bin": "application/octet-stream",
};
const ISOLATION = {
  "cross-origin-opener-policy": "same-origin",
  "cross-origin-embedder-policy": "require-corp",
};

const PAGE = `<!doctype html><meta charset="utf-8"><title>threads</title>
<script type="module">
  const worker = new Worker("/wasm/threads_bench_worker.mjs", { type: "module" });
  worker.onmessage = ({ data }) =>
    fetch("/result", { method: "POST", body: JSON.stringify(data) });
  worker.onerror = (e) =>
    fetch("/result", { method: "POST", body: JSON.stringify({ ok: false, error: String(e.message) }) });
  worker.postMessage(${JSON.stringify({ build, threadCounts, decisions, level })});
</script>`;

let resolve;
const answered = new Promise((r) => { resolve = r; });
const server = createServer(async (request, response) => {
  if (request.method === "POST" && request.url === "/result") {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    response.writeHead(204).end();
    resolve(JSON.parse(Buffer.concat(chunks).toString()));
    return;
  }
  if (request.url === "/" || request.url.startsWith("/?")) {
    response.writeHead(200, { "content-type": TYPES[".html"], ...ISOLATION });
    response.end(PAGE);
    return;
  }
  const path = normalize(join(ROOT, decodeURIComponent(request.url.split("?")[0])));
  const allowed = ["wasm", "build/wasm", "models"].some((d) => path.startsWith(join(ROOT, d)));
  if (!allowed) { response.writeHead(403).end(); return; }
  try {
    const body = await readFile(path);
    response.writeHead(200, {
      "content-type": TYPES[path.slice(path.lastIndexOf("."))] || "application/octet-stream",
      ...ISOLATION,
    });
    response.end(body);
  } catch { response.writeHead(404).end(); }
});

await new Promise((r) => server.listen(0, "127.0.0.1", r));
const url = `http://127.0.0.1:${server.address().port}/`;
const profile = await mkdtemp(join(tmpdir(), "gn-threads-"));
const flags = browser.includes("firefox")
  ? ["--headless", "--profile", profile, url]
  : ["--headless=new", `--user-data-dir=${profile}`, "--no-first-run", "--disable-gpu", url];
const child = spawn(browser, flags, { stdio: "ignore" });
const timer = setTimeout(() => resolve({ ok: false, error: `rien en ${timeoutMs} ms` }), timeoutMs);
const result = await answered;
clearTimeout(timer);
child.kill();
server.close();
await new Promise((r) => setTimeout(r, 500));
await rm(profile, { recursive: true, force: true }).catch(() => {});

if (!result.ok) {
  console.error(`${browser} : ${result.error}`);
  process.exit(1);
}
console.log(`${browser} — ${result.decisions} décisions, niveau ${result.level}, ` +
            `hardwareConcurrency ${result.hardwareConcurrency}, ` +
            `crossOriginIsolated ${result.crossOriginIsolated}`);
const base = result.rows[0].seconds;
for (const row of result.rows) {
  console.log(`  ${String(row.threads).padStart(2)} fil(s)  ${row.seconds.toFixed(4)} s/décision  ` +
              `×${(base / row.seconds).toFixed(2)}  ${row.identical ? "identique" : "DIFFÉRENT"}`);
}
if (result.rows.some((row) => !row.identical)) process.exit(1);
