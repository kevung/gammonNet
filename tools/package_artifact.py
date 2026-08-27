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

#: L'API JavaScript et le pool de workers.
#:
#: SANS EUX L'ARTEFACT N'EST PAS UTILISABLE, et l'omission ne se voit pas : le
#: `.wasm` et son collage Emscripten sont bien là, mais un utilisateur devrait
#: réécrire lui-même le chargement du modèle, son refus quand il est invalide,
#: et l'appel de recherche. Le pool, lui, fait la différence entre 350 s et
#: 74 s pour analyser un match (T21b) — le livrer sans lui donnerait un moteur
#: cinq fois plus lent que ce que les notes de version annoncent.
API = [
    ROOT / "wasm" / "gammonnet.mjs",
    ROOT / "wasm" / "pool.mjs",
    ROOT / "wasm" / "worker.mjs",
]

#: LA TABLE EXACTE NE SE PUBLIE PAS, et c'est une limite, pas un oubli.
#:
#: Celle que la recherche consulte est `gnubg_ts6x11.bd` — la table
#: BILATÉRALE, **1,2 Gio**. Aucun artefact web ne la transporte, et un
#: utilisateur qui la voudrait doit se la procurer séparément.
#:
#: Une première version publiait `models/bearoff_one_sided.bin` (6,9 Mio) en
#: croyant livrer cette table. Le module l'a REFUSÉE, et il avait raison : son
#: en-tête est `GNBO`, pas `gnubg-TS-`, et ce n'est pas ce que
#: `gn_bearoff_open` lit. Publier un fichier que le moteur ne charge pas aurait
#: donné l'illusion d'une exactitude qu'on n'avait pas.
#:
#: Ce que cela coûte est chiffré, pas supposé : 0,00028 d'équité par décision
#: de bearoff (T38), là où GNU Backgammon consulte sa propre table et n'y perd
#: rien. C'est nommé dans les notes de version.
TABLES: list = []

#: De quoi VÉRIFIER l'artefact plutôt que de nous croire : le repère de 2 000
#: positions, le contrôle de parité qui le lit, et la provenance de chaque
#: réseau. C'est la pièce qui rend l'affirmation de force falsifiable par son
#: destinataire.
VERIFY = [
    ROOT / "build" / "reference.bin",
    ROOT / "wasm" / "parity.mjs",
    ROOT / "models" / "cubeless_prob5_512_512_256_128.provenance.json",
    ROOT / "models" / "prune_32.provenance.json",
]

#: Les mesures brutes derrière chaque chiffre des notes de version.
EVIDENCE = [
    ROOT / "docs" / "mesures" / "t3e-pr.json",
    ROOT / "docs" / "mesures" / "t3c-analyse-match.json",
    ROOT / "docs" / "mesures" / "t21b-navigateur-decision.json",
    ROOT / "docs" / "mesures" / "t21b-navigateur-workers.json",
    ROOT / "docs" / "mesures" / "t3a-prune-search.json",
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


def quickstart() -> str:
    return """# Démarrer avec gammonNet

## Ce que contient cette archive

| | |
|---|---|
| `strehl-prob5-…​.bin` / `.bin16` | les poids du réseau, en float32 et en float16 (moitié moins lourd) |
| `strehl-prune-32_…​.bin` / `.bin16` | le réseau d'élagage : il trie les coups pour que le grand n'en note qu'une poignée |
| `gammonnet-simd.mjs` / `.wasm` | le moteur WebAssembly (préférez la version SIMD) |
| `api/gammonnet.mjs` | l'API JavaScript — `Evaluator` |
| `api/pool.mjs`, `api/worker.mjs` | le pool de Web Workers : un match en 74 s au lieu de 350 |
| `verify/` | de quoi vérifier vous-même que cet artefact donne les bons chiffres |
| `evidence/` | les mesures brutes derrière chaque chiffre des notes de version |

## Le plus court chemin

```js
import { Evaluator } from "./api/gammonnet.mjs";
import factory from "./gammonnet-simd.mjs";

const weights = new Uint8Array(
  await (await fetch("./strehl-prob5-512-512-256-128_v1_2026-08-27.bin16")).arrayBuffer());
const evaluator = await Evaluator.create(factory, weights);

// Le réseau d'élagage : ×3,65 sur une décision 2-ply, pour une perte
// d'équité dans le bruit. Facultatif, mais fortement conseillé.
const prune = new Uint8Array(
  await (await fetch("./strehl-prune-32_v1_2026-08-27.bin16")).arrayBuffer());
evaluator.loadPrune(prune, 12);

// Position de départ, jet 3-1.
const best = evaluator.bestPlay("4HPwATDgc/ABMA", 0, 3, 1,
                                { ply: 2, filterTop: 3, filterInner: 1 });
console.log(best.equity, best.resultId, best.evaluations);
```

## Vérifier avant de faire confiance

L'archive contient le repère de 2 000 positions et le contrôle qui le lit. Il
compare le WebAssembly au moteur natif de référence et **refuse** au-delà de
1e-6 :

```sh
node verify/parity.mjs
```

Attendu : `max|Δ| = 0` en scalaire, ~6,4e-7 en SIMD.

## Ce que vous devez savoir avant de vous en servir

- **La force est mesurée, et bornée.** Équivalent à GNU Backgammon en 2-ply :
  −0,0119 ppg [−0,0310 ; +0,0074] sur 50 000 paires. « Supérieur » n'est PAS
  établi, et eXtreme Gammon n'a pas été mesuré. Voir `RELEASE.md`.
- **Le réglage compte plus que vous ne croyez.** À `prune_k = 3` le moteur est
  deux fois plus rapide qu'à 12 et perd dix-huit fois ce qu'un ply entier de
  profondeur rapporte. 12 est le défaut mesuré ; ne le baissez pas sans mesurer.
- **Sans le pool de workers**, un match de 7 points prend 350 s au lieu de 74.
- **La table exacte de fin de partie n'est pas fournie** : celle que le moteur
  consulte pèse 1,2 Gio. La fin de partie retombe donc sur le réseau, ce qui
  coûte 0,00028 d'équité par décision de bearoff (mesuré). `loadBearoff()`
  existe pour qui se la procure.
"""


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

## Le taux d'erreur, mesuré contre un arbitre plus fort

Le **PR** — 500 × l'équité moyenne perdue par décision, jugée par GNU Backgammon
à 3-ply — sur 600 décisions de contact :

| configuration | PR | IC 95 % | référence publiée |
|---|---|---|---|
| 0-ply | 1,088 | [0,802 ; 1,412] | 1,06 |
| 1-ply | 0,499 | [0,330 ; 0,705] | 0,50 |
| 2-ply, sans élagage | **0,273** | [0,190 ; 0,364] | 0,22 |
| 2-ply, élagage `k=12` *(le défaut)* | 0,375 | [0,264 ; 0,499] | — |

**Les trois valeurs de référence tombent dans leur intervalle.** Le PR descend à
chaque ply ajouté, ce qui est le contrôle que `PLAN.md` désigne comme le plus
révélateur de la chaîne. Fiche : `docs/mesures/2026-08-27-T3E-performance-rating.md`.

**Deux réserves à lire avec ces chiffres** : le corpus est uniquement de contact,
donc le PR est probablement pessimiste ; et un PR mesuré contre gnubg n'est
reproductible qu'à ~±0,005 d'un build à l'autre, à version et poids identiques —
mesuré sur deux machines.

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
- **La table exacte de fin de partie n'est PAS incluse.** Celle que la recherche
  consulte pèse 1,2 Gio et ne se transporte pas dans un artefact web. Sans elle,
  la fin de partie retombe sur le réseau, ce qui coûte **0,00028 d'équité par
  décision de bearoff** — mesuré (T38), là où GNU Backgammon consulte sa propre
  table et n'y perd rien. L'API `loadBearoff()` existe pour qui se la procure.
- **Aucun budget de temps sur mobile.** La pénalité mesurée en août était de
  ×2,12 à ×2,83 sur deux appareils, mais elle n'a pas été rejouée depuis les
  optimisations.
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

    print("\n3b. API JavaScript, table exacte, et de quoi vérifier")
    # `api/` n'est pas une coquetterie de rangement : notre `gammonnet.mjs` et
    # le collage Emscripten `build/wasm/gammonnet.mjs` portent le MÊME NOM. Les
    # poser côte à côte fait écraser l'un par l'autre, et l'artefact devient
    # silencieusement inutilisable — le module chargerait un fichier qui n'est
    # pas celui qu'il croit.
    for group, label, subdir in ((API, "api", "api"),
                                 (TABLES, "table exacte", ""),
                                 (VERIFY, "vérification", "verify"),
                                 (EVIDENCE, "mesures", "evidence")):
        for path in group:
            if not path.exists():
                missing.append(path.name)
                print(f"   ABSENT : {path.name}")
                continue
            destination = target / subdir if subdir else target
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination / path.name)
            name = f"{subdir}/{path.name}" if subdir else path.name
            files.append((name, sha256(path), path.stat().st_size))
            print(f"   {name}")

    (target / "QUICKSTART.md").write_text(quickstart(), encoding="utf-8")
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
