# Briques tierces

Inventaire des sources utilisées par gammonNet, avec leur licence et **ce qui en est
effectivement utilisé**. Tenu à jour à chaque ajout de dépendance.

> La licence MIT exige que la notice de copyright accompagne *« all copies or substantial
> portions of the Software »*. **Un module WebAssembly servi à un navigateur est une copie
> distribuée** : la notice doit donc vivre aussi dans l'artefact lui-même, pas seulement ici.

## Distribué (embarqué dans les artefacts)

| Brique | Auteur | Licence | Ce qui est utilisé | Source |
|---|---|---|---|---|
| `backgammon-ai-engine` | Alexander Strehl | MIT | **Les poids** `cubeless_prob5_512_512_256_128`, publiés sous le nom `strehl-prob5-512-512-256-128` — la paternité reste à l'auteur (`BRIEF.md` §8) ; **le moteur de règles** `c_engine/bg_engine.c` et **le moteur d'inférence** `c_inference/nn_eval.c`, compilés dans l'artefact | [dépôt](https://github.com/alexstrehl/backgammon-ai-engine), commit `b2750df` |
| Table d'équité de match Kazaross-XG2 | Neil Kazaross | œuvre de N. Kazaross, avec attribution | La table, compilée dans l'artefact (`src/gn_met_table.h`) | précédent MIT dans [blunderDB](https://github.com/kevung/blunderDB) |
| `strehl-prune-32` | poids produits par ce dépôt, **distillés de** `strehl-prob5-...` (Strehl, MIT) | MIT | Le réseau d'élagage, qui trie les coups candidats | `tools/train_prune.py`, provenance dans `models/prune_32.provenance.json` |

> **La notice voyage avec l'artefact.** `tools/package_artifact.py` écrit un fichier `NOTICE`
> dans le répertoire publié, et `wasm/notice.js` la place en tête du module WebAssembly. Les
> deux portent le texte MIT complet d'Alexander Strehl et l'attribution à Neil Kazaross.

## Présent dans l'arbre de travail (`vendor/`, non distribué en l'état)

`vendor/` est gitignoré. Ce qui est **versionné** est le commit épinglé dans
`tools/fetch_vendor.py`, afin qu'une mesure puisse toujours être rattachée à l'arbre amont
exact qui l'a produite.

| Brique | Auteur | Licence | Commit épinglé | Ce qui en est utilisé |
|---|---|---|---|---|
| [`backgammon-ai-engine`](https://github.com/alexstrehl/backgammon-ai-engine) | Alexander Strehl | MIT — vérifiée par lecture du fichier `LICENSE` (« Copyright (c) 2026 alexstrehl »), pas par confiance dans le nom du dépôt | `b2750df` | **`c_engine/bg_engine.c`, compilé dans `build/libgammonnet.so`** — le moteur de règles, derrière notre `src/gn_rules.h`. Également : les poids `cubeless_prob5_512_512_256_128.pt` comme référence de mesure. À terme dans l'artefact distribué : les poids, et le moteur d'inférence C (`c_inference/nn_eval.c`) |

> **`bg_engine.c` est déjà lié dans notre bibliothèque native.** Dès que celle-ci sera
> distribuée — et un module WebAssembly servi à un navigateur **est** une distribution — la
> notice MIT d'Alexander Strehl devra accompagner l'artefact, et pas seulement ce fichier.
> C'est une condition de livraison de T50, notée ici pour qu'elle ne se découvre pas à ce
> moment-là.

## Prévu

| Brique | Auteur | Licence | Ce qui serait utilisé | Source |
|---|---|---|---|---|
| Modèle de Zadeh | N. Zadeh, *Management Science* 23, 986 (1977) | Publication académique | Repli au-delà de 25 points | — |

## Une œuvre citée, pas une dépendance

| Brique | Auteur | Fondement | Ce qui est embarqué |
|---|---|---|---|
| **Table d'équité de match Kazaross-XG2** | **Neil Kazaross** | Attribution. Œuvre de N. Kazaross, générée par rollouts XG jusqu'à 9 points, GNU Backgammon Supremo jusqu'à 15, étendue à 25 par projection des points de prise. GNU Backgammon n'en est que le véhicule de distribution | La table 25×25 pré-Crawford et les 24 entrées post-Crawford, dans `src/gn_met_table.h` |

**La transcription** vient de [blunderDB](https://github.com/kevung/blunderDB) — MIT, Copyright (c)
2024 Facteur Pat, fichier `pkg/blunderdb/engine/met.go` — que `BRIEF.md` §3.3 cite comme le
précédent MIT pour embarquer cette table. Le fichier généré porte les deux mentions, et
`tests/data/met_reference.json` conserve les valeurs de blunderDB comme repère de contrôle.

> **Ce que le contrôle croisé prouve, et ce qu'il ne prouve pas.** Les 625 entrées coïncident avec
> celles de blunderDB — mais c'est de là qu'elles viennent. Cela vérifie la **transcription**, pas
> la table. Ce qui vérifie la table, ce sont ses propriétés : antisymétrie exacte, diagonale à 0,5,
> monotonie, dentelure pair/impair du post-Crawford, et un point de prise mesuré **dans la table**
> à **25,20 %** près du money game.

**Au-delà de 25 points**, `BRIEF.md` prévoit un repli sur le modèle de Zadeh (*Management Science*
23, 986, 1977). **Il n'est pas implémenté** : les matchs de plus de 25 points ne se jouent pas, et
un chemin de code non éprouvé serait un passif plutôt qu'une fonctionnalité. Ces états sont
**refusés**, jamais extrapolés.

## Consulté, non embarqué

Ces briques ne sont **pas** distribuées avec nos artefacts. Elles figurent ici parce qu'elles ont
pesé sur la conception, et qu'une dette intellectuelle se cite même quand aucune ligne n'est
reprise.

| Brique | Auteur | Licence | Ce qu'on lui doit |
|---|---|---|---|
| Highway (SIMD) | Google | Apache-2.0 **ou** BSD-3-Clause | **Non utilisé.** Il n'arrivait que par transitivité, via une piste écartée. S'il devenait nécessaire, il sera pris à la source comme dépendance nommée, avec ses obligations propres — fichier `NOTICE` et marquage des fichiers modifiés |

> **Aucun réseau portant une clause non commerciale n'est utilisé** : une telle clause est
> incompatible avec l'engagement de licence de ce dépôt.

## Outillage (non distribué)

| Brique | Licence | Rôle |
|---|---|---|
| GNU Backgammon (`gnubg-nn`) | GPL-3 | **Oracle de mesure uniquement.** Jamais une source de code ni de poids. Sa sortie n'est pas couverte par sa licence — cf. [GPL FAQ](https://www.gnu.org/licenses/gpl-faq.html#WhatCaseIsOutputGPL) |
| PyTorch, NumPy | BSD-3-Clause | Entraînement et mesure |
| Emscripten | MIT / NCSA | Compilation WebAssembly |

## Une distinction qui compte

**Un dépôt et les modèles qu'il publie n'ont pas forcément la même licence.** Le nom du dépôt ne
renseigne pas sur la licence des poids : un dépôt MIT peut publier des réseaux sous clause non
commerciale. C'est pourquoi chaque brique de ce tableau est vérifiée par lecture de sa licence,
poids et code séparément, et pourquoi le seul réseau embarqué ici est celui dont la licence a été
lue — celui d'Alexander Strehl.
