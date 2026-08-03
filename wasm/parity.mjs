/*
 * parity.mjs -- T20's criterion: WebAssembly and native agree to max|Δ| < 1e-6.
 *
 * The reference is produced by the native build (`tools/dump_reference.py`) and
 * read here verbatim. Recomputing both sides from a seed would establish
 * nothing if the two generators had drifted apart.
 *
 * Both builds are checked -- scalar and SIMD. Checking only one would leave the
 * other free to be wrong in exactly the way T21 would then measure.
 *
 * SPDX-License-Identifier: MIT
 */

import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { Evaluator } from "./gammonnet.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");

const REFERENCE = join(ROOT, "build", "reference.bin");
const MODEL = join(ROOT, "models", "cubeless_prob5_512_512_256_128.bin");

const TOLERANCE = 1e-6;
const MAGIC = 0x46524e47; // 'GNRF' little-endian

async function loadReference() {
  const raw = await readFile(REFERENCE);
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);

  if (view.getUint32(0, true) !== MAGIC) {
    throw new Error(`${REFERENCE} : magic inattendu`);
  }
  const count = view.getInt32(4, true);
  const numFeatures = view.getInt32(8, true);
  const numOutputs = view.getInt32(12, true);

  const featuresBytes = count * numFeatures * 4;
  const featuresOffset = raw.byteOffset + 16;
  const outputsOffset = featuresOffset + featuresBytes;

  return {
    count,
    numFeatures,
    numOutputs,
    features: new Float32Array(raw.buffer, featuresOffset, count * numFeatures),
    outputs: new Float32Array(raw.buffer, outputsOffset, count * numOutputs),
  };
}

async function check(label, factoryPath, reference, modelBytes) {
  const { default: factory } = await import(factoryPath);
  const evaluator = await Evaluator.create(factory, modelBytes);

  if (evaluator.numFeatures !== reference.numFeatures) {
    throw new Error(
      `${label} : ${evaluator.numFeatures} caractéristiques, ` +
        `${reference.numFeatures} dans le repère`,
    );
  }

  const got = evaluator.evaluateBatch(reference.features, reference.count);

  let worst = 0;
  let worstAt = -1;
  for (let i = 0; i < got.length; i++) {
    const delta = Math.abs(got[i] - reference.outputs[i]);
    if (delta > worst) {
      worst = delta;
      worstAt = i;
    }
  }

  const simd = evaluator.hasSimd ? "SIMD" : "scalaire";
  const ok = worst < TOLERANCE;
  console.log(
    `${ok ? "✅" : "❌"} ${label.padEnd(10)} ${simd.padEnd(9)} ` +
      `max|Δ| = ${worst.toExponential(3)}` +
      (worstAt >= 0 && !ok
        ? `  (position ${Math.floor(worstAt / reference.numOutputs)}, ` +
          `sortie ${worstAt % reference.numOutputs})`
        : ""),
  );

  evaluator.destroy();
  return { ok, worst, simd: evaluator.hasSimd };
}

const reference = await loadReference();
const modelBytes = new Uint8Array(await readFile(MODEL));

console.log(
  `repère : ${reference.count} positions × ${reference.numOutputs} sorties, ` +
    `tolérance ${TOLERANCE.toExponential(0)}`,
);

const results = [
  await check("scalaire", "../build/wasm/gammonnet.mjs", reference, modelBytes),
  await check("SIMD", "../build/wasm/gammonnet-simd.mjs", reference, modelBytes),
];

// Les deux builds doivent aussi être d'accord entre eux : une divergence
// signalerait que la vectorisation a changé le résultat, pas seulement sa
// vitesse -- et T21 comparerait alors deux moteurs, pas deux compilations.
if (results[0].simd === results[1].simd) {
  console.log("⚠️  les deux builds rapportent le même drapeau SIMD");
}

if (!results.every((r) => r.ok)) {
  console.error(`\n❌ parité échouée : la tolérance est ${TOLERANCE.toExponential(0)}`);
  process.exit(1);
}
console.log("\n✅ parité WebAssembly ↔ natif établie sur les deux builds");
