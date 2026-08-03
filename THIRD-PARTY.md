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
| [`backgammon-ai-engine`](https://github.com/alexstrehl/backgammon-ai-engine) | Alexander Strehl | MIT — vérifiée par lecture du fichier `LICENSE` (« Copyright (c) 2026 alexstrehl »), pas par confiance dans le nom du dépôt | `b2750df` | Aujourd'hui : le moteur de règles C (`c_engine/bg_engine.c`) et les poids `cubeless_prob5_512_512_256_128.pt` comme référence de mesure. À terme embarqués dans l'artefact : les poids, et le moteur d'inférence C (`c_inference/nn_eval.c`) |

## Prévu

| Brique | Auteur | Licence | Ce qui serait utilisé | Source |
|---|---|---|---|---|
| `hedgehog-public` | Eran Lambooij | MIT | **Le code seulement** — évaluateur NNUE, recherche expectiminimax, SIMD Highway. **Les réseaux de neurones de ce projet ne sont pas utilisés** : ils portent une clause non commerciale | <https://gitlab.com/eranlambooij/hedgehog-public> |
| Table d'équité de match Kazaross-XG2 | Neil Kazaross | Attribution | La table 25×25 pré-Crawford et post-Crawford | Diffusée par GNU Backgammon ; précédent MIT dans [blunderDB](https://github.com/kevung/blunderDB) |
| Modèle de Zadeh | N. Zadeh, *Management Science* 23, 986 (1977) | Publication académique | Repli au-delà de 25 points | — |

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
