/*
 * worker.mjs -- one evaluator, off the main thread.
 *
 * Each worker owns its own module instance and its own copy of the weights.
 * That is not a design preference, it is what the platform allows: sharing the
 * 2 MiB of weights across workers needs a `SharedArrayBuffer`, which needs
 * COOP/COEP response headers, which a static host such as GitHub Pages does not
 * grant. Four workers therefore cost about 8 MiB of weights rather than 2 --
 * measured in the T23 report rather than hand-waved.
 *
 * The protocol is deliberately tiny: `init`, `evaluate`, `stop`. A worker that
 * did more would be a second place where the perspective rule could go wrong.
 *
 * SPDX-License-Identifier: MIT
 */

import { Evaluator } from "./gammonnet.mjs";

let evaluator = null;

/* Set by `stop`. Checked between chunks so a long job can be abandoned without
 * waiting for it to finish -- cancellation that only takes effect at the end is
 * not cancellation. */
let cancelled = false;

self.onmessage = async (event) => {
  const { type, id } = event.data;

  try {
    if (type === "init") {
      const { factoryUrl, modelBytes } = event.data;
      const { default: factory } = await import(factoryUrl);
      evaluator = await Evaluator.create(factory, modelBytes);
      self.postMessage({ type: "ready", id, simd: evaluator.hasSimd });
      return;
    }

    if (type === "evaluate") {
      if (evaluator === null) throw new Error("worker non initialisé");
      cancelled = false;

      const { features, count, chunk } = event.data;
      const outputs = new Float32Array(count * evaluator.numOutputs);
      const size = chunk || count;

      let done = 0;
      while (done < count && !cancelled) {
        const batch = Math.min(size, count - done);
        const slice = features.subarray(
          done * evaluator.numFeatures,
          (done + batch) * evaluator.numFeatures,
        );
        outputs.set(evaluator.evaluateBatch(slice, batch), done * evaluator.numOutputs);
        done += batch;
        /* Yield between chunks so `stop` can be delivered. A worker that never
         * returns to its event loop cannot be interrupted. */
        if (done < count) await new Promise((resolve) => setTimeout(resolve, 0));
      }

      if (cancelled) {
        self.postMessage({ type: "cancelled", id, done });
      } else {
        self.postMessage({ type: "result", id, outputs, count }, [outputs.buffer]);
      }
      return;
    }

    if (type === "stop") {
      cancelled = true;
      return;
    }

    throw new Error(`message inconnu : ${type}`);
  } catch (error) {
    self.postMessage({ type: "error", id, message: String(error?.stack || error) });
  }
};
