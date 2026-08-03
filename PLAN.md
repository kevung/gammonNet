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
Phase 3 — Profondeur & exactitude  T30 T31 T32 T33 T34 T35      (la force arrive ici)
Phase 4 — Modèle propre au projet  T40 T41 T42                  ← CONDITIONNEL
Phase 5 — Publication              T50
```

**Chemin critique** : `T00 → T01 → T02 → T10 → T20 → T21 → T30 → T32 → T35 → T50`.

Tout le reste peut se paralléliser autour. **T02 (le codec) est le goulot** : rien de mesurable
n'existe avant lui, et une erreur à cet endroit invalide silencieusement toutes les mesures
ultérieures. Lui consacrer le soin qu'on donnerait à un chiffrement.

**Règle de séquencement** : la phase 4 ne s'ouvre **que si** la phase 1 échoue à confirmer la
force annoncée du modèle de référence, ou si la phase 3 révèle un plafond. Ne pas l'engager par
enthousiasme.

---

## Répartition entre machines — deux pistes *(à partir du 2026-08-03)*

> **Si vous êtes un agent qui exécute la roadmap : cette section vous concerne, lisez-la avant de
> prendre la tâche suivante.**

Le travail est réparti sur deux machines aux profils **complémentaires**, pas concurrents.

| | `mochy` — **piste A** | machine de bureau — **piste B** |
|---|---|---|
| Profil | Threadripper 16 c / 32 f, 94 Gio, 2 × RTX 4090, RHEL 8, **GCC 8.5** | 16 cœurs, 4 Gio libres, pas de GPU, **GCC 16.1**, Firefox 153, Node 26 |
| Vocation | Gros volumes : oracle, round-robins, entraînement | Navigateur : Emscripten, WASM, bancs de débit client |
| Réseau | — | Sortie internet, **pas de LAN** |

**La piste navigateur ne peut pas tourner sur `mochy`** — aucun navigateur, et une chaîne C++17
ancienne. **La piste calcul ne peut pas tourner sur la machine de bureau** — 4 Gio libres et pas
de GPU. La séparation n'est pas une commodité d'organisation, elle est matérielle.

### Qui prend quoi

| Tâche | Machine | Note |
|---|---|---|
| T02, T03, T04 | **`mochy`** | L'instrument de mesure ; T03 et T04 veulent les 32 fils |
| **T10** | **bureau** | **Déplacée.** Toute la piste B en dépend directement ; la refaire des deux côtés serait du gaspillage |
| T20, T21, T30, T31 | **bureau** | Descente anticipée vers le verdict navigateur |
| T22, T23 | **bureau** | Suite naturelle de la phase 2 : le choix du moteur (T22) se tranche **sur mesure**, donc là où l'on mesure |
| T11, T12 | **`mochy`** | Reprend après T10 ; c'est le seul très gros calcul |
| **T32** | **bureau** | **Déplacée le 2026-08-04.** Son critère est de l'antisymétrie et de la monotonie, pas du volume. Et elle est consommée par la **recherche**, qui vit ici : la laisser sur l'autre machine imposerait un aller-retour pour le piège du niveau intermédiaire |
| T34, T35 | **`mochy`** | Besoin de l'oracle et du volume |
| T33 (volet **coût**) | bureau | Générer le bearoff et **mesurer ses octets** — entrée du budget navigateur |

**Point de rendez-vous** : `mochy` s'arrête après **T04** et attend que **T10** soit livrée par la
piste B avant d'attaquer **T11**. *(Levé le 2026-08-03 ; T11 est livrée.)*

### Certaines tâches ne s'attribuent pas — elles se coupent

À partir de T31, la règle « le calcul lourd va sur `mochy` » ne suit plus le découpage en fiches :
une même tâche a une moitié bon marché et une moitié coûteuse.

| Tâche | Bureau | `mochy` |
|---|---|---|
| **T31** | écrit le harnais et le corpus, valide sur une poignée de positions | **génère la référence 2-ply non filtrée** — ~1,8 M évaluations par décision |
| **T33** | mesure les octets, entrée du budget navigateur | **génère les tables de fin de partie** |

Le livrable reste unique et la fiche aussi ; c'est l'exécution qui se répartit.

### File d'attente de `mochy` *(au 2026-08-04)*

> **Agent qui exécute la roadmap sur `mochy` : prendre dans cet ordre.**

| | Tâche | Pourquoi maintenant |
|---|---|---|
| **1** | **T33** — tables de fin de partie | **Ne dépend de rien** : ni du filtre, ni de l'équité de match, ni du modèle. Son critère est une **vérification croisée** — deux implémentations correctes d'un calcul exact produisent des fichiers identiques. Travail long, parfaitement isolé |
| **2** | **T31, la moitié coûteuse** — référence 2-ply **non filtrée** | ~1 812 000 évaluations par décision, soit **~5,1 s** sur 32 fils. Le bureau écrit le harnais et le corpus ; `mochy` produit la référence |
| **3** | **T12** — corpus de non-régression | Peu coûteux, indépendant, à glisser entre les deux |

**Ne pas prendre T35.** Elle est la **somme** de T31, T32, T33 et T34 — son périmètre dit
« configuration complète ». Lancée avant, elle mesurerait un filtre arbitraire, sans équité de
match et sans bearoff, et **produirait un chiffre que chacune des quatre viendrait invalider**.
Dans un projet qui ne cite que des mesures, un chiffre obsolète est pire que pas de chiffre : on
le retrouve cité six mois plus tard.

#### Dimensionner la référence de T31 plutôt que la fixer

Le critère de T31 demande « ≥ 100 000 décisions ». À 5,1 s la décision, cela ferait **six jours de
`mochy` pour la seule référence**.

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

## T34 — Décision de videau

**Objectif** — doubler, prendre, passer.

**Périmètre** — Modèle cubeful à partir de la distribution `prob5` et de la table d'équité de
match (formules de Janowski, ou modèle dead-cube pondéré).

**Critères d'acceptation**
- Sur un corpus de ≥ 5 000 décisions de videau, le taux d'accord avec l'oracle est mesuré, et les
  désaccords sont classés par ampleur d'équité.
- La fenêtre de double et le point de prise sont monotones (tests de propriété).

## T35 — Round-robin complet en 2-ply

**Objectif** — la mesure qui répond à l'objectif du projet.

**Périmètre** — Configuration complète (réseau + recherche 2-ply filtrée + équité de match +
tables de fin de partie) contre GNU Backgammon à profondeur équivalente, en money et en match,
~~≥ 1 M parties par paire~~ **≥ 100 000 parties par paire — amendé le 2026-08-04**.

> **Le million était sur-spécifié pour la question posée, et infaisable.** T30 a mesuré le coût
> réel : 12 951 évaluations par décision en 2-ply filtré 1/1. Un million de parties représente
> donc `12 951 × ~55 décisions × 10⁶ ≈ 7,1 × 10¹¹` évaluations, soit **~23 jours sur `mochy`**
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
