#!/usr/bin/env python3
"""T50 — assembler l'artefact publiable, et refuser de le faire s'il manque une pièce.

## Ce que « publiable » exige, et pourquoi chaque pièce est là

`PLAN.md` fixe cinq conditions, et ce script les traite comme des conditions, pas
comme des intentions : il **refuse** de produire un répertoire incomplet plutôt
que d'en produire un qui aurait l'air fini.

| Condition | Ce que le script en fait |
|---|---|
| poids versionnés, `.wasm`, somme de contrôle | nomme, copie, hache — et signale l'absence du `.wasm` |
| rejeu du corpus de non-régression T12 sans écart | **vérifié avant d'écrire quoi que ce soit** |
| `THIRD-PARTY.md` à jour, notice MIT dans l'artefact | la notice est écrite DANS le répertoire |
| nomenclature du `BRIEF` §8 | le nom du réseau garde la paternité de son auteur |
| notes de version citant protocole, volume, IC | reprises des fiches, jamais réécrites de mémoire |

## La nomenclature, qui n'est pas un détail

`BRIEF.md` §8 : **un réseau ne devient un autre réseau que si ses poids changent.**
Ni le couplage à une table de fin de partie, ni la compilation en WebAssembly, ni
une conversion de format n'en produisent un nouveau. Le fichier de poids porte
donc `strehl-prob5-512-512-256-128` — la paternité d'Alexander Strehl — et c'est
la **configuration** qui s'appelle gammonNet. Rebaptiser les poids reviendrait à
s'attribuer ce qu'on n'a pas produit, et coûterait la provenance traçable que le
critère de succès exige.

La variante float16 est « le même réseau, quantifié » : même nom, suffixe de
format. Pas un réseau nouveau.

Usage :
    python tools/package_artifact.py --version v1
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

#: Le nom du réseau garde la paternité de son auteur (BRIEF §8). Le nôtre est
#: celui de la CONFIGURATION, pas des poids.
NETWORKS = {
    "strehl-prob5-512-512-256-128": ROOT / "models" / "cubeless_prob5_512_512_256_128.bin",
    "strehl-prune-32": ROOT / "models" / "prune_32.bin",
}

WASM = [
    ROOT / "build" / "wasm" / "gammonnet.mjs",
    ROOT / "build" / "wasm" / "gammonnet.wasm",
    ROOT / "build" / "wasm" / "gammonnet-simd.mjs",
    ROOT / "build" / "wasm" / "gammonnet-simd.wasm",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_regression() -> None:
    """Le corpus T12, rejoué. Une version qui le déplace n'est pas publiable."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(ROOT / "tests" / "test_regression.py"),
         "-q"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            "REFUSÉ : le corpus de non-régression T12 ne passe pas.\n"
            + result.stdout[-2000:])


def notice() -> str:
    return """gammonNet — évaluateur de positions de backgammon

Cet artefact est une copie distribuée. Les notices ci-dessous voyagent donc avec
lui, comme la licence MIT l'exige pour « all copies or substantial portions of
the Software ». L'inventaire complet, avec ce qui est effectivement utilisé de
chaque brique, est dans THIRD-PARTY.md.

── Poids du réseau et moteur d'inférence ──────────────────────────────────
backgammon-ai-engine — Copyright (c) 2026 alexstrehl — licence MIT
https://github.com/alexstrehl/backgammon-ai-engine

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in all
  copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
  SOFTWARE.

── Table d'équité de match ────────────────────────────────────────────────
Kazaross-XG2 — œuvre de Neil Kazaross, avec attribution.

── Le reste ───────────────────────────────────────────────────────────────
Codec, recherche, équité de match dans la recherche, videau, portage
WebAssembly : écrits dans ce dépôt, licence MIT.
"""


def release_notes(version: str, date: str, files: list[tuple[str, str, int]]) -> str:
    listing = "\n".join(f"| `{name}` | {size:,} | `{digest}` |".replace(",", " ")
                        for name, digest, size in files)
    return f"""# gammonNet {version} — {date}

## La force, telle qu'elle est mesurée

**Une version publiée sans mesure n'est pas publiable** (`PLAN.md`, T50). Voici
la mesure, avec son protocole, son volume et son intervalle de confiance.

**Configuration mesurée** : réseau + recherche 2-ply filtrée `(0,1,3)` + équité
de match Kazaross-XG2 + tables exactes de fin de partie + videau 2-ply.
**Adversaire** : GNU Backgammon au même réglage — 2-ply, filtre `(0,1,3)`,
videau 2-ply, `prune=1`.

| | volume | mesure | IC 95 % |
|---|---|---|---|
| money cubeful, ppg | 50 000 paires | **−0,0119** | [−0,0310 ; +0,0074] |
| match 7 points, MWC | 50 000 paires | **50,42 %** | [50,16 ; 50,69] |

Dés communs, bootstrap sur les paires dupliquées. Graine 20260810.
Fiche : `docs/mesures/2026-08-26-T35-verdict.md`.

**Le verdict, dans les termes exacts où il a été rendu** : *niveau équivalent à
GNU Backgammon en 2-ply, confirmé*. « Supérieur » n'est **pas** établi.
**eXtreme Gammon n'a pas été mesuré**, et cette moitié de l'objectif ne se
déduit pas de l'autre.

## Ce que l'analyse d'un vrai match montre

139 décisions d'un match de 7 points, au score et au videau réels : **86,3 %
d'accord** sur le meilleur coup avec GNU Backgammon. Les 19 désaccords coûtent,
selon l'arbitre gnubg, une médiane de **+0,0048** d'équité et un maximum de
**+0,0195** — **aucun au-dessus de 0,05**. Les deux moteurs divergent là où
plusieurs coups se valent, pas là où une partie se décide.
Fiche : `docs/mesures/2026-08-27-T3C-analyse-de-match.md`.

## Ce que cette version contient

| fichier | octets | sha256 |
|---|---|---|
{listing}

**Les deux formats de poids sont le MÊME réseau.** `.bin` est en float32,
`.bin16` en float16 — moitié moins lourd à télécharger, pour 0,015 % des
décisions déplacées et ~1e-9 d'équité (`docs/mesures/2026-08-04-quantification.md`).
Une quantification ne produit pas un réseau nouveau (`BRIEF.md` §8).

**Le réseau d'élagage** accompagne le réseau principal : il trie les coups
candidats pour que le grand réseau n'en note qu'une poignée. À `k=12` — le
défaut — il rend ×3,9 pour une perte d'équité dans le bruit
(`docs/mesures/2026-08-27-T3D-elagage-par-defaut.md`).

## Nomenclature

Le nom des fichiers de poids conserve la paternité d'**Alexander Strehl**
(`strehl-prob5-...`). **gammonNet** est le nom de la *configuration* — réseau,
recherche, équité de match, fins de partie — pas celui des poids. `BRIEF.md` §8.

## Ce que cette version ne promet pas

- **Aucun budget de temps dans un navigateur.** Les gains de vitesse récents
  viennent du remplissage des lots, et le lot rend ×2,21 dans un navigateur
  contre ×8,5 en natif : les chiffres natifs ne s'y transportent pas, et ils
  n'ont pas encore été remesurés là-bas
  (`docs/mesures/2026-08-27-T21-navigateur-a-refaire.md`).
- **Aucun PR.** La métrique n'a jamais tourné.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="v1")
    parser.add_argument("--date", default=None)
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    parser.add_argument("--skip-regression", action="store_true",
                        help="pour un essai ; une publication ne le fait jamais")
    args = parser.parse_args()

    date = args.date or dt.date.today().isoformat()

    for name, source in NETWORKS.items():
        if not source.exists():
            raise SystemExit(f"REFUSÉ : {source} absent")

    if not args.skip_regression:
        print("1. Corpus de non-régression T12")
        check_regression()
        print("   passé")
    else:
        print("1. Corpus de non-régression T12 — SAUTÉ (essai)")

    target = args.out / f"gammonnet-{args.version}"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    print(f"\n2. Poids → {target}")
    from pack_fp16 import pack

    files: list[tuple[str, str, int]] = []
    for name, source in NETWORKS.items():
        stem = f"{name}_{args.version}_{date}"
        wide = target / f"{stem}.bin"
        shutil.copy2(source, wide)
        half = target / f"{stem}.bin16"
        pack(wide, half)
        for path in (wide, half):
            files.append((path.name, sha256(path), path.stat().st_size))
            print(f"   {path.name}  {path.stat().st_size} octets")

    print("\n3. WebAssembly")
    missing = [p.name for p in WASM if not p.exists()]
    for path in WASM:
        if path.exists():
            shutil.copy2(path, target / path.name)
            files.append((path.name, sha256(path), path.stat().st_size))
            print(f"   {path.name}")
    if missing:
        print(f"   ABSENT : {', '.join(missing)}")
        print("   → `make wasm` sur une machine où Emscripten est installé, "
              "puis relancer.")

    (target / "NOTICE").write_text(notice(), encoding="utf-8")
    (target / "RELEASE.md").write_text(
        release_notes(args.version, date, files), encoding="utf-8")
    shutil.copy2(ROOT / "THIRD-PARTY.md", target / "THIRD-PARTY.md")
    shutil.copy2(ROOT / "LICENSE", target / "LICENSE")

    sums = "\n".join(f"{digest}  {name}" for name, digest, _ in files) + "\n"
    (target / "SHA256SUMS").write_text(sums, encoding="utf-8")

    print(f"\n4. NOTICE, RELEASE.md, THIRD-PARTY.md, LICENSE, SHA256SUMS")
    print(f"\n→ {target}")
    if missing:
        print("\nINCOMPLET : le WebAssembly manque. L'artefact n'est pas publiable "
              "en l'état.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
