/*
 * parity_int8.mjs -- T73's criterion: the deterministic int8 GEMM agrees
 * with native EXACTLY, not within a tolerance. Integer addition is
 * associative; if these two kernels ever disagree by even one unit, the
 * central claim of `gn_gemm_int8.h` -- that the bit-for-bit guarantee is
 * unconditional here, unlike float32's 4.77e-7 -- is false, and this must
 * fail loudly rather than round the difference away.
 *
 * The reference is produced by the native build
 * (`tools/dump_reference_int8.c`) and read here verbatim -- the same
 * discipline `parity.mjs` already applies to the float32 network.
 *
 * SPDX-License-Identifier: MIT
 */

import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const REFERENCE = join(ROOT, "build", "reference_int8.bin");
const MAGIC = 0x38494e47; // 'GNI8' little-endian

async function loadReference() {
  const raw = await readFile(REFERENCE);
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  if (view.getUint32(0, true) !== MAGIC) {
    throw new Error(`${REFERENCE} : magic inattendu`);
  }
  const numLayers = view.getInt32(4, true);
  const batch = view.getInt32(8, true);
  const shift = view.getInt32(12, true);

  let offset = 16;
  const layers = [];
  for (let i = 0; i < numLayers; i++) {
    const rows = view.getInt32(offset, true);
    const cols = view.getInt32(offset + 4, true);
    offset += 8;

    const weights = new Int8Array(raw.buffer, raw.byteOffset + offset, rows * cols);
    offset += rows * cols;
    const bias = new Int32Array(
      raw.buffer.slice(raw.byteOffset + offset, raw.byteOffset + offset + rows * 4),
    );
    offset += rows * 4;
    const input = new Uint8Array(raw.buffer, raw.byteOffset + offset, cols * batch);
    offset += cols * batch;
    const reluOut = new Uint8Array(raw.buffer, raw.byteOffset + offset, rows * batch);
    offset += rows * batch;
    const rawOut = new Int32Array(
      raw.buffer.slice(raw.byteOffset + offset, raw.byteOffset + offset + rows * batch * 4),
    );
    offset += rows * batch * 4;

    layers.push({ rows, cols, weights, bias, input, reluOut, rawOut });
  }
  return { numLayers, batch, shift, layers };
}

function countMismatches(got, expected) {
  let mismatches = 0;
  let worst = 0;
  for (let i = 0; i < expected.length; i++) {
    const delta = Math.abs(got[i] - expected[i]);
    if (delta > 0) mismatches++;
    if (delta > worst) worst = delta;
  }
  return { mismatches, worst };
}

async function check(label, factoryPath, reference) {
  const { default: factory } = await import(factoryPath);
  const module = await factory();

  let reluMismatches = 0;
  let rawMismatches = 0;
  let worstRelu = 0;
  let worstRaw = 0;

  for (const layer of reference.layers) {
    const { rows, cols, weights, bias, input } = layer;

    const wPtr = module._malloc(rows * cols);
    const bPtr = module._malloc(rows * 4);
    const iPtr = module._malloc(cols * reference.batch);
    const reluPtr = module._malloc(rows * reference.batch);
    const rawPtr = module._malloc(rows * reference.batch * 4);

    try {
      module.HEAP8.set(weights, wPtr);
      module.HEAP32.set(bias, bPtr >> 2);
      module.HEAPU8.set(input, iPtr);

      const reluStatus = module._gnw_gemm_int8_relu(
        wPtr, rows, cols, bPtr, iPtr, reference.batch, reference.shift, reluPtr,
      );
      if (reluStatus !== 0) throw new Error(`gnw_gemm_int8_relu refusée (${reluStatus})`);
      const gotRelu = new Uint8Array(
        module.HEAPU8.buffer, reluPtr, rows * reference.batch,
      );
      const relu = countMismatches(gotRelu, layer.reluOut);
      reluMismatches += relu.mismatches;
      worstRelu = Math.max(worstRelu, relu.worst);

      const rawStatus = module._gnw_gemm_int8_raw(
        wPtr, rows, cols, bPtr, iPtr, reference.batch, rawPtr,
      );
      if (rawStatus !== 0) throw new Error(`gnw_gemm_int8_raw refusée (${rawStatus})`);
      const gotRaw = new Int32Array(
        module.HEAP32.buffer.slice(rawPtr, rawPtr + rows * reference.batch * 4),
      );
      const rawCmp = countMismatches(gotRaw, layer.rawOut);
      rawMismatches += rawCmp.mismatches;
      worstRaw = Math.max(worstRaw, rawCmp.worst);
    } finally {
      module._free(wPtr);
      module._free(bPtr);
      module._free(iPtr);
      module._free(reluPtr);
      module._free(rawPtr);
    }
  }

  const ok = reluMismatches === 0 && rawMismatches === 0;
  console.log(
    `${ok ? "✅" : "❌"} ${label.padEnd(10)} relu: ${reluMismatches} désaccord(s) ` +
      `(pire écart ${worstRelu})   raw: ${rawMismatches} désaccord(s) (pire écart ${worstRaw})`,
  );
  return ok;
}

const reference = await loadReference();
console.log(
  `repère : ${reference.numLayers} couches, lot ${reference.batch}, ` +
    `décalage ${reference.shift} — comparaison au bit près, pas à une tolérance`,
);

const results = await Promise.all([
  check("scalaire", "../build/wasm/gammonnet.mjs", reference),
  check("SIMD", "../build/wasm/gammonnet-simd.mjs", reference),
]);

if (!results.every(Boolean)) {
  console.error("\n❌ parité int8 échouée : un désaccord d'un seul bit invaliderait "
    + "la garantie inconditionnelle de gn_gemm_int8.h");
  process.exit(1);
}
console.log("\n✅ parité int8 WebAssembly ↔ natif établie au bit près, sur les deux builds");
