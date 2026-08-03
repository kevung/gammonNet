# Briques tierces

Inventaire des sources utilisées par gammonNet, avec leur licence et **ce qui en est
effectivement utilisé**. Tenu à jour à chaque ajout de dépendance.

> La licence MIT exige que la notice de copyright accompagne *« all copies or substantial
> portions of the Software »*. **Un module WebAssembly servi à un navigateur est une copie
> distribuée** : la notice doit donc vivre aussi dans l'artefact lui-même, pas seulement ici.

## Distribué (embarqué dans les artefacts)

| Brique | Auteur | Licence | Ce qui est utilisé | Source |
|---|---|---|---|---|
| *(aucune pour l'instant — le dépôt ne produit pas encore d'artefact)* | | | | |

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
| [`hedgehog-public`](https://gitlab.com/eranlambooij/hedgehog-public) | Eran Lambooij | MIT — vérifiée par lecture du fichier `LICENSE` | **Aucun code embarqué** (décision T22, [ADR-0001](docs/adr/0001-moteur-inference.md)). Leur **benchmark public** est l'étalon que T11 confronte, et leur principe *« refused, not approximated »* est devenu la règle n° 2 de `CLAUDE.md` |
| Highway (SIMD) | Google | Apache-2.0 **ou** BSD-3-Clause | **Non utilisé.** Il n'arrivait que par transitivité via `hedgehog-public`. S'il devenait nécessaire, il sera pris à la source comme dépendance nommée, avec ses obligations propres — fichier `NOTICE` et marquage des fichiers modifiés |

> **Les réseaux de neurones de HedgeHog ne sont pas utilisés** : ils portent une clause non
> commerciale, incompatible avec l'engagement de licence de ce dépôt. Leur **code** est MIT. Les
> deux n'ont pas la même licence, et la distinction doit rester visible partout.

## Outillage (non distribué)

| Brique | Licence | Rôle |
|---|---|---|
| GNU Backgammon (`gnubg-nn`) | GPL-3 | **Oracle de mesure uniquement.** Jamais une source de code ni de poids. Sa sortie n'est pas couverte par sa licence — cf. [GPL FAQ](https://www.gnu.org/licenses/gpl-faq.html#WhatCaseIsOutputGPL) |
| PyTorch, NumPy | BSD-3-Clause | Entraînement et mesure |
| Emscripten | MIT / NCSA | Compilation WebAssembly |

## Une distinction qui compte

**Le code de HedgeHog et les réseaux de HedgeHog n'ont pas la même licence.** Le dépôt
`hedgehog-public` est MIT ; les réseaux publiés sur leur site portent une clause **non
commerciale**. gammonNet peut utiliser le premier, pas les seconds. Toute mention publique de ce
projet doit préserver cette distinction — écrire « propulsé par HedgeHog » sans plus laisserait
croire qu'on emploie leurs modèles, ce qui serait faux et injuste envers eux comme envers
l'auteur du modèle réellement utilisé.
