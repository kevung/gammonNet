# gammonNet

Un **évaluateur de positions de backgammon** : un réseau de neurones, une recherche
expectiminimax, une table d'équité de match et des tables exactes de fin de partie, compilés pour
le navigateur (WebAssembly) et pour le natif.

```{admonition} Ce que ce projet affirme, et comment le vérifier
:class: important

**Niveau équivalent à GNU Backgammon en 2-ply** — mesuré sur 50 000 paires de parties en money
(−0,0119 ppg, IC 95 % [−0,0310 ; +0,0074]) et 50 000 paires en match de 7 points (50,42 % de MWC,
[50,16 ; 50,69]).

**« Supérieur » n'est pas établi**, et **eXtreme Gammon n'a pas été mesuré**.

Chaque chiffre de cette documentation renvoie à sa fiche de mesure et à la commande qui le
reproduit. L'artefact publié contient de quoi **vérifier vous-même** qu'il donne les bons
résultats, sans nous croire sur parole.
```

## Les trois volets

::::{grid} 1 1 3 3

:::{grid-item-card} Manuel utilisateur
:link: manuel/index
:link-type: doc

Installer, choisir un réglage, lire une analyse, vérifier l'artefact. Ce qu'il faut savoir avant
de s'en servir.
:::

:::{grid-item-card} Documentation scientifique
:link: science/index
:link-type: doc

L'architecture, le protocole de mesure, les benchmarks, les optimisations — et **toutes les
hypothèses et limites**, y compris celles qui ne nous flattent pas.
:::

:::{grid-item-card} Documentation développeur
:link: developpeur/index
:link-type: doc

L'architecture du dépôt, les invariants qui ne se voient pas, comment reproduire chaque mesure.
:::

::::

## En bref

| | |
|---|---|
| Force, money cubeful | **−0,0119 ppg** [−0,0310 ; +0,0074], 50 000 paires |
| Force, match 7 points | **50,42 % de MWC** [50,16 ; 50,69], 50 000 paires |
| Taux d'erreur (PR), 2-ply | **0,273** [0,190 ; 0,364] — référence publiée : 0,22 |
| Accord coup par coup avec gnubg, sur un vrai match | **86,3 %**, aucun désaccord au-dessus de 0,02 d'équité |
| Coût d'une décision 2-ply, natif | **0,306 s** |
| Coût d'un match de 7 points, navigateur, 8 workers | **74 s** |
| Taille de l'artefact | **1,06 Mio** de poids en float16 |

```{toctree}
:hidden:
:maxdepth: 2

manuel/index
science/index
developpeur/index
```

---

*English version: <a href="../en/">/en/</a>*
