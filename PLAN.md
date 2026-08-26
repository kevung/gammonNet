# gammonNet — plan d'exécution

> Se lit après `CLAUDE.md` (les règles) et `BRIEF.md` (le contexte, les sources, les licences).
>
> **Chaque fiche porte un critère d'acceptation mesurable.** Une tâche n'est pas « finie » parce
> que le code existe : elle est finie quand son critère est **vérifié par une commande dont la
> sortie a été lue**.

## Vue d'ensemble

```
Phase 0 — Socle & instrument       T00 T01 T02 T03 T04 T05      (aucune force produite)
Phase 1 — Reproduire               T10 T11 T12                  (certitude, pas force)
Phase 2 — Navigateur               T20 T21 T22 T23              (la frontière se chiffre)
Phase 3 — Profondeur & exactitude  T30 T31 T32 T33             (la recherche, les fins)
                                   T36 T37 T38 T39 T34 T35     (le videau, puis le verdict)
Phase 4 — Modèle propre au projet  T40 T41 T42                  ← CONDITIONNEL
Phase 5 — Publication              T50
```

**Chemin critique** :
`T00 → T01 → T02 → T10 → T20 → T21 → T30 → T32 → T36 → T38 → T34 → T35 → T50`.

Tout le reste peut se paralléliser autour. **T02 (le codec) est le goulot** : rien de mesurable
n'existe avant lui, et une erreur à cet endroit invalide silencieusement toutes les mesures
ultérieures. Lui consacrer le soin qu'on donnerait à un chiffrement.

**Règle de séquencement** : la phase 4 ne s'ouvre **que si** la phase 1 échoue à confirmer la
force annoncée du modèle de référence, ou si la phase 3 révèle un plafond. Ne pas l'engager par
enthousiasme.

> ### La phase 4 reste FERMÉE — décidé le 2026-08-04
>
> **Le critère est atteint à la lettre, et écarté délibérément.** T11 a établi que le +0,0578
> publié n'est pas reproductible, et l'hypothèse de l'oracle a été testée puis **réfutée** : GNU
> Backgammon et `gnubg-nn` jouent le même coup dans 99,64 % des cas. Notre harnais est exclu,
> notre chaîne l'est aussi, l'oracle l'est aussi.
>
> Mais le critère visait *« si le modèle n'est pas assez bon »*, et **le modèle est bon** :
> +0,0400 ppg [+0,0377 ; +0,0425] sur GNU Backgammon est un avantage large et mesuré. Ce qui a
> échoué, c'est la reproduction d'un **chiffre publié**, pas la valeur du réseau.
>
> Ouvrir le plus gros chantier du projet sur une lecture littérale l'engagerait pour une raison
> qui n'est pas la bonne. **La condition de réouverture reste T35** : si le round-robin complet
> révèle un plafond, la question se reposera sur des données neuves.

---

## Recadrage vers l'objectif — *le 2026-08-06*

> **Question posée** : quel chemin pour un moteur d'évaluation **en match, avec videau**, au moins
> aussi bon que GNU Backgammon ? Cette section y répond. Elle ne remplace rien de ce qui précède ;
> elle ordonne ce qui reste.

### Ce que le seul chiffre de force du projet dit — et ne dit pas

L'unique mesure de force du dépôt est **+0,0400 ppg [+0,0377 ; +0,0425]** contre GNU Backgammon,
sur 10⁶ parties (T11). Elle est solide. Elle est aussi mesurée en **0-ply, cubeless, money** —
c'est-à-dire dans la configuration la plus éloignée de l'objectif.

**Trois transports séparent ce chiffre de la cible**, et aucun n'est gratuit :

| Transport | Ce qu'on en sait |
|---|---|
| 0-ply → 2-ply | L'auteur du modèle mesure lui-même un **rétrécissement** : +57,8 mEq/partie en 0-ply, +45,0 en 2-ply, avec son hypothèse que *« gnubg's base networks are more tuned for deep search than ours »*. Non vérifié ici |
| cubeless → cubeful | Aucun code. `gn_search.h` : *« The cube is still absent »* |
| money → match | La table est branchée dans la recherche (T32), mais aucune force n'a été mesurée en match |

**Aucun des trois ne se déduit du chiffre de départ.** C'est la règle 3 de `CLAUDE.md` appliquée à
la force plutôt qu'au débit : une conclusion se mesure, elle ne s'extrapole pas.

### Les quatre paliers, et la règle qui les sépare

> **Chaque palier se termine par une mesure qui autorise ou interdit le suivant.** Un palier dont
> la mesure n'a pas été lue ne libère pas celui d'après.

| | Palier | Fiches | Ce que sa mesure décide |
|---|---|---|---|
| **A** | **Diagnostic — avant de construire** | T36, T37 | Le réseau tient-il sous la profondeur, et sa distribution est-elle assez calibrée pour porter un videau ? |
| **B** | **Exactitude en fin de partie** | T38 *(et le reste de T33)* | Ce que les tables exactes rapportent, et à quel prix dans l'artefact |
| **C** | **Le videau** | T34, puis T39 si nécessaire | Est-on au niveau sur la décision de videau, arbitré autrement que par la ressemblance à gnubg ? |
| **D** | **L'arbitre et le verdict** | T39, T35 | L'objectif est-il atteint, et sinon la phase 4 s'ouvre-t-elle ? |

**Le palier A passe avant le palier C, et ce n'est pas de la prudence rituelle.** Les deux mesures
de A sont bon marché et disponibles maintenant ; elles disent si le videau se construit sur un
réseau qui tiendra. Construire C d'abord, c'est risquer de mesurer la qualité d'un modèle cubeful
posé sur une distribution biaisée, et de conclure sur le mauvais maillon.

### La difficulté que le plan doit regarder en face : *« mieux que »* ne se mesure pas par ressemblance

Le critère actuel de T34 demande « le taux d'accord avec l'oracle ». **L'accord avec GNU Backgammon
ne peut pas établir qu'on lui est supérieur** — au mieux qu'on lui ressemble, et un moteur qui
ressemble parfaitement à gnubg est exactement aussi bon que gnubg, jamais meilleur. Sur les
décisions où l'on diffère, il faut un **arbitre tiers**.

D'où **T39**, promue de commodité à brique du chemin critique. Sa réserve est nommée d'avance :
un rollout conduit par *notre* réseau nous favorise, un rollout gnubg les favorise. Les deux
colonnes seront produites et publiées ; aucune ne sera présentée seule.

### Ce que le dépôt du 2026-08-06 change

Deux bases de fin de partie produites par GNU Backgammon ont été déposées dans le projet :

| Fichier | En-tête | Portée |
|---|---|---|
| `gnubg_os13.bd` — 1,6 Gio | `gnubg-OS-13-15-1-1-0` | **Unilatérale**, 13 points, 15 pions |
| `gnubg_ts6x11.bd` — 1,2 Gio | `gnubg-TS-06-11-1` | **Bilatérale**, 6 points, 11 pions — équités exactes, **cubeful** |

`CLAUDE.md` les autorise sans réserve : *« tables de fin de partie, quelle que soit leur origine —
calcul exact reproductible, pas une œuvre de création »*.

**La bilatérale est la pièce qui manquait au videau en course.** Une décision de videau en fin de
course se joue sur des marges où l'approximation du réseau est la plus grossière ; une table
bilatérale y donne l'équité cubeful exacte, sans modèle intermédiaire.

**Mais 2,8 Gio ne partent pas dans un navigateur.** Ces bases sont un actif **natif et de mesure**.
Le trajet vers l'artefact distribué reste celui de T33 — notre propre table, calculée, tronquée à
ce que le budget navigateur autorise. Les deux ne se remplacent pas : les bases gnubg deviennent
**la référence contre laquelle notre table embarquée se mesure**.

### Ce que l'exécution du 2026-08-06 a changé au plan lui-même

Trois constats de terrain, chacun assis sur une mesure, modifient l'ordre et les moyens.

**1. `gnubg-nn` est hors-jeu au-delà du 0-ply.** Segfault reproductible sur les positions de
bearoff, base unilatérale activée ou non. La référence est **GNU Backgammon lui-même**, via son
mode Python — ce qui apporte en prime la vraie table d'équité, les vraies bases de fin de partie et
`cfevaluate`, dont T34 aura besoin. Voir `docs/prerequis.md`.

**2. L'instrument de T36 change : par décision, plus par partie.** Le round-robin en 2-ply
demandait ~24 h pour douze mille parties et aurait rendu ±0,017, quand l'effet à détecter vaut
~0,02 — donc « on ne peut pas conclure », après une journée de machine. Une partie ne rend **qu'un**
point de donnée et en contient cinquante-cinq. Mesurer la perte d'équité par décision contre une
référence commune est deux ordres de grandeur plus sensible.

En fin de partie, l'arbitre est **exact** (T38, table bilatérale) : sans variance et sans réserve.
En contact, il faut des rollouts — donc **T39 remonte au chemin critique**, et le nouvel ordre est
`T39 → T36 → T34`.

**3. Notre moteur est ~330 fois plus lent que gnubg au 2-ply.** 3,29 s contre ~10 ms, entièrement
expliqué par 38 244 évaluations à 86 µs — ~~pas de gaspillage caché~~ **amendé le 2026-08-26 : cette
comptabilité datait d'avant l'inférence par lot.** Le lot a rendu une évaluation ~8,5× moins chère,
et « pas de gaspillage caché » n'y a pas survécu — à ce point de fonctionnement, retirer 4,7× des
évaluations chères déplace le temps par décision de moins de 3 %
(`docs/mesures/2026-08-26-T3A-branchement.md`). Ce qui borne une décision est désormais la recherche
elle-même : génération des coups légaux, copies, tris, récursion. Ses réseaux d'élagage rendent son
coût quasi plat avec la profondeur. Cela engage la faisabilité de T35 **et** le budget navigateur,
et ouvre une fiche à part : cache d'évaluation, inférence par lots, réseaux d'élagage distillés de
**notre** réseau.

> **Une réserve à ne pas perdre.** T31 n'a mesuré la qualité du filtre qu'à la **racine** — sa
> référence était un 2-ply dont l'intérieur n'était pas filtré. La garde **intérieure**, dont
> dépend tout 2-ply jouable en volume, **n'a jamais été mesurée en qualité**. C'est un choix de
> coût, pas un choix mesuré, et il doit être nommé partout où il sert.

### L'objectif, reprécisé — *le 2026-08-07*

> **Formulation du propriétaire du projet** : un moteur d'évaluation en **match play avec
> videau**, offrant des profondeurs **jusqu'au 3-ply**, **aussi bon que GNU Backgammon** — mieux
> si on y arrive —, et qui tourne **raisonnablement vite dans un navigateur** pour analyser des
> positions et des matchs en local.

Deux choses changent par rapport au cadrage initial du `BRIEF.md` :

1. **Le 3-ply entre au périmètre navigateur.** Le cadrage initial visait le 2-ply dans le
   navigateur et renvoyait les profondeurs supérieures au natif. La vitesse cesse donc d'être un
   confort : c'est une **exigence produit**. Elle avait perdu son statut de levier de *force* — la
   mesure a montré que le calcul supplémentaire se perd — mais elle en gagne un autre, celui de
   condition d'usage.

2. **Le critère de succès est la parité, la supériorité est l'extension.** « Aussi bon que
   GNU Backgammon, voire meilleur si on réussit. » Cela change la lecture de T36 du tout au tout.

### Pourquoi l'objectif est atteignable **sans** la phase 4

La mesure de T36 disait : notre avantage s'annule au 2-ply. Lue contre un objectif de
*supériorité*, c'était une mauvaise nouvelle. Lue contre un objectif de **parité**, c'est
l'inverse : **la parité au jeu de pions en 2-ply est déjà mesurée** — +0,00007 par décision
[−0,00005 ; +0,00019] par l'arbitre de gnubg, zéro dans l'intervalle, léger positif au point
d'estimation.

Le chemin vers l'objectif est donc :

| Étape | État | Ce qui manque |
|---|---|---|
| Jeu de pions en contact, parité 2-ply | **mesurée** | rien |
| Fin de partie | déficit chiffré (0,00028/déc.) | **brancher** le lecteur natif dans la recherche — gain certain |
| Videau, money et match | absent | **T34**, avec sa référence exacte de validation |
| Vitesse 3-ply navigateur | 60–96 s/déc. natif | **T3A** — cache, inférence par lots, réseaux d'élagage distillés *(les trois faits ; l'élagage rend ×1,36, voir le 2026-08-26)* |
| Verdict | — | **T35**, en match, cubeful, réglage nommé |

**La phase 4 redevient ce que le plan voulait qu'elle soit** : un chantier de différenciation
qu'on choisit si l'on veut *dépasser* gnubg au jeu de pions — pas un passage obligé vers l'objectif.

### Répartition du travail — *à partir du 2026-08-07*

L'orchestration, la conception et la validation des mesures restent au fil principal. **Les
sous-tâches d'implémentation sont déléguées à des agents économiques** (Sonnet), chacun dans son
worktree, avec un cahier des charges fermé : les décisions de conception sont prises avant le
lancement, l'agent implémente et mesure, le fil principal vérifie et fusionne.

### Où en est le chemin — *au 2026-08-07*

Trois mesures ont refermé des questions et en ont ouvert d'autres. La carte des leviers, telle
qu'elle se lit maintenant :

| Levier | État | Fondement |
|---|---|---|
| **Tables de fin de partie** | **ouvert, gain certain** | T38 : notre réseau perd 0,00028/décision là où gnubg, qui consulte sa table, ne perd rien. Lecteur natif écrit et croisé ; reste à le brancher dans la recherche |
| **Videau (T34)** | **ouvert, potentiel inconnu** | Seul composant totalement absent. Et il dispose d'une référence **exacte** pour se valider : la table bilatérale porte les équités cubeful |
| ~~Profondeur comme levier de force~~ | **fermé** | Notre 3-ply contre leur 2-ply, à 180 fois leur coût, ne gagne rien de plus que notre 2-ply |
| **Réentraîner sous recherche (T41)** | le levier qui reste pour le jeu de pions | L'avantage s'annule au 2-ply, et ce n'est pas la faute du filtre |

**Ce que cela impose à l'ordre des travaux.** La phase 4 ne s'ouvre toujours que sur T35 ; c'est la
règle et elle tient. Mais les deux voies bon marché qui restent doivent être épuisées d'abord — et
elles le seront vite, l'une étant du branchement et l'autre une fiche déjà cadrée.

**Ce que cela impose au ton des rapports.** Sur le jeu de pions en contact, il n'existe plus de voie
bon marché vers une supériorité. Un rapport qui laisserait croire le contraire serait faux.

### Le protocole d'étude de GNU Backgammon

`CLAUDE.md` autorise déjà « lire le code et le manuel » et « réimplémenter des idées documentées ».
Le fondement est solide — la GPL régit la distribution, pas la lecture ; et le droit d'auteur
protège l'expression, pas l'idée. Ce qui manquait est la **discipline qui rend la position
défendable trois ans plus tard**, quand personne ne se souvient de ce qui a été lu.

Elle est écrite dans [`docs/etudes/`](docs/etudes/), avec son registre. En un mot : trois niveaux
— la littérature publiée d'abord, le manuel ensuite, le code source en dernier recours et sous
protocole — et **aucune constante réglée à la main n'est jamais transcrite**.

**Pour le videau en particulier, la recommandation est de ne pas lire la source du tout** : le
modèle de Janowski et la dérivation des points de prise depuis la table d'équité de match sont
publiés et suffisent. Garder la composante la plus délicate du projet entièrement traçable à de la
littérature publique est un avantage net, et gratuit.

---

## Répartition entre machines — deux pistes *(à partir du 2026-08-03)*

> **Si vous êtes un agent qui exécute la roadmap : cette section vous concerne, lisez-la avant de
> prendre la tâche suivante.**

Le travail est réparti sur deux machines aux profils **complémentaires**, pas concurrents.

| | la machine de calcul — **piste A** | machine de bureau — **piste B** |
|---|---|---|
| Profil | 16 cœurs / 32 fils, 94 Gio, 2 GPU CUDA, RHEL 8, **GCC 8.5** | 16 cœurs, 4 Gio libres, pas de GPU, **GCC 16.1**, Firefox 153, Node 26 |
| Vocation | Gros volumes : oracle, round-robins, entraînement | Navigateur : Emscripten, WASM, bancs de débit client |
| Réseau | — | Sortie internet, **pas de LAN** |

**La piste navigateur ne peut pas tourner sur la machine de calcul** — aucun navigateur, et une chaîne C++17
ancienne. **La piste calcul ne peut pas tourner sur la machine de bureau** — 4 Gio libres et pas
de GPU. La séparation n'est pas une commodité d'organisation, elle est matérielle.

### Qui prend quoi

| Tâche | Machine | Note |
|---|---|---|
| T02, T03, T04 | **la machine de calcul** | L'instrument de mesure ; T03 et T04 veulent les 32 fils |
| **T10** | **bureau** | **Déplacée.** Toute la piste B en dépend directement ; la refaire des deux côtés serait du gaspillage |
| T20, T21, T30, T31 | **bureau** | Descente anticipée vers le verdict navigateur |
| T22, T23 | **bureau** | Suite naturelle de la phase 2 : le choix du moteur (T22) se tranche **sur mesure**, donc là où l'on mesure |
| T11, T12 | **la machine de calcul** | Reprend après T10 ; c'est le seul très gros calcul |
| **T32** | **bureau** | **Déplacée le 2026-08-04.** Son critère est de l'antisymétrie et de la monotonie, pas du volume. Et elle est consommée par la **recherche**, qui vit ici : la laisser sur l'autre machine imposerait un aller-retour pour le piège du niveau intermédiaire |
| T34, T35 | **la machine de calcul** | Besoin de l'oracle et du volume |
| T33 (volet **coût**) | bureau | Générer le bearoff et **mesurer ses octets** — entrée du budget navigateur |

**Point de rendez-vous** : la machine de calcul s'arrête après **T04** et attend que **T10** soit livrée par la
piste B avant d'attaquer **T11**. *(Levé le 2026-08-03 ; T11 est livrée.)*

### Certaines tâches ne s'attribuent pas — elles se coupent

À partir de T31, la règle « le calcul lourd va sur la machine de calcul » ne suit plus le découpage en fiches :
une même tâche a une moitié bon marché et une moitié coûteuse.

| Tâche | Bureau | la machine de calcul |
|---|---|---|
| **T31** | écrit le harnais et le corpus, valide sur une poignée de positions | **génère la référence 2-ply non filtrée** — ~1,8 M évaluations par décision |
| **T33** | mesure les octets, entrée du budget navigateur | **génère les tables de fin de partie** |

Le livrable reste unique et la fiche aussi ; c'est l'exécution qui se répartit.

### File d'attente de la machine de calcul *(au 2026-08-04)*

> **Agent qui exécute la roadmap sur la machine de calcul : prendre dans cet ordre.**

| | Tâche | Pourquoi maintenant |
|---|---|---|
| **1** | **T33** — tables de fin de partie | **Ne dépend de rien** : ni du filtre, ni de l'équité de match, ni du modèle. Son critère est une **vérification croisée** — deux implémentations correctes d'un calcul exact produisent des fichiers identiques. Travail long, parfaitement isolé |
| **2** | **T31, la moitié coûteuse** — référence 2-ply **non filtrée** | ~1 812 000 évaluations par décision, soit **~5,1 s** sur 32 fils. Le bureau écrit le harnais et le corpus ; la machine de calcul produit la référence |
| **3** | **T12** — corpus de non-régression | Peu coûteux, indépendant, à glisser entre les deux |

**Ne pas prendre T35.** Elle est la **somme** de T31, T32, T33 et T34 — son périmètre dit
« configuration complète ». Lancée avant, elle mesurerait un filtre arbitraire, sans équité de
match et sans bearoff, et **produirait un chiffre que chacune des quatre viendrait invalider**.
Dans un projet qui ne cite que des mesures, un chiffre obsolète est pire que pas de chiffre : on
le retrouve cité six mois plus tard.

#### Dimensionner la référence de T31 plutôt que la fixer

Le critère de T31 demande « ≥ 100 000 décisions ». À 5,1 s la décision, cela ferait **six jours de
la machine de calcul pour la seule référence**.

C'est probablement sur-spécifié, du même genre que le million de T35. Si le taux de désaccord est
de l'ordre de 5 %, **2 000 décisions en produisent une centaine**, soit un intervalle de ±1 % sur
le taux — de quoi distinguer 3 % de 10 % sans hésitation.

**Faire 2 000 décisions d'abord, mesurer la variance observée, puis dimensionner.** Fixer un
nombre à l'avance dans un sens ou dans l'autre serait deviner.

### La référence finale est **GNU Backgammon lui-même**, pas `gnubg-nn` *(2026-08-04)*

> **Décision de projet.** Les mesures qui engagent une conclusion de force en **match** ou sur le
> **videau** se font contre **GNU Backgammon**, pas contre `gnubg-nn`.

**Le motif est une mesure, faite en T32.** L'oracle `gnubg-nn` 1.1.0a9 n'utilise pas la même table
d'équité de match que nous :

| | |
|---|---|
| `gnubg-nn` contre Kazaross-XG2 | **`max\|Δ\| = 2,679e-02`** sur 625 entrées |
| Pire écart | 8-away contre 15-away : oracle `+0,562000`, Kazaross `+0,588794` |

Une décision de videau se joue sur des marges bien inférieures à 0,027 d'équité. Comparer nos
décisions à celles de `gnubg-nn` mesurerait donc surtout **l'écart entre les tables**, pas entre
les modèles — un confondant qui aurait pollué T34 et la moitié match de T35 sans jamais se
signaler.

**GNU Backgammon n'a pas ce problème** : il charge **Kazaross-XG2 par défaut**, c'est-à-dire notre
table, vérifiée entrée par entrée à `max|Δ| = 0`. La comparaison porte alors sur ce qu'on veut
comparer.

**Il est scriptable**, ce qui rend l'automatisation possible :

```bash
printf 'show matchequitytable\nquit\n' | gnubg --tty --quiet --no-rc
```

Version présente sur la machine de bureau : **1.08.003 (2026-02-24)**.

**Trois tâches sont concernées :**

- **T34** — le taux d'accord sur les décisions de videau n'a de sens que contre un moteur qui
  partage la table.
- **T35** — la moitié **match** du round-robin. La moitié money reste comparable à `gnubg-nn`,
  qui ne consulte aucune table en money.
- **T11** — et c'est un bénéfice inattendu : le rapport de T11 citait *« rejouer contre GNU
  Backgammon lui-même plutôt que contre `gnubg-nn`, qui en est un fork ancien »* comme l'une des
  trois façons de trancher son écart inexpliqué. **C'est le même travail.** L'outillage construit
  pour T34 donnera à T11 son test décisif.

`gnubg-nn` reste utile là où il excelle : rapide, appelable en processus, sans table à consulter —
donc parfait pour les gros volumes en **money**.

#### Une répétition avant T35, quand son tour viendra

Avant d'engager les ~2,3 jours de T35, faire tourner le pipeline complet sur **2 000 parties**.
Non pour un chiffre de force — il n'en sortirait rien de citable — mais pour **mesurer le débit
réel** et **attraper les défauts d'échelle du harnais avant qu'ils ne coûtent deux jours**.

Ce n'est pas théorique : T11 a trouvé exactement cela, un bootstrap en
`O(rééchantillonnages × n)` qui laissait la machine au repos quarante minutes en affichant
« calcul en cours ». Le trouver sur 2 000 parties coûte trois heures ; sur 100 000, quarante-huit.

### Pourquoi T20/T21 remontent avant T11

Le critère de T21 — *« le 2-ply tient-il dans le navigateur ? »* — est **la mesure qui peut
invalider la cible du projet**. Or elle dépend de la **forme** du réseau
(`196 → 512 → 512 → 256 → 128 → 5`), pas de la **valeur** de ses poids. Elle est donc disponible
dès maintenant, et **ses chiffres survivent au verdict de T11** : si la phase 4 s'ouvre, on
réentraîne dans la même enveloppe de taille, puisque celle-ci est bornée par le navigateur et non
par la machine d'entraînement (`BRIEF.md` §4). La faire tôt est du dérisquage.

### Amendements aux critères d'acceptation, et ce qui les motive

Deux critères sont amendés faute de **matériel**, pas faute d'exigence. Les manques sont
**nommés dans les rapports**, jamais comblés par extrapolation.

- **T20 — Safari.** ~~Amendé faute de Mac.~~ **Retiré le 2026-08-03** : deux iPhone ont permis de
  mesurer WebKit directement, et le critère est satisfait en entier. Le motif de l'amendement était
  d'ailleurs faux — on redoutait iOS comme la plateforme la plus contrainte, la mesure en fait
  **la plus rapide des sept** testées.
- **T21 — le volet mobile.** ~~Ouvert faute d'appareil, avec un seuil falsifiable publié à sa
  place.~~ **Refermé le 2026-08-03** : quatre appareils mesurés via une page statique publiée, le
  téléphone atteignant internet plutôt que la machine de mesure. Le seuil réfutable — il aurait
  fallu une pénalité de ×13 — est confirmé avec une marge de 3,6 à 13.

  **La méthode mérite d'être retenue** : publier une prédiction réfutable plutôt qu'une
  extrapolation a permis de trancher dès qu'un appareil est apparu, sans rien réécrire.

---

# Phase 0 — Socle & instrument de mesure

> Objectif de phase : disposer d'un **instrument** avant d'avoir quoi que ce soit à mesurer.
> Aucune force n'est produite ici, et c'est normal.

## T00 — Amorçage du dépôt et de l'environnement

**Objectif** — un dépôt qui compile et un environnement qui calcule.

**Périmètre** — Structure : `src/`, `tests/`, `bench/`, `models/` (gitignoré sauf artefacts
publiés), `tools/`. Environnement : Python ≥ 3.10 en environnement virtuel, PyTorch, NumPy,
`gnubg-nn`, GCC, Emscripten. Clone du dépôt de référence et compilation de son moteur C.

**Exclut** — toute logique métier.

**Livrables** — un `Makefile` (ou équivalent) avec les cibles `setup`, `build`, `test`, `bench` ;
`THIRD-PARTY.md` initialisé.

**Critères d'acceptation**
- `cd c_engine && bash build_unix.sh` se termine sans erreur.
- `python play_models.py --model1 best_models/cubeless_prob5_512_512_256_128.pt --gnubg --game-mode cubeless-money --games 1000` produit un résultat chiffré.
- Si un GPU CUDA est présent, `torch.cuda.device_count()` le confirme et le nombre est consigné.
- `THIRD-PARTY.md` liste déjà l'origine, l'auteur et la licence de chaque dépendance clonée.

## T01 — Représentation de position et génération de coups légaux

**Objectif** — une position et ses coups légaux, corrects et rapides.

**Périmètre** — Reprendre le moteur de règles C du dépôt de référence (MIT) plutôt que d'en
écrire un : il est déjà accordé à l'encodage attendu par le réseau. L'isoler derrière une
interface propre, pour pouvoir le remplacer plus tard sans toucher au reste.

**Exclut** — l'évaluation, la recherche, le videau.

**Critères d'acceptation**
- Sur un corpus figé d'au moins 200 positions couvrant barre, fermetures, sorties forcées et
  bearoff, le **nombre** de coups légaux et l'**ensemble** des positions résultantes coïncident
  avec un générateur de référence indépendant, position par position.
- Les cas dégénérés sont couverts explicitement : aucun coup légal, un seul dé jouable, doubles
  partiellement jouables, obligation de jouer le plus grand dé.

## T02 — Codec position ↔ vecteur de 196 caractéristiques

> **La tâche la plus critique du projet.** Une erreur ici ne provoque aucun plantage : elle
> produit des évaluations plausibles et fausses, et contamine toutes les mesures suivantes.

**Objectif** — le pont entre les formats de position usuels et l'entrée du réseau.

**Périmètre** — Lecture et écriture des identifiants de position courants (XGID, GNU Backgammon
Position ID) ; conversion position → vecteur de 196 flottants selon la convention de
`encoding.py` : bloc « moi » (24 points × 4 unités thermomètre, barre / 2,0, sortis / 15,0) puis
bloc « adversaire », toujours **du point de vue du joueur au trait**, avec **indices miroités**
quand c'est Noir qui joue.

**Exclut** — les 4 entrées de videau (le modèle retenu est cubeless).

**Critères d'acceptation**
- **Parité exacte contre la référence Python** : sur ≥ 10 000 positions tirées au hasard, le
  vecteur produit est identique à celui de `encoding.py`, `max|Δ| = 0`.
- **Aller-retour** : `decode(encode(p)) == p` sur le même corpus.
- **Sentinelle du compte de pips** : pour chaque position, le compte de pips calculé depuis le
  vecteur correspond à celui calculé depuis l'identifiant.
- **Test d'asymétrie** : le corpus contient au moins 50 positions **franchement asymétriques**
  (une position d'ouverture ne détecte pas une inversion de perspective). Pour chacune,
  `encode(p, joueur=Blanc)` et `encode(miroir(p), joueur=Noir)` produisent le **même** vecteur.

## T03 — Oracle GNU Backgammon

**Objectif** — pouvoir interroger GNU Backgammon comme référence de mesure.

**Périmètre** — Enveloppe autour de `gnubg-nn` (ou du binaire piloté par fichier de commandes)
exposant : évaluation d'une position, choix du meilleur coup, décision de videau, à profondeur
paramétrable. Rappel de `CLAUDE.md` : c'est un **instrument de mesure**, jamais une source
d'apprentissage ni de code.

**Critères d'acceptation**
- Sur ≥ 1 000 positions, l'oracle rend un résultat sans erreur et son débit est mesuré.
- Un contrôle croisé valide du même coup la traduction de position de T02 : les positions
  envoyées à l'oracle sont bien celles qu'on croit (vérification par compte de pips).

## T04 — Harnais de round-robin

**Objectif** — l'instrument central : faire jouer N moteurs les uns contre les autres et en
tirer une matrice de force lisible.

**Périmètre** — Boucle de match moteur-contre-moteur (money et match, cubeless et cubeful),
parallélisée. Sorties : **points par partie** avec **IC 95 % bootstrap**, pourcentage de
victoire, matrice complète. **Dés déterministes par graine**, et **dés communs entre les deux
camps** (chaque paire rejoue les mêmes séquences avec les rôles inversés) pour diviser la
variance.

**Exclut** — l'interface graphique, la persistance.

**Critères d'acceptation**
- **Antisymétrie** : `ppg[A][B] == -ppg[B][A]` à l'arrondi près.
- **Contrôle nul** : un moteur contre lui-même donne `0` dans son intervalle de confiance.
- **Reproductibilité** : deux exécutions à graine identique donnent le même résultat au bit près.
- L'intervalle de confiance est calculé et affiché, jamais un chiffre nu.

## T05 — Banc de débit

**Objectif** — établir les débits réels, une bonne fois.

**Périmètre** — Mesurer : parties de self-play par seconde (1 fil, puis tous), évaluations par
seconde et par cœur, durée réelle d'un round-robin d'un million de parties, occupation mémoire.

**Critères d'acceptation**
- Les quatre nombres sont mesurés, consignés avec la date et la configuration exacte.
- Le rapport distingue explicitement ce qui est **mesuré** de ce qui reste **extrapolé**.

---

# Phase 1 — Reproduire

> Objectif de phase : **la certitude**, pas la force. On ne gagne pas un point d'équité ici ; on
> gagne le droit de croire les chiffres qu'on lira ensuite.

## T10 — Charger et exécuter le modèle de référence

**Objectif** — faire tourner `cubeless_prob5_512_512_256_128` dans notre code.

**Périmètre** — `export_weights.py` → `model.bin` (magic `BGNN`) ; lecture par notre code
d'inférence ; exposition des **cinq probabilités brutes**.

> **Piège à traiter frontalement** : `nn_eval.c` réduit les cinq sorties en équité money après
> sigmoïde et clamp d'événements imbriqués. Le match play a besoin de la **distribution**, pas du
> scalaire. Vérifier l'ordre et la sémantique exacte des cinq sorties avant tout usage, et
> exposer un chemin qui court-circuite la réduction.

**Critères d'acceptation**
- Sur ≥ 1 000 positions, les 5 sorties de notre code et celles de PyTorch coïncident à
  `max|Δ| < 1e-5`.
- Le clamp d'imbrication est vérifié : `P(gain) ≥ P(gain-gammon) ≥ P(gain-backgammon)` et de même
  côté perte, sur l'intégralité du corpus.
- Une note documente l'ordre des cinq sorties, en clair, avec la ligne de `nn_eval.c` qui
  l'établit.

## T11 — Round-robin de vérification

**Objectif** — retrouver par nous-mêmes la force annoncée.

**Périmètre** — Round-robin `modèle` × `GNU Backgammon`, ≥ 1 M parties, cubeless money d'abord,
puis cubeful.

**Critères d'acceptation**
- Le ppg mesuré est comparé au **+0,0673 publié** (benchmark HedgeHog, `colossus` vs `gnubg`,
  0-ply cubeful) et au **+57,8 mEq/partie** annoncé par l'auteur en 0-ply.
- **Si l'écart dépasse les intervalles de confiance, il est expliqué avant de continuer** :
  protocole différent, traitement du videau, sur-représentation des fins de partie. Un écart
  inexpliqué **arrête la phase 2**.
- Le rapport indique le volume, la graine, la configuration et l'intervalle de confiance.

## T12 — Corpus de non-régression

**Objectif** — qu'une dérive future se voie.

**Périmètre** — Figer ≥ 2 000 positions et leurs 5 sorties dans un fichier versionné ; un test
qui échoue si l'encodage, le chargement ou les poids changent.

**Critères d'acceptation**
- Le test passe sur le modèle de référence, et **échoue** si l'on perturbe volontairement un
  poids d'un pour mille (vérifier que le test détecte réellement).
- Le corpus couvre contact, course, bearoff, barre et backgame.

---

# Phase 2 — Le navigateur

> Objectif de phase : **chiffrer la frontière** entre ce qui tient sur l'appareil et ce qui n'y
> tient pas. Tant que ces mesures n'existent pas, le partage 2-ply / 3-ply est une hypothèse.

## T20 — Build WebAssembly de l'inférence

**Objectif** — le même calcul, dans un navigateur.

**Périmètre** — Compilation Emscripten du code d'inférence et du codec ; API JavaScript minimale
(`loadModel`, `evaluate`) ; chargement du `.bin` par `fetch`.

**Critères d'acceptation**
- Sur le corpus de T12, les sorties WebAssembly et natives coïncident à `max|Δ| < 1e-6`.
- Le module se charge sur Chrome, Firefox et Safari (versions supportant WASM SIMD). **Satisfait
  en entier** : Chromium 150, Firefox 153, et Safari 26.5 sur iOS 18.7. L'amendement pris faute de
  Mac a été **retiré** — un iPhone a permis de mesurer WebKit directement.
- La taille du `.wasm` et celle du modèle sont mesurées et consignées.

## T21 — Banc de débit navigateur

**Objectif** — le seul chiffre qui tranche l'architecture.

**Périmètre** — Mesurer les évaluations par seconde en WebAssembly, sur ≥ 2 navigateurs de bureau
et ≥ 1 mobile réel (pas un émulateur), avec et sans SIMD, en fil principal et en Web Worker.

**Critères d'acceptation**
- La **pénalité WebAssembly par rapport au natif** est chiffrée (l'hypothèse de travail est ×1,5
  à ×2,5 : elle est confirmée ou corrigée).
- Le **budget d'un match complet en 2-ply** est déduit de la mesure, pour 1 et pour 4 workers.
- **Verdict explicite** : le 2-ply tient-il dans le navigateur, oui ou non, sur mobile compris ?
  Si non, la cible du projet doit être révisée — c'est un résultat légitime, pas un échec.
  **Mesuré sur quatre appareils** : la pénalité mobile va de **×0,95** (iPhone iOS 18.7, plus
  rapide que le desktop) à **×3,66** (Chrome sur Android). Le seuil réfutable publié — ×13 — est
  confirmé avec une large marge. L'amendement pris faute d'appareil a été **retiré**.

## T22 — Décision du moteur d'inférence

**Objectif** — trancher entre les candidats, sur mesure.

**Périmètre** — Comparer : (i) le C du dépôt de référence, (ii) le C++ de `hedgehog-public`
complété du layout `DENSE_FLOAT` qu'il refuse délibérément. Critères : débit WebAssembly, taille
de l'artefact, effort d'intégration, dette.

**Livrable** — une note de décision **chiffrée**, versionnée dans le dépôt.

**Critères d'acceptation**
- ~~Les deux candidats sont réellement mesurés, pas seulement discutés.~~ **Amendé le
  2026-08-03** : le second candidat n'a pas été construit. Son gain est **plafonné par
  arithmétique** — l'accumulation NNUE n'optimise que la couche d'entrée, soit 19 % des
  528 389 MACs de ce réseau, et le mode dense la désactive de toute façon. Les ×9 obtenus l'ont
  été dans le code existant, sur des causes indépendantes du moteur. Motif et conséquences dans
  [ADR-0001](docs/adr/0001-moteur-inference.md).
- La note dit ce qui a été mesuré et ce qui a été estimé.

**Décidé** — le moteur retenu est le C du dépôt de référence, isolé derrière `src/gn_infer.h`.
Voir [ADR-0001](docs/adr/0001-moteur-inference.md).

## T23 — Ordonnancement Web Worker

**Objectif** — que l'analyse ne gèle jamais l'interface qui l'appelle.

**Périmètre** — Pool de workers, découpage d'une analyse de match en unités, progression
rapportée, annulation. API : `analyzeMatch(match, ply, onProgress) → AbortController`.

**Critères d'acceptation**
- Le fil principal reste réactif pendant une analyse complète (mesuré : aucune tâche longue
  > 50 ms sur le fil principal).
- L'annulation libère effectivement les workers.

---

# Phase 3 — Profondeur et exactitude

> Objectif de phase : **c'est ici que la force arrive**. Le modèle seul donne un PR d'environ
> 1,06 ; c'est la recherche, l'équité de match et les tables exactes qui le descendent vers 0,22.

## T30 — Recherche expectiminimax

**Objectif** — le 1-ply, puis le 2-ply.

**Périmètre** — Pour chaque coup candidat : énumérer les 21 jets adverses, retenir la meilleure
réponse, évaluer, moyenner (**1/36** pour les doubles, **2/36** pour les autres).

> **Subtilité du match play, à ne pas manquer** : au niveau intermédiaire, l'adversaire choisit sa
> réponse en maximisant **son équité de match**, pas son équité cubeless. À 4-away/2-away, un coup
> gammonesque ne vaut pas ce qu'il vaut en money. Un 2-ply qui maximise l'équité cubeless au
> niveau intermédiaire est **faux en match**, et cette erreur est invisible en money — donc
> invisible à tout test qui n'utiliserait que du money.

**Critères d'acceptation**
- La pondération des dés est vérifiée par un test : la somme des poids vaut exactement 1.
- Le PR mesuré descend d'environ 1,06 (0-ply) à environ 0,50 (1-ply) — référence publiée.
- **Un PR qui ne bouge pas quand on ajoute un ply signale une recherche fausse.** C'est le test
  le plus révélateur de toute la chaîne : le traiter comme bloquant.

## T31 — Filtrage de coups

**Objectif** — rendre le 2-ply praticable.

**Périmètre** — Ne descendre en profondeur que sur les N meilleurs coups du niveau précédent. Le
mécanisme et ses réglages sont documentés publiquement par GNU Backgammon (filtres de coups,
réseaux d'élagage) : réimplémenter l'idée, ne rien copier.

**Critères d'acceptation**
- Le débit 2-ply est multiplié par un facteur mesuré.
- **La perte de qualité est chiffrée** : sur ≥ 100 000 décisions, le taux de désaccord avec le
  2-ply non filtré, et l'équité moyenne perdue quand il y a désaccord. Un filtre qui « ne change
  rien » n'a pas été mesuré.

## T32 — Équité de match

**Objectif** — passer des cinq probabilités à une équité de match.

**Périmètre** — Table Kazaross-XG2 (attribution à **Neil Kazaross**), repli sur le modèle de
Zadeh au-delà de 25 points ; conversion `prob5 + score + videau → MWC` ; Crawford et
post-Crawford.

**Critères d'acceptation**
- **Antisymétrie** : `MET[i][j] + MET[j][i] = 1,0` sur toute la table.
- Le point de prise près du money game ressort à ~25 %.
- Les valeurs coïncident avec une implémentation de référence indépendante.
- `THIRD-PARTY.md` porte l'attribution.

## T33 — Tables de fin de partie

**Objectif** — combler le trou que ni le build public de HedgeHog ni le modèle de référence ne
comblent.

**Périmètre** — Charger les tables au format GNU Backgammon, **ou** les recalculer par
programmation dynamique. Chemin de repli sur le réseau quand la position sort de la table.

**Critères d'acceptation**
- **Vérification croisée** : si les tables sont recalculées, elles sont identiques aux tables de
  référence — c'est un calcul exact, deux implémentations correctes coïncident.
- Sur un corpus de course et de bearoff, l'écart entre le réseau seul et la table exacte est
  **mesuré** : c'est la valeur de cette tâche, et elle doit être connue.
- Le PR mesuré sur des positions de course s'améliore de façon significative.

## T36 — Diagnostic : ce que la profondeur fait à l'avantage

> **Palier A.** Mesure bon marché, disponible immédiatement, et qui conditionne tout le reste.

**Objectif** — savoir si l'avantage mesuré en 0-ply survit à la profondeur, **avant** de bâtir le
videau dessus.

**Périmètre** — Round-robin `modèle` × `GNU Backgammon` en money cubeless, **à profondeur égale
des deux côtés**, pour 0-ply, 1-ply et 2-ply. Dés communs, graine fixe, IC 95 % bootstrap. Le
volume est dimensionné pour distinguer l'érosion, pas pour publier une force : l'effet cherché est
la **pente** entre trois points, pas la valeur absolue de chacun.

**Exclut** — le videau, le match, toute conclusion sur l'objectif.

**Critères d'acceptation**
- Les trois points sont mesurés avec leur intervalle, et la pente est explicitement commentée.
- Le rapport dit ce que la pente implique pour la suite : si l'avantage s'annule au 2-ply, le
  chemin vers l'objectif passe par la phase 4 et non par le videau, et le plan doit le dire.
- La comparaison est faite à réglage de GNU Backgammon **nommé** — la profondeur seule ne suffit
  pas à définir un adversaire.

## T37 — Diagnostic : la calibration de la distribution

> **Palier A.** Une décision de videau vit sur `P(gammon)` bien plus qu'un choix de coup.

**Objectif** — savoir si les cinq sorties du réseau sont assez calibrées pour porter une décision
de videau, **avant** d'en construire une.

**Périmètre** — Comparer la distribution `prob5` du réseau à une référence à faible biais, sur un
corpus couvrant contact, course et bearoff : les tables exactes là où elles s'appliquent, des
rollouts ailleurs. Regarder séparément `P(gain)`, `P(gammon)` et `P(backgammon)` des deux côtés :
un réseau peut être excellent sur la première et biaisé sur les autres sans qu'aucune mesure
faite jusqu'ici ne le voie.

**Critères d'acceptation**
- Le biais et la dispersion sont chiffrés **par composante**, pas globalement.
- Le rapport dit si le biais observé suffit à déplacer une décision de videau, et de combien —
  un biais de 1 % sur les gammons ne vaut pas la même chose selon le score.
- Si un biais significatif est trouvé, il est consigné comme **entrée de la phase 4**, non corrigé
  par un facteur ajusté à la main.

## T38 — Bases de fin de partie GNU Backgammon : lecteur et branchement

> **Palier B.** Fait suite à T33, dont le point dur — notre propre table, croisée — est acquis.

**Objectif** — que l'évaluateur consulte une table exacte là où il en existe une, et qu'on sache
ce que cela rapporte.

**Périmètre** — Lecteur des deux formats déposés : `gnubg-OS` (unilatérale, distribution du nombre
de jets) et `gnubg-TS` (bilatérale, équités exactes, **cubeful**). Branchement dans l'évaluateur
avec **repli explicite** sur le réseau hors table. Mesure de l'écart réseau seul ↔ table exacte.

> **Le repli est le piège de cette fiche.** Une position hors table qui reçoit silencieusement une
> valeur de table voisine produit une équité plausible et fausse. La règle de `CLAUDE.md`
> s'applique littéralement : **refusé, jamais approximé** — la table répond, ou elle dit qu'elle ne
> sait pas, et alors c'est le réseau qui répond.

**Exclut** — la troncature pour le navigateur, qui reste à T33 et se mesure contre ces bases.

**Critères d'acceptation**
- Le lecteur est **croisé contre notre propre table** de T33 sur le domaine commun (6 points,
  ≤ 15 pions), avec l'écart chiffré. Deux lecteurs d'un calcul exact qui divergent signalent un
  bug de lecture, pas un désaccord de calcul.
- L'appartenance à la table est un **prédicat testé**, jamais une supposition : un corpus
  contient des positions juste à l'intérieur et juste à l'extérieur du domaine, et le
  comportement des deux est vérifié.
- L'écart réseau seul ↔ table exacte est mesuré sur un corpus de course et de bearoff. **C'est la
  valeur de cette tâche**, et elle n'est pas connue aujourd'hui.
- Le coût d'accès est mesuré : ces fichiers font 2,8 Gio, et une consultation par nœud de
  recherche n'a pas le même prix qu'une consultation par décision.

## T34 — Décision de videau

> **Palier C.** C'est ici que se joue l'objectif.
>
> **État au 2026-08-08** — le modèle existe et la simplification v1 est levée : la récursion de
> re-doublement à score (spec §9) est implémentée, ancrée et mesurée. Accord contesté avec gnubg
> 67,6 % → **84,1 %** [83,6 ; 84,7] sur les 30 000 décisions du protocole §6.3 rejoué ; le foyer
> 2-away/4-away rejoint l'ordre du money (84,9/85,6 %), money inchangé, aucun contexte dégradé
> (`docs/mesures/2026-08-08-T34-recursion-v2.md`). L'arbitrage des désaccords résiduels
> appartient à T39, pas à l'accord.
>
> **Phase 2 (spec §8), même jour** — le videau est dans l'arbre : la distribution se propage à
> toute profondeur (`gn_search_probs`, contrôles §8 verts), les feuilles se valuent cubeful
> (`use_cube`, possession en miroir par pli, antisymétrie testée), exactes dans le domaine de
> la table bilatérale. Décision contre l'exact : 96,8/95,3 % contesté, zéro effet de profondeur
> dans le domaine exact ; corpus bold/safe versionné (338 entrées, rejouées par la suite de
> tests). Voir `docs/mesures/2026-08-08-T34-arbre.md`. **3b est mesurée aussi**
> (`docs/mesures/2026-08-08-T34-coups-cubeful.md`) : accord des choix de coups stable à
> ~81-83 % quel que soit l'état du videau ; sur les décisions cube-sensibles (~2 % du volume),
> les deux moteurs plient sur des positions presque disjointes (intersection ≤ 1) — des
> quasi-égalités que chaque modèle départage à sa façon, arbitrables seulement par T39. La
> phase 2 de T34 est close ; la suite du chemin est T39 puis T35.

**Objectif** — doubler, prendre, passer.

**Périmètre** — Modèle cubeful à partir de la distribution `prob5` et de la table d'équité de
match. Le point de départ est le modèle publié par **Rick Janowski** (*Take-Points in Money
Games*, 1993) : interpolation entre videau mort et videau vivant, indexée par une efficacité de
videau. En match, les points de prise se dérivent de la table d'équité, jamais d'une constante.

**Les cas de bord du match sont au périmètre, pas en annexe** — Crawford, post-Crawford et le
*free drop*, videau mort à ou au-delà du point de match, 2-away/2-away, plafonnement du videau par
la longueur restante. Chacun est une source d'erreur silencieuse : aucun ne fait planter quoi que
ce soit, tous font prendre un videau qu'il fallait passer.

**Exclut** — la propagation du cubeful à travers la recherche, qui est T39 et reste conditionnelle.

**Critères d'acceptation**
- La fenêtre de double et le point de prise sont **monotones** (tests de propriété), et continus
  aux frontières de la table.
- Sur un corpus de ≥ 5 000 décisions de videau, le taux d'accord avec GNU Backgammon est mesuré,
  et les désaccords sont classés par ampleur d'équité.
- **Amendé le 2026-08-06 — le taux d'accord ne conclut pas.** Il mesure une ressemblance. Les
  désaccords sont arbitrés par T39, et le rapport ne prononce aucun verdict de qualité avant.
- L'efficacité de videau retenue est **mesurée sur nos propres données**, jamais reprise d'une
  valeur publiée par un autre moteur.

## T39 — Moteur de rollout : l'arbitre indépendant

> **Palier D.** Promue au chemin critique le 2026-08-06 : sans elle, T34 et T35 ne peuvent
> constater qu'une ressemblance.
>
> **État au 2026-08-08** — l'arbitre est cubeless ET cubeful. Le rollout cubeless (dés
> communs, troncature, différences appariées) était en place ; le videau vivant s'y ajoute,
> décisions exactes dans le domaine de la table et modèle ajusté ailleurs. La sonde a fixé la
> convention des équités cubeful stockées (l'option du tour courant exclue → `cube_defer_first`).
> Non-biais mesuré en volume : 360 positions × 4 colonnes × 2 592 essais, la colonne témoin
> cubeless partage les artefacts de méthode et l'appariement donne Δz compatibles avec zéro
> pour les trois états (`docs/mesures/2026-08-08-T39-rollout-cubeful.md`). La campagne
> d'arbitrage des désaccords de videau money est faite : 394 désaccords sur 6 000 décisions,
> deux colonnes de rollout plus la table exacte en domaine
> (`docs/mesures/2026-08-08-T39-arbitrage-money.md`). Verdict : en contact, égalité
> statistique sur le consensus des deux colonnes (38–31, p = 0,235, 37 non tranchées) ; en
> course, le chemin neuronal sous-double (25 défaites à coût réel, +1,95 d'équité total) —
> la table exacte corrige en domaine, le hors-domaine est un chantier nommé. Limite
> d'instrument constatée : notre colonne tronquée ne résout que 35 % des fenêtres fines.
>
> **CLOSE le 2026-08-08** (`docs/mesures/2026-08-08-T39-fin.md`). Les trois pièces restantes
> sont écrites et mesurées. **Réduction de variance par la chance** : espérance nulle par
> construction, vérifiée contre 15 552 essais bruts (écart +0,0011 ± 0,0043) ; variance ÷159
> en contact cubeless (efficacité ×8,3), ÷20 en cubeful — les queues de videau ne sont pas
> des dés, réserve nommée. **Arrêt sur IC** : cible de se par familles de 36 essais, plafond
> conservé. **Rollout de MATCH** : une partie par essai, points → score → MWC par la MET,
> décisions §9, Crawford et videau mort respectés ; ancres exactes tenues (identité DMP dés
> pour dés, free drop d'après-Crawford trouvé par le modèle, refus hors table). Le
> ré-arbitrage des 210 fenêtres non résolues (colonne corrigée, mêmes graines) en résout 72
> — concordance à 73 % avec la colonne gnubg — et laisse 138 quasi-égalités authentiques
> (écart médian 0,025 pour se 0,012). Cumul des campagnes : pas de vainqueur global
> (54–62, p = 0,26), mais la fenêtre du double marginal en contact est perdue
> significativement (26–60, p = 1,6×10⁻⁴) : **nous sur-doublons les fenêtres fines de
> contact**, miroir de la sous-double de course — les deux défauts du doublage 0-ply sont
> nommés, mesurés, et bornés par le faible coût propre à ces fenêtres.

**Objectif** — pouvoir dire lequel de deux moteurs a raison quand ils diffèrent.

**Périmètre** — Rollouts à variance réduite : dés communs entre les variantes comparées, rollouts
**tronqués** puis évalués par le réseau, arrêt sur intervalle de confiance plutôt que sur un
nombre de parties fixé. Rollouts cubeful et rollouts cubeless.

**Exclut** — l'usage du rollout comme source d'entraînement, qui relève de la phase 4.

**Critères d'acceptation**
- **Contrôle de non-biais** : sur un corpus où la table exacte de T38 donne la réponse, le rollout
  la retrouve dans son intervalle de confiance. Un arbitre qu'on n'a pas vérifié n'arbitre rien.
- La variance obtenue avec dés communs est comparée à celle sans, et le gain est chiffré.
- **La réserve est publiée avec chaque usage** : un rollout conduit par notre réseau nous favorise.
  Tout arbitrage d'un désaccord avec GNU Backgammon produit **les deux colonnes**, la nôtre et la
  leur, et aucune n'est présentée seule.

## T35 — Round-robin complet en 2-ply

**Objectif** — la mesure qui répond à l'objectif du projet.

**Périmètre** — Configuration complète (réseau + recherche 2-ply filtrée + équité de match +
tables de fin de partie) contre GNU Backgammon à profondeur équivalente, en money et en match,
~~≥ 1 M parties par paire~~ **≥ 100 000 parties par paire — amendé le 2026-08-04**.

> **Le million était sur-spécifié pour la question posée, et infaisable.** T30 a mesuré le coût
> réel : 12 951 évaluations par décision en 2-ply filtré 1/1. Un million de parties représente
> donc `12 951 × ~55 décisions × 10⁶ ≈ 7,1 × 10¹¹` évaluations, soit **~23 jours sur la machine de calcul**
> (32 fils à 11 171 éval/s), ou ~10 jours avec le traitement par lot.
>
> Le million vient du `BRIEF.md` §5, qui vise à séparer des moteurs distants de 0,005 à 0,07 ppg.
> Or **T11 a établi que l'écart à mesurer ici vaut +0,0400 ppg**, avec ±0,0024 à un million de
> parties. À **100 000 parties**, l'intervalle s'élargit à ~±0,0076 — **cinq fois plus petit que
> l'effet à détecter**, pour **~2,3 jours** de calcul.
>
> Si le résultat tombait *dans* l'intervalle plutôt que loin de zéro, le volume devrait être
> augmenté : l'amendement borne le coût, il ne dispense pas de conclure.

**Critères d'acceptation**
- Le résultat est publié dans le dépôt avec protocole, volume, graine et intervalle de confiance.
- **Verdict sur l'objectif** : « niveau équivalent ou supérieur à GNU Backgammon et eXtreme
  Gammon », confirmé ou infirmé, avec le chiffre. Si infirmé, la phase 4 s'ouvre.

### Amendements du 2026-08-06 — ce que « en match, avec videau » impose de plus

- **Le réglage de l'adversaire est nommé, pas sous-entendu.** « Aussi bon que GNU Backgammon » est
  une phrase vide tant qu'on n'a pas dit à quel réglage. La référence est fixée explicitement
  (profondeur pions, profondeur videau, filtres) et publiée avec le résultat.
- **Trois métriques, parce qu'aucune ne suffit seule** :

  | Métrique | Ce qu'elle apporte | Ce qu'elle coûte |
  |---|---|---|
  | **ppg cubeful money** | Bon marché, faible variance grâce aux dés communs, comparable à T11 | Ne dit rien du match |
  | **MWC en match** | La métrique de l'objectif | Très bruitée — un match rend ±1 |
  | **PR** | Le contrôle de T30 qui n'a jamais tourné | Demande un corpus de référence |

- **Les scores de départ sont échantillonnés, pas fixés à 0–0.** Partir toujours du début d'un
  match donne une couverture ridicule de l'espace des scores — or c'est là, et pas à 0–0, que le
  videau se décide. L'échantillonnage est publié avec le protocole.
- **La répétition sur 2 000 parties reste obligatoire** avant d'engager le volume, et vaut
  désormais pour la configuration cubeful : c'est elle qui a le plus de chances de révéler un
  défaut d'échelle du harnais.

### État au 2026-08-09 — l'instrument de la campagne est prêt, la campagne n'est pas lancée

**Construit et mergé** (`gammonnet/cubeful.py`, `bench/run_t35.py`, `bench/report_t35.py`) :

- **La boucle cubeful**, money et match, chaque camp répondant avec son propre modèle. Contrôle
  nul A-contre-A **exactement** nul à tout score — obtenu en collant le score au siège dans les
  paires de matchs (les dés sont attachés aux sièges ; faire voyager le score avec eux casse la
  propriété, le test l'a montré).
- **Le pilote segmentable** : journal JSONL une ligne par paire, reprise en sautant les index
  présents, arrêt par `--minutes`/`--limit`/Ctrl-C/extinction de la machine. Un run segmenté est
  **identique bit à bit** à un run d'une traite — testé, money et match. L'en-tête fige le
  protocole (empreinte d'évaluation comprise : un build numériquement différent refuse).
- **gnubg au score** : sonde EMG du 2026-08-09 (`docs/mesures/2026-08-09-t35-sonde-emg.md`) —
  `evaluate` sous `cubeinfo` de match rend l'EMG, affine en MWC à pente positive, donc la
  convention composée de T36 vaut à tout score. Videau gnubg par `cfevaluate` (sonde T34).

**Protocole arrêté le 2026-08-09** (décision utilisateur) :

- **Nous** : pions 2-ply **garde 3** (biais nommé ~0,009 ppg **contre nous** d'après T31 —
  conservateur pour un verdict « équivalent ou supérieur »), filtre `(0,1,3)`, **videau 2-ply** ;
  table exacte en domaine, efficacités T34, Jacoby money.
- **Eux** : gnubg pions 2-ply même garde racine, `prune=1` (son jeu réel), videau `cfevaluate`
  2-ply.
- **Build `NATIVE_FP=1`** (4× plus rapide ; sorties déplacées de ~6e-07, tolérance documentée du
  test de régression ; l'empreinte du journal le verrouille). **Machine : le bureau, 11 ouvriers.**
- Graine `20260810` ; match : longueur 7, scores échantillonnés uniformes, pile ou face
  Crawford-joué/derrière quand un seul joueur est à 1-away.

**Dimensionnement mesuré** (2026-08-09) : décision garde 3 = 38 721 évals = 2,9 s ; videau 2-ply
= 1,7 s ; gnubg ≈ 0,2 s (nous coûtons ~20× eux). **Cache d'évaluation ×3,41** (paire identique,
bit à bit — activé par défaut). **Le débit agrégé plafonne à ×4,4-4,6 à 11 ouvriers** (bande
passante mémoire, pas les cœurs ; 14 ouvriers retombent à ×3,0). Estimation — hypothèse, la
répétition tranchera : **~4-6 jours la moitié money** (100 000 parties), autant en match, en
lots interruptibles.

**L'inférence par lot est faite** (2026-08-09) : la passe peu profonde de `rank_plays` évalue
ses coups frères par lots de 32 à **largeur fixe** — le dispositif qui garantit l'invariance au
découpage bit à bit, y compris sous les drapeaux de réassociation (`tests/test_batch.py`).
Mesuré : 0,055 ms/éval contre 0,076 (garde 3 : décision 2,13 s contre 2,93, ×1,38 seul ;
**×1,19 au point de fonctionnement** 11 ouvriers + cache, 3,35 s/décision). Sur build par
défaut, le lot est bit-identique au scalaire ; l'empreinte du journal couvre les deux chemins.

**La répétition est faite** (2026-08-09, `docs/mesures/2026-08-09-t35-repetition.md`) : aucun
défaut d'échelle (0 partie bloquée, videau plausible, reprise après SIGINT exercée en vrai).
Débit **mesuré** : 5,9 s/partie à 11 ouvriers, 8,3 à 9 ouvriers `nice` (le réglage retenu —
bureau utilisable). **La variance cubeful mesurée (écart-type 2,27/paire) fixe l'IC réel à
~±0,020 ppg à 100 000 parties** — pas les ±0,0076 extrapolés de la variance cubeless de T11 ;
si le résultat tombe dans l'intervalle, la fiche prévoit d'augmenter le volume, pas de conclure.

**Reste à faire, dans l'ordre** :

1. **La campagne money** (50 000 paires, journal `t35-money.jsonl`), puis **la moitié match**,
   en lots (mêmes commandes, relancées ; ~9,6 jours la moitié money à 9 ouvriers `nice`).
2. La métrique **PR** n'est pas branchée dans ce pilote — elle demande le corpus de référence
   de T30 ; à traiter comme un complément du verdict, pas un préalable.

```bash
NATIVE_FP=1 make build       # le build de campagne, AVANT tout lot
GN_REGRESSION_TOLERANCE=1e-6 python -m pytest tests/test_regression.py -q  # sanité du build

# un lot de campagne money (arrêt : Ctrl-C, --minutes, --limit, ou extinction ;
# reprise : relancer la même commande)
nice -n 10 python bench/run_t35.py --mode money --pairs 50000 --workers 9 \
    --journal docs/mesures/t35-money.jsonl \
    --ours-ply 2 --ours-filter 0,1,3 --gnubg-ply 2 --gnubg-filter 0,1,3
python bench/report_t35.py --journal docs/mesures/t35-money.jsonl   # à tout moment
```

### État au 2026-08-21 — money faite, match à refaire

**La moitié money est faite** : 50 000 paires, **−0,0119 ppg** [−0,0310 ; +0,0074].
L'écart de +0,0400 ppg que T11 mesurait en cubeless **ne se reproduit pas** en cubeful ;
le résultat tombe *dans* l'intervalle, ce que la fiche prévoit de traiter par plus de
volume et non par une conclusion.

**La moitié match est invalide et à refaire.** Elle contredisait la money — 56,4 % de MWC
contre l'égalité, tout l'écart concentré là où le videau vit, culminant à 60,3 % en
post-Crawford. La sonde du 2026-08-21
(`docs/mesures/2026-08-21-T35-sonde-videau-au-score.md`, 21 600 décisions) a séparé les
deux lectures possibles : le pilotage de gnubg au score est **mesuré correct** partout —
conventions de `cubeinfo`, orientation du score, propriétaire, take/pass, et la
compression `match_to = max(away)` est exactement gratuite — **sauf un mot**.
`classify_gnubg_verdict` lisait « Never redouble, take (dead cube) » comme *double, et
l'autre prend* : la campagne faisait redoubler gnubg là où gnubg dit de ne jamais
redoubler, dans les états où le videau n'est mort que pour le joueur au trait
(`away_mover <= cube < away_opponent`) — que la garde de `cubeful.py` ne filtre pas. À
sens unique : notre modèle, au même état, refuse correctement. Signature dans le journal
lui-même : **84,1 % des paires post-Crawford atteignent un videau de 4 ou 8**, là où le
jeu correct ne peut pas dépasser 2.

Corrigé et couvert par test (`tests/test_gnubg_engine.py`). La moitié money n'est pas
touchée — en money le videau n'est jamais mort, et la sonde le confirme à 100 %.

**Reste à faire** : relancer la moitié match sur un journal neuf, avec le correctif.

```bash
# la moitié match, journal NEUF — l'ancien mesure un gnubg estropié.
# `setsid` : la campagne dure des jours et doit survivre à la session qui
# la lance. Vérifier `pgrep -f run_t35` AVANT de relancer : deux campagnes
# concurrentes divisent le débit par trois, et c'est arrivé.
setsid nohup env PYTHONUNBUFFERED=1 python3 bench/run_t35.py --mode match \
    --pairs 50000 --workers 30 --journal docs/mesures/t35-match-v2.jsonl \
    --ours-ply 2 --ours-filter 0,1,3 --gnubg-ply 2 --gnubg-filter 0,1,3 \
    > ~/t35-match-v2.log 2>&1 < /dev/null &
```

**Lancée le 2026-08-21 à 17:26**, empreinte d'évaluation `1d92f0d39fb70cb4` — la même
que la moitié money, donc le même moteur. Débit mesuré ~430 paires/h à 30 ouvriers :
**~4,8 jours**.

### État au 2026-08-26 — **T35 est rendue** : équivalent à gnubg, confirmé

**Terminée le 2026-08-26 à 14:56** — 50 000/50 000 paires, 7 051,0 min, 0 partie bloquée.
Fiche : [`docs/mesures/2026-08-26-T35-verdict.md`](docs/mesures/2026-08-26-T35-verdict.md).

| Moitié | Volume | Mesure | IC 95 % |
|---|---|---|---|
| money cubeful | 50 000 paires | **−0,0119 ppg** | [−0,0310 ; +0,0074] |
| match MWC | 50 000 paires | **50,42 %** | [50,16 ; 50,69] |

**Le verdict** : « équivalent » **confirmé** contre gnubg 2-ply filtre (0,1,3) videau 2-ply
prune 1 ; « supérieur » **non établi** ; **eXtreme Gammon non mesuré**, et cette moitié de
l'objectif ne se déduit pas de l'autre. **La phase 4 ne s'ouvre pas** — aucun plafond *sous*
gnubg n'est démontré.

**Le correctif est vérifié par le journal** : les paires post-Crawford atteignant un videau ≥ 4
passent de 84,1 % à 2,2 %, le videau 8 disparaît, et l'avantage n'est plus concentré en
post-Crawford (+0,0099 par match hors Crawford, −0,0020 dedans).

**Un défaut résiduel est nommé, et il est de notre côté** : dans un videau mort pour le seul
joueur au trait (`away_mover <= cube < away_opponent`), notre modèle redoublait — **3,1 %** des
positions sondées, là où le seul taux correct est zéro. Trois paires rejouées, trois fois nous,
zéro fois gnubg. Il pèse +0,0003 sur les +0,0085 publiés, **contre nous**. Correctif en une
garde + son test ; il ne justifie pas de relancer 4,9 jours de calcul.

**Ce que T35 ne clôt pas** : la métrique **PR** n'a jamais tourné, et la condition de sortie de
la phase 3 est libellée en PR (1,06 → 0,50 → 0,22).

---

# Phase 4 — Modèle propre au projet *(conditionnel)*

> **Ne s'ouvre que si T11 échoue à confirmer la force annoncée, ou si T35 révèle un plafond.**
> Si le modèle MIT existant tient ses promesses, cette phase est un chantier de différenciation
> qu'on choisit, pas un passage obligé.

## T40 — Reproduire la recette de référence

**Objectif** — savoir entraîner, avant de chercher à mieux entraîner.

**Périmètre** — La recette du `BRIEF.md` §4 : TD(0) en ligne, expansion progressive
`[80] → … → [512,512,256,256]`, raffinement par backups de Bellman exacts. Self-play sur tous les
fils, rétropropagation sur GPU si disponible.

**Critères d'acceptation**
- Un modèle entraîné de zéro atteint, dans notre propre round-robin, une force **du même ordre**
  que le modèle de référence.
- Le temps-machine réel de chaque étape est mesuré et consigné.

## T41 — Optimiser le modèle *pour* la recherche

**Objectif** — corriger le défaut que l'auteur de la référence identifie lui-même : son avantage
sur GNU Backgammon **se rétrécit** avec la profondeur (+57,8 mEq/partie en 0-ply, +45,0 en
2-ply), ce qui suggère que les réseaux de GNU Backgammon sont mieux accordés à la recherche
profonde.

**Périmètre** — Distiller une recherche profonde dans le réseau : générer des cibles par recherche
2-ply ou 3-ply (voire par rollouts tronqués) et entraîner le réseau à les prédire directement.
Travail massivement parallèle et coûteux en calcul.

**Contrainte dure** — le réseau reste dans une **enveloppe de taille et de débit compatible avec
le budget navigateur mesuré en T21**. Un modèle meilleur mais trop lent chez l'utilisateur est un
échec. La taille n'est jamais limitée par la mémoire d'entraînement : elle est limitée par le
navigateur.

**Critères d'acceptation**
- L'avantage **en 2-ply** progresse par rapport au modèle de référence, mesuré en round-robin.
- Le débit WebAssembly reste dans l'enveloppe de T21.

## T42 — Round-robin d'arbitrage

**Objectif** — choisir ce qu'on embarque.

**Périmètre** — Modèle de référence contre les modèles entraînés, à profondeur égale, volume
complet.

**Critères d'acceptation**
- Le modèle retenu l'est **sur un chiffre**, avec son intervalle de confiance. En cas d'égalité
  statistique, on garde le plus petit et le plus rapide.

---

# Phase 5 — Publication

## T50 — Publier l'artefact

**Objectif** — qu'un consommateur puisse utiliser une version figée.

**Périmètre** — Poids versionnés (`<réseau>_<version>_<date>.bin`), `.wasm` correspondant, somme
de contrôle, notes de version portant la **mesure de force** de cette version. API JavaScript et
API native documentées.

**Critères d'acceptation**
- La version publiée rejoue le corpus de non-régression de T12 sans écart.
- `THIRD-PARTY.md` est à jour et la notice MIT accompagne l'artefact.
- La nomenclature du `BRIEF.md` §8 est respectée : le nom du réseau conserve la paternité de son
  auteur ; seul le nom de configuration est le nôtre.
- Les notes de version citent le protocole, le volume et l'intervalle de confiance de la mesure
  de force. Une version publiée sans mesure n'est pas publiable.

---

## Ce que ce plan ne couvre pas

- Le format de sérialisation à long terme. Le `.bin` du dépôt de référence suffit à démarrer ;
  adopter OGXF ou un format propre est une question de T50, pas de T10.
- Les rollouts complets (Monte-Carlo à variance réduite). Utiles, mais après le 2-ply.
- Toute interface graphique. Ce dépôt produit une bibliothèque, pas une application.
