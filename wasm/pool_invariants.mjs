/*
 * Les invariants de l'ORDONNANCEUR — ce que `pool.mjs` doit tenir, sans
 * navigateur et sans réseau de neurones.
 *
 * POURQUOI UN TROISIÈME FICHIER. `api_invariants.mjs` vérifie ce que le module
 * RÉPOND, `worker_invariants.mjs` ce que le worker RELAIE. Ni l'un ni l'autre
 * ne regarde ce que le pool DISTRIBUE : combien de tâches il fabrique, à qui
 * il les donne, et ce qu'il rend quand on l'interrompt. C'est pourtant là que
 * T87 travaille, et une propriété d'ordonnancement se teste beaucoup mieux
 * avec des workers dont on CHOISIT le temps de réponse qu'avec de vrais
 * workers dont on le subit.
 *
 * SUR LE FAUX `Worker`. Node n'a pas l'API `Worker` du DOM. Elle est donc
 * remplacée par une boîte qui répond après un délai que le test fixe. Ce qui
 * est vérifié est la LOGIQUE de distribution — nombre de tâches, couverture,
 * ordre du résultat, annulation, relevé — et non l'isolation de thread, qui
 * est celle du navigateur et que `wasm/ordonnancement.html` exerce pour de
 * vrai. Un worker qui répond en 1 ms est un excellent révélateur de
 * déséquilibre : à coût égal, tout écart de fin vient de l'ordonnancement.
 *
 * SPDX-License-Identifier: MIT
 */

let failures = 0;
function check(label, ok, detail = "") {
  console.log(`${ok ? "✅" : "❌"} ${label}${detail ? "  " + detail : ""}`);
  if (!ok) failures++;
}

const NUM_OUTPUTS = 5;
const NUM_FEATURES = 4;

/*
 * LE FAUX WORKER.
 *
 * `costOf(message)` donne le temps de réponse en millisecondes. C'est tout ce
 * qu'il faut pour fabriquer un déséquilibre reproductible : une tâche chère et
 * dix bon marché, et l'on voit immédiatement si le pool sait rattraper.
 */
let costOf = () => 1;
let liveWorkers = [];

class FakeWorker {
  constructor() {
    this.onmessage = null;
    this.onerror = null;
    this.terminated = false;
    this.inFlight = null;
    this.generation = 0;
    liveWorkers.push(this);
  }

  postMessage(data) {
    if (this.terminated) return;
    const { type, id } = data;

    if (type === "init") {
      setTimeout(() => this.onmessage?.({ data: { type: "ready", id, simd: false } }), 0);
      return;
    }

    if (type === "stop") {
      this.generation++;
      const flying = this.inFlight;
      this.inFlight = null;
      if (flying) {
        clearTimeout(flying.timer);
        setTimeout(() => this.onmessage?.({
          data: { type: "cancelled", id: flying.id, computeMs: 0 },
        }), 0);
      }
      return;
    }

    const ms = costOf(data);
    const mine = this.generation;
    const timer = setTimeout(() => {
      if (this.terminated || this.generation !== mine) return;
      this.inFlight = null;
      if (type === "evaluate") {
        const outputs = new Float32Array(data.count * NUM_OUTPUTS);
        /* Une sortie qui DIT de quelle position elle vient : c'est ce qui
         * permet de vérifier que le pool a réassemblé dans le bon ordre, et
         * pas seulement qu'il a rendu le bon nombre de flottants. */
        for (let i = 0; i < data.count; i++) {
          for (let k = 0; k < NUM_OUTPUTS; k++) {
            outputs[i * NUM_OUTPUTS + k] = data.features[i * NUM_FEATURES] + k / 10;
          }
        }
        this.onmessage?.({
          data: { type: "result", id: data.id, outputs, count: data.count, computeMs: ms },
        });
      } else {
        this.onmessage?.({
          data: {
            type: "result", id: data.id, kind: type, ply: 0, computeMs: ms,
            outcome: { positionId: data.positionId, equity: 0, resultId: "x", evaluations: ms },
          },
        });
      }
    }, ms);
    this.inFlight = { id: data.id, timer };
  }

  terminate() {
    this.terminated = true;
    if (this.inFlight) clearTimeout(this.inFlight.timer);
  }
}

globalThis.Worker = FakeWorker;
if (typeof performance === "undefined") globalThis.performance = { now: () => Date.now() };

const { EvaluatorPool } = await import("./pool.mjs");

async function makePool(size) {
  liveWorkers = [];
  return EvaluatorPool.create(size, "ignored", "ignored", new Uint8Array(0));
}

function makeFeatures(count) {
  const features = new Float32Array(count * NUM_FEATURES);
  for (let i = 0; i < count; i++) features[i * NUM_FEATURES] = i;
  return features;
}

/* ── 1. Le découpage de `analyze` : le défaut, et le réglage ────────────── */
{
  costOf = () => 1;
  const pool = await makePool(4);
  const count = 400;
  const job = pool.analyze(makeFeatures(count), count, NUM_FEATURES, { chunk: 64 });
  const outputs = await job.done;
  const report = job.schedule.toJSON();

  /* Le défaut est UNE TÂCHE PAR WORKER, et ce n'est pas un oubli : la mesure
   * T87 dit qu'en fabriquer davantage coûte plus de `postMessage` que cela ne
   * rattrape d'oisiveté sur ce chemin-là. Voir l'en-tête de `pool.mjs`. */
  check("`analyze` fait une tâche par worker par défaut",
        report.tasks === pool.size, `${report.tasks} tâches pour ${pool.size} workers`);

  let ordered = true;
  for (let i = 0; i < count; i++) {
    if (outputs[i * NUM_OUTPUTS] !== i) { ordered = false; break; }
  }
  check("le résultat est réassemblé dans l'ordre du corpus", ordered);
  check("chaque position est calculée une fois et une seule",
        outputs.length === count * NUM_OUTPUTS, `${outputs.length} sorties`);
  check("le relevé compte autant de tâches qu'il en a distribué",
        report.taskCounts.reduce((a, b) => a + b, 0) === report.tasks);
  pool.destroy();
}

/* ── 2. Le rattrapage : une tâche chère ne doit pas figer les autres ────── */
{
  /* Un corpus dont la PREMIÈRE moitié est lente. Avec une tâche par worker,
   * le worker qui hérite du début retient tout le monde ; avec plus de tâches
   * que de workers, les autres viennent l'aider. */
  costOf = (message) => (message.features[0] < 200 ? 20 : 2);
  const pool = await makePool(4);
  const count = 400;
  const job = pool.analyze(makeFeatures(count), count, NUM_FEATURES,
                           { chunk: 64, tasksPerWorker: 8 });
  await job.done;
  const report = job.schedule.toJSON();

  check("le réglage fabrique bien plus de tâches que de workers",
        report.tasks > pool.size, `${report.tasks} tâches pour ${pool.size} workers`);
  check("l'oisiveté reste sous 25 % malgré un corpus deux fois plus lent d'un côté",
        report.idlePool < 0.25, `${(report.idlePool * 100).toFixed(1)} %`);
  const spread = Math.max(...report.busyMs) - Math.min(...report.busyMs);
  check("les workers finissent ensemble à moins d'une tâche près",
        spread < report.taskMsMax * 1.5,
        `écart ${spread.toFixed(0)} ms, tâche max ${report.taskMsMax.toFixed(0)} ms`);
  pool.destroy();
}

/* ── 3. `decide` : une position, une tâche, et l'ordre du corpus ────────── */
{
  costOf = (message) => 1 + (Number(message.positionId) % 5);
  const pool = await makePool(3);
  const positions = Array.from({ length: 31 }, (_, i) => ({
    positionId: String(i), turn: 0, d1: 3, d2: 1,
  }));
  const job = pool.decide(positions, { kind: "bestPlay" });
  const outcomes = await job.done;
  const report = job.schedule.toJSON();

  check("`decide` fait une tâche par position",
        report.tasks === positions.length, `${report.tasks} tâches`);
  check("le tableau rendu est parallèle au tableau reçu",
        outcomes.every((o, i) => o.positionId === String(i)));
  check("aucun worker ne reste sans rien faire",
        report.taskCounts.every((n) => n > 0), report.taskCounts.join("/"));
  pool.destroy();
}

/* ── 4. L'annulation rend la main, et le relevé reste cohérent ──────────── */
{
  costOf = () => 30;
  const pool = await makePool(2);
  const positions = Array.from({ length: 20 }, (_, i) => ({
    positionId: String(i), turn: 0, d1: 3, d2: 1,
  }));
  const job = pool.decide(positions, { kind: "bestPlay" });
  await new Promise((resolve) => setTimeout(resolve, 5));
  job.cancel();
  const outcomes = await job.done;
  check("une annulation résout `done` plutôt que de suspendre", outcomes === null);
  check("le pool reste utilisable après une annulation",
        (await pool.decide(positions.slice(0, 4), { kind: "bestPlay" }).done)?.length === 4);
  pool.destroy();
}

/* ── 5. L'arithmétique du relevé ────────────────────────────────────────── */
{
  costOf = () => 5;
  const pool = await makePool(2);
  const count = 40;
  const job = pool.analyze(makeFeatures(count), count, NUM_FEATURES, { chunk: 8 });
  await job.done;
  const report = job.schedule.toJSON();

  check("l'oisiveté est une fraction, pas un temps",
        report.idlePool >= -0.001 && report.idlePool <= 1.001, String(report.idlePool));
  check("l'occupation vue du pool dépasse celle vue du worker",
        report.busyMs.reduce((a, b) => a + b, 0)
          >= report.computeMs.reduce((a, b) => a + b, 0) - 1e-6,
        "le protocole ne peut pas coûter un temps négatif");
  check("le temps mural n'est pas nul", report.wallMs > 0, `${report.wallMs} ms`);
  pool.destroy();
}

/* ── 6. Le nombre de workers conseillé n'est pas `hardwareConcurrency` ──── */
{
  const suggested = EvaluatorPool.suggestedSize({ hardwareConcurrency: 16 });
  check("16 fils annoncés ne donnent pas 16 workers",
        suggested < 16, `conseillé : ${suggested}`);
  check("un seul cœur annoncé donne un seul worker",
        EvaluatorPool.suggestedSize({ hardwareConcurrency: 1 }) === 1);
  check("un `hardwareConcurrency` absent ne fait pas planter",
        EvaluatorPool.suggestedSize({ hardwareConcurrency: undefined }) >= 1);
  check("le budget mémoire peut brider le conseil",
        EvaluatorPool.suggestedSize({ hardwareConcurrency: 16, memoryBudgetMB: 4 })
          < EvaluatorPool.suggestedSize({ hardwareConcurrency: 16 }));
}

console.log(failures === 0
  ? "\n✅ invariants de l'ordonnanceur tenus"
  : `\n❌ ${failures} invariant(s) d'ordonnancement rompu(s)`);
process.exit(failures === 0 ? 0 : 1);
