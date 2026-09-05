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
 * ── CE QUE CE PROTOCOLE RELAIE, ET POURQUOI IL A CHANGÉ (T86) ──────────
 *
 * Il ne relayait que `init` / `evaluate` / `stop` : des LOTS DE
 * CARACTÉRISTIQUES, jamais une décision. Les trois points d'entrée de la
 * recherche étaient pourtant exportés du module depuis le début
 * (`_gnw_best_play`, `_gnw_rank_plays`, `_gnw_cube_decide`) — le manque
 * était ici, et pas dans `EXPORTED_FUNCTIONS`.
 *
 * Le prix de ce manque se paie hors du moteur, et il s'est payé : faute de
 * pouvoir atteindre ces trois décisions par message, il ne reste qu'à
 * ordonnancer soi-même des lots bruts et à réécrire à côté ce que le module
 * sait déjà faire. Un moteur qui ne relaie pas ses décisions se fait réécrire
 * à côté ; c'est ce que l'ADR-0003 appelle la condition des autres fiches.
 *
 * Le protocole reste petit, et il reste UN SEUL endroit où la règle de
 * référentiel peut se tromper : les points d'entrée ajoutés ne calculent
 * rien, ils passent la main à `Evaluator`, qui passe la main au C.
 *
 * ── L'ANNULATION, DITE HONNÊTEMENT ────────────────────────────────────
 *
 * `evaluate` s'annule ENTRE LOTS parce qu'il rend la main à la boucle
 * d'événements entre deux lots ; sans ce retour, aucun message `stop` ne
 * pourrait être délivré. C'est la contrainte de fond, et elle vaut pour
 * tout ce fichier :
 *
 *   **un appel WASM synchrone ne peut pas être interrompu depuis
 *   JavaScript.** Le worker est mono-thread : tant que `_gnw_best_play`
 *   s'exécute, `self.onmessage` ne tourne pas, donc `stop` n'arrive pas.
 *   Un drapeau coopératif posé dans le C n'y changerait rien — personne ne
 *   pourrait le lever. Il faudrait un `SharedArrayBuffer` écrit par un
 *   autre thread (COOP/COEP absents, cf. plus haut) ou Asyncify, qui
 *   instrumente tout le module et le fait grossir — ce que le seuil de
 *   taille de T86 refuse.
 *
 * Ce que ce worker fait donc, et qui n'existait pas :
 *
 *   1. Les requêtes sont MISES EN FILE et exécutées une par une, la boucle
 *      d'événements reprenant la main entre deux. `stop` vide la file et
 *      périme la génération courante : le résultat d'une requête dépassée
 *      n'est jamais posté.
 *   2. Un travail à plusieurs positions (`analyze`) s'annule ENTRE
 *      POSITIONS, ce qui est la granularité d'une analyse de match.
 *   3. `progressive: true` calcule d'abord à 0-ply, poste ce résultat, rend
 *      la main, puis relance en profondeur — une frontière d'annulation
 *      AVANT l'étape qui coûte, et une première réponse tout de suite.
 *   4. LE WORKER SURVIT À L'ANNULATION. C'est le point pratique : le seul
 *      arrêt dur du navigateur reste `Worker.terminate()`, et il emporte les
 *      1,06 Mo de poids avec lui. Sans file ni générations, annuler impose
 *      un worker neuf par geste ; avec elles, un geste dépassé coûte
 *      l'attente de la décision en cours, pas un rechargement des poids.
 *
 * SPDX-License-Identifier: MIT
 */

import { Evaluator } from "./gammonnet.mjs";

let evaluator = null;

/* Set by `stop`. Checked between chunks so a long job can be abandoned without
 * waiting for it to finish -- cancellation that only takes effect at the end is
 * not cancellation. */
let cancelled = false;

/*
 * LA GÉNÉRATION. Elle monte à chaque `stop`. Une requête retient la sienne au
 * moment où elle est reçue ; si elle a vieilli quand le résultat est prêt, le
 * résultat n'est pas posté. C'est ce qui remplace `terminate()` pour un geste
 * dépassé : le calcul en cours va au bout (on ne peut pas l'interrompre), mais
 * sa réponse ne remonte pas, et le worker reste chaud.
 */
let generation = 0;

/* La file, et le fait qu'un seul travail tourne à la fois. Entre deux travaux
 * la boucle d'événements reprend la main — c'est là, et seulement là, que
 * `stop` peut arriver. */
const queue = [];
let running = false;

const yieldToLoop = () => new Promise((resolve) => setTimeout(resolve, 0));

/*
 * LE TEMPS RÉELLEMENT PASSÉ DANS LE WASM, pour la tâche en cours (T87).
 *
 * Le pool relève de son côté l'occupation d'un worker de l'ENVOI à la
 * RÉPONSE : cette mesure-là compte la sérialisation et les deux traversées de
 * `postMessage`. Prise seule, elle ferait passer une latence de messagerie
 * pour du travail et SOUS-ESTIMERAIT l'oisiveté. Le worker rapporte donc ce
 * qu'il a vraiment calculé, et l'écart entre les deux est publié comme tel.
 *
 * Les `await yieldToLoop()` n'entrent pas dans ce compte : rendre la main
 * n'est pas calculer, et c'est précisément ce qu'il fallait pouvoir
 * distinguer.
 */
let computeMs = 0;
const timed = (fn) => {
  const start = performance.now();
  try {
    return fn();
  } finally {
    computeMs += performance.now() - start;
  }
};

function requireEvaluator() {
  if (evaluator === null) throw new Error("worker non initialisé");
  return evaluator;
}

/*
 * Les octets d'un réseau d'élagage, d'une table de fin de partie, la taille du
 * cache : tout est optionnel. Un worker qui ne reçoit rien de plus se comporte
 * exactement comme avant.
 */
function applyConfiguration({ pruneBytes, pruneK, bearoffBytes, cacheLog2 }) {
  const ev = requireEvaluator();
  if (pruneBytes !== undefined || pruneK !== undefined) {
    ev.loadPrune(pruneBytes ? new Uint8Array(pruneBytes) : null, pruneK ?? 0);
  }
  if (bearoffBytes !== undefined) {
    ev.loadBearoff(bearoffBytes ? new Uint8Array(bearoffBytes) : null);
  }
  if (cacheLog2 !== undefined) {
    ev.enableCache(cacheLog2);
  }
}

/*
 * UNE DÉCISION, éventuellement en deux temps.
 *
 * `progressive` n'est pas un réglage de confort : c'est la seule frontière
 * d'annulation qu'un appelant puisse obtenir à l'intérieur d'une décision. Le
 * 0-ply coûte ~6 ms et le 2-ply ~2,7 s (T30) ; poster le premier, rendre la
 * main, puis vérifier la génération avant d'engager le second, c'est
 * transformer 2,7 s d'attente incompressible en 6 ms.
 */
async function runDecision(kind, message, mine) {
  const ev = requireEvaluator();
  /* `positionId` et non `id` : `id` est l'identifiant de la REQUÊTE dans ce
   * protocole, celui que la réponse porte en retour. Deux identifiants de
   * nature différente sous le même nom est exactement le genre de collision
   * qui produit un résultat plausible attaché à la mauvaise demande. */
  const { positionId, turn, d1, d2, options = {}, progressive = false } = message;
  const stale = () => generation !== mine;

  const call = (opts) => {
    if (kind === "bestPlay") return ev.bestPlay(positionId, turn, d1, d2, opts);
    if (kind === "rankPlays") return ev.rankPlays(positionId, turn, d1, d2, opts);
    return ev.cubeDecision(positionId, turn, opts);
  };

  const deep = options.ply ?? 0;
  if (progressive && deep > 0) {
    const shallow = timed(() => call({ ...options, ply: 0, filterTop: 0, filterInner: 0 }));
    if (stale()) return undefined;
    self.postMessage({ type: "partial", id: message.requestId, kind, ply: 0, outcome: shallow });
    await yieldToLoop();
    if (stale()) return undefined;
  }

  const outcome = timed(() => call(options));
  if (stale()) return undefined;
  return { outcome, ply: deep };
}

/*
 * PLUSIEURS DÉCISIONS D'AFFILÉE — la forme d'une analyse de match.
 *
 * Chaque position est un travail, et l'annulation mord entre deux. C'est la
 * granularité utile : personne n'annule au milieu d'une décision, on annule
 * une analyse.
 */
async function runAnalysis(message, mine) {
  const ev = requireEvaluator();
  const { positions, options = {}, kind = "rankPlays" } = message;
  const outcomes = [];
  for (let i = 0; i < positions.length; i++) {
    if (generation !== mine) return undefined;
    const p = positions[i];
    const opts = { ...options, ...(p.options || {}) };
    outcomes.push(timed(() => (
      kind === "cubeDecision"
        ? ev.cubeDecision(p.positionId, p.turn, opts)
        : kind === "bestPlay"
          ? ev.bestPlay(p.positionId, p.turn, p.d1, p.d2, opts)
          : ev.rankPlays(p.positionId, p.turn, p.d1, p.d2, opts)
    )));
    self.postMessage({
      type: "progress", id: message.requestId,
      done: i + 1, total: positions.length,
    });
    /* La main rendue APRÈS chaque position, jamais seulement à la fin : c'est
     * ce qui rend `stop` délivrable. */
    await yieldToLoop();
  }
  return { outcome: outcomes };
}

async function serve(message, mine) {
  switch (message.type) {
    case "bestPlay":
    case "rankPlays":
    case "cubeDecision":
      return runDecision(message.type, message, mine);
    case "analyze":
      return runAnalysis(message, mine);
    default:
      throw new Error(`message inconnu : ${message.type}`);
  }
}

async function pump() {
  if (running) return;
  running = true;
  try {
    while (queue.length > 0) {
      const { message, mine } = queue.shift();
      /* Périmée, en file ou en vol : elle reçoit UNE réponse quand même, et
       * c'est `cancelled`. Un appelant qui attend une promesse ne doit pas
       * rester suspendu parce que son travail a été dépassé — l'annulation
       * silencieuse est un blocage, pas une annulation. */
      if (generation !== mine) {
        self.postMessage({ type: "cancelled", id: message.requestId });
        continue;
      }
      try {
        computeMs = 0;
        const answer = await serve(message, mine);
        self.postMessage(answer === undefined
          ? { type: "cancelled", id: message.requestId, computeMs }
          : {
            type: "result", id: message.requestId,
            kind: message.type, ply: answer.ply, outcome: answer.outcome,
            computeMs,
          });
      } catch (error) {
        self.postMessage({
          type: "error", id: message.requestId,
          message: String(error?.stack || error),
        });
      }
      await yieldToLoop();
    }
  } finally {
    running = false;
  }
}

self.onmessage = async (event) => {
  const { type, id } = event.data;

  try {
    if (type === "init") {
      const { factoryUrl, modelBytes } = event.data;
      const { default: factory } = await import(factoryUrl);
      evaluator = await Evaluator.create(factory, modelBytes);
      /* Élagage, table de fin de partie, cache : optionnels, et pris ici
       * plutôt que par un aller-retour de plus. */
      applyConfiguration(event.data);
      self.postMessage({
        type: "ready", id,
        simd: evaluator.hasSimd,
        pruneK: evaluator.pruneK(),
      });
      return;
    }

    if (type === "configure") {
      applyConfiguration(event.data);
      self.postMessage({ type: "configured", id, pruneK: evaluator.pruneK() });
      return;
    }

    if (type === "evaluate") {
      requireEvaluator();
      cancelled = false;

      const { features, count, chunk } = event.data;
      const outputs = new Float32Array(count * evaluator.numOutputs);
      const size = chunk || count;

      computeMs = 0;
      let done = 0;
      while (done < count && !cancelled) {
        const batch = Math.min(size, count - done);
        const slice = features.subarray(
          done * evaluator.numFeatures,
          (done + batch) * evaluator.numFeatures,
        );
        outputs.set(timed(() => evaluator.evaluateBatch(slice, batch)),
                    done * evaluator.numOutputs);
        done += batch;
        /* Yield between chunks so `stop` can be delivered. A worker that never
         * returns to its event loop cannot be interrupted. */
        if (done < count) await yieldToLoop();
      }

      if (cancelled) {
        self.postMessage({ type: "cancelled", id, done, computeMs });
      } else {
        self.postMessage({ type: "result", id, outputs, count, computeMs },
                         [outputs.buffer]);
      }
      return;
    }

    if (type === "bestPlay" || type === "rankPlays" || type === "cubeDecision"
        || type === "analyze") {
      requireEvaluator();
      queue.push({ message: { ...event.data, requestId: id }, mine: generation });
      pump();
      return;
    }

    if (type === "stop") {
      /* Deux effets, et ils sont distincts. Le drapeau arrête `evaluate` entre
       * deux lots ; la génération périme tout ce qui est en file ou en vol côté
       * recherche. Ce qui tourne DÉJÀ dans le WASM va au bout — la plateforme
       * ne permet rien d'autre — mais sa réponse ne remonte pas, et le worker
       * reste utilisable, poids compris. */
      cancelled = true;
      generation++;
      /* La file est VIDÉE EN RÉPONDANT. La jeter en silence laisserait chaque
       * appelant en attente d'une promesse qui ne se résoudra jamais — le
       * même défaut que l'annulation muette, déplacé d'un cran. */
      while (queue.length > 0) {
        const abandoned = queue.shift();
        self.postMessage({ type: "cancelled", id: abandoned.message.requestId });
      }
      self.postMessage({ type: "stopped", id, generation });
      return;
    }

    throw new Error(`message inconnu : ${type}`);
  } catch (error) {
    self.postMessage({ type: "error", id, message: String(error?.stack || error) });
  }
};
