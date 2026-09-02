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

/* GN_NOTATION_LENGTH (`src/gn_notation.h`) : la place d'une notation de coup. */
const NOTATION_LENGTH = 40;

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
   * LE RÉFÉRENTIEL DES PROBABILITÉS EST CELUI DU JOUEUR QUI JOUE — le même
   * que celui de `equity`, à côté d'elles, et le même que celui de
   * `/v1/eval` et de `cubeDecision`. gammonNet n'a plus qu'une convention.
   *
   * Avant v1.1.0 elles décrivaient la position RÉSULTANTE, donc l'adversaire,
   * et `forMover` portait le retournement. `forMover` A DISPARU : le laisser
   * à côté d'un `probs` déjà retourné aurait recréé le piège au lieu de le
   * fermer. Un code qui l'utilisait lit désormais `undefined`, ce qui est
   * bruyant — au contraire de cinq nombres parfaitement plausibles et faux.
   *
   * `probs` est un tableau de cinq : `[gain, gammon gagné, backgammon gagné,
   * gammon perdu, backgammon perdu]`, imbriqués (un backgammon est un gammon
   * est un gain).
   *
   * CE QU'ELLES NE SONT PAS : au-delà de `ply: 0`, elles viennent de la passe
   * superficielle qui a servi à classer les coups, pas de la recherche
   * profonde qui a produit l'équité. Le côté est le bon, la profondeur non —
   * `2·gain + gammon − gammonPerdu … = equity` ne tient donc qu'à 0-ply.
   */
  rankPlays(positionId, turn, d1, d2, {
    ply = 0, filterTop = 0, filterInner = 0,
    useMatch = false, awayOnRoll = 0, awayOpponent = 0,
    cube = 1, crawford = false, max = 10,
    cubeOwner = null, efficiency = 0.566,
  } = {}) {
    const m = this.#module;
    const outPtr = m._malloc(4 * 6 * max);
    const idPtr = m._malloc(15 * max);
    /* GN_NOTATION_LENGTH, comme les 15 ci-dessus sont GN_POSITION_ID_LENGTH. */
    const notationPtr = m._malloc(NOTATION_LENGTH * max);
    try {
      const count = m.ccall(
        "gnw_rank_plays", "number",
        ["string", "number", "number", "number", "number", "number", "number",
         "number", "number", "number", "number", "number", "number", "number",
         "number", "number", "number", "number"],
        [positionId, turn, d1, d2, ply, filterTop, filterInner,
         useMatch ? 1 : 0, awayOnRoll, awayOpponent, cube, crawford ? 1 : 0,
         cubeOwner === null ? -1 : cubeOwner, efficiency,
         max, outPtr, idPtr, notationPtr]);
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
          // LE NOM DU COUP, tel que la recherche l'a retenu — « 6/5 8/5 »
          // sur l'ouverture 3-1. L'ordre des sous-coups est celui que la
          // recherche a produit, pas un ordre d'affichage.
          //
          // `resultId` est un PLATEAU, et un plateau ne dit pas quel pion est
          // allé où : deux appariements peuvent laisser le même. Le rendre
          // seul revenait à jeter la moitié de la réponse. Voir
          // `src/gn_notation.h` ; c'est la MÊME notation que le champ `move`
          // de `/v1/eval`, et non une seconde.
          notation: m.UTF8ToString(notationPtr + i * NOTATION_LENGTH),
          // Du côté du joueur qui joue, comme `equity` : `gnw_rank_plays`
          // retourne la distribution une fois pour toutes.
          probs,
        });
      }
      return out;
    } finally {
      m._free(outPtr); m._free(idPtr); m._free(notationPtr);
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

  /**
   * La TABLE EXACTE de fin de partie.
   *
   * L'artefact la livre (`bearoff_one_sided.bin`, 6,9 Mio). Sans elle la
   * recherche retombe sur le réseau et perd 0,00028 d'équité par décision de
   * bearoff — mesuré, et silencieux. Passez `null` pour la retirer.
   */
  loadBearoff(bytes) {
    const m = this.#module;
    if (!bytes || bytes.length === 0) {
      m._gnw_load_bearoff(0, 0);
      return;
    }
    const ptr = m._malloc(bytes.length);
    try {
      m.HEAPU8.set(bytes, ptr);
      const status = m._gnw_load_bearoff(ptr, bytes.length);
      if (status !== 0) {
        throw new Error(status === -2
          ? "table de fin de partie refusée : illisible ou d'un format inconnu"
          : "la table n'a pas pu être chargée en mémoire");
      }
    } finally {
      m._free(ptr);
    }
  }

  /**
   * Le CACHE D'ÉVALUATION.
   *
   * Il rejoue les réponses du réseau et n'en invente aucune : vérifié qu'il ne
   * change aucun résultat. Mesuré ×1,35 en contact, ×4,6 en course à 2-ply.
   * `log2Entries = 21` donne deux millions d'entrées (le réglage de la
   * campagne de mesure) ; `0` le désactive.
   */
  enableCache(log2Entries = 21) {
    if (this.#module._gnw_enable_cache(log2Entries) !== 0) {
      throw new Error("cache d'évaluation refusé : mémoire insuffisante ?");
    }
  }

  /**
   * Un NIVEAU D'ANALYSE, plutôt que six réglages à accorder soi-même.
   *
   * Rend l'objet d'options à passer à `rankPlays` / `bestPlay`. Les budgets de
   * temps sont mesurés et documentés ; les composer autrement est possible,
   * mais alors c'est à vous de mesurer ce que ça coûte.
   */
  static level(name) {
    const LEVELS = {
      // 0-ply : le réseau seul. ~6 ms par décision dans un navigateur.
      instant: { ply: 0, filterTop: 0, filterInner: 0, pruneK: 0 },
      // Le défaut. 2-ply filtré, élagage k=12 : ×3,65 pour une perte d'équité
      // dans le bruit. ~2,7 s par décision, ~74 s le match à huit workers.
      normal: { ply: 2, filterTop: 3, filterInner: 1, pruneK: 12 },
      // Le même sans élagage : ~9,8 s par décision. Pour trancher une
      // décision précise, pas pour parcourir un match.
      thorough: { ply: 2, filterTop: 3, filterInner: 1, pruneK: 0 },
    };
    const level = LEVELS[name];
    if (!level) {
      throw new Error(
        `niveau inconnu : ${name}. Connus : ${Object.keys(LEVELS).join(", ")}`);
    }
    return { ...level };
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
    const notationPtr = m._malloc(NOTATION_LENGTH);
    try {
      const equity = m.ccall(
        "gnw_best_play", "number",
        ["string", "number", "number", "number", "number", "number", "number",
         "number", "number", "number", "number", "number", "number", "number",
         "number"],
        [positionId, turn, d1, d2, ply, filterTop, filterInner,
         match ? 1 : 0,
         match ? match.awayOnRoll : 0,
         match ? match.awayOpponent : 0,
         match ? (match.cube ?? 1) : 1,
         match ? (match.crawford ? 1 : 0) : 0,
         idPtr, countPtr, notationPtr],
      );
      if (equity <= -99.0) {
        // Refusé : position illisible, aucun coup légal, ou score hors table.
        // Pas de repli silencieux.
        return null;
      }
      return {
        equity,
        resultId: m.UTF8ToString(idPtr),
        // Le coup, nommé. Voir `rankPlays` ci-dessus et `src/gn_notation.h`.
        notation: m.UTF8ToString(notationPtr),
        evaluations: m.HEAP32[countPtr >> 2],
      };
    } finally {
      m._free(idPtr);
      m._free(countPtr);
      m._free(notationPtr);
    }
  }

  /* ── Le codec de position ────────────────────────────────────────────
   *
   * POURQUOI IL EST ICI (T86). Le C possède `gn_position_id`,
   * `gn_position_from_id`, `gn_xgid` et `gn_position_from_xgid` depuis T02,
   * croisés contre gnubg-nn sur 10 000 positions. Aucun n'était atteignable
   * depuis JavaScript : le module prenait un identifiant en entrée et n'a
   * jamais su en fabriquer un.
   *
   * Un consommateur qui part de SON plateau n'avait donc qu'une option,
   * réécrire le codec. gammonGo l'a fait, et son en-tête est honnête sur la
   * méthode : algorithme déduit, puis validé empiriquement contre ce module.
   * C'est la seule des trois écritures de ce codec qui ne descende pas d'une
   * référence indépendante — une déduction confirmée par son propre
   * consommateur est un accord avec soi-même, pas une vérification.
   *
   * UN PLATEAU, dans la convention de `gn_rules.h` et sans en inventer une
   * seconde :
   *
   *     { points: [24 comptes SIGNÉS, positif BLANC, négatif NOIR],
   *       bar: [blanc, noir], off: [blanc, noir], turn: 0 | 1 }
   *
   * L'indice i désigne le point (i+1) pour BLANC et (24-i) pour NOIR.
   */

  /** Le tampon de 29 entiers que le C attend, alloué et rendu par l'appelant. */
  #withBoard(board, use) {
    const m = this.#module;
    const ptr = m._malloc(29 * 4);
    try {
      const view = m.HEAP32.subarray(ptr >> 2, (ptr >> 2) + 29);
      const points = board?.points ?? [];
      for (let i = 0; i < 24; i++) view[i] = points[i] | 0;
      view[24] = board?.bar?.[0] | 0;
      view[25] = board?.bar?.[1] | 0;
      view[26] = board?.off?.[0] | 0;
      view[27] = board?.off?.[1] | 0;
      view[28] = board?.turn | 0;
      return use(ptr);
    } finally {
      m._free(ptr);
    }
  }

  #readBoard(ptr) {
    const view = this.#module.HEAP32.subarray(ptr >> 2, (ptr >> 2) + 29);
    return {
      points: Array.from(view.subarray(0, 24)),
      bar: [view[24], view[25]],
      off: [view[26], view[27]],
      turn: view[28],
    };
  }

  /**
   * Le Position ID d'un plateau, vu par le joueur au trait.
   *
   * Refuse (lève) un plateau structurellement impossible plutôt que d'en
   * tirer un identifiant plausible : quinze pions par camp, aucun point des
   * deux couleurs. C'est `gn_position_is_valid` qui tranche, pas ce fichier.
   */
  positionId(board) {
    const m = this.#module;
    return this.#withBoard(board, (boardPtr) => {
      const idPtr = m._malloc(16);
      try {
        if (m._gnw_position_encode(boardPtr, idPtr) !== 0) {
          throw new Error("plateau refusé : ce n'est pas une position valide");
        }
        return m.UTF8ToString(idPtr);
      } finally {
        m._free(idPtr);
      }
    });
  }

  /**
   * Le plateau d'un Position ID, `turn` au trait.
   *
   * `turn` EST UN PARAMÈTRE, et c'est le piège de ce format : l'identifiant
   * ne porte pas le joueur au trait, deux positions qui n'en diffèrent que
   * partagent leur identifiant. Le `resultId` que rend `bestPlay` décrit la
   * position D'APRÈS le coup, donc l'autre camp est au trait — passer le même
   * `turn` qu'à l'aller rend silencieusement le plateau du mauvais côté.
   */
  positionFromId(id, turn) {
    const m = this.#module;
    const ptr = m._malloc(29 * 4);
    try {
      /* `ccall` et non l'export nu : l'identifiant est une chaîne
       * JavaScript, qu'il faut copier dans le tas du module. */
      if (m.ccall("gnw_position_decode", "number",
                  ["string", "number", "number"], [id, turn, ptr]) !== 0) {
        throw new Error("identifiant de position illisible");
      }
      return this.#readBoard(ptr);
    } finally {
      m._free(ptr);
    }
  }

  /**
   * Le XGID d'un plateau. `fields` est optionnel — absent, le XGID décrit une
   * partie d'argent sans videau, aucun jet posé, le trait pris du plateau.
   *
   * SON DEGRÉ DE VÉRIFICATION N'EST PAS CELUI DU POSITION ID, et
   * `gn_position_id.h` le dit : le XGID est ancré sur l'identifiant
   * d'ouverture canonique et sur l'aller-retour, faute d'implémentation
   * indépendante contre laquelle le croiser. Orientation établie, non oraclée.
   */
  xgid(board, fields = null) {
    const m = this.#module;
    return this.#withBoard(board, (boardPtr) => {
      const outPtr = m._malloc(64);
      const fieldsPtr = fields ? m._malloc(10 * 4) : 0;
      try {
        if (fields) {
          m.HEAP32.set(Evaluator.#xgidFieldsToInts(fields), fieldsPtr >> 2);
        }
        if (m._gnw_xgid_encode(boardPtr, fieldsPtr, outPtr) !== 0) {
          throw new Error("plateau refusé : ce n'est pas une position valide");
        }
        return m.UTF8ToString(outPtr);
      } finally {
        m._free(outPtr);
        if (fieldsPtr) m._free(fieldsPtr);
      }
    });
  }

  /** Le plateau et les dix champs d'un XGID. */
  positionFromXgid(xgid) {
    const m = this.#module;
    const boardPtr = m._malloc(29 * 4);
    const fieldsPtr = m._malloc(10 * 4);
    try {
      if (m.ccall("gnw_xgid_decode", "number",
                  ["string", "number", "number"], [xgid, boardPtr, fieldsPtr]) !== 0) {
        throw new Error("XGID illisible");
      }
      const f = m.HEAP32.subarray(fieldsPtr >> 2, (fieldsPtr >> 2) + 10);
      return {
        board: this.#readBoard(boardPtr),
        fields: {
          cubePower: f[0], cubeOwner: f[1], turn: f[2], die1: f[3], die2: f[4],
          scoreUpper: f[5], scoreLower: f[6], flags: f[7],
          matchLength: f[8], maxCube: f[9],
        },
      };
    } finally {
      m._free(boardPtr);
      m._free(fieldsPtr);
    }
  }

  static #xgidFieldsToInts(f) {
    return Int32Array.from([
      f.cubePower | 0, f.cubeOwner | 0, f.turn | 0, f.die1 | 0, f.die2 | 0,
      f.scoreUpper | 0, f.scoreLower | 0, f.flags | 0,
      f.matchLength | 0, f.maxCube | 0,
    ]);
  }

  /**
   * LE COMPTE DE PIPS — la sentinelle, pas un ornement.
   *
   * `BRIEF.md` §6 : *« si le compte de pips d'une position traduite n'est pas
   * celui qu'on attendait, tout ce qui suit est dénué de sens. Utilisez-le
   * chaque fois qu'une position traverse une frontière de format. »*
   * Convertir un plateau d'application vers celui-ci EST une telle frontière.
   */
  pipCount(board, player) {
    const count = this.#withBoard(board,
      (ptr) => this.#module._gnw_pip_count(ptr, player));
    if (count < 0) throw new Error("plateau refusé : position invalide");
    return count;
  }

  destroy() {
    const m = this.#module;
    m._gnw_free_model();
    if (this.#featuresPtr) m._free(this.#featuresPtr);
    if (this.#outputsPtr) m._free(this.#outputsPtr);
    this.#featuresPtr = this.#outputsPtr = this.#capacity = 0;
  }
}
