/*
 * pool.mjs -- keep the analysis off the thread that draws.
 *
 * ON THE NAME. `PLAN.md` sketches this as `analyzeMatch(match, ply, onProgress)`.
 * It is called `analyze(positions, ...)` here, and the difference is not
 * cosmetic: a *match* is a sequence of games with a score and a cube, and
 * `CLAUDE.md` puts match import squarely "ailleurs". This repository is handed
 * positions and hands back evaluations. Accepting a `match` would have let the
 * boundary erode through a parameter name.
 *
 * WHAT IS MEASURED, AND WHY IT MATTERS BEYOND THIS FILE. Every match duration
 * quoted in T21 and T30 divides by four workers and assumes the scaling is
 * linear. Nothing had verified that. This pool exists to make the assumption
 * testable, and the T23 report either confirms those numbers or invalidates
 * them.
 *
 * SPDX-License-Identifier: MIT
 */

const DEFAULT_CHUNK = 256;

export class EvaluatorPool {
  #workers = [];
  #idle = [];
  #queue = [];
  #nextId = 1;
  #pending = new Map();

  constructor(workers) {
    this.#workers = workers;
    this.#idle = [...workers];
  }

  get size() {
    return this.#workers.length;
  }

  /**
   * Spin up `count` workers, each with its own module and its own weights.
   *
   * @param {number} count
   * @param {string} workerUrl   URL of `worker.mjs`
   * @param {string} factoryUrl  URL of the generated `.mjs`
   * @param {Uint8Array} modelBytes
   */
  static async create(count, workerUrl, factoryUrl, modelBytes) {
    const workers = await Promise.all(
      Array.from({ length: count }, () => new Promise((resolve, reject) => {
        const worker = new Worker(workerUrl, { type: "module" });
        worker.onmessage = (event) => {
          if (event.data.type === "ready") resolve(worker);
          else if (event.data.type === "error") reject(new Error(event.data.message));
        };
        worker.onerror = (event) => reject(new Error(event.message || "worker en erreur"));
        // The weights are copied, not transferred: every worker needs its own,
        // and transferring would leave the next one with a detached buffer.
        worker.postMessage({ type: "init", id: 0, factoryUrl, modelBytes });
      })),
    );
    return new EvaluatorPool(workers);
  }

  #run(worker, job) {
    const id = this.#nextId++;
    this.#pending.set(id, { worker, job });

    worker.onmessage = (event) => {
      const { type } = event.data;
      if (type === "result") job.resolve(event.data.outputs);
      else if (type === "cancelled") job.resolve(null);
      else if (type === "error") job.reject(new Error(event.data.message));
      else return;

      this.#pending.delete(id);
      this.#idle.push(worker);
      this.#pump();
    };

    worker.postMessage({
      type: "evaluate", id,
      features: job.features, count: job.count, chunk: job.chunk,
    });
  }

  #pump() {
    while (this.#idle.length > 0 && this.#queue.length > 0) {
      this.#run(this.#idle.pop(), this.#queue.shift());
    }
  }

  /**
   * Evaluate `count` encoded positions, spread across the pool.
   *
   * Returns `{ outputs, cancel, done }`. `cancel()` tells every busy worker to
   * stop between chunks; `done` resolves with the outputs, or with `null` if the
   * work was abandoned.
   */
  analyze(features, count, numFeatures, { chunk = DEFAULT_CHUNK, onProgress } = {}) {
    const slots = this.size;
    const per = Math.ceil(count / slots);
    const jobs = [];

    for (let start = 0; start < count; start += per) {
      const length = Math.min(per, count - start);
      const slice = features.subarray(start * numFeatures, (start + length) * numFeatures);
      jobs.push({ features: slice, count: length, chunk, start });
    }

    let completed = 0;
    const promises = jobs.map((job) => new Promise((resolve, reject) => {
      job.resolve = (outputs) => {
        completed += job.count;
        if (onProgress) onProgress(completed, count);
        resolve({ start: job.start, outputs });
      };
      job.reject = reject;
      this.#queue.push(job);
    }));
    this.#pump();

    const done = Promise.all(promises).then((parts) => {
      if (parts.some((p) => p.outputs === null)) return null;
      const numOutputs = parts[0].outputs.length / jobs[0].count;
      const outputs = new Float32Array(count * numOutputs);
      for (const { start, outputs: piece } of parts) {
        outputs.set(piece, start * numOutputs);
      }
      return outputs;
    });

    const cancel = () => {
      for (const worker of this.#workers) worker.postMessage({ type: "stop" });
      this.#queue.length = 0;
    };

    return { done, cancel };
  }

  destroy() {
    for (const worker of this.#workers) worker.terminate();
    this.#workers = [];
    this.#idle = [];
    this.#queue = [];
  }
}
