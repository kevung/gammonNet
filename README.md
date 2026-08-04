# gammonNet

**Un évaluateur de positions de backgammon qui tourne dans le navigateur.**

Un réseau de neurones, une recherche expectiminimax, une table d'équité de match et des tables
exactes de fin de partie, compilés pour deux cibles : **WebAssembly** (analyse à 2-ply sur
l'appareil de la personne) et **natif** (profondeurs supérieures et rollouts).

Tout ce qui est distribué est sous **licence permissive**, sans clause d'usage — un module
WebAssembly servi à un navigateur est une **distribution**, ce qui exclut d'emblée toute brique
sous copyleft fort ou sous clause non commerciale.

## Ce que ce dépôt apporte

Les **poids du réseau ne sont pas de nous** : ils viennent de
[`alexstrehl/backgammon-ai-engine`](https://github.com/alexstrehl/backgammon-ai-engine) (MIT),
entraîné en self-play. La force brute du réseau lui revient.

> **Un modèle n'est pas un moteur, et un moteur n'est pas un artefact distribuable.**
> Ce dépôt produit les deux derniers.

| Brique | Origine | Statut |
|---|---|---|
| Poids du réseau, moteur de règles, lecteur `.bin` | Strehl, MIT | **réutilisés**, isolés derrière nos interfaces |
| Table d'équité de match **Kazaross-XG2** | œuvre de **Neil Kazaross** | **réutilisée**, vérifiée contre le rendu que GNU Backgammon charge |
| **Codec position ↔ 196 caractéristiques** | — | **neuf** — le pont n'existait nulle part |
| **Recherche expectiminimax 0→3 ply, filtrage de coups** | *idée* documentée par le manuel de GNU Backgammon ; aucun code repris | **neuf** |
| **Équité de match dans la recherche** | *architecture* de GNU Backgammon : réseau cubeless, conversion après | **neuf** |
| **Portage WebAssembly, pool de Web Workers** | — | **neuf** |
| **×9 de débit sur la passe avant** | — | **neuf**, exact au bit près |

**Ce que cela change concrètement.** Sans le codec, ce modèle n'évalue que des positions issues de
son propre moteur de self-play ; avec, il évalue **une position qu'on lui donne**. Sans la
recherche, il joue en 0-ply — et le 1-ply change déjà le coup choisi **une fois sur treize**. Sans
l'équité de match, il ne joue qu'en money, le réseau étant *cubeless* et **aveugle au score**.

Les mesures elles-mêmes sont un produit : la force publiée du modèle s'est révélée **non
reproductible**, un **bug de règles** a été trouvé dans le moteur amont, et une **probabilité
négative** dans le dénestage naïf des cinq sorties.

### Annoncé, et mesuré ici

Ce dépôt distingue partout ce qu'il **mesure** de ce qu'il **suppose**. Les écarts étaient
importants.

| | annoncé | **mesuré ici** |
|---|---|---|
| Force du modèle contre GNU Backgammon, 0-ply money | +0,0578 ppg *(auteur)* | **+0,0400 [+0,0377 ; +0,0425]** sur 10⁶ parties |
| Pénalité WebAssembly | ×1,5 à ×2,5 *(hypothèse)* | **×1,18 à ×1,29** |
| Coût d'une décision 2-ply | 245 ms *(extrapolé)* | **1 394 ms**, filtre 1/1 |
| Match de 7 points dans le navigateur | 30 à 60 s | **~2 min** sur 3,3 workers *(mise à l'échelle mesurée)* |
| PR du modèle, 0-ply → 2-ply | 1,06 → 0,22 *(auteur)* | **non vérifié** — c'est l'objet de T35 |

**Le chiffre publié n'est pas reproductible, et l'écart est expliqué.** Le harnais du dépôt de
référence, exécuté inchangé ici, donne +0,0351 — c'est-à-dire le nôtre. L'hypothèse d'un oracle
différent a été **testée et réfutée**. Notre harnais est exclu, notre chaîne est exclue, l'oracle
est exclu. La base de comparaison de ce projet est donc **+0,0400 dans cet environnement**.

**La dernière ligne est le contrepoids honnête** : la force de la configuration complète n'est pas
encore mesurée. Tant que T35 n'est pas faite, la valeur ajoutée en *force* est argumentée, pas
démontrée — et ce dépôt a pour règle de ne pas affirmer une force sans mesure.

## Pourquoi le navigateur

Mesuré sur le moteur de ce dépôt, dans un navigateur, sur la position d'ouverture :

| Profondeur | Évaluations réseau | Coût d'une décision |
|---|---|---|
| 0-ply | 16 | 1,7 ms |
| 1-ply | 7 475 | 797 ms |
| **2-ply, filtre 1/1** | **12 951** | **1 394 ms** |

Un match de 7 points représente **environ deux minutes** de calcul — par match, et par personne qui
l'analyse. Prohibitif à centraliser, **gratuit** sur l'appareil de celui qui regarde son propre
match. Vérifié sur sept plateformes : Chromium, Firefox, deux Android et deux iPhone
([détail](docs/mesures/2026-08-04-decision-navigateur.md)).

Sur ces sept plateformes — trois moteurs de navigateur, deux jeux d'instructions — l'écart au
repère natif vaut `4,77e-07`, **le même partout** : une analyse produite sur un téléphone est
identique, **au bit près**, à celle produite sur un ordinateur.

## État

**Phases 0, 1 et 2 terminées. La phase 3 est engagée.**

| | Tâches | État |
|---|---|---|
| **0** — Socle & instrument | T00 · T01 · T02 · T03 · T04 · T05 | ✅ |
| **1** — Reproduire | T10 · T11 · T12 | ✅ |
| **2** — Navigateur | T20 · T21 · T22 · T23 | ✅ |
| **3** — Profondeur & exactitude | T30 · T31 · T32 ✅ · T33 ⏳ · T34 · T35 | en cours |
| **4** — Modèle propre au projet | — | **fermée délibérément** |
| **5** — Publication | T50 | à venir |

Chaque tâche porte un rapport dans [`docs/mesures/`](docs/mesures/), et chaque rapport distingue le
**mesuré** de l'**estimé**.

**La phase 4 reste fermée.** Son critère — *« si la phase 1 échoue à confirmer la force
annoncée »* — est atteint à la lettre, et écarté : il visait *« si le modèle n'est pas assez
bon »*, or le modèle est bon. Ce qui a échoué est la reproduction d'un **chiffre publié**, pas la
valeur du réseau. La condition de réouverture reste T35.

## Démarrer

```bash
make setup     # environnement Python, sources tierces épinglées, moteur C compilé
make build     # bibliothèque native
make wasm      # module WebAssembly
make test
```

Python ≥ 3.10 et un compilateur C. Emscripten pour la cible navigateur.

## Le cadrage

| Document | Contenu |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Les règles de travail — frontière, contraintes non négociables |
| [`BRIEF.md`](BRIEF.md) | Le contexte — sources, licences, chaîne technique, protocole |
| [`PLAN.md`](PLAN.md) | Le plan d'exécution — 5 phases, 21 fiches |
| [`THIRD-PARTY.md`](THIRD-PARTY.md) | L'inventaire des briques et de leurs licences |
| [`docs/adr/`](docs/adr/) | Les décisions d'architecture et leurs motifs |

**Objectif mesurable** : atteindre un niveau équivalent ou supérieur à GNU Backgammon et à eXtreme
Gammon, et le **justifier par une mesure reproductible** dont chaque source est traçable.

## Crédits

- **Réseau et moteur de règles** — [Alexander Strehl](https://github.com/alexstrehl/backgammon-ai-engine), MIT.
- **Table d'équité de match Kazaross-XG2** — Neil Kazaross ; transcription croisée avec
  [blunderDB](https://github.com/kevung/blunderDB), MIT.
- **GNU Backgammon** — oracle de mesure, et référence de la table d'équité. Jamais une source de
  code ni de poids.
- **[HedgeHog](https://hedgehog-bg.com/)** — leur principe *« refused, not approximated »* est
  devenu la règle n° 2 de ce dépôt, et leurs chiffres publiés ont servi d'hypothèses de départ,
  depuis remplacées par nos mesures. **Ni leur code ni leurs réseaux ne sont utilisés** — voir
  [ADR-0001](docs/adr/0001-moteur-inference.md).

Inventaire complet et licences : [`THIRD-PARTY.md`](THIRD-PARTY.md).

## Licence

MIT. Voir [`LICENSE`](LICENSE).
