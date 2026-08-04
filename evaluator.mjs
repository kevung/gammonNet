/*
 * gammonnet.mjs -- the JavaScript face of the evaluator.
 *
 * A position in, five probabilities out. This module knows nothing about
 * matches, users, or storage; see CLAUDE.md's boundary rule.
 *
 * It wraps either build -- scalar or SIMD -- because T21 has to compare them,
 * and a wrapper that could only load one of them would quietly decide the
 * comparison in advance.
 *
 * SPDX-License-Identifier: MIT
 */

const F32 = 4;

/**
 * A loaded evaluator.
 *
 * Buffers are allocated once, in WASM memory, and reused. Allocating per
 * evaluation would put `malloc` inside the measurement, and at 0-ply speeds
 * that is not a rounding error -- it is a large share of what T21 is trying to
 * time.
 */
export class Evaluator {
  #module;
  #featuresPtr = 0;
  #outputsPtr = 0;
  #capacity = 0;

  constructor(module) {
    this.#module = module;
    this.numFeatures = module._gnw_num_features();
    this.numOutputs = module._gnw_num_outputs();
    this.hasSimd = module._gnw_has_simd() === 1;
  }

  /**
   * Instantiate a build and load a model into it.
   *
   * @param {Function} factory  the default export of a generated `.mjs`
   * @param {Uint8Array} modelBytes  the contents of a `.bin` file
   */
  static async create(factory, modelBytes) {
    const module = await factory();
    const evaluator = new Evaluator(module);
    evaluator.loadModel(modelBytes);
    return evaluator;
  }

  loadModel(modelBytes) {
    const m = this.#module;
    const ptr = m._malloc(modelBytes.length);
    try {
      m.HEAPU8.set(modelBytes, ptr);
      const status = m._gnw_load_model(ptr, modelBytes.length);
      if (status !== 0) {
        // Refused, never approximated. A model this build cannot evaluate
        // would otherwise return five perfectly plausible wrong numbers.
        throw new Error(
          status === -2
            ? "modèle refusé : illisible, ou que ce build ne sait pas évaluer " +
              "(mode de sortie autre que prob5, ou taille d'entrée étrangère)"
            : "le modèle n'a pas pu être chargé en mémoire",
        );
      }
    } finally {
      m._free(ptr);
    }
  }

  #reserve(count) {
    if (count <= this.#capacity) return;
    const m = this.#module;
    if (this.#featuresPtr) m._free(this.#featuresPtr);
    if (this.#outputsPtr) m._free(this.#outputsPtr);
    this.#featuresPtr = m._malloc(count * this.numFeatures * F32);
    this.#outputsPtr = m._malloc(count * this.numOutputs * F32);
    this.#capacity = count;
  }

  /**
   * Evaluate one encoded feature vector.
   *
   * @param {Float32Array} features  length `numFeatures`
   * @returns {Float32Array} the five probabilities, nested
   */
  evaluate(features) {
    return this.evaluateBatch(features, 1);
  }

  /**
   * Evaluate `count` feature vectors laid out back to back.
   *
   * One boundary crossing for many evaluations. The returned array is a copy:
   * the WASM heap can move under `ALLOW_MEMORY_GROWTH`, and a view handed to a
   * caller would silently detach.
   */
  evaluateBatch(features, count) {
    const m = this.#module;
    this.#reserve(count);
    m.HEAPF32.set(features, this.#featuresPtr / F32);
    if (m._gnw_evaluate_batch(this.#featuresPtr, this.#outputsPtr, count) !== 0) {
      throw new Error("évaluation refusée : aucun modèle chargé");
    }
    const base = this.#outputsPtr / F32;
    return m.HEAPF32.slice(base, base + count * this.numOutputs);
  }

  /** Cubeless money equity from a distribution. A projection: it loses what
   *  match play needs. See `src/gn_infer.h`. */
  moneyEquity(probs) {
    const m = this.#module;
    const ptr = m._malloc(this.numOutputs * F32);
    try {
      m.HEAPF32.set(probs, ptr / F32);
      return m._gnw_money_equity(ptr);
    } finally {
      m._free(ptr);
    }
  }

  /**
   * Décider d'un coup, recherche complète comprise.
   *
   * C'est ce que T21 n'avait pas pu chronométrer : son verdict multipliait un
   * débit d'évaluations mesuré par un nombre d'évaluations projeté. Ici la
   * décision entière est faite, génération des coups et parcours de l'arbre
   * inclus.
   *
   * @param {string} positionId  identifiant de position (codec T02)
   * @param {number} turn        0 pour Blanc, 1 pour Noir
   * @param {number} d1, d2      les dés
   * @param {object} options     ply, filterTop, filterInner, match
   * @returns {{equity: number, resultId: string, evaluations: number}}
   */
  bestPlay(positionId, turn, d1, d2, {
    ply = 0, filterTop = 0, filterInner = 0, match = null,
  } = {}) {
    const m = this.#module;
    // 16 octets pour l'identifiant (14 caractères plus le NUL), 4 pour le
    // compteur. Alloués et libérés ici : les garder entre appels ferait entrer
    // une allocation dans la mesure, ce que le chemin par lot évite déjà.
    const idPtr = m._malloc(16);
    const countPtr = m._malloc(4);
    try {
      const equity = m.ccall(
        "gnw_best_play", "number",
        ["string", "number", "number", "number", "number", "number", "number",
         "number", "number", "number", "number", "number", "number", "number"],
        [positionId, turn, d1, d2, ply, filterTop, filterInner,
         match ? 1 : 0,
         match ? match.awayOnRoll : 0,
         match ? match.awayOpponent : 0,
         match ? (match.cube ?? 1) : 1,
         match ? (match.crawford ? 1 : 0) : 0,
         idPtr, countPtr],
      );
      if (equity <= -99.0) {
        // Refusé : position illisible, aucun coup légal, ou score hors table.
        // Pas de repli silencieux.
        return null;
      }
      return {
        equity,
        resultId: m.UTF8ToString(idPtr),
        evaluations: m.HEAP32[countPtr >> 2],
      };
    } finally {
      m._free(idPtr);
      m._free(countPtr);
    }
  }

  destroy() {
    const m = this.#module;
    m._gnw_free_model();
    if (this.#featuresPtr) m._free(this.#featuresPtr);
    if (this.#outputsPtr) m._free(this.#outputsPtr);
    this.#featuresPtr = this.#outputsPtr = this.#capacity = 0;
  }
}
