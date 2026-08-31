# L'architecture du dépôt

## La règle de frontière

> **Ce dépôt évalue une position. Il ne connaît pas ses appelants.**

| Ici | Ailleurs |
|---|---|
| réseau, recherche, équité de match, fins de partie | stockage, bibliothèque de parties |
| entraînement, mesure de force | **import de matchs**, recherche multi-critères |
| | interface utilisateur |

Aucune notion d'utilisateur, de compte, de session ni de persistance n'entre ici. C'est pourquoi
l'analyse d'un match fait **lire le fichier par GNU Backgammon** et ne consomme que des
identifiants de position.

## Les répertoires

| | |
|---|---|
| `src/` | le moteur en C : règles, encodage, inférence, recherche, équité de match, videau, tables |
| `python/gammonnet/` | l'enveloppe `ctypes` — aucune logique métier, seulement le passage de frontière |
| `bench/` | les instruments de mesure. Un banc par question |
| `tests/` | ~1 500 tests, dont le corpus de non-régression |
| `tools/` | export des poids, entraînement du réseau d'élagage, empaquetage de l'artefact |
| `wasm/` | le portage navigateur : module C, API JavaScript, pool de workers, pages de mesure |
| `docs/mesures/` | **une fiche par mesure** — protocole, volume, intervalle, commande |
| `docs/etudes/` | les idées instruites mais non implémentées, et le registre des lectures |
| `vendor/` | les sources tierces, à un commit épinglé. Gitignoré |

## Les deux cibles

Le **même** code C sert les deux. `WASM_SOURCES` dans le `Makefile` doit donc suivre `SOURCES` :
quand la recherche a gagné des dépendances pendant la phase 3, la cible WebAssembly a cessé de
compiler — ce qui est **la bonne façon d'échouer**, mais ne s'est vu qu'à la construction suivante.

## Le flux d'une décision

```
Position ID
   └─ gn_position_from_id
        └─ gn_search_plays
             ├─ gn_legal_plays              (règles)
             ├─ passe d'élagage             (petit réseau, si configuré)
             ├─ passe superficielle         (grand réseau, par lots)
             │    └─ evaluate_cheap : table exacte, puis cache, puis réseau
             ├─ value_sweep                 (probabilités → équité, money ou match)
             └─ passe profonde              (récursion sur les filter[d] meilleurs)
```

## Les points d'entrée

| | |
|---|---|
| `gn_search_plays` | les coups classés — ce qu'une analyse affiche |
| `gn_best_play` | le meilleur, quand seul le coup compte |
| `gn_search_equity` | l'équité **avant le jet** — ce dont une décision de videau a besoin |
| `gn_search_probs` | la distribution avant le jet |
| `gn_cube_decide` | la décision de videau |
| `gn_rollout` | l'arbitre |
