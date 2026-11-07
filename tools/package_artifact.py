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
donc `strehl-prob5-768-768-256-256-256` — la paternité d'Alexander Strehl — et c'est
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
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.search import search_level  # noqa: E402

#: Le nom du réseau garde la paternité de son auteur (BRIEF §8). Le nôtre est
#: celui de la CONFIGURATION, pas des poids.
NETWORKS = {
    "strehl-prob5-768-768-256-256-256": ROOT / "models" / "cubeless_prob5_768_768_256_256_256.bin",
    # Le réseau d'avant, à ses poids rafraîchis : publié à côté, il est le chemin de
    # retour de l'appelant et son repère de coût. Jamais le défaut.
    "strehl-prob5-512-512-256-256": ROOT / "models" / "cubeless_prob5_512_512_256_256.bin",
    "strehl-prune-32": ROOT / "models" / "prune_32.bin",
}

WASM = [
    ROOT / "build" / "wasm" / "gammonnet.mjs",
    ROOT / "build" / "wasm" / "gammonnet.wasm",
    ROOT / "build" / "wasm" / "gammonnet-simd.mjs",
    ROOT / "build" / "wasm" / "gammonnet-simd.wasm",
    # Le multi-fils (`make wasm-threads`) : sans lui, aucune page isolée ne
    # peut avoir plus d'un cœur par décision, quoi qu'en dise l'API.
    ROOT / "build" / "wasm" / "gammonnet-simd-mt.mjs",
    ROOT / "build" / "wasm" / "gammonnet-simd-mt.wasm",
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
    #: Le repère du `.bin16` : ce qu'un lecteur du format `BGN6` doit rendre
    #: (`docs/specs/format-bgn6-spec.md`). Il n'est pas celui du float32 —
    #: les poids arrondis sont d'autres poids.
    ROOT / "build" / "reference16.bin",
    ROOT / "wasm" / "parity.mjs",
    ROOT / "wasm" / "api_invariants.mjs",
    ROOT / "models" / "cubeless_prob5_768_768_256_256_256.provenance.json",
    ROOT / "models" / "cubeless_prob5_512_512_256_256.provenance.json",
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


def retarget_check(source: Path, destination: Path, weights_name: str,
                   prune_name: str) -> None:
    """`wasm/parity.mjs` est écrit pour l'arborescence du DÉPÔT, pas pour celle
    de l'archive : il importe `./gammonnet.mjs` (voisin dans `wasm/`), lit
    `../build/reference.bin` et `../models/…`, et charge les modules depuis
    `../build/wasm/`. Recopié tel quel dans `verify/`, il échoue au premier
    import — et la commande que le README et le QUICKSTART promettent
    (`node verify/parity.mjs`) ne marche pas.

    Il est donc transposé, pas dupliqué : le contrôle lui-même — le repère de
    2 000 positions, la tolérance de 1e-6 — reste défini à un seul endroit.
    Seuls les chemins changent. `check_artifact_parity()` l'exécute ensuite sur
    l'artefact produit, pour que cette transposition ne puisse pas pourrir en
    silence.
    """
    text = source.read_text(encoding="utf-8")
    common = [('from "./gammonnet.mjs"', 'from "../api/gammonnet.mjs"')]
    per_file = {
        "parity.mjs": [
            ('join(ROOT, "build", "reference.bin")', 'join(HERE, "reference.bin")'),
            ('join(ROOT, "build", "reference16.bin")', 'join(HERE, "reference16.bin")'),
            ('join(ROOT, "models", "cubeless_prob5_768_768_256_256_256.bin")',
             f'join(ROOT, "{weights_name}")'),
            ('join(ROOT, "models", "cubeless_prob5_768_768_256_256_256.bin16")',
             f'join(ROOT, "{weights_name}16")'),
            ('"../build/wasm/gammonnet.mjs"', '"../gammonnet.mjs"'),
            ('"../build/wasm/gammonnet-simd.mjs"', '"../gammonnet-simd.mjs"'),
        ],
        "api_invariants.mjs": [
            ('join(ROOT, "models", "cubeless_prob5_768_768_256_256_256.bin")',
             f'join(ROOT, "{weights_name}")'),
            ('join(ROOT, "models", "prune_32.bin")', f'join(ROOT, "{prune_name}")'),
            ('join(ROOT, "build", "wasm", "gammonnet-simd.mjs")',
             'join(ROOT, "gammonnet-simd.mjs")'),
        ],
    }
    moves = common + per_file[source.name]
    for before, after in moves:
        if before not in text:
            raise SystemExit(
                f"REFUSÉ : `wasm/parity.mjs` a changé de forme — « {before} » "
                "ne s'y trouve plus. La transposition vers l'archive est "
                "obsolète ; corrigez `retarget_parity`.")
        text = text.replace(before, after)
    destination.write_text(text, encoding="utf-8")


def check_artifact_parity(target: Path) -> None:
    """L'artefact passe-t-il sa PROPRE vérification ?

    Le README et le QUICKSTART promettent `node verify/parity.mjs`. Une
    promesse qu'on ne tient pas soi-même avant de publier n'est pas une
    garantie, c'est une intention.
    """
    node = shutil.which("node")
    if node is None:
        print("   node absent — vérification non exécutée (SAUTÉE)")
        return
    for script in ("verify/parity.mjs", "verify/api_invariants.mjs"):
        result = subprocess.run([node, script], cwd=target,
                                capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(
                f"REFUSÉ : l'artefact ne passe pas `{script}`.\n"
                + (result.stdout + result.stderr)[-2000:])
        print("   " + (result.stdout.strip().splitlines() or ["passée"])[-1])


def check_weights() -> None:
    """Les poids publiés sont-ils CEUX qui ont été mesurés ?

    La question n'est pas rhétorique. Le réseau d'élagage a été entraîné sur
    GPU, et sa propre provenance le dit : l'accumulation atomique de la
    rétro-propagation CUDA n'est pas reproductible au bit près. Une chaîne
    d'intégration qui le RÉENTRAÎNE produit donc un réseau différent — proche,
    sûrement, mais différent — et publierait un artefact auquel les mesures de
    T3D (`k=12` ne coûte rien) et de T3E (PR 0,273) ne s'appliquent plus.

    Rien d'autre ne l'attraperait : le corpus de non-régression T12 évalue le
    GRAND réseau et ne touche pas l'élagage. Le défaut serait silencieux, ce
    qui est exactement le mode de défaillance que `CLAUDE.md` §2 nomme.

    D'où ce contrôle : chaque réseau porte une provenance versionnée qui
    contient son `sha256`. Ils doivent correspondre, sinon on refuse.
    """
    for source in NETWORKS.values():
        provenance = source.with_suffix(".provenance.json")
        if not provenance.exists():
            raise SystemExit(f"REFUSÉ : {source.name} n'a pas de provenance")
        recorded = json.loads(provenance.read_text())["sha256"]
        actual = sha256(source)
        if actual != recorded:
            raise SystemExit(
                f"REFUSÉ : {source.name} n'est pas le réseau mesuré.\n"
                f"  attendu (provenance) : {recorded}\n"
                f"  trouvé               : {actual}\n"
                "Les mesures de force publiées portent sur le réseau attendu. "
                "Publier celui-ci reviendrait à leur faire dire ce qu'elles ne "
                "disent pas. Restaurez les poids, ou mesurez à nouveau.")


def quickstart() -> str:
    return """# Démarrer avec gammonNet

## Ce que contient cette archive

| | |
|---|---|
| `strehl-prob5-768-…​.bin` / `.bin16` | les poids du réseau par défaut, en float32 et en float16 (moitié moins lourd) |
| `strehl-prob5-512-…​.bin` / `.bin16` | le réseau publié à côté : même interface, le choix revient à l'appelant (`alternate_network` dans `manifest.json`) ; ses équités ne se comparent pas à celles de l'autre |
| `strehl-prune-32_…​.bin` / `.bin16` | le réseau d'élagage : il trie les coups pour que le grand n'en note qu'une poignée |
| `gammonnet-simd.mjs` / `.wasm` | le moteur WebAssembly (préférez la version SIMD) |
| `gammonnet-simd-mt.mjs` / `.wasm` | le même moteur sur plusieurs cœurs, pour une page isolée (voir plus bas) |
| `api/gammonnet.mjs` | l'API JavaScript — `Evaluator` |
| `api/pool.mjs`, `api/worker.mjs` | le pool de Web Workers : un match en 74 s au lieu de 350 |
| `manifest.json` | les noms de fichiers de cette version — lisez-le plutôt que de les recopier |
| `verify/` | de quoi vérifier vous-même que cet artefact donne les bons chiffres |
| `evidence/` | les mesures brutes derrière chaque chiffre des notes de version |

## Le plus court chemin

```js
import { Evaluator } from "./api/gammonnet.mjs";
import factory from "./gammonnet-simd.mjs";

// L'archive nomme ses propres fichiers : ne figez jamais une version dans
// votre code, elle change à chaque publication.
const files = await (await fetch("./manifest.json")).json();

const weights = new Uint8Array(
  await (await fetch("./" + files.network_fp16)).arrayBuffer());
const evaluator = await Evaluator.create(factory, weights);

// Le réseau d'élagage : ×3,65 sur une décision 2-ply, pour une perte
// d'équité dans le bruit. Facultatif, mais fortement conseillé.
const prune = new Uint8Array(
  await (await fetch("./" + files.prune_fp16)).arrayBuffer());
evaluator.loadPrune(prune, files.prune_k);

// Position de départ, jet 3-1 -- la forme canonique "normal" (ply=2, filtre
// en triplet : le meilleur, plus jusqu'à 2 autres à moins de 0,04), lue
// plutôt que retapée : `Evaluator.level` porte sa
// mesure de qualité avec elle (issue #25).
const best = evaluator.bestPlay("4HPwATDgc/ABMA", 0, 3, 1, Evaluator.level("normal"));
console.log(best.equity, best.resultId, best.evaluations);
```

## Plusieurs cœurs par décision

Une décision peut se répartir sur plusieurs fils, **au même résultat près au
bit**. Il faut trois choses :

1. **Une page isolée.** Le serveur qui sert la page envoie
   `Cross-Origin-Opener-Policy: same-origin` et
   `Cross-Origin-Embedder-Policy: require-corp`. Sans eux le navigateur refuse
   la mémoire partagée (`crossOriginIsolated` reste faux). Attention : COEP
   bloque toute ressource d'une autre origine qui ne s'y prête pas.
2. **Le module multi-fils**, que `chooseBuild()` désigne seul quand la page
   est isolée, et `gammonnet-simd.mjs` sinon :

   ```js
   import { chooseBuild } from "./api/gammonnet.mjs";
   const { file } = chooseBuild();   // "gammonnet-simd-mt.mjs" ou "gammonnet-simd.mjs"
   ```
3. **Un Web Worker** (`api/worker.mjs`) : la recherche y attend ses fils, ce
   que le fil principal n'a pas le droit de faire. Un worker initialisé sur le
   module multi-fils prend de lui-même `Evaluator.suggestedThreads()` — les
   fils annoncés, plafonnés à 16 ; passez `threads` à l'`init` pour en décider
   autrement. Un `EvaluatorPool` de plusieurs workers reste à un fil par worker.

Mesuré (poste 16 cœurs / 32 fils, décision 2-ply `normal`, médiane de trois
passes) : ×3,8 à 4 fils, ×7,4 à 8, ×12 à 16, dans Chromium 131 comme dans
Firefox 140. Sur votre
appareil, mesurez : un téléphone ou des cœurs hétérogènes ne se déduisent pas
de ces chiffres.

## Vérifier avant de faire confiance

L'archive contient le repère de 2 000 positions et le contrôle qui le lit. Il
compare le WebAssembly au moteur natif de référence et **refuse** au-delà de
1e-6, pour chacun des deux formats de poids contre son propre repère
(`verify/reference.bin` pour le `.bin`, `verify/reference16.bin` pour le
`.bin16`) :

```sh
node verify/parity.mjs
```

Attendu : `max|Δ| = 0` sur les deux builds, pour les deux formats.

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
backgammon-ai-engine — Copyright (c) 2026 Alex Strehl — licence MIT
(poids, commit c373141 ; les sources compilées, commit 7184e2f, portent
« Copyright (c) 2026 alexstrehl », le même auteur)
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


#: CE QUI CHANGE DANS CETTE VERSION, en tête des notes.
#:
#: Une archive dont les notes ne disent que la force mesurée laisse un
#: utilisateur qui met à jour deviner ce qui a bougé sous ses pieds. Quand ce
#: qui bouge est le SENS de cinq nombres, deviner est exactement ce qu'il ne
#: faut pas lui demander.
CHANGES = """## Ce qui change depuis v1.8.2 — À LIRE AVANT DE METTRE À JOUR

**Les deux réseaux changent, et le réseau par défaut aussi.** Toute décision peut
rendre un autre coup et d'autres équités qu'en v1.8.2. Un appelant qui a figé des
résultats les verra changer, et c'est voulu. Mêmes 196 entrées, mêmes cinq
sorties : aucune convention ne bouge.

- **Par défaut** : `strehl-prob5-768-768-256-256-256` (deux couches de 768, trois
  de 256, 1 071 621 paramètres), poids de l'amont au commit `c373141`.
- **Publié à côté** : `strehl-prob5-512-512-256-256`, le réseau par défaut de
  v1.8.2, **sur ses poids rafraîchis** par l'amont au même commit `c373141` —
  ce n'est donc pas le fichier de v1.8.2. Même interface ; le choix revient à
  l'appelant (`alternate_network` dans `manifest.json`, `serve --alternate`).
  Les équités de deux réseaux ne se comparent pas : une clé de cache d'analyses
  doit inclure le réseau, et `/healthz` le nomme (contrat `gammonNet-serve/5`).
- **L'élagueur** `strehl-prune-32` ne change pas : redistillé du 768×768 sur trois
  graines, il n'a pas fait mieux.

Poids d'Alex Strehl, MIT (« Copyright (c) 2026 Alex Strehl », licence relue à
`c373141`).

### 1. Ce que vaut le réseau par défaut — mesures (issues #34 et #38)

768×768 contre 4 couches, poids `c373141` des deux côtés :

| mesure | volume | 768×768 − 4 couches | IC 95 % |
|---|---|---|---|
| tête-à-tête 0-ply sans arbitre, cubeless money | 1 000 000 de parties | **+0,0059 ppg** | [+0,0038 ; +0,0080] |
| registre arbitré T70, 2-ply niveau `normal` | 9 698 décisions appariées | **−0,00026** de perte par décision | [−0,00035 ; −0,00016] |
| cubeful match 7 points, `normal` des deux côtés | 35 000 paires | MWC 49,92 % | [49,70 ; 50,13] |
| cubeful money, `normal` des deux côtés | 150 000 paires | +0,0009 ppg | [−0,0047 ; +0,0065] |

**Plus fort sur les décisions, et sans régression en jeu.** Sous recherche, la
perte par décision passe de 0,00277 à 0,00252. En partie complète avec videau,
les seuils de non-régression fixés avant lecture (MWC ≥ 49,5 %, money ≥ −0,010)
sont tenus, mais **aucun gain n'est résolu** à ce volume : un gain de cet ordre
par décision se chiffre en millièmes de ppg, sous la précision de 150 000 paires.
Le 4 couches rafraîchi, lui, fait −0,00011 [−0,00021 ; −0,00001] contre ses
anciens poids. Fiches : `docs/mesures/2026-11-06-i38-768-c373141.md`,
`docs/mesures/2026-11-04-poids-c373141.md`,
`docs/mesures/2026-10-30-i34-etape4-decision.md`.

### 2. Ce qu'il coûte — et le noyau qui le paie

Le noyau par lot saute désormais les unités qu'une ReLU laisse à zéro, et le noyau
écrit à la main lit ses poids en place : **résultats identiques au bit près**,
pour les deux réseaux. Une décision 2-ply `(0,1,3)` `k=12`, noyau de l'artefact,
même machine (Threadripper PRO 3955WX) :

| navigateur | 4 couches | 768×768 | rapport |
|---|---|---|---|
| Chromium 131 | 0,230 s | 0,406 s | ×1,76 |
| Firefox 140 | 0,245 s | 0,429 s | ×1,75 |

Sur une autre machine (EPYC 9254), le gain du noyau seul, pour le 4 couches :
0,330 → 0,206 s dans Chromium, 0,688 → 0,205 s dans Firefox. **Le 768×768 sur le
nouveau noyau coûte donc à peu près ce que coûtait le 4 couches en v1.8.2.**
Les temps ne se transportent pas d'une machine à l'autre ; seul le rapport ×1,75
entre réseaux le fait. **Non mesurés : le mobile, et la mémoire dans un vrai
navigateur.**

**En natif, le noyau écrit à la main devient le build par défaut**, en SSE2 que
tout x86-64 possède (aucune instruction AVX) : décision 2-ply `normal`, un fil,
0,182 → 0,138 s (4 couches), 0,336 → 0,250 s (768×768), mêmes empreintes des
classements. `make build KERNEL_INTRINSICS=0` revient à l'ancien.

### 3. Nouveau : une décision découpée en tâches (issue #36)

`planDecision`, `runTask`, `advance` et `combineDecision` découpent une décision
(coup, videau, politique par niveau nommé, position avant le jet) en tâches sans
état, exécutables sur des instances WebAssembly mono-fil qui ne partagent aucune
mémoire. Recombinée, la décision est **égale au bit près** à l'appel en un bloc,
quel que soit l'ordre d'exécution. `EvaluatorPool.decideSplit` la répartit sur un
pool de workers ; `evaluatePositionAtPly` rend l'équité d'une position avant le
jet, passe forcée comprise. Contrat : `docs/specs/decision-decomposee-spec.md`.
Le gain de temps réel n'est **pas** chronométré.

### 4. Nouveau : `/v1/cube` à N-ply (issue #37)

`/v1/cube` accepte `ply` : la position avant le jet est évaluée par la recherche,
puis le videau sur cette distribution, pour `double`, `take` et `equity`. Sans
`ply`, la réponse est identique à v1.8.2 octet pour octet ; avec, elle rend le
niveau réellement appliqué.

### 5. Le format float16

Le `.bin16` du 768×768 coûte en jeu −0,00000 [−0,00001 ; +0,00000] par décision
au réglage servi ; le coup à 0-ply change dans 0,075 % [0,066 ; 0,084] des
positions, sans écart isolé.
"""


def release_notes(version: str, date: str, files: list[tuple[str, str, int]]) -> str:
    listing = "\n".join(f"| `{name}` | {size:,} | `{digest}` |".replace(",", " ")
                        for name, digest, size in files)
    return f"""# gammonNet {version} — {date}

{CHANGES}

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
Fiche : `docs/mesures/2026-08-26-T35-verdict.md`. **Mesuré en août 2026 sur le
réseau de l'époque**, pas rejoué sur ceux de cette version : chaque changement de
réseau depuis a été mesuré contre son prédécesseur (§1), pas contre GNU
Backgammon.

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
`.bin16` en float16 — moitié moins lourd à télécharger, pour une perte en jeu
indiscernable de zéro au réglage servi : −0,00000 [−0,00001 ; +0,00000] par
décision pour le réseau par défaut, le coup à 0-ply changeant dans 0,075 % des
positions (`docs/mesures/2026-11-06-i38-768-c373141.md`). Chaque format a son repère
de parité ; le format est décrit dans `docs/specs/format-bgn6-spec.md`.
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

- **Un seul budget de temps dans un navigateur, et sur une seule machine.** Une
  décision 2-ply `(0,1,3)` `k=12` du réseau par défaut coûte **0,406 s** dans
  Chromium 131 et **0,429 s** dans Firefox 140 sur un Threadripper PRO 3955WX
  — mesuré, pas déduit du natif (§2). Ne transportez ce chiffre ni vers un autre
  navigateur, ni vers une autre machine : seul le rapport entre les deux réseaux
  (×1,75) a été retrouvé d'une machine à l'autre.
- **La table exacte de fin de partie n'est PAS incluse.** Celle que la recherche
  consulte pèse 1,2 Gio et ne se transporte pas dans un artefact web. Sans elle,
  la fin de partie retombe sur le réseau, ce qui coûte **0,00028 d'équité par
  décision de bearoff** — mesuré (T38), là où GNU Backgammon consulte sa propre
  table et n'y perd rien. L'API `loadBearoff()` existe pour qui se la procure.
- **Aucun budget de temps sur mobile.** La pénalité mesurée en août était de
  ×2,12 à ×2,83 sur deux appareils, et elle n'a été rejouée depuis **aucune** des
  optimisations de cette version — le noyau SIMD128 étant précisément ce qu'un
  processeur mobile exécute le moins bien, l'extrapoler serait une invention.
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

    print("0. Les poids sont-ils ceux qui ont été mesurés ?")
    check_weights()
    print("   sha256 conformes aux provenances")

    if not args.skip_regression:
        print("\n1. Corpus de non-régression T12")
        check_regression()
        print("   passé")
    else:
        print("\n1. Corpus de non-régression T12 — SAUTÉ (essai)")

    target = args.out / f"gammonnet-{args.version}"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    print(f"\n2. Poids → {target}")
    from pack_fp16 import pack

    files: list[tuple[str, str, int]] = []
    big_name = prune_name = ""
    for name, source in NETWORKS.items():
        stem = f"{name}_{args.version}_{date}"
        if name == "strehl-prune-32":
            prune_name = f"{stem}.bin"
        if name == "strehl-prob5-768-768-256-256-256":
            #: `verify/parity.mjs` doit charger CES poids-là, sous le nom
            #: qu'ils portent dans l'archive — pas celui du dépôt.
            big_name = f"{stem}.bin"
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
            if path.name in ("parity.mjs", "api_invariants.mjs"):
                retarget_check(path, destination / path.name, big_name, prune_name)
            else:
                shutil.copy2(path, destination / path.name)
            written = destination / path.name
            name = f"{subdir}/{path.name}" if subdir else path.name
            files.append((name, sha256(written), written.stat().st_size))
            print(f"   {name}")

    (target / "QUICKSTART.md").write_text(quickstart(), encoding="utf-8")
    (target / "NOTICE").write_text(notice(), encoding="utf-8")
    (target / "RELEASE.md").write_text(
        release_notes(args.version, date, files), encoding="utf-8")
    shutil.copy2(ROOT / "THIRD-PARTY.md", target / "THIRD-PARTY.md")
    shutil.copy2(ROOT / "LICENSE", target / "LICENSE")

    #: LES NOMS DE FICHIERS PORTENT LA VERSION ET LA DATE — donc ils changent à
    #: chaque publication. Tout extrait de code qui en fige un devient faux à la
    #: version suivante, et l'utilisateur qui le copie récolte un 404. Le
    #: manifeste rend les noms interrogeables : la documentation lit d'ici,
    #: plutôt que de répéter ce qui bouge.
    manifest = {
        "version": args.version,
        "date": date,
        "network": f"strehl-prob5-768-768-256-256-256_{args.version}_{date}.bin",
        "network_fp16": f"strehl-prob5-768-768-256-256-256_{args.version}_{date}.bin16",
        "alternate_network": f"strehl-prob5-512-512-256-256_{args.version}_{date}.bin",
        "alternate_network_fp16": f"strehl-prob5-512-512-256-256_{args.version}_{date}.bin16",
        "prune": f"strehl-prune-32_{args.version}_{date}.bin",
        "prune_fp16": f"strehl-prune-32_{args.version}_{date}.bin16",
        # La forme canonique "normal" (issue #25) : `gn_search_level`
        # (src/gn_search.c) est l'unique source de ce nombre, lue ici plutôt
        # que retapée -- ce manifeste est justement ce qu'on lit, ici comme
        # dans le QUICKSTART.md de l'artefact, au lieu de recopier `12`.
        "prune_k": search_level("normal").prune_k,
        "wasm": "gammonnet-simd.mjs",
        "wasm_scalar": "gammonnet.mjs",
        "wasm_threads": "gammonnet-simd-mt.mjs",
        "api": "api/gammonnet.mjs",
        "pool": "api/pool.mjs",
    }
    for key in ("network", "network_fp16", "alternate_network", "alternate_network_fp16",
                "prune", "prune_fp16", "wasm", "wasm_scalar",
                "wasm_threads", "api", "pool"):
        if not (target / manifest[key]).exists():
            raise SystemExit(
                f"REFUSÉ : le manifeste annonce `{manifest[key]}`, qui n'est pas "
                "dans l'artefact. Un manifeste faux est pire que pas de manifeste.")
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    files.append(("manifest.json", sha256(target / "manifest.json"),
                  (target / "manifest.json").stat().st_size))
    print("   manifest.json")

    if not missing:
        print("\n3c. L'artefact passe-t-il sa propre vérification ?")
        check_artifact_parity(target)

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
