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
 * ── CE QUE T87 Y AJOUTE : L'OISIVETÉ SE MESURE AVANT DE SE CORRIGER ────
 *
 * `analyze()` découpait en EXACTEMENT `size` tâches (une par worker) et son
 * oisiveté était donc exactement le déséquilibre de ce découpage — plus
 * aucun rattrapage possible, puisqu'un worker en avance n'a rien à prendre.
 * Corriger cela sans l'avoir chiffré aurait été une conviction, pas une
 * mesure : `ScheduleReport` est donc écrit et publié AVANT le correctif.
 *
 * Il relève DEUX occupations, et l'écart entre les deux est lui-même une
 * mesure :
 *
 *   - `busyMs`    — vue du POOL : de l'envoi du message à la réponse. Elle
 *                   compte la sérialisation et les deux traversées de
 *                   `postMessage`.
 *   - `computeMs` — vue du WORKER : le temps réellement passé dans le WASM,
 *                   que le worker rapporte lui-même.
 *
 * `busy − compute` est le coût du protocole. Le confondre avec du travail
 * ferait passer une latence de messagerie pour de l'occupation, et
 * SOUS-ESTIMERAIT l'oisiveté — exactement l'erreur qu'un instrument doit
 * refuser de commettre.
 *
 * SPDX-License-Identifier: MIT
 */

const DEFAULT_CHUNK = 256;

/*
 * LE RELEVÉ D'ORDONNANCEMENT d'un travail.
 *
 * Une fraction d'oisiveté n'a de sens qu'accompagnée de son dénominateur :
 * `workers × wall` est le temps-worker OFFERT, `busy` (ou `compute`) est le
 * temps-worker CONSOMMÉ. Ce que l'oisiveté chiffre est donc ce que le pool a
 * laissé sur la table, et rien d'autre — ni la qualité du parallélisme
 * matériel, ni le rendement d'un worker.
 */
export class ScheduleReport {
  constructor(workers) {
    this.workers = workers;
    this.tasks = 0;
    this.startedAt = Number.POSITIVE_INFINITY;
    this.finishedAt = 0;
    this.busyMs = new Float64Array(workers);
    this.computeMs = new Float64Array(workers);
    this.taskCounts = new Int32Array(workers);
    /* CHAQUE TÂCHE, et pas seulement leur somme. Sans le détail, on peut
     * dire QUE le pool a été oisif mais pas POURQUOI — et la seule question
     * qui décide de la suite est celle-là : est-ce le découpage, la queue de
     * fin, ou la dispersion des coûts ? Le relevé porte donc l'étiquette de
     * la tâche, son slot et ses deux dates. */
    this.entries = [];
  }

  note(slot, sentAt, doneAt, computeMs, label) {
    this.tasks += 1;
    this.taskCounts[slot] += 1;
    this.busyMs[slot] += doneAt - sentAt;
    this.computeMs[slot] += Number.isFinite(computeMs) ? computeMs : 0;
    this.entries.push({
      slot, label,
      sentAt, doneAt,
      busyMs: doneAt - sentAt,
      computeMs: Number.isFinite(computeMs) ? computeMs : null,
    });
    if (sentAt < this.startedAt) this.startedAt = sentAt;
    if (doneAt > this.finishedAt) this.finishedAt = doneAt;
  }

  /** Les coûts de tâche, du plus petit au plus grand. */
  get taskMs() {
    return this.entries.map((e) => e.busyMs).sort((a, b) => a - b);
  }

  /** Le temps mural du travail, du premier envoi à la dernière réponse. */
  get wallMs() {
    return this.finishedAt > this.startedAt ? this.finishedAt - this.startedAt : 0;
  }

  get totalBusyMs() {
    return this.busyMs.reduce((a, b) => a + b, 0);
  }

  get totalComputeMs() {
    return this.computeMs.reduce((a, b) => a + b, 0);
  }

  /** La fraction de temps-worker offert que personne n'a utilisée. */
  get idle() {
    const offered = this.workers * this.wallMs;
    if (offered <= 0) return { pool: 0, worker: 0 };
    return {
      pool: 1 - this.totalBusyMs / offered,
      worker: 1 - this.totalComputeMs / offered,
    };
  }

  toJSON({ entries = false } = {}) {
    const ms = this.taskMs;
    const origin = this.startedAt;
    return {
      ...(entries
        ? {
          entries: this.entries.map((e) => ({
            slot: e.slot, label: e.label,
            startMs: Number((e.sentAt - origin).toFixed(1)),
            endMs: Number((e.doneAt - origin).toFixed(1)),
            busyMs: Number(e.busyMs.toFixed(1)),
            computeMs: e.computeMs === null ? null : Number(e.computeMs.toFixed(1)),
          })),
        }
        : {}),
      workers: this.workers,
      tasks: this.tasks,
      wallMs: Number(this.wallMs.toFixed(1)),
      busyMs: Array.from(this.busyMs, (v) => Number(v.toFixed(1))),
      computeMs: Array.from(this.computeMs, (v) => Number(v.toFixed(1))),
      taskCounts: Array.from(this.taskCounts),
      /* Deux oisivetés, jamais une seule : voir l'en-tête du fichier. */
      idlePool: Number(this.idle.pool.toFixed(4)),
      idleWorker: Number(this.idle.worker.toFixed(4)),
      /* La dispersion des coûts de tâche — la condition pour qu'un tri ait un
       * objet. Une médiane et un maximum suffisent à la dire. */
      taskMsMedian: ms.length ? Number(ms[Math.floor(ms.length / 2)].toFixed(1)) : 0,
      taskMsMax: ms.length ? Number(ms[ms.length - 1].toFixed(1)) : 0,
      taskMsMin: ms.length ? Number(ms[0].toFixed(1)) : 0,
    };
  }
}

export class EvaluatorPool {
  #workers = [];
  #idle = [];
  #queue = [];
  #nextId = 1;
  #pending = new Map();
  #slot = new Map();

  constructor(workers) {
    this.#workers = workers;
    this.#idle = [...workers];
    workers.forEach((worker, index) => this.#slot.set(worker, index));
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
    const slot = this.#slot.get(worker);
    const sentAt = performance.now();

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

      /* Relevé AVANT de rendre le worker au pool : l'oisiveté commence
       * exactement ici. */
      if (job.report) {
        job.report.note(slot, sentAt, performance.now(), event.data.computeMs, job.label);
      }
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
   * Returns `{ outputs, cancel, done, schedule }`. `cancel()` tells every busy
   * worker to stop between chunks; `done` resolves with the outputs, or with
   * `null` if the work was abandoned. `schedule` est le relevé
   * d'ordonnancement, lisible une fois `done` résolu.
   */
  analyze(features, count, numFeatures, { chunk = DEFAULT_CHUNK, onProgress } = {}) {
    const slots = this.size;
    const per = Math.ceil(count / slots);
    const jobs = [];
    const report = new ScheduleReport(slots);

    for (let start = 0; start < count; start += per) {
      const length = Math.min(per, count - start);
      const slice = features.subarray(start * numFeatures, (start + length) * numFeatures);
      jobs.push({ features: slice, count: length, chunk, start, report, label: jobs.length });
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

    return { done, cancel, schedule: report };
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
   * Rend `{ done, cancel, schedule }` comme `analyze`. `done` résout sur un
   * tableau parallèle à `positions`, ou sur `null` si le travail a été
   * abandonné.
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
    const report = new ScheduleReport(this.size);
    let completed = 0;

    const promises = positions.map((position, index) => new Promise((resolve, reject) => {
      const job = {
        decision: true,
        report,
        label: index,
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

    return { done, cancel, schedule: report };
  }

  destroy() {
    for (const worker of this.#workers) worker.terminate();
    this.#workers = [];
    this.#idle = [];
    this.#queue = [];
    this.#slot.clear();
  }
}
