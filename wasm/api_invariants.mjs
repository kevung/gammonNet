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
import { Evaluator, MEASURED_EFFICIENCY } from "./gammonnet.mjs";

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

/* 5. LES PROBABILITÉS ET L'ÉQUITÉ DÉCRIVENT LE MÊME JOUEUR.
 *
 * Le second défaut silencieux de cette API, et le plus difficile à voir :
 * `GnCandidate.probs` décrit la position RÉSULTANTE — donc l'adversaire —
 * alors que `GnCandidate.equity` du même candidat est déjà retournée du côté
 * du joueur. `gnw_rank_plays` recopiait les deux tels quels. Sur l'ouverture
 * 3-1, un appelant lisait « 44,56 % de victoires » sous une équité de +0,166.
 *
 * AUCUN CONTRÔLE D'IMBRICATION NE PEUT LE VOIR : une distribution retournée
 * reste parfaitement imbriquée (c'est le contrôle 4 ci-dessus, qui passait des
 * deux côtés). Ce qui mord, c'est l'identité elle-même — l'équité cubeless
 * money EST une fonction des cinq probabilités, donc si les deux champs
 * parlent du même joueur, recalculer l'une depuis les autres doit reproduire
 * l'autre. Sous l'inversion, la reconstruction sort avec le signe opposé, et
 * aucune tolérance ne cache ça.
 *
 * À 0-PLY SEULEMENT, et c'est une limite honnête : au-delà, l'équité vient de
 * la recherche profonde tandis que les cinq probabilités restent celles de la
 * passe superficielle de classement (`gn_search.h`, `GnCandidate`). Le côté
 * est le bon à toute profondeur ; l'identité, non. */
const money = ([w, wg, wbg, lg, lbg]) => 2 * w + wg + wbg - lg - lbg - 1;

const zeroPly = evaluator.rankPlays(POSITION, 0, 3, 1,
                                    { ply: 0, filterTop: 0, filterInner: 0, max: 40 });
const identity = zeroPly.every((c) => Math.abs(money(c.probs) - c.equity) < 1e-6);
const worst = zeroPly.reduce((a, c) =>
  Math.max(a, Math.abs(money(c.probs) - c.equity)), 0);
check("0-ply : l'équité se recalcule depuis les cinq probabilités", identity,
      `max|Δ| = ${worst.toExponential(2)}`);

/* Et la lecture nue, celle qu'une interface affiche : faire le point de 5 à
 * l'ouverture 3-1 laisse celui qui joue AU-DESSUS de la moitié. C'est le
 * nombre que deux consommateurs ont lu à l'envers. */
check("le meilleur coup d'ouverture donne >50 % au joueur qui le joue",
      zeroPly[0].probs[0] > 0.5, `P(gain) = ${zeroPly[0].probs[0].toFixed(4)}`);

/* 5b. LE COUP QUI FINIT LA PARTIE.
 *
 * `shallow_fill` mettait les probabilités d'un résultat terminal à zéro — un
 * vecteur nul n'est pas « pas de réponse », c'est une distribution
 * parfaitement formée qui dit « partie perdue sèche ». Retournée pour
 * l'affichage, elle devenait « gain certain, aucun gammon » sur une sortie
 * qui GAGNE un gammon : équité +2, probabilités disant +1. C'est le dernier
 * coup de chaque partie, donc pas un cas de bord.
 *
 * Position : Blanc a un pion sur son point 2 et quatorze sortis, Noir a ses
 * quinze pions dans sa zone intérieure et aucun sorti. Le 3-2 n'a qu'un coup,
 * il sort le dernier pion, et c'est un gammon — jamais un backgammon, aucun
 * pion noir ne traînant chez Blanc. */
const FINISHER = "+L4PAAACAAAAAA";
const last = evaluator.rankPlays(FINISHER, 0, 3, 2, { ply: 0, max: 5 });
check("la sortie gagnante rend une seule ligne", last.length === 1, `${last.length}`);
if (last.length === 1) {
  const [w, wg, wbg, lg, lbg] = last[0].probs;
  check("gammon gagné : (1, 1, 0, 0, 0) et équité +2",
        w === 1 && wg === 1 && wbg === 0 && lg === 0 && lbg === 0
        && Math.abs(last[0].equity - 2) < 1e-6,
        `(${last[0].probs.join(", ")}) équité ${last[0].equity}`);
}

/* 6. La décision de videau rend ses trois équités, et un verdict connu.
 *
 * L'efficacité est FOURNIE, et c'est le fond du correctif : ce fichier
 * appelait `cubeDecision` avec `owner: 0` (centré) en laissant le défaut du
 * wrapper poser 0,566, l'efficacité du videau POSSÉDÉ. Il exerçait donc
 * exactement le défaut qu'il était censé surveiller, sans le voir passer. */
const CENTRED = 0;
const cube = evaluator.cubeDecision(POSITION, 0, {
  ...level, owner: CENTRED, efficiency: MEASURED_EFFICIENCY[CENTRED],
});
const VERDICTS = new Set(["no-double", "double-take", "double-pass", "too-good"]);
check("verdict de videau connu", VERDICTS.has(cube.action), cube.action);
check("équités de videau finies",
      Number.isFinite(cube.equityNoDouble) && Number.isFinite(cube.equityDouble));

/* 6b. L'EFFICACITÉ N'EST PLUS INVENTÉE.
 *
 * L'omettre doit refuser, bruyamment, plutôt que rendre une décision
 * plausible calculée avec le chiffre d'un autre état de possession. */
let refused = false;
try {
  evaluator.cubeDecision(POSITION, 0, { ...level, owner: CENTRED });
} catch {
  refused = true;
}
check("cubeDecision sans efficacité : refusé, jamais approximé", refused);

/* Et la valeur passée est bien celle qui sert : deux efficacités différentes
 * ne peuvent pas rendre la même équité de double. */
const other = evaluator.cubeDecision(POSITION, 0, {
  ...level, owner: CENTRED, efficiency: MEASURED_EFFICIENCY[1],
});
check("l'efficacité fournie est celle qui sert",
      cube.takePoint !== other.takePoint,
      `x=0,688 → point de prise ${cube.takePoint.toFixed(6)} ; ` +
      `x=0,566 → ${other.takePoint.toFixed(6)}`);

console.log(failures === 0
  ? "\n✅ invariants de l'API tenus"
  : `\n❌ ${failures} invariant(s) rompu(s)`);
process.exit(failures === 0 ? 0 : 1);
