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

L'analyse de backgammon a un coût de calcul qui explose avec la profondeur. **Mesuré sur le moteur
de ce dépôt**, dans un navigateur, sur la position d'ouverture :

| Profondeur | Évaluations réseau | Coût d'une décision |
|---|---|---|
| 0-ply | 16 | 1,7 ms |
| 1-ply | 7 475 | 797 ms |
| **2-ply, filtre 1/1** | **12 951** | **1 394 ms** |

Une décision 2-ply coûte de l'ordre de **800 fois** une décision 0-ply. Un match de 7 points
(~300 décisions) représente **environ deux minutes** de calcul réparties sur quatre Web Workers —
par match, et par personne qui l'analyse. Ce coût est prohibitif à centraliser, et **gratuit** à
exécuter sur l'appareil de celui qui regarde son propre match.

C'est le pari de ce dépôt, et il est désormais **vérifié plutôt que supposé** : le 2-ply appartient
au navigateur. Chromium 150, Firefox 153, deux Android et deux iPhone —
[le détail](docs/mesures/2026-08-04-decision-navigateur.md).

## État

**Phases 0, 1 et 2 terminées. La phase 3 est engagée.**

| | Tâches | État |
|---|---|---|
| **0** — Socle & instrument | T00 · T01 · T02 · T03 · T04 · T05 | ✅ |
| **1** — Reproduire | T10 · T11 · T12 | ✅ |
| **2** — Navigateur | T20 · T21 · T22 · T23 | ✅ |
| **3** — Profondeur & exactitude | T30 · T31 · T32 ✅ · T33 ⏳ · T34 · T35 | en cours |
| **4** — Modèle propre au projet | — | **fermée délibérément** — voir plus bas |
| **5** — Publication | T50 | à venir |

Chaque tâche porte un rapport de mesure dans [`docs/mesures/`](docs/mesures/), et chaque rapport
distingue ce qui est **mesuré** de ce qui est **estimé**.

### Les trois chiffres qui résument l'état

**La force**, mesurée sur un million de parties : le modèle de référence bat GNU Backgammon de
**+0,0400 ppg [+0,0377 ; +0,0425]** en 0-ply money sans videau.

> Ce n'est **pas** le +0,0578 publié par l'auteur du modèle, et l'écart est expliqué. Le harnais du
> dépôt de référence, exécuté inchangé ici, donne +0,0351 [+0,0291 ; +0,0410] — c'est-à-dire le
> nôtre. L'hypothèse d'un oracle différent a été **testée et réfutée** : GNU Backgammon et
> `gnubg-nn` jouent le même coup dans 99,64 % des cas. Notre harnais est exclu, notre chaîne est
> exclue, l'oracle est exclu. **La force publiée n'est pas reproductible depuis le dépôt tel qu'il
> est publié**, et la base de comparaison de ce projet est donc **+0,0400 dans cet environnement**.

**Le navigateur** : la pénalité WebAssembly est de **×1,18 à ×1,29** — l'hypothèse de travail
allait de ×1,5 à ×2,5. Sur sept plateformes — trois moteurs de navigateur, deux jeux
d'instructions — l'écart au repère natif vaut `4,77e-07`, **le même partout** : une analyse
produite sur un téléphone est identique, au bit près, à celle produite sur un ordinateur.

**Le débit** : ×9 récupérés sur la passe avant, sans aucune concession de justesse — ×4,1 en
levant une dépendance d'accumulateur qui interdisait toute vectorisation, ×2,2 par traitement par
lot, exact au bit près.

### Pourquoi la phase 4 reste fermée

`PLAN.md` prévoit d'entraîner un modèle propre au projet **si** la phase 1 échoue à confirmer la
force annoncée. Littéralement, c'est le cas : le chiffre publié n'est pas reproductible.

Elle reste **fermée délibérément**, parce que le critère visait *« si le modèle n'est pas assez
bon »* — et le modèle est bon. **+0,0400 ppg sur GNU Backgammon est un avantage large et mesuré.**
Ouvrir le plus gros chantier du projet sur une lecture littérale l'engagerait pour une raison qui
n'est pas la bonne.

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

Ne rien réinventer de ce qui existe déjà sous licence permissive — et **vérifier ce qu'on emprunte
avant de s'y adosser**.

- **Le modèle** : [`alexstrehl/backgammon-ai-engine`](https://github.com/alexstrehl/backgammon-ai-engine)
  (MIT, poids inclus), entraîné entièrement en self-play. C'est ce que ce dépôt distribue.
- **Le moteur d'inférence** : le **C de ce même dépôt**, isolé derrière `src/gn_infer.h`. Le choix
  a été tranché sur mesure en T22 — [ADR-0001](docs/adr/0001-moteur-inference.md).
- **La table d'équité de match** : **Kazaross-XG2**, œuvre de **Neil Kazaross**, vérifiée entrée
  par entrée contre le rendu que GNU Backgammon charge par défaut.
- **La mesure** : GNU Backgammon comme oracle — un instrument de référence, jamais une source
  d'apprentissage ni de code.

### Ce que ce dépôt doit à HedgeHog, et ce qu'il ne lui doit pas

[HedgeHog](https://hedgehog-bg.com/) a beaucoup compté dans la conception de ce projet, et **son
code n'y est pas**. La distinction mérite d'être faite précisément plutôt que laissée floue.

**Ce qui n'est pas utilisé.** Ni leurs réseaux — ils portent une clause non commerciale,
incompatible avec l'engagement de licence de ce dépôt — ni le code de
[`hedgehog-public`](https://gitlab.com/eranlambooij/hedgehog-public), pourtant MIT. Ce second point
a été **tranché sur mesure** : leur argument de vitesse est l'accumulation incrémentale NNUE, qui
n'optimise que la couche d'entrée — **19 % des 528 389 multiplications-accumulations de ce
réseau** — et que le mode dense désactive de toute façon. Les ×9 de débit obtenus l'ont été
ailleurs, sur des causes indépendantes du moteur.

**Ce qui a compté.** Leur discipline, d'abord : *« A model this build cannot evaluate is refused,
not approximated »* est devenue la règle n° 2 de [`CLAUDE.md`](CLAUDE.md), et elle a attrapé plus
d'une erreur ici. Leurs chiffres publiés, ensuite, qui ont servi d'**hypothèses de départ** — la
frontière 2-ply/3-ply, le budget navigateur, la pénalité WebAssembly.

**Et ces hypothèses ont toutes été remplacées par nos propres mesures.** La pénalité WebAssembly
qu'ils laissaient estimer entre ×1,5 et ×2,5 vaut ×1,18. Le coût d'une décision 2-ply qu'on
extrapolait de leurs débits est mesuré ici, sur notre moteur, dans un vrai navigateur.

**C'était l'échafaudage, pas la structure.** Le citer ainsi est plus juste — envers eux comme
envers l'auteur du modèle réellement embarqué — que de laisser croire que leur moteur nous
propulse. L'inventaire complet est dans [`THIRD-PARTY.md`](THIRD-PARTY.md).

### Ce qui restait à construire, et qui l'est

Le codec entre les formats de position usuels et l'entrée du réseau ; une recherche
expectiminimax 0→3 ply ; l'équité de match, branchée **dans** la recherche — un 2-ply qui
maximiserait l'équité cubeless aux niveaux intermédiaires est faux en match, et aucun test money
ne le dirait ; le portage WebAssembly et son ordonnancement en Web Workers.

Reste : les tables de fin de partie, la décision de videau, le round-robin final et la
publication. Le détail est dans [`PLAN.md`](PLAN.md).

## Licence

MIT. Voir [`LICENSE`](LICENSE) et [`THIRD-PARTY.md`](THIRD-PARTY.md).
