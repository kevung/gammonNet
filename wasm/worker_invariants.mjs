/*
 * Les invariants du PROTOCOLE DE WORKER — ce que `worker.mjs` doit tenir
 * maintenant qu'il relaie la recherche et plus seulement des lots.
 *
 * POURQUOI CE FICHIER EXISTE. `api_invariants.mjs` vérifie ce que le module
 * RÉPOND ; celui-ci vérifie ce que le worker RELAIE. Ce sont deux surfaces
 * distinctes, et c'est la seconde qui manquait : trois points d'entrée de la
 * recherche étaient exportés du `.wasm` sans qu'aucun message ne permette de
 * les atteindre, et le consommateur a réécrit la recherche à côté plutôt que
 * de le remarquer. Une surface non testée est une surface qu'on croit avoir.
 *
 * SUR LE FAUX `self`. Node n'a pas l'API `Worker` du DOM. Le protocole est
 * donc exercé en installant un `self` factice avant d'importer `worker.mjs` :
 * ce qui est testé est la LOGIQUE du protocole — file, générations,
 * annulation, relais — et non l'isolation de thread, qui est celle du
 * navigateur et que `wasm/decision.html` exerce pour de vrai.
 *
 * SPDX-License-Identifier: MIT
 */
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const MODEL = join(ROOT, "models", "cubeless_prob5_512_512_256_128.bin");
const PRUNE = join(ROOT, "models", "prune_32.bin");
const MODULE = pathToFileURL(join(ROOT, "build", "wasm", "gammonnet-simd.mjs")).href;

const POSITION = "4HPwATDgc/ABMA";

let failures = 0;
function check(label, ok, detail = "") {
  console.log(`${ok ? "✅" : "❌"} ${label}${detail ? "  " + detail : ""}`);
  if (!ok) failures++;
}

/* Le faux `self` : une boîte aux lettres, et rien d'autre. */
const inbox = [];
let notify = null;
globalThis.self = {
  onmessage: null,
  postMessage(data) {
    inbox.push(data);
    if (notify) { const n = notify; notify = null; n(); }
  },
};

await import("./worker.mjs");

const send = (data) => self.onmessage({ data });

/* Attendre un message d'un type donné, avec un plafond : un protocole qui
 * ne répond jamais doit échouer, pas suspendre la suite de tests. */
async function next(predicate, label, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const index = inbox.findIndex(predicate);
    if (index >= 0) return inbox.splice(index, 1)[0];
    if (Date.now() > deadline) throw new Error(`aucun message « ${label} » avant expiration`);
    await new Promise((resolve) => {
      notify = resolve;
      setTimeout(resolve, 20);
    });
  }
}

const modelBytes = new Uint8Array(readFileSync(MODEL));
const pruneBytes = new Uint8Array(readFileSync(PRUNE));

/* 1. `init` prend la CONFIGURATION, pas seulement le modèle.
 *
 * Un worker qui charge le modèle et rien d'autre tourne sans élagage et sans
 * table de fin de partie, sans que rien ne le dise : c'est le mode de
 * défaillance de CLAUDE.md §2, appliqué à une configuration au lieu d'un
 * réseau. `ready` porte donc le `k` réellement en vigueur. */
send({ type: "init", id: 0, factoryUrl: MODULE, modelBytes, pruneBytes, pruneK: 12 });
const ready = await next((m) => m.type === "ready" || m.type === "error", "ready");
check("init rend `ready`", ready.type === "ready", ready.message || "");
check("`ready` dit l'élagage réellement en vigueur", ready.pruneK === 12, `k=${ready.pruneK}`);

/* 2. LES TROIS POINTS D'ENTRÉE DE LA RECHERCHE SONT RELAYÉS.
 *
 * C'est l'invariant de la fiche T86, et il tient en trois lignes parce que le
 * manque tenait en trois lignes. */
send({ type: "bestPlay", id: 1, positionId: POSITION, turn: 0, d1: 3, d2: 1,
       options: { ply: 0 } });
const best = await next((m) => m.id === 1, "bestPlay");
check("`bestPlay` relayé", best.type === "result" && typeof best.outcome?.equity === "number",
      best.message || `${best.outcome?.resultId}`);

send({ type: "rankPlays", id: 2, positionId: POSITION, turn: 0, d1: 3, d2: 1,
       options: { ply: 0, max: 10 } });
const ranked = await next((m) => m.id === 2, "rankPlays");
check("`rankPlays` relayé", ranked.type === "result" && Array.isArray(ranked.outcome)
      && ranked.outcome.length > 1, ranked.message || `${ranked.outcome?.length} candidats`);

send({ type: "cubeDecision", id: 3, positionId: POSITION, turn: 0,
       options: { ply: 0, owner: 0, efficiency: 0.688 } });
const cube = await next((m) => m.id === 3, "cubeDecision");
check("`cubeDecision` relayé", cube.type === "result" && typeof cube.outcome?.action === "string",
      cube.message || cube.outcome?.action);

/* 3. Le worker répond LA MÊME CHOSE que l'appel direct. Un relais qui
 * transforme n'est plus un relais. */
const { Evaluator } = await import("./gammonnet.mjs");
const factory = (await import(MODULE)).default;
const direct = await Evaluator.create(factory, modelBytes);
direct.loadPrune(pruneBytes, 12);
const reference = direct.bestPlay(POSITION, 0, 3, 1, { ply: 0 });
check("le relais ne transforme rien",
      best.outcome.resultId === reference.resultId
      && Math.abs(best.outcome.equity - reference.equity) < 1e-9,
      `${best.outcome.resultId} / ${reference.resultId}`);

/* 4. LE MODE PROGRESSIF rend deux réponses, la superficielle d'abord.
 *
 * C'est la seule frontière d'annulation qui existe à l'intérieur d'une
 * décision : le 0-ply coûte ~6 ms, le 2-ply ~2,7 s. */
send({ type: "bestPlay", id: 4, positionId: POSITION, turn: 0, d1: 3, d2: 1,
       progressive: true, options: { ply: 2, filterTop: 1, filterInner: 1 } });
const partial = await next((m) => m.id === 4 && m.type === "partial", "partial");
check("progressif : le 0-ply arrive d'abord", partial.ply === 0
      && typeof partial.outcome?.equity === "number", `${partial.outcome?.equity}`);
const deep = await next((m) => m.id === 4 && m.type !== "partial", "result profond");
check("progressif : le résultat profond suit", deep.type === "result" && deep.ply === 2,
      deep.message || `ply=${deep.ply}`);

/* 5. UN TRAVAIL ANNULÉ REÇOIT UNE RÉPONSE, ET C'EST `cancelled`.
 *
 * L'annulation silencieuse n'est pas une annulation, c'est un blocage : un
 * appelant qui attend une promesse resterait suspendu. Ici deux décisions
 * profondes sont mises en file puis `stop` arrive : la seconde n'a pas encore
 * tourné, elle doit revenir annulée, et le worker doit rester UTILISABLE. */
send({ type: "rankPlays", id: 5, positionId: POSITION, turn: 0, d1: 3, d2: 1,
       options: { ply: 0, max: 5 } });
send({ type: "rankPlays", id: 6, positionId: POSITION, turn: 0, d1: 3, d2: 1,
       options: { ply: 0, max: 5 } });
send({ type: "stop", id: 7 });
const stopped = await next((m) => m.id === 6, "réponse à la requête dépassée");
check("une requête dépassée revient `cancelled`", stopped.type === "cancelled", stopped.type);

/* 6. LE WORKER SURVIT À L'ANNULATION — le point qui vaut 1,06 Mo.
 *
 * `Worker.terminate()` est le seul arrêt dur du navigateur, et il emporte les
 * poids : un geste annulé coûte alors un rechargement complet. Avec les
 * générations, le worker reste chaud et répond à la requête suivante. */
send({ type: "bestPlay", id: 8, positionId: POSITION, turn: 0, d1: 3, d2: 1,
       options: { ply: 0 } });
const afterStop = await next((m) => m.id === 8, "requête après annulation");
check("le worker reste chaud après un `stop`",
      afterStop.type === "result" && afterStop.outcome.resultId === reference.resultId,
      afterStop.message || afterStop.type);

/* 7. `analyze` : plusieurs décisions, une progression, un tableau parallèle. */
send({ type: "analyze", id: 9, kind: "bestPlay", options: { ply: 0 },
       positions: [
         { positionId: POSITION, turn: 0, d1: 3, d2: 1 },
         { positionId: POSITION, turn: 0, d1: 6, d2: 5 },
         { positionId: POSITION, turn: 0, d1: 5, d2: 5 },
       ] });
const progress = await next((m) => m.id === 9 && m.type === "progress", "progress");
check("`analyze` rend compte de sa progression", progress.total === 3, `${progress.done}/${progress.total}`);
const analysed = await next((m) => m.id === 9 && m.type === "result", "analyze");
check("`analyze` rend une décision par position",
      Array.isArray(analysed.outcome) && analysed.outcome.length === 3
      && analysed.outcome.every((o) => typeof o?.equity === "number"),
      `${analysed.outcome?.length}`);

/* 8. Le protocole d'AVANT est intact : `evaluate` répond toujours des lots.
 *
 * `gammonnet.mjs` et `pool.mjs` sont vendorisés tels quels par gammonGo ;
 * T86 ajoute, elle ne remplace pas. */
const features = new Float32Array(direct.numFeatures * 2);
send({ type: "evaluate", id: 10, features, count: 2, chunk: 1 });
const batch = await next((m) => m.id === 10, "evaluate");
check("`evaluate` répond comme avant",
      batch.type === "result" && batch.count === 2
      && batch.outputs.length === 2 * direct.numOutputs, batch.message || batch.type);

console.log(failures === 0
  ? "\n✅ invariants du protocole de worker tenus"
  : `\n❌ ${failures} invariant(s) rompu(s)`);
process.exit(failures === 0 ? 0 : 1);
