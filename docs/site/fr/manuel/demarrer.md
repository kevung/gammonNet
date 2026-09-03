# Démarrer

## Ce que contient la release

| Fichier | Ce que c'est |
|---|---|
| `manifest.json` | Les noms de fichiers de cette version — lisez-le plutôt que de les recopier |
| `strehl-prob5-512-512-256-128_v1_….bin` | Les poids du réseau, **float32** — 2,1 Mio |
| `…​.bin16` | Les mêmes, **float16** — 1,06 Mio. Préférez celui-ci pour le web |
| `strehl-prune-32_v1_….bin` / `.bin16` | Le **réseau d'élagage** : il trie les coups pour que le grand n'en note qu'une poignée |
| `bearoff_one_sided.bin` | La table **exacte** de fin de partie — 6,9 Mio |
| `gammonnet-simd.mjs` + `.wasm` | Le moteur WebAssembly, version SIMD |
| `gammonnet.mjs` + `.wasm` | Idem, version scalaire, pour les environnements sans SIMD |
| `api/gammonnet.mjs` | L'API JavaScript : la classe `Evaluator` |
| `api/pool.mjs`, `api/worker.mjs` | Le pool de Web Workers |
| `verify/` | Le repère de 2 000 positions et le contrôle de parité |
| `evidence/` | Les mesures brutes derrière chaque chiffre |
| `NOTICE`, `THIRD-PARTY.md`, `LICENSE` | Les licences et attributions |

```{admonition} Pourquoi le nom des poids n'est pas « gammonNet »
:class: note

Les poids viennent du travail d'**Alexander Strehl** (MIT) et portent son nom. **gammonNet** est
le nom de la *configuration* — réseau, recherche, équité de match, fins de partie. Un réseau ne
devient un autre réseau que si ses poids changent ; les rebaptiser reviendrait à s'attribuer ce
qu'on n'a pas produit.
```

## Le plus court chemin

```javascript
import { Evaluator } from "./api/gammonnet.mjs";
import factory from "./gammonnet-simd.mjs";

// L'archive nomme ses propres fichiers : ne figez jamais une version dans
// votre code.
const files = await (await fetch("./manifest.json")).json();

const weights = new Uint8Array(
  await (await fetch("./" + files.network_fp16)).arrayBuffer());
const evaluator = await Evaluator.create(factory, weights);

// Le réseau d'élagage : ×3,65 sur une décision 2-ply dans un navigateur, pour
// une perte d'équité dans le bruit. Facultatif, mais fortement conseillé.
const prune = new Uint8Array(
  await (await fetch("./" + files.prune_fp16)).arrayBuffer());
evaluator.loadPrune(prune, files.prune_k);

const best = evaluator.bestPlay("4HPwATDgc/ABMA", 0, 3, 1,
                                { ply: 2, filterTop: 3, filterInner: 1 });
console.log(best.equity, best.resultId, best.evaluations);
```

`"4HPwATDgc/ABMA"` est un **Position ID** au format de GNU Backgammon : l'encodage standard d'une
position, que tout logiciel de backgammon sait produire. Le `0` qui suit désigne le joueur au
trait.

## Un match entier, sans figer la page

Une décision 2-ply coûte ~2 s dans un navigateur : une centaine de décisions sur le fil qui
dessine, et l'interface est gelée pendant plusieurs minutes. Le pool distribue les décisions à des
Web Workers, **une décision par tâche**, et rend la main entre chacune.

```javascript
import { EvaluatorPool } from "./api/pool.mjs";

// COMBIEN DE WORKERS : surtout pas `navigator.hardwareConcurrency`. Il compte
// des FILS, quand le débit est borné par les cœurs physiques et par la bande
// passante — chaque worker recharge sa propre copie des poids, faute de
// `SharedArrayBuffer` sur un hébergeur statique.
const size = EvaluatorPool.suggestedSize();

const pool = await EvaluatorPool.create(
  size, "./api/worker.mjs", "./gammonnet-simd.mjs", weights,
  { pruneBytes: prune, pruneK: files.prune_k });

const { done, cancel, schedule } = pool.decide(
  decisions,                       // [{ positionId, turn, d1, d2, options }, …]
  { kind: "rankPlays",
    options: Evaluator.level("normal"),
    onProgress: (fait, total) => console.log(`${fait}/${total}`) });

const analyses = await done;       // parallèle à `decisions`, ou `null` si annulé
console.log(schedule.toJSON());    // le relevé d'ordonnancement de CE travail
pool.destroy();
```

`cancel()` périme ce qui attend et ce qui est en vol **sans détruire les workers** : leurs poids
restent chargés, et le pool sert la demande suivante immédiatement.

```{admonition} Mesurez sur votre appareil, ne nous croyez pas
:class: tip

`suggestedSize()` est une **règle prudente tirée de trois relevés**, pas une mesure de votre
appareil : la plateforme ne dit pas combien de cœurs physiques elle a, et `hardwareConcurrency`
est plafonné à 4 sur iOS quel que soit le téléphone. `schedule.toJSON()` rend l'oisiveté de
chaque travail — c'est avec elle qu'on tranche, sur la machine qui compte.
```

## Les identifiants de position

gammonNet ne lit **pas** de fichiers de match — c'est une frontière volontaire du projet. Il
consomme des **positions**. Pour analyser un match, faites-le lire par un logiciel qui sait le
faire (GNU Backgammon exporte des Position ID), et passez les positions une par une.

## En natif

La bibliothèque C se construit avec un compilateur et rien d'autre :

```sh
make setup    # environnement, sources vendorées
make build    # build/libgammonnet.so
```

L'interface Python (`python/gammonnet/`) enveloppe la bibliothèque par `ctypes` :

```python
from gammonnet.codec import position_from_id
from gammonnet.infer import Network
from gammonnet.rules import WHITE
from gammonnet.search import SearchConfig, search_plays

net = Network.load("models/cubeless_prob5_512_512_256_128.bin")
small = Network.load("models/prune_32.bin")
position = position_from_id("4HPwATDgc/ABMA", WHITE)

config = SearchConfig(ply=2, filter=(0, 1, 3), prune_net=small, prune_k=12)
for candidate in search_plays(net, position, 3, 1, config)[:5]:
    print(candidate.equity, candidate.evaluation.as_tuple())
```
