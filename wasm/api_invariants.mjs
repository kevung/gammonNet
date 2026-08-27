/*
 * Les invariants de l'API JavaScript — ce que `rankPlays` et `cubeDecision`
 * doivent tenir, quoi qu'on leur demande.
 *
 * POURQUOI CE FICHIER EXISTE. `gnw_rank_plays` dimensionnait son tampon de
 * candidats sur `max_out`, la taille demandée par l'appelant. Or `rank_plays`
 * tronque à la taille du tampon AVANT d'évaluer quoi que ce soit, dans l'ordre
 * de génération des coups : demander 3 coups faisait donc classer 3 coups
 * ARBITRAIRES. Mesuré sur l'ouverture 3-1 : le deuxième coup rendu valait
 * -0,1262 à `max = 3` contre -0,0029 sur la liste complète.
 *
 * Le défaut était invisible — cinq probabilités parfaitement plausibles, une
 * équité plausible, un classement décroissant. Rien ne clochait, sauf que ce
 * n'étaient pas les bons coups. C'est le mode de défaillance que `CLAUDE.md`
 * §2 nomme, et il a fallu comparer deux appels pour le voir.
 *
 * D'où l'invariant central ci-dessous : LES N MEILLEURS NE DÉPENDENT PAS DE N.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { Evaluator } from "./gammonnet.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const MODEL = join(ROOT, "models", "cubeless_prob5_512_512_256_128.bin");
const PRUNE = join(ROOT, "models", "prune_32.bin");
const MODULE = join(ROOT, "build", "wasm", "gammonnet-simd.mjs");

/* Position d'ouverture, jet 3-1 : le coup 8/5 6/5 y est franchement meilleur
 * que le reste, ce qui rend un mauvais classement visible. */
const POSITION = "4HPwATDgc/ABMA";

let failures = 0;
function check(label, ok, detail = "") {
  console.log(`${ok ? "✅" : "❌"} ${label}${detail ? "  " + detail : ""}`);
  if (!ok) failures++;
}

const factory = (await import(MODULE)).default;
const evaluator = await Evaluator.create(factory, new Uint8Array(readFileSync(MODEL)));
evaluator.loadPrune(new Uint8Array(readFileSync(PRUNE)), 12);
const level = Evaluator.level("normal");

/* 1. SANS FILTRE, les N meilleurs ne dépendent pas de N.
 *
 * C'est l'invariant qui attrape le défaut d'origine. Il est posé sans filtre,
 * car AVEC filtre il ne peut pas tenir, et ce n'est pas un défaut : un filtre à
 * N cherche en profondeur les N coups les plus prometteurs de la passe
 * superficielle, et le vrai N-ième peut se trouver ailleurs. GNU Backgammon a
 * la même propriété. Ce qui n'était pas acceptable, c'était de classer N coups
 * pris dans l'ORDRE DE GÉNÉRATION, sans les avoir regardés. */
const unfiltered = { ply: 2, filterTop: 0, filterInner: 1 };
const widths = [1, 3, 5, 40];
const runs = widths.map((max) => evaluator.rankPlays(POSITION, 0, 3, 1, { ...unfiltered, max }));
const reference = runs[runs.length - 1];
for (let i = 0; i < runs.length - 1; i++) {
  const got = runs[i];
  const same = got.every((c, k) =>
    c.resultId === reference[k].resultId && Math.abs(c.equity - reference[k].equity) < 1e-6);
  check(`sans filtre, max=${widths[i]} rend le même préfixe que la liste complète`, same,
        same ? "" : `${got[got.length - 1].resultId} au lieu de ${reference[got.length - 1].resultId}`);
}

/* 2. Le classement est décroissant en équité, DANS TOUTES les configurations.
 *
 * Second défaut trouvé : au-delà du filtre, les candidats gardaient une équité
 * d'une passe plus superficielle, et les deux échelles se mélangeaient dans une
 * même liste. Sur l'ouverture 3-1 à `filterTop = 3`, le 4e coup rendu était
 * meilleur que le 3e. `gnw_rank_plays` élargit désormais le filtre à ce que
 * l'appelant demande : les N rendus sont cherchés à la même profondeur. */
for (const [label, opts] of [["sans filtre", unfiltered],
                             ["niveau normal", level],
                             ["filtre étroit", { ply: 2, filterTop: 2, filterInner: 1 }]]) {
  const list = evaluator.rankPlays(POSITION, 0, 3, 1, { ...opts, max: 40 });
  const sorted = list.every((c, i) => i === 0 || list[i - 1].equity >= c.equity - 1e-9);
  check(`classement décroissant en équité — ${label}`, sorted);
}

/* 3. Le premier de `rankPlays` est celui de `bestPlay`. */
const best = evaluator.bestPlay(POSITION, 0, 3, 1, level);
check("rankPlays[0] == bestPlay", best.resultId === reference[0].resultId,
      `${reference[0].resultId} / ${best.resultId}`);

/* 4. Chaque candidat porte cinq probabilités exploitables. */
const probsOk = reference.every((c) =>
  Array.isArray(c.probs) && c.probs.length === 5
  && c.probs.every((p) => Number.isFinite(p) && p >= 0 && p <= 1));
check("cinq probabilités finies et dans [0,1] par candidat", probsOk);

/* 5. La décision de videau rend ses trois équités, et un verdict connu. */
const cube = evaluator.cubeDecision(POSITION, 0, { ...level, owner: 0 });
const VERDICTS = new Set(["no-double", "double-take", "double-pass", "too-good"]);
check("verdict de videau connu", VERDICTS.has(cube.action), cube.action);
check("équités de videau finies",
      Number.isFinite(cube.equityNoDouble) && Number.isFinite(cube.equityDouble));

console.log(failures === 0
  ? "\n✅ invariants de l'API tenus"
  : `\n❌ ${failures} invariant(s) rompu(s)`);
process.exit(failures === 0 ? 0 : 1);
