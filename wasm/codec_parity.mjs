/*
 * La PARITÉ DU CODEC : le module WebAssembly contre le C natif, sur le corpus
 * T12 entier.
 *
 * POURQUOI CONTRE LE C, ET PAS CONTRE CE QU'IL REMPLACE. Le codec exporté ici
 * remplace des écritures faites à côté du moteur, déduites puis validées
 * contre ce même module. Vérifier l'un contre l'autre serait donc circulaire.
 * La
 * référence est le C — croisé, lui, contre gnubg-nn sur 10 000 positions
 * (`docs/mesures/`, `tests/test_codec.py`) — et le critère est l'égalité
 * EXACTE : un identifiant est une chaîne, il n'y a pas de tolérance à lui
 * accorder.
 *
 * Le repère est produit par `tools/dump_codec_reference.py`, qui contrôle déjà
 * l'aller-retour côté natif avant d'écrire quoi que ce soit.
 *
 * SPDX-License-Identifier: MIT
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { Evaluator } from "./gammonnet.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const REFERENCE = join(ROOT, "build", "codec_reference.json");

const BUILDS = [
  ["scalaire", join(ROOT, "build", "wasm", "gammonnet.mjs")],
  ["SIMD", join(ROOT, "build", "wasm", "gammonnet-simd.mjs")],
];

const entries = JSON.parse(readFileSync(REFERENCE, "utf-8"));
console.log(`repère : ${entries.length} positions du corpus T12, égalité exacte`);

const boardOf = (ints) => ({
  points: ints.slice(0, 24),
  bar: [ints[24], ints[25]],
  off: [ints[26], ints[27]],
  turn: ints[28],
});

let failures = 0;

for (const [label, modulePath] of BUILDS) {
  const factory = (await import(modulePath)).default;
  /* Aucun modèle n'est chargé : le codec ne dépend pas du réseau, et exiger un
   * modèle pour encoder une position ferait croire l'inverse. */
  const evaluator = new Evaluator(await factory());

  const wrong = { encode: 0, decode: 0, xgid: 0, xgidBack: 0, pips: 0 };
  let firstMismatch = null;

  for (const e of entries) {
    const board = boardOf(e.board);

    /* 1. ENCODER : le plateau redonne l'identifiant du corpus. */
    const id = evaluator.positionId(board);
    if (id !== e.position_id) {
      wrong.encode++;
      firstMismatch ??= `${e.id} : encode ${id} au lieu de ${e.position_id}`;
    }

    /* 2. DÉCODER : l'identifiant redonne le plateau que le C rend. */
    const back = evaluator.positionFromId(e.position_id, e.turn);
    const sameBoard = JSON.stringify([...back.points, ...back.bar, ...back.off, back.turn])
      === JSON.stringify(e.board);
    if (!sameBoard) {
      wrong.decode++;
      firstMismatch ??= `${e.id} : décodage différent du natif`;
    }

    /* 3. XGID, et son aller-retour. Son degré de vérification n'est pas celui
     * du Position ID (`gn_position_id.h` : ancré sur l'ouverture canonique et
     * l'aller-retour, pas oraclé) — raison de plus pour que les deux cibles en
     * disent exactement la même chose. */
    const xg = evaluator.xgid(board);
    if (xg !== e.xgid) {
      wrong.xgid++;
      firstMismatch ??= `${e.id} : xgid ${xg} au lieu de ${e.xgid}`;
    }
    const fromXgid = evaluator.positionFromXgid(e.xgid);
    const sameFromXgid =
      JSON.stringify(fromXgid.board.points) === JSON.stringify(e.board.slice(0, 24))
      && fromXgid.board.bar[0] === e.board[24] && fromXgid.board.bar[1] === e.board[25]
      && fromXgid.board.off[0] === e.board[26] && fromXgid.board.off[1] === e.board[27];
    if (!sameFromXgid) {
      wrong.xgidBack++;
      firstMismatch ??= `${e.id} : le XGID ne redonne pas le plateau`;
    }

    /* 4. LA SENTINELLE. `BRIEF.md` §6 : le compte de pips est le contrôle le
     * moins cher qui existe au passage d'une frontière de format. */
    if (evaluator.pipCount(board, 0) !== e.pips[0]
        || evaluator.pipCount(board, 1) !== e.pips[1]) {
      wrong.pips++;
      firstMismatch ??= `${e.id} : compte de pips différent du natif`;
    }
  }

  const total = Object.values(wrong).reduce((a, b) => a + b, 0);
  if (total > 0) failures++;
  console.log(`${total === 0 ? "✅" : "❌"} ${label.padEnd(9)} `
    + `encode ${wrong.encode} · décode ${wrong.decode} · xgid ${wrong.xgid} `
    + `· xgid⁻¹ ${wrong.xgidBack} · pips ${wrong.pips}`
    + (firstMismatch ? `\n   premier écart : ${firstMismatch}` : ""));
}

/* 5. CE QUI EST REFUSÉ L'EST VRAIMENT.
 *
 * Un plateau impossible ne doit pas produire un identifiant plausible : c'est
 * le mode de défaillance de CLAUDE.md §2 appliqué au codec, et il est
 * silencieux par nature. Seize pions d'une couleur, ou un identifiant tronqué.
 */
{
  const factory = (await import(BUILDS[1][1])).default;
  const evaluator = new Evaluator(await factory());
  const impossible = {
    points: [16, ...new Array(23).fill(0)],
    bar: [0, 0], off: [0, 0], turn: 0,
  };
  let refused = false;
  try { evaluator.positionId(impossible); } catch { refused = true; }
  console.log(`${refused ? "✅" : "❌"} un plateau impossible est REFUSÉ, pas encodé`);
  if (!refused) failures++;

  let refusedId = false;
  try { evaluator.positionFromId("pas-un-identifiant", 0); } catch { refusedId = true; }
  console.log(`${refusedId ? "✅" : "❌"} un identifiant illisible est REFUSÉ`);
  if (!refusedId) failures++;
}

console.log(failures === 0
  ? "\n✅ parité du codec WebAssembly ↔ natif établie sur les deux builds"
  : `\n❌ ${failures} vérification(s) en échec`);
process.exit(failures === 0 ? 0 : 1);
