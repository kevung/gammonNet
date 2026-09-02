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
import { createHash } from "node:crypto";
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

/* 5c. L'ORDRE DES EX ÆQUO (T88).
 *
 * `compare_candidates` ne comparait que l'équité et `qsort` n'est pas stable :
 * l'ordre de deux candidats de MÊME équité venait de la libc. Ici, c'est celle
 * d'Emscripten (musl, smoothsort), et elle N'EST PAS stable — mesuré sur des
 * éléments de 72 octets, comme `GnCandidate` : 13 / 64 / 297 / 1 184 ex æquo
 * permutés à n = 32 / 128 / 512 / 2 048, là où la glibc n'en permute aucun.
 * C'est donc précisément ici, dans l'artefact servi au navigateur, que le
 * défaut sortait — et la parité ne pouvait pas le voir, puisqu'elle compare
 * des équités à 1e-6 et qu'une permutation d'ex æquo les laisse identiques.
 *
 * La position ci-dessous est du corpus T12 : sur le 1-1, ses NEUF coups
 * légaux gagnent tous immédiatement et valent tous exactement -1. Le
 * classement n'est donc QUE l'ordre de départage, et le repère est l'ordre
 * rendu par le natif (`make tie-census PLY=0 TIE_DUMP=1`), qui est l'ordre de
 * génération de `gn_legal_plays` — la règle du portage Go. */
const TIED = "AQAAfB4AAAAAAA";
const TIED_ORDER = [
  "3wMAAAQAAAAAAA", "vwUAAAQAAAAAAA", "7wIAAAIAAAAAAA",
  "fwYAAAQAAAAAAA", "XwMAAAIAAAAAAA", "twEAAAEAAAAAAA",
  "zwEAAAEAAAAAAA", "6wAAgAAAAAAAAA", "eQAAQAAAAAAAAA",
];
const tied = evaluator.rankPlays(TIED, 1, 1, 1, { ply: 0, max: 40 });
check("neuf coups d'équité BIT-À-BIT égale", 
      tied.length === TIED_ORDER.length
      && tied.every((c) => c.equity === tied[0].equity),
      `${tied.length} coups, équités ${new Set(tied.map((c) => c.equity)).size} distinctes`);
check("ex æquo : le module rend l'ORDRE du natif, pas celui de sa libc",
      tied.every((c, i) => c.resultId === TIED_ORDER[i]),
      tied.map((c) => c.resultId).join(" "));

/* 5d. LE GROS GROUPE, celui qui discrimine vraiment.
 *
 * Le cas ci-dessus documente la règle mais ne l'éprouve pas : le smoothsort de
 * musl est stable en pratique sur neuf éléments — vérifié, avant comme après
 * le correctif il rend le même ordre. Il faut un GROUPE, et le corpus T12 en
 * donne un : 230 des 231 coups légaux de cette position sur le 1-1 valent
 * exactement la même chose.
 *
 * MESURÉ sur ce cas précis : avant le tri stable, le module rendait 4 places
 * sur 231 différentes du natif ; après, zéro.
 *
 * L'élagage est éteint le temps de la mesure, et il le faut : à k=12 il ne
 * reste que douze survivants, taille à laquelle la libc ne permute plus rien —
 * l'invariant passerait sans rien prouver. Il est rallumé juste après, les
 * contrôles suivants en dépendant.
 *
 * L'ordre attendu est celui du natif, résumé par une empreinte — 231
 * identifiants dans ce fichier le rendraient illisible pour rien. Il se
 * régénère par `make tie-census PLY=0 TIE_DUMP=1`, ligne
 * `DwAA4FGYYQsAAA 1 1 1`. */
const TIED_BIG = "DwAA4FGYYQsAAA";
const TIED_BIG_DIGEST =
  "71e97e36c59c1ae30870be61b136a5489164042b56f60652e8b9b0a89858a49c";
evaluator.loadPrune(null, 0);
const big = evaluator.rankPlays(TIED_BIG, 1, 1, 1, { ply: 0, max: 2048 });
evaluator.loadPrune(new Uint8Array(readFileSync(PRUNE)), 12);
const bigTies = big.filter((c, i) => i > 0 && c.equity === big[i - 1].equity).length;
check("un groupe de 230 ex æquo, assez gros pour que la libc les permute",
      big.length === 231 && bigTies === 229,
      `${big.length} coups, ${bigTies} paires égales`);
const digest = createHash("sha256")
  .update(big.map((c) => c.resultId).join(" ")).digest("hex");
check("l'ordre du gros groupe est celui du natif, au caractère près",
      digest === TIED_BIG_DIGEST, digest.slice(0, 16));

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
/* 7. LE CODEC, ET LE PIÈGE QU'IL PORTE (T86).
 *
 * `wasm/codec_parity.mjs` établit l'égalité exacte avec le C sur le corpus
 * entier ; ce qui est vérifié ICI est ce qu'un appelant peut se tromper à
 * faire avec, et c'est une seule chose : LE POSITION ID NE PORTE PAS LE
 * JOUEUR AU TRAIT. Le `resultId` que rend `bestPlay` décrit la position
 * d'APRÈS le coup, donc l'autre camp est au trait ; le décoder avec le `turn`
 * de l'aller rend le plateau du mauvais côté — sans erreur, sans signe, et
 * avec des comptes de pions parfaitement plausibles. Le consommateur qui a
 * écrit ce codec de son côté a documenté ce piège pour l'avoir rencontré. */
const opening = evaluator.positionFromId(POSITION, 0);
check("le codec fait l'aller-retour", evaluator.positionId(opening) === POSITION,
      evaluator.positionId(opening));
check("l'ouverture compte 167 pips des deux côtés",
      evaluator.pipCount(opening, 0) === 167 && evaluator.pipCount(opening, 1) === 167,
      `${evaluator.pipCount(opening, 0)} / ${evaluator.pipCount(opening, 1)}`);

/* Le 3-1 déplace quatre pips. Décodé avec `1 - turn` — le trait a changé —
 * Blanc, qui vient de jouer, en a 163 et Noir toujours 167. Décodé avec le
 * `turn` de l'aller, les deux camps sont ÉCHANGÉS : on lit 167 pour Blanc,
 * c'est-à-dire le nombre d'avant le coup, ce qui est exactement ce qui rend
 * l'erreur invisible. */
const after = evaluator.positionFromId(best.resultId, 1);
check("resultId décodé du bon côté : Blanc a joué 4 pips, 167 → 163",
      evaluator.pipCount(after, 0) === 163 && evaluator.pipCount(after, 1) === 167,
      `${evaluator.pipCount(after, 0)} / ${evaluator.pipCount(after, 1)}`);
const wrongSide = evaluator.positionFromId(best.resultId, 0);
check("décodé du mauvais côté : 167 pour Blanc, aucun signe d'erreur",
      evaluator.pipCount(wrongSide, 0) === 167
      && JSON.stringify(wrongSide.points) !== JSON.stringify(after.points),
      `${evaluator.pipCount(wrongSide, 0)}`);

/* Et le XGID de l'ouverture, l'ancrage même du format (`gn_position_id.h`). */
check("le XGID de l'ouverture est l'identifiant canonique",
      evaluator.xgid(opening).startsWith("XGID=-b----E-C---eE---c-e----B-"),
      evaluator.xgid(opening));

/* 8. LE COUP EST NOMMÉ, ET C'EST LE COUP QUE LA RECHERCHE A CHOISI (T86).
 *
 * `resultId` est un PLATEAU : il ne dit pas quel pion est allé où, et deux
 * appariements peuvent le produire. La notation vient de `GnPlay.moves`, la
 * liste ordonnée que la recherche a réellement retenue — ce n'est pas une
 * présentation ajoutée, c'est une partie de la réponse qu'on cessait de
 * rendre. Elle est la MÊME que celle du champ `move` de `/v1/eval` : le C
 * l'écrit une fois (`src/gn_notation.c`) et les deux surfaces l'appellent. */
check("le meilleur coup d'ouverture 3-1 se nomme", best.notation === "6/5 8/5",
      `« ${best.notation} »`);
check("chaque candidat porte sa notation",
      reference.every((c) => typeof c.notation === "string" && c.notation.length > 0),
      `${reference.length} candidats`);
check("rankPlays[0] et bestPlay nomment le même coup",
      reference[0].notation === best.notation,
      `« ${reference[0].notation} » / « ${best.notation} »`);

/* Un double regroupe ses sous-coups identiques : `13/8(2)` et non
 * `13/8 13/8`. C'est la forme que la notation ajoute à une simple paire. */
const heavy = evaluator.rankPlays(POSITION, 0, 5, 5, { ply: 0, max: 5 });
check("les sous-coups répétés sont regroupés",
      heavy.some((c) => /\(\d\)/.test(c.notation)),
      heavy.map((c) => c.notation).join(" | "));

console.log(failures === 0
  ? "\n✅ invariants de l'API tenus"
  : `\n❌ ${failures} invariant(s) rompu(s)`);
process.exit(failures === 0 ? 0 : 1);
