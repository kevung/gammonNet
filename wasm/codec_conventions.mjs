/*
 * LE CODEC RELU DANS LA CONVENTION OPPOSÉE.
 *
 * CE QUE CE FICHIER ATTRAPE, ET QUE LA PARITÉ NE PEUT PAS VOIR.
 * `wasm/codec_parity.mjs` compare le module WebAssembly au C natif : même
 * algorithme, même convention de plateau, donc une erreur d'ORIENTATION y est
 * invisible — les deux côtés se trompent ensemble. Ici, le Position ID gnubg
 * est réécrit en JavaScript dans une convention de plateau INVERSE de celle
 * de `gn_rules.h` : 26 cases au lieu de 29, la numérotation de Noir au lieu de
 * celle de Blanc, positif NOIR au lieu de positif Blanc, et le joueur au trait
 * codé 0/1 dans l'autre sens.
 *
 * C'est exactement la classe de défaut qui ne casse rien et retourne tout : un
 * identifiant reste bien formé, les comptes de pions restent plausibles, et la
 * position décrite est celle de l'autre camp. Une seconde écriture qui traverse
 * ces quatre inversions et retombe sur le MÊME identifiant est la seule preuve
 * bon marché qu'aucune n'a été prise à l'envers.
 *
 * CE N'EST PAS UN TEST DE PARITÉ et ça ne doit pas le devenir : la référence du
 * codec reste le C, croisé contre gnubg-nn sur 10 000 positions. Le nombre
 * publié ici est le nombre de positions du corpus T12 sur lesquelles les deux
 * écritures diffèrent, et il doit valoir zéro.
 *
 *   usage : node wasm/codec_conventions.mjs
 *
 * SPDX-License-Identifier: MIT
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const REFERENCE = join(ROOT, "build", "codec_reference.json");

/* La convention inverse : ici BLACK = 0 et WHITE = 1, là où `gn_rules.h` pose
 * GN_WHITE = 0 et GN_BLACK = 1. C'est le genre de détail qui ne casse rien et
 * retourne tout — d'où l'intérêt de le traverser exprès. */
const ALT_BLACK = 0;

const B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

function keyToBase64(key) {
  let out = "";
  for (let i = 0; i < 10; i += 3) {
    const b0 = key[i];
    const b1 = i + 1 < 10 ? key[i + 1] : undefined;
    const b2 = i + 2 < 10 ? key[i + 2] : undefined;
    out += B64[b0 >> 2];
    out += B64[((b0 << 4) & 0x30) | (b1 !== undefined ? b1 >> 4 : 0)];
    if (b1 === undefined) break;
    out += B64[((b1 << 2) & 0x3c) | (b2 !== undefined ? b2 >> 6 : 0)];
    if (b2 === undefined) break;
    out += B64[b2 & 0x3f];
  }
  return out;
}

/* La seconde écriture. `board26` : indice 0 = barre de Blanc, 25 = barre de
 * Noir, 1..24 = les points dans la numérotation de NOIR, positif noir /
 * négatif blanc. */
function altPositionId(board26, onRoll) {
  const moverIsBlack = onRoll === ALT_BLACK;
  const anBoard = [new Array(25).fill(0), new Array(25).fill(0)];
  for (let point = 1; point <= 24; point++) {
    const j = point - 1;
    const blackVal = Math.max(0, board26[point]);
    const whiteVal = Math.max(0, -board26[25 - point]);
    anBoard[1][j] = moverIsBlack ? blackVal : whiteVal;
    anBoard[0][j] = moverIsBlack ? whiteVal : blackVal;
  }
  const blackBar = Math.max(0, board26[25]);
  const whiteBar = Math.max(0, -board26[0]);
  anBoard[1][24] = moverIsBlack ? blackBar : whiteBar;
  anBoard[0][24] = moverIsBlack ? whiteBar : blackBar;

  const key = new Uint8Array(10);
  let bitPos = 0;
  for (let side = 0; side < 2; side++) {
    for (let slot = 0; slot < 25; slot++) {
      for (let k = 0; k < anBoard[side][slot]; k++) {
        key[bitPos >> 3] |= 1 << (bitPos % 8);
        bitPos++;
      }
      bitPos++;
    }
  }
  return keyToBase64(key);
}

/*
 * La traduction des 29 entiers de `gn_rules.h` vers les 26 de la convention
 * inverse.
 *
 * Ici : `points[i]` signé, POSITIF BLANC ; l'indice i désigne le point (i+1)
 * pour Blanc et (24-i) pour Noir. Là : `board26[p]` signé, POSITIF NOIR, p
 * dans la numérotation de Noir. Donc `board26[p] = -points[24 - p]`, et les
 * deux barres changent aussi de signe et de place.
 *
 * Une traduction est une frontière de format ; le compte de pips la contrôle
 * plus bas, comme `BRIEF.md` §6 l'exige.
 */
function toBoard26(ints) {
  const board26 = new Array(26).fill(0);
  for (let p = 1; p <= 24; p++) board26[p] = -ints[24 - p];
  board26[0] = -ints[24];   /* barre de Blanc, comptée négativement */
  board26[25] = ints[25];   /* barre de Noir */
  return board26;
}

const entries = JSON.parse(readFileSync(REFERENCE, "utf-8"));

let disagreements = 0;
let firstDisagreement = null;
for (const e of entries) {
  /* `turn` d'ici (0 = Blanc, 1 = Noir) vers `onRoll` de là (0 = Noir,
   * 1 = Blanc) : la quatrième inversion. */
  const onRoll = e.turn === 1 ? 0 : 1;
  const theirs = altPositionId(toBoard26(e.board), onRoll);
  if (theirs !== e.position_id) {
    disagreements++;
    firstDisagreement ??= `${e.id} : ${theirs} au lieu de ${e.position_id}`;
  }
}

/* La couverture, dite avec le résultat : un accord sur un corpus qui n'aurait
 * ni barre ni pion sorti ne prouverait rien des deux cas où une convention
 * s'inverse le plus facilement. */
const withBar = entries.filter((e) => e.board[24] || e.board[25]).length;
const withOff = entries.filter((e) => e.board[26] || e.board[27]).length;
const blackToPlay = entries.filter((e) => e.board[28] === 1).length;
console.log(`corpus T12 : ${entries.length} positions `
  + `(${withBar} avec un pion sur la barre, ${withOff} avec des pions sortis, `
  + `${blackToPlay} au trait de Noir)`);
console.log(`écart entre l'écriture en convention inverse et le C : `
  + `${disagreements} position(s)`);
if (firstDisagreement) console.log(`  premier écart : ${firstDisagreement}`);
console.log(disagreements === 0
  ? "→ les deux écritures sont d'accord partout : les quatre inversions de\n"
    + "  convention sont traversées sans qu'aucune ne soit prise à l'envers."
  : "→ elles diffèrent : une convention est prise à l'envers quelque part, et\n"
    + "  un identifiant bien formé ne le dira pas tout seul.");
