# CLAUDE.md — gammonNet

> Trois documents, à lire dans cet ordre : **`CLAUDE.md`** (les règles) → **`BRIEF.md`**
> (le contexte, les sources, les licences) → **`PLAN.md`** (les fiches de tâches).
> **Lire les trois en entier avant de proposer du code.**

## Ce qu'est gammonNet

Un **évaluateur de positions de backgammon** : un réseau de neurones, une recherche
expectiminimax, une table d'équité de match et des tables exactes de fin de partie, compilés
pour **deux cibles** — WebAssembly (navigateur, 2-ply) et natif (profondeurs supérieures et
rollouts).

Il produit deux choses : un **artefact** (des poids versionnés, dont la force est mesurée) et
une **bibliothèque d'inférence**.

## LA règle de frontière

> **Ce dépôt évalue une position. Il ne connaît pas ses appelants.**

- Réseau, recherche, équité de match, fins de partie, entraînement, mesure de force → **ici**.
- Stockage, bibliothèque de parties, import de matchs, recherche multi-critères, interface
  utilisateur → **ailleurs**.

Aucune notion d'utilisateur, de compte, de session ni de persistance n'entre dans ce dépôt. Une
position entre, une évaluation sort.

## Les trois règles non négociables

### 1. Rien de non-libre dans un artefact distribué

Un module WebAssembly servi à un navigateur **est une distribution**. Donc :

| Interdit | Motif |
|---|---|
| Poids GNU Backgammon, ou tout dérivé de ceux-ci | GPL-3 |
| Code GNU Backgammon copié dans le pipeline | Œuvre dérivée |
| Tout réseau sous clause non commerciale, ou un fine-tuning d'un tel réseau | Hors du périmètre de licence de ce dépôt |
| Copier du code bgsage | MPL-2.0 vérifiée (et non AGPL-3 comme d'abord noté) — copyleft de fichier ; lecture et réimplémentation d'idées permises, voir `BRIEF.md` §3.5 |

| Autorisé | Fondement |
|---|---|
| Lire le code et le manuel de GNU Backgammon | La GPL régit la distribution, pas la lecture |
| Faire tourner GNU Backgammon comme **oracle de mesure** | FSF, GPL FAQ : *« The output of a program is not, in general, covered by the copyright on the code of the program. »* |
| Réimplémenter des idées documentées (élagage, filtres de coups, classification) | Une idée n'est pas une œuvre |
| Tables de fin de partie, quelle que soit leur origine | Calcul exact reproductible, pas une œuvre de création |
| Table d'équité de match Kazaross-XG2, avec attribution à Neil Kazaross | Œuvre de N. Kazaross ; précédent MIT dans [blunderDB](https://github.com/kevung/blunderDB) |
| Code et poids sous MIT | Sous réserve de conserver la notice |

**En cas de doute sur une source : ne pas l'intégrer, et poser la question.** Une brique
juridiquement douteuse embarquée dans un artefact distribué est le seul type d'erreur qu'on ne
peut pas corriger par un correctif.

### 2. Aucune force n'est affirmée sans mesure

> **Un réseau à qui l'on donne une entrée qu'il n'a jamais vue retourne cinq probabilités
> parfaitement plausibles.**

C'est le mode de défaillance central du domaine, et il est silencieux : un moteur peut se tromper
d'une demi-unité d'équité sur une fraction notable des positions sans qu'aucun signe extérieur ne
le trahisse. D'où la règle : **un modèle qu'un build ne sait pas évaluer est refusé, jamais
approximé.**

Deux conséquences pratiques :

- **Le harnais de mesure se construit avant le modèle**, jamais après. On ne peut pas améliorer
  ce qu'on ne sait pas mesurer.
- **Un modèle qu'un build ne sait pas évaluer est refusé, jamais approximé.** Une entrée
  manquante qui vaut zéro par défaut est un bug qui ne se voit pas.

Toute affirmation de force cite : le protocole, le volume, et l'intervalle de confiance. En
dessous d'environ un million de parties par paire, les écarts entre bons moteurs ne sortent pas
du bruit.

### 3. Une conclusion de performance se mesure, elle ne se déduit pas

Aucun chiffre de débit, de latence ou de taille ne se tire d'une lecture de code ou d'une
extrapolation. La pénalité WebAssembly, en particulier, est **une inconnue tant qu'elle n'est
pas chronométrée dans un vrai navigateur** — et toute la frontière 2-ply / 3-ply en dépend.

Un rapport doit toujours dire s'il énonce **une mesure** ou **une hypothèse**.

## Conventions

**Langue** — français pour la documentation et les échanges ; **anglais** pour le code, les
identifiants et les commentaires de code.

**Code** — C/C++ pour l'inférence (cibles WebAssembly via Emscripten, et natif), Python pour
l'entraînement et la mesure. Pas de dépendance système exotique : la cible est « ça compile avec
un compilateur et rien d'autre ».

**Tests** — tout composant numérique a un test de non-régression sur un corpus de positions
figées. Un changement de poids ou d'encodage qui déplace une sortie doit le faire
**visiblement**.

**Commits** — atomiques et bien nommés, au fil de l'eau, sans attendre une demande.

**Worktrees** — toute tâche non triviale démarre par
`git worktree add ../gammonNet-<tâche> -b <branche>`. Ne pas travailler sur `main`. Une fois les
tests verts : merger, puis nettoyer. Pas de worktree orphelin.

**Attribution** — `THIRD-PARTY.md` est tenu à jour à chaque ajout de dépendance : nom, auteur,
licence, lien, et **ce qui est effectivement utilisé**. La notice MIT doit aussi vivre dans
l'artefact lui-même (bannière du build WebAssembly, ou fichier de licence servi à côté).

**Nomenclature** — un réseau ne change de nom que si ses **poids** changent. Ni le couplage à
une table de fin de partie, ni la compilation en WebAssembly, ni une conversion de format n'en
font un réseau nouveau. Voir `BRIEF.md`.

## Garde-fous d'agent

- **Ne jamais conclure « ça marche » sans avoir lancé la commande et lu sa sortie.**
- **Ne jamais annoncer une force sans le protocole, le volume et l'intervalle de confiance.**
- **Ne jamais intégrer une source dont la licence n'a pas été lue.** Le nom du dépôt ne suffit
  pas : les modèles peuvent avoir une licence différente du code qui les charge. Un dépôt MIT peut
  parfaitement publier des poids sous clause non commerciale.
- **Ne pas élargir le périmètre.** L'entraînement d'un modèle propre au projet (phase 4) est
  **conditionnel** au résultat de la phase 1. Ne pas l'engager avant.

## Les phases, dans l'ordre

Le détail est dans `PLAN.md`, une fiche par tâche, chacune avec son critère d'acceptation
mesurable.

| Phase | Objet | Tâches | Condition de sortie |
|---|---|---|---|
| **0** | Socle & instrument de mesure | T00–T05 | Débits réels mesurés ; round-robin exécutable et antisymétrique |
| **1** | Reproduire les chiffres publiés | T10–T12 | L'écart au benchmark de référence est mesuré **et expliqué** |
| **2** | Portage WebAssembly & navigateur | T20–T23 | Pénalité WASM chiffrée ; verdict explicite sur le 2-ply, mobile compris |
| **3** | Profondeur & exactitude | T30–T35 | Le PR descend conformément à la référence (1,06 → 0,50 → 0,22) |
| **4** | Modèle propre au projet | T40–T42 | **Conditionnelle, restée fermée** — T35 n'a pas révélé de plafond ; T41 est remplacée par T71 |
| **5** | Publication de l'artefact | T50 | Force mesurée, notice et attribution en place |
| **7** | Dépasser — programme du plan de recherche (`docs/recherche/`, §14–§15) | T70–T80 | **Choisie le 2026-08-27** — l'avantage 2-ply par décision sort de zéro (T71, arbitré par T70) et la vitesse gagnée est mesurée (T72–T73) |

**Chemin critique** : `T00 → T01 → T02 → T10 → T20 → T21 → T30 → T32 → T35 → T50`.
**T02 (le codec de position) est le goulot** — une erreur y est silencieuse et contamine toutes
les mesures suivantes.

**La phase 4 n'est pas le but.** Si le modèle MIT existant tient ses promesses, elle devient un
chantier de différenciation qu'on choisit, pas un passage obligé. Ne pas l'ouvrir par
enthousiasme.

## Pointeurs

- `BRIEF.md` — sources, licences, chaîne technique, recette d'entraînement, protocole de mesure.
- `PLAN.md` — le plan d'exécution : 29 fiches de tâches, chacune avec son critère d'acceptation.
- `THIRD-PARTY.md` — l'inventaire des briques et de leurs licences.
