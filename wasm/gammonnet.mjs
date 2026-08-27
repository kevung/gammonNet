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

  /**
   * Charger le réseau d'ÉLAGAGE et fixer combien de candidats il laisse
   * passer. `k <= 0` l'éteint et rend la recherche d'avant, bit pour bit.
   *
   * Le gain natif est ×3,9 à k=12 pour une perte dans le bruit. Ce qu'il
   * devient ICI n'est pas connu : il vient du remplissage des lots, et le lot
   * rend ×2,21 dans un navigateur contre ×8,5 en natif. Cette méthode existe
   * pour que ce soit mesuré, pas transporté.
   */
  loadPrune(pruneBytes, k) {
    const m = this.#module;
    if (!k || k <= 0) {
      if (m._gnw_load_prune(0, 0, 0) !== 0) {
        throw new Error("l'extinction de l'élagage a été refusée");
      }
      return;
    }
    const ptr = m._malloc(pruneBytes.length);
    try {
      m.HEAPU8.set(pruneBytes, ptr);
      const status = m._gnw_load_prune(ptr, pruneBytes.length, k);
      if (status !== 0) {
        // Refusé, jamais ignoré : un élagage silencieusement inactif ferait
        // tourner une configuration qui n'est pas celle qu'on croit mesurer.
        throw new Error(
          status === -2
            ? "réseau d'élagage refusé : illisible, ou que ce build ne sait " +
              "pas évaluer"
            : "le réseau d'élagage n'a pas pu être chargé en mémoire",
        );
      }
    } finally {
      m._free(ptr);
    }
  }

  /**
   * Les N meilleurs coups, avec tout ce qu'une analyse affiche.
   *
   * `bestPlay` ne rend que le premier, ce qui suffit pour JOUER et pas pour
   * ANALYSER. Ici chaque candidat porte son équité, les cinq probabilités et
   * l'identifiant de la position résultante.
   *
   * ATTENTION AUX PROBABILITÉS : elles décrivent la position RÉSULTANTE, donc
   * vues par l'ADVERSAIRE — la convention du moteur. `forMover` les retourne
   * pour l'affichage ; les inverser en silence produirait cinq nombres
   * parfaitement plausibles et faux.
   */
  rankPlays(positionId, turn, d1, d2, {
    ply = 0, filterTop = 0, filterInner = 0,
    useMatch = false, awayOnRoll = 0, awayOpponent = 0,
    cube = 1, crawford = false, max = 10,
  } = {}) {
    const m = this.#module;
    const outPtr = m._malloc(4 * 6 * max);
    const idPtr = m._malloc(15 * max);
    try {
      const count = m.ccall(
        "gnw_rank_plays", "number",
        ["string", "number", "number", "number", "number", "number", "number",
         "number", "number", "number", "number", "number", "number", "number",
         "number"],
        [positionId, turn, d1, d2, ply, filterTop, filterInner,
         useMatch ? 1 : 0, awayOnRoll, awayOpponent, cube, crawford ? 1 : 0,
         max, outPtr, idPtr]);
      if (count < 0) {
        throw new Error("classement refusé : position illisible, ou score " +
                        "hors de la table d'équité de match");
      }
      const out = [];
      for (let i = 0; i < count; i++) {
        const base = (outPtr >> 2) + i * 6;
        const probs = Array.from(m.HEAPF32.subarray(base + 1, base + 6));
        out.push({
          equity: m.HEAPF32[base],
          resultId: m.UTF8ToString(idPtr + i * 15),
          // Vues par l'adversaire, comme le moteur les produit.
          probs,
          // Et retournées, pour l'affichage.
          forMover: {
            win: 1 - probs[0],
            winGammon: probs[3], winBackgammon: probs[4],
            loseGammon: probs[1], loseBackgammon: probs[2],
          },
        });
      }
      return out;
    } finally {
      m._free(outPtr); m._free(idPtr);
    }
  }

  /**
   * La décision de videau, avec ses équités et non seulement son verdict.
   *
   * *« Une décision juste à 0,001 près et une décision juste à 0,5 près ne
   * sont pas la même décision »* — d'où `noDouble`, `double` et le point de
   * prise, en plus de l'action.
   *
   * `efficiency` est MESURÉE (`bench/fit_efficiency.py`), jamais empruntée à
   * une constante publiée.
   */
  cubeDecision(positionId, turn, {
    owner = 0, useMatch = false, awayOnRoll = 0, awayOpponent = 0,
    cube = 1, crawford = false, efficiency = 0.566, jacoby = true,
    ply = 0, filterTop = 0, filterInner = 0,
  } = {}) {
    const m = this.#module;
    const outPtr = m._malloc(8 * 9);
    try {
      const status = m.ccall(
        "gnw_cube_decide", "number",
        ["string", "number", "number", "number", "number", "number", "number",
         "number", "number", "number", "number", "number", "number", "number"],
        [positionId, turn, owner, useMatch ? 1 : 0, awayOnRoll, awayOpponent,
         cube, crawford ? 1 : 0, efficiency, jacoby ? 1 : 0,
         ply, filterTop, filterInner, outPtr]);
      if (status !== 0) {
        throw new Error("décision de videau refusée : position illisible, ou " +
                        "score hors de la table d'équité de match");
      }
      const v = m.HEAPF64.subarray(outPtr >> 3, (outPtr >> 3) + 9);
      const ACTIONS = ["no-double", "double-take", "double-pass", "too-good"];
      return {
        action: ACTIONS[v[0]] ?? String(v[0]),
        equityNoDouble: v[1],
        equityDouble: v[2],
        takePoint: v[3],
        probs: Array.from(v.subarray(4, 9)),
      };
    } finally {
      m._free(outPtr);
    }
  }

  /** Le k réellement en vigueur — 0 si l'élagage est éteint. */
  pruneK() {
    return this.#module._gnw_prune_k();
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
