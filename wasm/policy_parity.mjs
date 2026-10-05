/*
 * La politique sans état, cible WebAssembly contre référence native.
 *
 * Rejoue `data/policy_reference.bin` (docs/specs/politique-spec.md §8) à
 * travers `Evaluator.policy` et exige, décision par décision : le même refus,
 * la même action, la même valeur d'abandon, le même coup et le même plateau
 * résultant — exactement. Les équités sont comparées au bit près et l'écart
 * maximal est rapporté : l'artefact se veut bit à bit avec le natif par
 * défaut (T91), et c'est ici que la politique le montre ou non.
 *
 *   node wasm/policy_parity.mjs [--all]    (sans --all : niveau instant seul)
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { Evaluator } from "./gammonnet.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const MODULE = join(ROOT, "build", "wasm", process.env.GN_WASM_MODULE ?? "gammonnet-simd.mjs");
const LEVELS = ["instant", "normal", "thorough"];
const PENDING = ["move", "cube", "take", "resign"];
const ACTIONS = ["move", "roll", "double", "resign", "take", "pass", "accept", "reject"];
const all = process.argv.includes("--all");

const data = readFileSync(join(ROOT, "data", "policy_reference.bin"));
const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
const magic = data.subarray(0, 4).toString("latin1");
const count = view.getUint32(8, true);
if (magic !== "GNPL" || view.getUint32(4, true) !== 1 || view.getUint32(12, true) !== 160) {
  throw new Error("corpus illisible");
}

const factory = (await import(MODULE)).default;
const evaluator = await Evaluator.create(
  factory, new Uint8Array(readFileSync(join(ROOT, "models", "cubeless_prob5_512_512_256_128.bin"))));
evaluator.loadPrune(new Uint8Array(readFileSync(join(ROOT, "models", "prune_32.bin"))), 12);

function boardAt(off) {
  const points = [];
  for (let i = 0; i < 24; i++) points.push(view.getInt8(off + i));
  return { points, bar: [data[off + 24], data[off + 25]], off: [data[off + 26], data[off + 27]],
           turn: data[off + 28] };
}

let failures = 0, compared = 0, maxDelta = 0, notBitExact = 0;
const perLevel = { instant: 0, normal: 0, thorough: 0 };
for (let r = 0; r < count; r++) {
  const o = 16 + r * 160;
  const i32 = (k) => view.getInt32(o + k, true);
  const level = LEVELS[i32(32)];
  if (level !== "instant" && !all) continue;
  const options = {
    pending: PENDING[i32(36)], level, d1: i32(40), d2: i32(44), cube: i32(48),
    cubeOwner: i32(52), jacoby: i32(56) === 1, useMatch: i32(60) === 1,
    awayOnRoll: i32(64), awayOpponent: i32(68), crawford: i32(72) === 1,
    resignValue: i32(76),
  };
  const refused = i32(80) === -1;
  let got = null;
  try {
    got = evaluator.policy(boardAt(o), options);
  } catch {
    got = null;
  }
  compared++;
  perLevel[level]++;
  const fail = (why) => { failures++; console.log(`❌ #${r} ${level} ${options.pending} : ${why}`); };
  if (refused || got === null) {
    if (refused !== (got === null)) fail(`refus ${refused} contre ${got === null}`);
    continue;
  }
  if (got.action !== ACTIONS[i32(84)]) { fail(`${got.action} contre ${ACTIONS[i32(84)]}`); continue; }
  if (got.resignValue !== i32(88) || (got.searched ? 1 : 0) !== i32(92)) fail("valeur ou searched");
  if (got.action === "move") {
    const n = i32(96);
    const moves = [];
    for (let k = 0; k < n; k++) moves.push([view.getInt8(o + 100 + 2 * k), view.getInt8(o + 101 + 2 * k)]);
    if (JSON.stringify(moves) !== JSON.stringify(got.play.moves)) fail("coup");
    if (JSON.stringify(boardAt(o + 108)) !== JSON.stringify(got.play.board)) fail("plateau résultant");
  }
  for (const [k, value] of [[140, got.equityA], [148, got.equityB]]) {
    const want = view.getFloat64(o + k, true);
    const d = Math.abs(value - want);
    if (!Object.is(value, want)) notBitExact++;
    maxDelta = Math.max(maxDelta, d);
  }
}
console.log(`${compared} décisions (${JSON.stringify(perLevel)}), ${failures} écart(s) d'action ; ` +
            `équités : max|Δ| = ${maxDelta.toExponential(3)}, ${notBitExact} non bit à bit`);
process.exit(failures === 0 && maxDelta < 1e-6 ? 0 : 1);
