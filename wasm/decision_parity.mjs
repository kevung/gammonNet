/*
 * La décision DÉCOUPÉE contre la décision EN UN BLOC (issue #36,
 * docs/specs/decision-decomposee-spec.md §6).
 *
 * Rejoue les positions de `data/policy_reference.bin`, à leur niveau
 * (instant, normal, thorough), en money et en match, et exige L'ÉGALITÉ AU
 * BIT PRÈS — `Object.is` sur chaque nombre, aucune tolérance — entre :
 *
 *   policy(...)               et  planDecision("policy", ...)
 *   bestPlay(...)             et  planDecision("move", ...)      (si dés)
 *   cubeDecision(...)         et  planDecision("cube", ...)
 *   evaluatePositionAtPly(...) et planDecision("position", ...)
 *
 * Les tâches sont exécutées sur une AUTRE instance que le planificateur,
 * dans un ordre MÉLANGÉ, et chaque plan, tâche et résultat passe par
 * `structuredClone` — ce qu'un `postMessage` fait subir. Le planificateur ne
 * calcule donc rien de ce qu'il recombine.
 *
 * Toute différence est un échec. Le relevé rend aussi la distribution du
 * nombre de tâches par décision et le total d'évaluations des deux chemins
 * (des COMPTES : rien ici n'est chronométré).
 *
 *   node wasm/decision_parity.mjs [--corpus t12] [--shard i/n] [--json out.json]
 *
 * Sans `--corpus`, les 1 411 décisions du corpus de la politique, à leur
 * niveau ; avec `--corpus t12`, les 2 050 positions figées de T12.
 *
 * SPDX-License-Identifier: MIT
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { Evaluator, MEASURED_EFFICIENCY } from "./gammonnet.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const MODULE = join(ROOT, "build", "wasm", process.env.GN_WASM_MODULE ?? "gammonnet-simd.mjs");
const LEVELS = ["instant", "normal", "thorough"];
const PENDING = ["move", "cube", "take", "resign"];

const arg = (name) => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : null;
};
const [shard, shards] = (arg("--shard") ?? "0/1").split("/").map(Number);

const data = readFileSync(join(ROOT, "data", "policy_reference.bin"));
const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
if (data.subarray(0, 4).toString("latin1") !== "GNPL" || view.getUint32(4, true) !== 1
    || view.getUint32(12, true) !== 160) {
  throw new Error("corpus illisible");
}
const count = view.getUint32(8, true);

const factory = (await import(MODULE)).default;
const model = new Uint8Array(readFileSync(join(ROOT, "models", "cubeless_prob5_512_512_256_256.bin")));
const prune = new Uint8Array(readFileSync(join(ROOT, "models", "prune_32.bin")));
/* Deux instances : le planificateur et l'exécutant. Mêmes réseaux — sinon
 * les tâches seraient refusées, et c'est vérifié plus bas. La table exacte
 * de fin de partie que le module lit (`gnubg_ts6x11.bd`, 1,2 Gio) n'entre
 * pas ici : le contrôle natif (`tests/test_plan.py`) la couvre. */
const planner = await Evaluator.create(factory, model);
const runner = await Evaluator.create(factory, model);
for (const e of [planner, runner]) e.loadPrune(prune, 12);
/* Et une paire SANS élagueur : `bestPlay` élague dès qu'un élagueur est
 * chargé, donc `thorough` — qui n'élague pas — se compare sur elle. */
const pruned = [planner, runner];
const bare = [await Evaluator.create(factory, model), await Evaluator.create(factory, model)];

function boardAt(off) {
  const points = [];
  for (let i = 0; i < 24; i++) points.push(view.getInt8(off + i));
  return { points, bar: [data[off + 24], data[off + 25]], off: [data[off + 26], data[off + 27]],
           turn: data[off + 28] };
}

/* Un mélange déterministe, graine par décision : rejouable. */
function shuffle(items, seed) {
  const out = [...items];
  let x = (seed * 2654435761) >>> 0 || 1;
  for (let i = out.length - 1; i > 0; i--) {
    x ^= x << 13; x >>>= 0; x ^= x >>> 17; x ^= x << 5; x >>>= 0;
    const j = x % (i + 1);
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/* L'égalité au bit : `Object.is` sur chaque feuille, même structure. */
function sameBits(a, b) {
  if (typeof a === "number" || typeof b === "number") return Object.is(a, b);
  if (a === null || b === null || typeof a !== "object" || typeof b !== "object") return a === b;
  const ka = Object.keys(a), kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  return ka.every((k) => kb.includes(k) && sameBits(a[k], b[k]));
}

const stats = { decisions: 0, failures: 0, byKind: {}, tasks: {}, evaluations: {} };
function note(kind, waves, blocEvals, planEvals) {
  stats.byKind[kind] = (stats.byKind[kind] ?? 0) + 1;
  const total = waves.reduce((s, w) => s + w, 0);
  (stats.tasks[kind] ??= []).push(total);
  if (blocEvals !== null) {
    const e = (stats.evaluations[kind] ??= { bloc: 0, plan: 0 });
    e.bloc += blocEvals;
    e.plan += planEvals;
  }
}

function decomposed(kind, id, turn, d1, d2, options, seed, [planner, runner] = pruned) {
  let step = structuredClone(planner.planDecision(kind, id, turn, d1, d2, options));
  const waves = [];
  while (!step.done) {
    waves.push(step.stage.length);
    const tasks = shuffle(structuredClone(step.stage), seed + waves.length);
    const results = tasks.map((t) => structuredClone(runner.runTask(t)));
    step = structuredClone(planner.advance(step.plan, shuffle(results, seed * 7 + 1)));
  }
  return { decision: planner.combineDecision(step.plan), waves };
}

function check(r, kind, bloc, split) {
  stats.decisions++;
  if (!sameBits(bloc, split)) {
    stats.failures++;
    console.log(`❌ #${r} ${kind}\n   bloc   ${JSON.stringify(bloc)}\n   tâches ${JSON.stringify(split)}`);
  }
}

const tryOr = (f) => { try { return f(); } catch { return null; } };

/* Le corpus figé de T12 (2 050 positions, sept catégories) : un jet tiré
 * d'une graine par position, coups aux niveaux qui cherchent, videau et
 * valeur avant le jet au niveau `normal` — en money, et une position sur
 * trois en match. C'est là que les coups cherchés sont nombreux. */
function t12() {
  const lines = readFileSync(join(ROOT, "tests", "data", "corpus_t12.jsonl"), "utf8")
    .split("\n").filter(Boolean).map((l) => JSON.parse(l));
  for (let r = shard; r < lines.length; r += shards) {
    const { position_id: id, turn } = lines[r];
    let x = (r * 2654435761 + 12345) >>> 0;
    const die = () => { x = (x * 1103515245 + 12345) >>> 0; return 1 + ((x >>> 16) % 6); };
    const d1 = die(), d2 = die();
    const match = r % 3 === 2 ? { awayOnRoll: 3, awayOpponent: 5, cube: 1, crawford: false } : null;
    for (const name of ["normal", "thorough"]) {
      const shape = Evaluator.level(name);
      const search = { ply: shape.ply, filterTop: shape.filterTop, filterInner: shape.filterInner,
                       filterExtra: shape.filterExtra, filterThreshold: shape.filterThreshold };
      const pair = shape.pruneK > 0 ? pruned : bare;
      const b = tryOr(() => pair[0].bestPlay(id, turn, d1, d2, { ...search, match }));
      const s = tryOr(() => decomposed("move", id, turn, d1, d2, { ...search, match }, r, pair));
      const strip = (v) => (v ? { ...v, evaluations: undefined } : v);
      check(r, `t12/move/${name}`, strip(b), strip(s?.decision ?? null));
      if (s && b) note(`t12/move/${name}${match ? "/match" : ""}`, s.waves, b.evaluations,
                       s.decision.evaluations);
      if (name !== "normal") continue;
      const cubeOptions = { ...search, owner: 0, efficiency: MEASURED_EFFICIENCY[0],
                            useMatch: match !== null, awayOnRoll: match ? 3 : 0,
                            awayOpponent: match ? 5 : 0, cube: 1, jacoby: true };
      const cb = tryOr(() => planner.cubeDecision(id, turn, cubeOptions));
      const cs = tryOr(() => decomposed("cube", id, turn, 0, 0, cubeOptions, r + 1));
      check(r, "t12/cube/normal", cb, cs?.decision ?? null);
      if (cs) note("t12/cube/normal", cs.waves, null, null);
      const pb = tryOr(() => planner.evaluatePositionAtPly(id, turn, { ...search, match }));
      const ps = tryOr(() => decomposed("position", id, turn, 0, 0, { ...search, match }, r + 2));
      check(r, "t12/position/normal", pb, ps?.decision ?? null);
    }
  }
}

if (arg("--corpus") === "t12") t12();
else for (let r = shard; r < count; r += shards) {
  const o = 16 + r * 160;
  const i32 = (k) => view.getInt32(o + k, true);
  const level = LEVELS[i32(32)];
  const options = {
    pending: PENDING[i32(36)], level, d1: i32(40), d2: i32(44), cube: i32(48),
    cubeOwner: i32(52), jacoby: i32(56) === 1, useMatch: i32(60) === 1,
    awayOnRoll: i32(64), awayOpponent: i32(68), crawford: i32(72) === 1,
    resignValue: i32(76),
  };
  const board = boardAt(o);

  /* 1. La politique, telle quelle. */
  const bloc = tryOr(() => planner.policy(board, options));
  const split = tryOr(() => decomposed("policy", board, board.turn, options.d1, options.d2,
                                       options, r));
  check(r, `policy/${level}/${options.pending}`, bloc, split?.decision ?? null);
  if (split) note(`policy/${level}`, split.waves, null, null);

  let id;
  try { id = planner.positionId(board); } catch { continue; }
  const shape = Evaluator.level(level);
  const match = options.useMatch
    ? { awayOnRoll: options.awayOnRoll, awayOpponent: options.awayOpponent,
        cube: options.cube, crawford: options.crawford }
    : null;
  const search = { ply: shape.ply, filterTop: shape.filterTop, filterInner: shape.filterInner,
                   filterExtra: shape.filterExtra, filterThreshold: shape.filterThreshold };

  /* 2. Le coup, s'il y a des dés — élagué si et seulement si le niveau
   * élague, comme `policy` le fait. */
  const pair = shape.pruneK > 0 ? pruned : bare;
  if (options.d1 >= 1) {
    const b = tryOr(() => pair[0].bestPlay(id, board.turn, options.d1, options.d2,
                                           { ...search, match }));
    const s = tryOr(() => decomposed("move", id, board.turn, options.d1, options.d2,
                                     { ...search, match }, r + 1, pair));
    const strip = (x) => (x ? { ...x, evaluations: undefined } : x);
    check(r, `move/${level}`, strip(b), strip(s?.decision ?? null));
    if (s && b) note(`move/${level}`, s.waves, b.evaluations, s.decision.evaluations);
  }

  /* 3. Le videau, au propriétaire de la décision. */
  const owner = options.cubeOwner;
  const cubeOptions = { ...search, owner, efficiency: MEASURED_EFFICIENCY[owner],
                        useMatch: options.useMatch, awayOnRoll: options.awayOnRoll,
                        awayOpponent: options.awayOpponent, cube: options.cube,
                        crawford: options.crawford, jacoby: options.jacoby };
  const cb = tryOr(() => pair[0].cubeDecision(id, board.turn, cubeOptions));
  const cs = tryOr(() => decomposed("cube", id, board.turn, 0, 0, cubeOptions, r + 2, pair));
  check(r, `cube/${level}`, cb, cs?.decision ?? null);
  if (cs) note(`cube/${level}`, cs.waves, null, null);

  /* 4. La position avant le jet — cubeless, puis cubeful aux feuilles. */
  for (const cubeful of [false, true]) {
    const po = { ...search, match,
                 ...(cubeful ? { cubeOwner: owner, efficiency: MEASURED_EFFICIENCY[owner] } : {}) };
    const pb = tryOr(() => pair[0].evaluatePositionAtPly(id, board.turn, po));
    const ps = tryOr(() => decomposed("position", id, board.turn, 0, 0, po, r + 3, pair));
    check(r, `position/${level}${cubeful ? "/cubeful" : ""}`, pb, ps?.decision ?? null);
    if (ps && !cubeful) note(`position/${level}`, ps.waves, null, null);
  }
}

/* 5. Les refus : une tâche portée sur une instance qui n'a pas le même
 * élagueur, une vague rendue avec un résultat en double, ou avec ceux d'un
 * autre plan. */
const refusals = [];
{
  const stranger = await Evaluator.create(factory, model);   // sans élagueur
  const step = planner.planDecision("move", "4HPwATDgc/ABMA", 0, 3, 1, Evaluator.level("normal"));
  let refused = false;
  try { stranger.runTask(step.stage[0]); } catch { refused = true; }
  refusals.push({ what: "tâche sur une instance sans le même élagueur", refused });
  const results = step.stage.map((t) => runner.runTask(t));
  results[1] = results[0];
  refused = false;
  try { planner.advance(step.plan, results); } catch { refused = true; }
  refusals.push({ what: "vague avec un résultat en double", refused });
  const other = planner.planDecision("move", "4HPwATDgc/ABMA", 0, 6, 4, Evaluator.level("normal"));
  refused = false;
  try { planner.advance(step.plan, other.stage.map((t) => runner.runTask(t))); } catch { refused = true; }
  refusals.push({ what: "vague avec les résultats d'un autre plan", refused });
}
for (const f of refusals) {
  if (!f.refused) { stats.failures++; console.log(`❌ non refusé : ${f.what}`); }
}

const summary = {};
for (const [kind, list] of Object.entries(stats.tasks)) {
  const s = [...list].sort((a, b) => a - b);
  summary[kind] = { n: s.length, min: s[0], median: s[Math.floor(s.length / 2)],
                    p90: s[Math.floor(0.9 * (s.length - 1))], max: s[s.length - 1],
                    mean: Number((s.reduce((a, b) => a + b, 0) / s.length).toFixed(1)) };
}
console.log(`${stats.decisions} comparaisons, ${stats.failures} écart(s) ; refus ${refusals.filter((f) => f.refused).length}/${refusals.length}`);
console.log("tâches par décision :", JSON.stringify(summary));
console.log("évaluations bloc / tâches :", JSON.stringify(stats.evaluations));
const out = arg("--json");
if (out) {
  writeFileSync(out, JSON.stringify({ shard, shards, ...stats, summary, refusals }));
}
process.exit(stats.failures === 0 ? 0 : 1);
