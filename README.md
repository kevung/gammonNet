# gammonNet

**Un évaluateur de positions de backgammon qui tourne dans le navigateur.**

Un réseau de neurones, une recherche expectiminimax, une table d'équité de match et des tables
exactes de fin de partie, compilés pour deux cibles : **WebAssembly** (analyse à 2-ply sur
l'appareil de la personne) et **natif** (profondeurs supérieures et rollouts).

Tout ce que ce dépôt distribue est sous **licence permissive**, sans clause d'usage. C'est une
contrainte de conception, pas une préférence : un module WebAssembly servi à un navigateur est
une **distribution**, ce qui exclut d'emblée toute brique sous copyleft fort ou sous clause non
commerciale.

## Pourquoi

L'analyse de backgammon a un coût de calcul qui explose avec la profondeur. D'après les débits
publiés par [HedgeHog](https://hedgehog-bg.com/) sur un cœur de Ryzen 5 3600 :

| Profondeur | Débit | Coût par décision |
|---|---|---|
| 0-ply | 195 382 pos/s | ~0,1 ms |
| 1-ply | 687 /s | 1,5 ms |
| **2-ply** | **4,08 /s** | **245 ms** |
| 3-ply | 0,43 /s | 2,3 s |

Une décision 2-ply coûte de l'ordre de **2 400 fois** une décision 0-ply. Un match de 7 points
(~300 décisions) représente donc ~75 secondes de calcul — par match, et par personne qui
l'analyse. Ce coût est prohibitif à centraliser, et **gratuit** à exécuter sur l'appareil de
celui qui regarde son propre match.

C'est le pari de ce dépôt : le 2-ply appartient au navigateur.

## État

**Phase 0 — le socle est en place.** Aucune force n'est encore produite, et c'est normal :
on construit l'instrument avant d'avoir quoi que ce soit à mesurer.

| Tâche | État |
|---|---|
| **T00** — Amorçage du dépôt et de l'environnement | ✅ [rapport](docs/mesures/2026-08-03-T00-socle.md) |
| **T01** — Position et coups légaux | ✅ [rapport](docs/mesures/2026-08-03-T01-regles.md) |
| **T02** — Codec ↔ 196 caractéristiques ⚠️ *goulot* | ✅ [rapport](docs/mesures/2026-08-03-T02-codec.md) |
| **T03** — Oracle GNU Backgammon | à faire |
| **T04** — Harnais de round-robin | à faire |
| **T05** — Banc de débit | à faire |

### Démarrer

```bash
make setup     # environnement Python, sources tierces épinglées, moteur C compilé
make build     # compile build/libgammonnet.so (cible native)
make env       # consigne la machine et la chaîne d'outils — toute mesure les cite
make test
```

Prérequis : Python ≥ 3.10 et un compilateur C. Emscripten n'est requis qu'en phase 2.

### Le cadrage

| Document | Contenu |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Les règles de travail — frontière, contraintes non négociables, conventions |
| [`BRIEF.md`](BRIEF.md) | Le contexte — sources, licences, chaîne technique, protocole de mesure |
| [`PLAN.md`](PLAN.md) | Le plan d'exécution — 5 phases, 21 fiches de tâches |
| [`THIRD-PARTY.md`](THIRD-PARTY.md) | L'inventaire des briques et de leurs licences |

La roadmap est suivie dans les issues.

## Objectif mesurable

Atteindre un niveau **équivalent ou supérieur à GNU Backgammon et à eXtreme Gammon**, et
pouvoir le **justifier par une mesure reproductible** dont chaque source est traçable.
« Équivalent » n'est pas une appréciation : c'est un nombre issu du protocole décrit dans
[`BRIEF.md`](BRIEF.md) — un round-robin, avec son volume et son intervalle de confiance.

## Approche

Ne rien réinventer de ce qui existe déjà sous licence permissive.

- **Le modèle** : [`alexstrehl/backgammon-ai-engine`](https://github.com/alexstrehl/backgammon-ai-engine)
  (MIT, poids inclus), entraîné entièrement en self-play. Mesuré en tête du benchmark public de
  HedgeHog, devant GNU Backgammon et eXtreme Gammon.
- **Le moteur** : [`hedgehog-public`](https://gitlab.com/eranlambooij/hedgehog-public) (MIT)
  fournit un évaluateur NNUE et une recherche expectiminimax 0–2 ply en C++17 sans dépendance.
- **La mesure** : GNU Backgammon comme oracle — un instrument de référence, jamais une source
  d'apprentissage ni de code.

Ce qui reste réellement à construire : le pont entre les formats de position usuels et l'entrée
du réseau, une recherche 2-ply correcte en **match play**, l'intégration des tables exactes de
fin de partie, et le portage WebAssembly. Le détail est dans [`PLAN.md`](PLAN.md).

## Licence

MIT. Voir [`LICENSE`](LICENSE) et [`THIRD-PARTY.md`](THIRD-PARTY.md).
