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
 * CE QUE T86 Y AJOUTE. Le pool ne distribuait que des LOTS DE
 * CARACTÉRISTIQUES, parce que `worker.mjs` ne relayait que cela. Un appelant
 * qui voulait une DÉCISION devait donc engendrer les coups et parcourir
 * l'arbre lui-même, en JavaScript, pour fabriquer les lots — c'est-à-dire
 * réécrire la recherche que le module embarque déjà. `decide()` distribue
 * maintenant des décisions, une tâche par position.
 *
 * SUR LE NOMBRE DE TÂCHES. `analyze()` découpe en EXACTEMENT `size` tâches
 * (une par worker) et son oisiveté est donc exactement le déséquilibre de ce
 * découpage. `decide()` ne reproduit pas ce choix : une position est une
 * tâche, donc il y a naturellement plus de tâches que de workers, et le
 * dernier worker ne retient pas les autres. Ce n'est pas l'ordonnancement de
 * T87 — qui doit MESURER l'oisiveté avant de la corriger, et sur `analyze()`
 * aussi — c'est simplement la granularité qu'une décision impose.
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
  static async create(count, workerUrl, factoryUrl, modelBytes, config = {}) {
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
        //
        // `config` porte l'élagage, la table de fin de partie et le cache. Ils
        // font partie de la CONFIGURATION mesurée d'une décision : les laisser
        // hors du pool obligeait à croire qu'un worker calcule comme le natif
        // alors qu'il tourne sans élagage et sans table, silencieusement.
        worker.postMessage({ type: "init", id: 0, factoryUrl, modelBytes, ...config });
      })),
    );
    return new EvaluatorPool(workers);
  }

  #run(worker, job) {
    const id = this.#nextId++;
    this.#pending.set(id, { worker, job });

    worker.onmessage = (event) => {
      const { type } = event.data;
      /* `progress` et `partial` n'achèvent pas le travail : le worker reste
       * occupé, on relaie et on attend la suite. Les traiter comme une fin
       * rendrait un worker au pool avant qu'il ait fini. */
      if (type === "progress" || type === "partial") {
        if (job.onMessage) job.onMessage(event.data);
        return;
      }
      if (type === "result") job.resolve(job.decision ? event.data.outcome : event.data.outputs);
      else if (type === "cancelled") job.resolve(null);
      else if (type === "error") job.reject(new Error(event.data.message));
      else return;

      this.#pending.delete(id);
      this.#idle.push(worker);
      this.#pump();
    };

    worker.postMessage(job.decision
      ? { ...job.request, id }
      : {
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

    const cancel = () => this.#cancelAll();

    return { done, cancel };
  }

  /*
   * Annuler : dire `stop` à chaque worker, ET RÉPONDRE à ce qui attendait
   * encore dans la file.
   *
   * Vider `#queue` sans résoudre ses travaux laissait leurs promesses en
   * suspens pour toujours : `done` ne se résolvait jamais, et l'appelant
   * attendait un résultat que plus personne n'allait produire. Une annulation
   * qui suspend n'est pas une annulation — c'est la même faute que
   * l'annulation muette côté worker, un cran plus haut.
   */
  #cancelAll() {
    for (const worker of this.#workers) worker.postMessage({ type: "stop" });
    while (this.#queue.length > 0) this.#queue.shift().resolve(null);
  }

  /**
   * DÉCIDER de N positions, réparties sur le pool.
   *
   * Une position, une tâche. Chaque tâche traverse la frontière une fois et
   * revient avec une décision complète — coup retenu, classement ou verdict de
   * videau — sans qu'une seule ligne de recherche ne soit écrite ici.
   *
   * @param {Array<{positionId: string, turn: number, d1?: number, d2?: number,
   *                options?: object}>} positions
   * @param {object} opts
   *   `kind`      "rankPlays" (défaut), "bestPlay" ou "cubeDecision"
   *   `options`   les options communes (`Evaluator.level("normal")`, un score…)
   *   `onProgress(done, total)`
   *
   * Rend `{ done, cancel }` comme `analyze`. `done` résout sur un tableau
   * parallèle à `positions`, ou sur `null` si le travail a été abandonné.
   *
   * SUR CE QUE `cancel()` PEUT ET NE PEUT PAS. Il périme la file de chaque
   * worker et les décisions en vol : rien de dépassé ne remonte, et les
   * workers restent chauds — leurs 1,06 Mo de poids ne sont pas rechargés.
   * La décision DÉJÀ engagée dans le WASM va jusqu'au bout ; un appel WASM
   * synchrone n'est pas interruptible depuis JavaScript (voir l'en-tête de
   * `worker.mjs`). C'est une limite de la plateforme, pas un raccourci : le
   * seul arrêt plus dur est `Worker.terminate()`, qui coûte le rechargement
   * des poids et détruit le pool.
   */
  decide(positions, { kind = "rankPlays", options = {}, onProgress } = {}) {
    const total = positions.length;
    let completed = 0;

    const promises = positions.map((position, index) => new Promise((resolve, reject) => {
      const job = {
        decision: true,
        request: {
          type: kind,
          positionId: position.positionId, turn: position.turn,
          d1: position.d1, d2: position.d2,
          options: { ...options, ...(position.options || {}) },
        },
        resolve: (outcome) => {
          completed++;
          if (onProgress) onProgress(completed, total);
          resolve({ index, outcome });
        },
        reject,
      };
      this.#queue.push(job);
    }));
    this.#pump();

    const done = Promise.all(promises).then((parts) => {
      if (parts.some((p) => p.outcome === null || p.outcome === undefined)) return null;
      const out = new Array(total);
      for (const { index, outcome } of parts) out[index] = outcome;
      return out;
    });

    const cancel = () => this.#cancelAll();

    return { done, cancel };
  }

  destroy() {
    for (const worker of this.#workers) worker.terminate();
    this.#workers = [];
    this.#idle = [];
    this.#queue = [];
  }
}
