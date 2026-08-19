# Le videau appris sans a priori — faisabilité, et plan de recherche

**Date** : 2026-08-19 · **Statut** : étude d'opportunité. **Aucune fiche n'est ouverte par ce
document.** Il instruit une question et propose un plan conditionnel ; `PLAN.md` n'est amendé que
si T35 conclut (voir §10).

## 1. La question

> Est-il faisable d'apprendre un réseau au moins aussi fort que GNU Backgammon, qui aurait appris
> **sans a priori** la gestion du videau **en match** — c'est-à-dire sans table d'équité de match
> (MET) ni formule de Janowski ?

Deux sous-questions qu'il faut séparer, parce qu'elles n'ont pas la même difficulté ni le même
risque :

1. **Apprendre le videau sans formule de point de prise** — déjà fait par quelqu'un d'autre, en
   money, et mesuré (§3.1).
2. **Apprendre la valeur du score** — c'est-à-dire faire émerger la MET de l'expérience au lieu
   de la lire dans une table. Publié comme idée en 2020, **jamais démontré en force** (§3.2).

## 2. Réponse courte

**Oui, c'est faisable, et c'est le seul axe de différenciation réellement ouvert que je vois pour
ce dépôt.** Mais « faisable » se décline, et les degrés de confiance ci-dessous sont **des avis,
pas des mesures** — c'est précisément ce que le plan du §7 propose de transformer en chiffres.

| Affirmation | Confiance | Ce qui la fonde |
|---|---|---|
| Un réseau conscient du score **apprend** une MET implicite cohérente | élevée | La MET est une marginale de la fonction de valeur qu'on entraîne déjà, pas une information extérieure (§4.1) |
| Il apprend des points de prise **meilleurs que Janowski + efficacité réglée** | moyenne-haute | Nos propres mesures T39 chiffrent déjà le prix de l'approximation : sous-double en course, sur-double en fenêtre fine de contact |
| Il égale ou dépasse **GNU Backgammon sur la décision de videau en match, à profondeur égale** | moyenne | La barre est une **heuristique non publiée** de gnubg (§3.4), pas un calcul exact ; et l'amont bat déjà gnubg largement au videau money |
| Il dépasse gnubg **en force globale de match** (pions + videau, 2-ply, mesuré) | basse-moyenne | Notre jeu de pions n'a pas encore de verdict : T35 est en cours, et la répétition cubeful ne conclut rien |
| Il dépasse **eXtreme Gammon** | faible | Aucun élément ne le suggère ; ne pas l'écrire dans un objectif |

**Le risque dominant n'est pas l'apprentissage, c'est la mesure.** En match, l'unité d'observation
est binaire (on gagne ou on perd le match) et la variance explose. Un plan qui ne règle pas ce
problème d'instrument d'abord produira des modèles qu'on ne saura pas départager — exactement la
faute que `CLAUDE.md` règle n°2 interdit.

## 3. Ce que l'état de l'art établit — au 2026-08-19

### 3.1 `alexstrehl/backgammon-ai-engine` (« PureTD ») — le videau money appris, mesuré

Le dépôt de référence du projet. Ce qu'il revendique, textuellement :

> *« Cube action for money games can be learned via RL in the very natural way of simply
> introducing new actions (offer double, take or drop) to the agent and then learning as usual
> from self-play. No formulas based on take-points were used. »*

Le dispositif est minimal : **4 entrées binaires** (`cube_centered`, `cube_own`,
`cube_opponent_own`, `is_cube_action`), les décisions de videau traitées comme de vraies
transitions état-action-état, l'équité estimée valant « sortie du modèle × valeur du videau ».
C'est tout. Aucune fenêtre de double, aucun point de prise, aucune efficacité.

**Et ça marche** — table du README au 2026-08-14, 10 M parties par ligne, IC 95 % bootstrap :

| Modèle | vs gnubg 0-ply | mEMG | XG++ PR (0-ply) |
|---|---|---|---|
| Best cubeful (562k, `[512,512,256,256]`) | **+78,8 mEq/partie** [+77,0 ; +80,6] | 1,85 [1,80 ; 1,90] | **0,94** [0,89 ; 0,99] |
| Cubeless prob5 (528k — **notre modèle**) | +46,3 mEq/partie [+45,5 ; +47,2] | 1,35 [1,32 ; 1,38] | — |
| Best DMP (561k) | 51,80 % [51,77 ; 51,83] | 1,5 | 1,19 [1,14 ; 1,24] |

Et, en 1-ply : *« A 562k-parameter network achieves +19.8 mEq/game against gnubg 1-ply (10M games,
95% CI [+18.0, +21.7]) »*.

**Lecture, en une phrase : un réseau qui n'a jamais vu de formule de point de prise bat le videau
money de gnubg de +78,8 mEq/partie.** C'est la preuve d'existence de la sous-question 1. Elle ne
préjuge pas de la sous-question 2, mais elle en retire le principal doute méthodologique.

Ce que l'amont **n'a pas** fait, et le dit :

> *« Currently it covers 1-point matches (DMP) and money games, but we plan to extend to match
> play. »* · *« We suspect this approach will also work for cube action in match play but that
> remains future work. »*

Le TODO amont porte « Extend to match play » en tête. **L'axe est libre, et il est revendiqué par
son auteur comme la suite qu'il n'a pas encore faite.**

### 3.2 Andrew Lin, TAAI 2020 — l'idée du réseau conscient du score existe

*Learning Cube Strategy in Backgammon with Neural Networks*, Andrew Lin, TAAI 2020,
DOI `10.1109/TAAI51410.2020.00014`. C'est la source que l'amont cite (*« the approach is the same
as described (but not evaluated for money games) by Andrew Lin »*).

Le point important pour nous : l'article **intègre le videau *et le score de match* dans le
réseau**, de sorte que celui-ci apprenne comment le score influence non seulement les décisions de
videau mais **le jeu de pions lui-même**. C'est exactement l'architecture visée ici.

**Réserve d'accès** : l'article est derrière IEEE Xplore et n'a pas été lu. Ce qui précède vient
de la notice, du titre, et de la citation qu'en fait l'amont. **Le lire est la première ligne du
plan (§7, T43) — pas pour en copier quoi que ce soit, mais pour savoir ce qui a déjà été essayé et
avec quel résultat.**

### 3.3 `wildbg` — la voie inverse, prise en juillet 2026

Le dépôt de Carsten Wenderdel (Apache-2.0/MIT), seul autre moteur libre moderne, a fusionné le
2026-07-24 : *« Implement doubling cube logic using Janowski formulas (#42) »*.

Autrement dit : **l'écosystème libre n'explore pas l'axe.** Le seul projet à videau récent vient
de choisir la formule. Si gammonNet fait aboutir le videau de match appris, il est premier —
et le premier résultat publiable du dépôt serait une contribution, pas une reproduction.

### 3.4 GNU Backgammon — la barre à franchir est plus basse qu'on ne croit

Le manuel de gnubg, page *Match Winning Chance*, sur le calcul de la MWC cubeful :

> *« Evaluating the cubeful MWC is more difficult […] it's possible to estimate cubeful MWCs from
> transformation on the w/g/bg distribution or directly calculate it from neural nets. »* — gnubg
> emploie la première voie, et *« the formula are currently not published »*.

Trois conséquences, qu'il faut énoncer sans triomphalisme :

1. Le videau de match de gnubg est une **transformation heuristique** d'une distribution cubeless
   par une table — pas un calcul exact, et pas une formule qu'on puisse auditer.
2. La deuxième voie que le manuel mentionne — *« directly calculate it from neural nets »* — est
   **exactement** ce que cette étude propose. Elle est donc connue et non prise par gnubg.
3. Nous employons aujourd'hui, en pire : la même famille de transformation, plus Janowski, dont
   T39 a **mesuré** les deux défauts (sous-double de course : 25 décisions à coût réel, +1,95
   d'équité totale ; sur-double des fenêtres fines de contact : 26–60, p = 1,6×10⁻⁴).

## 4. Pourquoi c'est apprenable — l'argument de fond

### 4.1 La MET n'est pas une information extérieure

C'est le cœur de l'affaire, et c'est un point de logique, pas d'optimisme.

La MET donne `MWC(a-away, b-away)` = la probabilité de gagner le match **au début d'une partie**,
à ce score. Or c'est, **exactement**, la valeur que prend une fonction de valeur consciente du
score évaluée à la position initiale :

```
MET(a, b)  ≡  V(position initiale, a-away, b-away, videau centré à 1)
```

La MET n'est donc pas une entrée qu'on retire au modèle : c'est **une marginale de la fonction
qu'on lui demande d'apprendre**. Et l'apprentissage y accède par la voie normale : à la fin d'une
partie, la cible du backup n'est pas un terminal, c'est `V(position initiale, nouveau score)` —
un TD qui traverse la frontière des parties. Rien d'exotique.

Le contrôle décisif est historique : **Kazaross-XG2 a elle-même été produite par rollouts**, donc
par du self-play. Demander à un réseau de retrouver cette table par self-play, ce n'est pas lui
demander de deviner une information qu'il n'a pas — c'est lui demander de refaire le calcul qui
l'a produite, en le compressant dans ses poids.

### 4.2 Janowski est une approximation dont nous payons déjà le prix

*Take-Points in Money Games* (1993) interpole linéairement entre videau mort et videau vivant,
indexée par une efficacité. C'est un **modèle**, avec un paramètre libre qu'il faut régler — nous
l'avons réglé sur nos données (x = 0,688 / 0,566 / 0,687), comme la fiche T34 l'exige. Un réseau
qui prend `is_cube_action` et la possession en entrée n'interpole pas : il **représente**
directement la valeur cubeful, et peut faire varier l'efficacité implicite avec la position — ce
que la formule à x constant par état ne peut pas.

C'est précisément la forme des deux défauts mesurés en T39 : ils sont **classe-dépendants**
(course vs contact), c'est-à-dire exactement ce qu'un x constant par état de videau ne peut pas
capturer.

### 4.3 Ce qui reste légitimement « en dur » — et ce n'est pas un a priori

Il faut être précis sur ce qu'on retire, sinon le projet dérive vers une pureté idéologique
coûteuse. On retire la **stratégie** tabulée. On garde les **règles** :

| Gardé (règle du jeu) | Retiré (savoir stratégique tabulé) |
|---|---|
| Crawford, post-Crawford | La table d'équité de match |
| Le *free drop* est **légal** (on ne dit pas quand l'exercer) | Le seuil auquel l'exercer |
| Le videau plafonné par les points restants | La fenêtre de double, le point de prise |
| Jacoby, beaver (activés ou non) | L'efficacité de videau, la formule d'interpolation |
| Le score, comme entrée du réseau | La valeur du score |

Encoder « le score existe » n'est pas un a priori, c'est une observation. Encoder « à 2-away
contre 4-away la MWC vaut 0,68 » en est un.

## 5. Pourquoi ça peut échouer — les modes d'échec, dont les silencieux

Cette section est la contrepartie du §4. Elle est écrite en premier dans l'esprit du plan.

**5.1 La couverture des scores.** Comptage : pour des matchs jusqu'à 25 points, 625 couples
(a-away, b-away), × drapeau Crawford, × 7 valeurs de videau (1…64), × 3 états de possession. Le
self-play naturel visite ces contextes très inégalement — les scores longs et les gros videaux
sont rares. **Mitigation, qui n'est pas un a priori** : tirer le score de départ (et l'état du
videau) uniformément sur la grille au lieu de partir toujours de 0-0 — un schéma d'échantillonnage
(*exploring starts*), pas une connaissance injectée.

**5.2 La dérive du bootstrap.** La valeur à (a,b) dépend des valeurs aux scores voisins, qui
dépendent d'elle. Sans ancre, une erreur systématique peut s'installer sans contradiction interne
— et rester parfaitement plausible. **C'est le mode de défaillance silencieux de `CLAUDE.md`
règle n°2, dans sa forme la plus pure.** Les ancres existent pourtant, et aucune n'est un a
priori stratégique : le bord terminal (0-away) est exact ; le DMP (1-away/1-away) est une partie
sans videau dont nous avons déjà l'étalon ; l'après-Crawford à videau mort est une récursion
élémentaire ; et la table bilatérale de fin de partie (T38) donne des décisions de videau
**exactes** dans son domaine.

**5.3 Le coût de mesure.** Arithmétique, pas mesure : une issue de match est binaire, donc
d'écart-type 0,5 ; séparer 50,5 % de 50 % à 95 % demande `(1,96 × 0,5 / 0,005)² ≈ 38 000` matchs.
À ~6,5 parties par match de 7 points, cela fait ~250 000 parties — l'ordre de la campagne T35
entière, **pour un seul point de comparaison**. Sans réduction de variance (matchs dupliqués,
dés communs) et sans métrique par décision, l'axe est inmesurable en pratique. **C'est le vrai
verrou du projet, et le plan le traite avant le modèle.**

**5.4 La perte d'une propriété d'architecture.** `BRIEF.md` §6 énonce : *« Le match play n'ajoute
rien à la recherche »* — parce que le réseau est aveugle au score. Un réseau conscient du score
casse cette propriété : le cache d'évaluation doit inclure le contexte de score et de videau dans
sa clé (donc taux de succès en baisse), et la recherche n'est plus identique en money et en
match. C'est un coût réel, à mesurer, pas à supposer.

**5.5 Le budget navigateur.** Comptage d'architecture, **pas mesure** : ajouter ~63 entrées
(25+25 one-hot d'away, Crawford, post-Crawford, 7 valeurs de videau, 3 possessions, 1
`is_cube_action`) sur une première couche de 512 ajoute 63 × 512 ≈ 32 000 MACs à un réseau qui en
compte ~527 000, soit **+6 %**. Négligeable — *à confirmer sur le banc T21, comme toute affirmation
de débit.* Le risque de budget n'est pas là : il est dans la tentation d'agrandir le réseau parce
que la tâche est plus dure.

**5.6 La nomenclature et la mesure repartent de zéro.** Des poids nouveaux, c'est un réseau
nouveau (`BRIEF.md` §8) : nouveau nom, et **toute la force à remesurer**. Ce n'est pas un
incrément sur `strehl-prob5`, c'est un second artefact à qualifier entièrement.

## 6. Les instruments qui rendent la chose falsifiable

C'est la partie qui distingue un plan d'un espoir. Chacun de ces instruments est **peu coûteux,
dense en signal, et échoue bruyamment**.

| Instrument | Ce qu'il vérifie | Coût |
|---|---|---|
| **MET implicite extraite** — évaluer la position initiale pour tous les (a,b) et comparer à Kazaross-XG2 | Que la valeur du score apprise est cohérente, et **où** elle diverge | quelques secondes |
| **Points de prise implicites** — à distribution (w,g,bg) figée, balayer et lire la frontière de décision, comparer aux courbes de Janowski | Que la fenêtre de double apprise est monotone et plausible ; le **profil** des écarts | minutes |
| **Identité DMP** — à 1-away/1-away le modèle doit se réduire au comportement DMP (gammons sans valeur) | Une ancre exacte, gratuite | minutes |
| **Ancre bearoff exacte (T38)** — décisions de videau dont la réponse est sans variance | Détecte la dérive là où il n'y a pas d'excuse | heures |
| **Antisymétrie et monotonies** — `MWC(a,b) = 1 − MWC(b,a)`, monotonie en score et en possession | Propriétés structurelles ; tests de propriété, pas d'échantillon | secondes |
| **Arbitre par rollout de match (T39, écrit)** | Tranche les désaccords, en deux colonnes | ~10 min-processus par décision (mesuré en T39) |

**Le point capital sur Kazaross-XG2** : elle est utilisée ici comme **instrument de mesure**,
jamais comme entrée du modèle — exactement le statut que `CLAUDE.md` accorde à GNU Backgammon
comme oracle. Comparer la MET apprise à la MET publiée ne réintroduit aucun a priori dans
l'artefact : rien de la table n'entre dans les poids ni dans le paquet distribué.

## 7. Le plan — six fiches, format `PLAN.md`

L'ordre est un ordre de **dérisquage croissant** : chaque fiche a une porte de sortie, et coûte
plus cher que la précédente. On n'entre dans la suivante que si la précédente passe.

### L'échelle d'architectures — la décision structurante

Trois cibles, de la moins à la plus ambitieuse. **Elles ne sont pas des alternatives : ce sont
trois marches d'un même escalier**, et le saut de l'une à l'autre est une mesure.

| | Architecture | Ce qui disparaît | Ce qui reste |
|---|---|---|---|
| **A** | *Actuel* : prob5 aveugle au score + MET + Janowski | — | — |
| **B0** | Petit MLP `(w, g, bg, lg, lbg, score, état du videau) → MWC cubeful` | MET **et** Janowski | Le réseau de pions, inchangé |
| **B** | Idem, mais la tête voit **aussi la position** | idem | Le réseau de pions, gelé |
| **C** | Un seul réseau conscient du score, actions de videau comprises, self-play de **matchs** | idem | rien du chemin classique |

**B0 est le premier tir, et il est presque gratuit** : c'est littéralement « remplacer MET +
Janowski par une petite fonction apprise », à réseau de pions gelé. S'il échoue, C échouera aussi,
pour beaucoup plus cher.

**L'écart B − B0 mesure exactement ce que vaut « l'efficacité de videau »** — la part de la valeur
cubeful qui dépend de la position et non de la seule distribution. C'est une connaissance qu'on
n'a pas, que personne n'a publiée, et qu'on obtient comme sous-produit. **Cette expérience produit
un résultat dans les deux cas**, ce qui est la meilleure raison de la faire.

---

### T43 — Les instruments, avant le modèle

**Objectif** — pouvoir constater un échec. Aucun poids n'est entraîné dans cette fiche.

**Périmètre** — Extracteur de MET implicite ; extracteur de points de prise et de fenêtres de
double ; corpus **stratifié par contexte de score** (couples d'away, Crawford, post-Crawford,
2-away/2-away, valeurs de videau, possession) figé et versionné ; extension de l'arbitre T39 aux
décisions **de match** (le rollout de match existe depuis le 2026-08-08) ; lecture de Lin (TAAI
2020) et fiche de lecture au registre `docs/etudes/`.

**Le contrôle qui valide les instruments** : les passer sur le **stack classique actuel**, dont on
connaît la réponse. L'extracteur de MET appliqué à la configuration A doit rendre **Kazaross-XG2
à l'identité**, et l'extracteur de points de prise doit rendre **les courbes de Janowski aux x
mesurés**. Un instrument qui ne retrouve pas la réponse connue n'instrumente rien.

**Critères d'acceptation**
- MET extraite de A = Kazaross-XG2, écart nul (identité, pas approximation).
- Points de prise extraits de A = Janowski(x mesurés), écart nul.
- Le corpus stratifié couvre chaque famille de contexte avec un effectif annoncé ; les contextes
  non couverts sont **nommés**, pas oubliés.
- Le coût d'arbitrage d'une décision de match est **mesuré** (T39 donne l'ordre en money).

**Porte de sortie** — aucune : cette fiche est un prérequis, pas un pari.

**Machine** — bureau (pas de volume). **Coût** — quelques jours-homme. *Hypothèse.*

---

### T44 — Réplication du videau money appris (B0 et B, en money)

**Objectif** — vérifier chez nous que le videau s'apprend sans formule, **avant** d'y ajouter la
difficulté du score.

**Périmètre** — Entraîner B0 puis B en **money** (Jacoby), réseau de pions `prob5` gelé, cible =
équité money cubeful, actions de videau comme transitions état-action. Rejouer la campagne
d'arbitrage T39 (mêmes 6 000 décisions, mêmes graines) avec la tête apprise à la place de
Janowski.

**Exclut** — le score, le match, et tout réentraînement du réseau de pions.

**Critères d'acceptation**
- Le **taux d'erreur arbitré** de B0 et de B est comparé à celui de A **sur le même corpus, avec
  les deux colonnes de rollout**, dans la discipline T39 (aucune colonne présentée seule).
- Les deux défauts nommés de A sont examinés **explicitement** : la sous-double de course
  disparaît-elle ? la sur-double des fenêtres fines de contact ?
- Le temps-machine de chaque étape d'entraînement est mesuré et consigné (comme T40 l'exige).

**Porte de sortie** — **si B n'améliore pas A en money, l'axe se referme ici.** Le match ne peut
pas rattraper ce que le money ne donne pas : c'est le même apprentissage avec un conditionnement
en plus.

**Machine** — la machine de calcul. **Coût** — *hypothèse* : la recette amont pour le cubeful
money est de l'ordre de 10 M épisodes 0-ply + 0,5 M en 1-ply + 2 M de raffinement sur 48 ouvriers ;
sur nos 32 fils, à mesurer en début de fiche et à publier avant d'engager la suite. B0, à réseau
gelé, est d'un ordre de grandeur en dessous.

---

### T45 — Le réseau conscient du score (B en match, puis C)

**Objectif** — la MET apprise.

**Périmètre** — Encodage du contexte : away one-hot des deux côtés (plafonné, avec **refus** au
delà — jamais d'approximation, `CLAUDE.md` règle n°2), Crawford, post-Crawford, valeur du videau
en one-hot, possession, `is_cube_action`. Sortie = MWC cubeful du joueur au trait. Entraînement
par self-play de **matchs**, TD traversant la frontière des parties, **départs tirés uniformément
sur la grille de scores**. B d'abord (pions gelés), C ensuite si B tient.

**Critères d'acceptation** — ce sont ceux du §6, et ils sont éliminatoires :
- MET implicite comparée à Kazaross-XG2 : l'écart est **publié cellule par cellule**, et les
  cellules divergentes de plus d'un seuil annoncé sont **arbitrées par rollout de match**, pas
  expliquées. (Un écart n'est pas nécessairement une erreur : la table est elle-même une mesure.)
- Identité DMP à 1-away/1-away : vérifiée, pas supposée.
- Antisymétrie et monotonies : tests de propriété verts.
- Décisions de videau dans le domaine de la table bilatérale : accord mesuré contre l'exact.
- Le *free drop* d'après-Crawford est **trouvé par le modèle** (T39 a déjà établi que notre
  chemin classique le trouve — le repère existe).

**Porte de sortie** — si la MET implicite s'écarte de Kazaross-XG2 de manière **structurée** (un
biais, pas du bruit) et que les rollouts donnent tort au modèle, l'échantillonnage ou l'ancrage
sont en cause ; deux itérations, puis arrêt.

**Machine** — la machine de calcul. **Coût** — *hypothèse* : ×2 à ×5 les épisodes de T44, démarrage à
chaud depuis les poids de T44.

---

### T46 — La recherche, le cache et le navigateur

**Objectif** — savoir ce que le score coûte au moteur livré, pas au modèle.

**Périmètre** — Propagation dans la recherche 2-ply (le piège du niveau intermédiaire de
`BRIEF.md` §6 **disparaît** : la feuille rend déjà une MWC cubeful, l'adversaire maximise donc la
bonne quantité par construction — à vérifier, pas à supposer) ; clé de cache étendue au contexte ;
mesure du taux de succès du cache avant/après ; débit natif et **débit navigateur** dans
l'enveloppe T21.

**Critères d'acceptation**
- Non-régression T12 sur la configuration A (le chemin classique reste intact et livrable).
- Débit WASM mesuré, dans l'enveloppe T21, ou le modèle est refusé.
- Perte de taux de succès du cache **chiffrée**.

**Machine** — bureau.

---

### T47 — L'arbitrage : appris contre classique, puis contre GNU Backgammon

**Objectif** — le chiffre.

**Périmètre, dans cet ordre — et l'ordre est le cœur de la fiche** :
1. **Par décision** (bon marché, dense) : corpus stratifié de T43, taux d'erreur arbitré par
   rollout de match, deux colonnes, par famille de contexte de score. C'est **l'instrument
   principal**.
2. **Par match** (cher, confirmatoire) : matchs **dupliqués** (mêmes dés, sièges échangés) contre
   gnubg à profondeur équivalente, volume **pré-enregistré** à partir de la variance mesurée sur
   une répétition — comme T35 l'a fait pour le money, et pour la même raison.

**Critères d'acceptation**
- Le volume de la campagne de matchs est calculé **avant** de la lancer, sur une variance
  **mesurée**, pas extrapolée d'une autre campagne (leçon explicite de T35 : l'estimation
  cubeless a sous-estimé l'intervalle cubeful d'un facteur ~2,6).
- Aucun verdict de force n'est prononcé sans protocole, volume et intervalle de confiance.
- Les contextes de score où l'appris **perd** sont publiés au même titre que ceux où il gagne.

**Machine** — la machine de calcul. **Coût** — *extrapolation, à requalifier* : ~250 000 parties pour
séparer un demi-point de pourcentage de taux de victoire en match, soit l'ordre de 6 jours au
débit 2-ply mesuré en T35. La réduction de variance par duplication doit être mesurée avant de
retenir ce chiffre.

---

### T48 — Verdict, licence, publication

**Objectif** — décider ce qu'on embarque, et le dire honnêtement.

**Critères d'acceptation**
- Règle de départage **énoncée avant la mesure** : en cas d'égalité statistique, on garde la
  configuration A — plus petite, cache mieux, déjà qualifiée (c'est la règle de T42).
- Si l'appris gagne : `THIRD-PARTY.md` et la notice sont mis à jour — **la MET Kazaross-XG2 sort
  du paquet distribué** (voir §9), et le nouveau réseau porte un nom nouveau (`BRIEF.md` §8), avec
  sa mesure de force propre.
- Le rapport dit, pour chaque chiffre, s'il énonce une mesure ou une hypothèse.

## 8. Ce que ça coûte — récapitulatif

| Fiche | Nature | Ordre de grandeur | Statut du chiffre |
|---|---|---|---|
| T43 | instruments | jours-homme, calcul négligeable | — |
| T44 | entraînement money | jours-machine | **hypothèse**, à mesurer en ouverture de fiche |
| T45 | entraînement match | semaines-machine | **hypothèse** |
| T46 | intégration | jours-homme | — |
| T47 | mesure | ~6 jours-machine par point de comparaison | **extrapolation** du débit T35 |

**Le poste dominant est T47, pas l'entraînement.** C'est contre-intuitif et c'est la raison d'être
de l'ordre choisi : la métrique par décision (T47.1) doit porter l'essentiel des conclusions, la
campagne de matchs ne servant qu'à confirmer.

## 9. Le bénéfice qui n'est pas de la force — et qui compte

`CLAUDE.md` pose comme non négociable qu'aucune brique non libre n'entre dans l'artefact
distribué, et impose l'attribution de tout ce qui vient d'ailleurs. Aujourd'hui, l'artefact
embarque **une œuvre d'un tiers** : la table Kazaross-XG2, œuvre de Neil Kazaross, utilisée avec
attribution (précédent blunderDB).

**Une MET apprise la remplace par du calcul que nous avons produit.** Ce n'est pas une question de
licence — l'usage actuel est légitime et attribué — mais de **provenance** : l'artefact ne
dépendrait plus que de choses reproductibles chez nous (poids entraînés, tables de fin de partie
calculées) plus le réseau de pions de l'amont. Pour un dépôt dont le critère de succès est
« justifiable par une mesure reproductible dont chaque source est traçable », c'est un gain
structurel, pas cosmétique.

Il faut aussi le dire dans l'autre sens : **la table restera dans le dépôt comme instrument de
mesure**, et son attribution avec elle. Elle change de statut, elle ne disparaît pas.

## 10. Décision proposée

**Ne rien ouvrir maintenant.** `CLAUDE.md` : « Ne pas élargir le périmètre. L'entraînement d'un
modèle propre au projet (phase 4) est conditionnel au résultat de la phase 1. Ne pas l'engager
avant. » Cette étude est un dossier, pas une ouverture de chantier.

**Ce que déclenche chaque issue de T35** :

| Issue de T35 | Ce que ça implique pour cet axe |
|---|---|
| Nous battons gnubg en 2-ply, nettement | La phase 4 reste fermée. Terminer T50 d'abord. L'axe reste en réserve — c'est un projet de recherche, pas un correctif |
| Égalité statistique, ou avantage qui se referme avec la profondeur | **Ouvrir T43 et T44.** Le videau est le poste où l'écart mesuré est le plus concret (T39 nomme deux défauts) et le moins cher à attaquer |
| Nous perdons | Le problème est le jeu de pions, pas le videau. T41 (optimiser le modèle *pour* la recherche) passe devant |

**Dans tous les cas, T43 est peu coûteuse et sans regret** : ses instruments — MET extraite,
points de prise extraits, corpus stratifié par score — mesurent aussi le chemin classique actuel,
qu'on garde de toute façon. C'est la seule fiche que je proposerais d'ouvrir tôt.

## 11. Veille amont — l'amont a bougé, et ça nous concerne

Constats du 2026-08-19, sur `alexstrehl/backgammon-ai-engine`. **Ces trois points sont
indépendants de l'étude ci-dessus et plus urgents qu'elle.**

**11.1 Un correctif de générateur de coups, postérieur à notre pin.** Commit `5c9aa87`
(2026-08-12), message textuel :

> *« Fix a false forced-pass in `get_legal_plays` where a shorter play shadowed the maximal play
> (incidence at most 1/3700). »*

Il touche `c_engine/bg_engine.c` — **le fichier que `THIRD-PARTY.md` déclare compilé dans
`build/libgammonnet.so` comme notre moteur de règles**, derrière `src/gn_rules.h`. Notre pin est
`b2750df` (2026-06-17), antérieur. Conséquence à vérifier, pas à supposer : nos parties peuvent
avoir déclaré un passage forcé là où un coup maximal existait, à raison d'au plus 1 pour 3 700.
`src/gn_rules_reference.c` est une implémentation indépendante — **le test différentiel entre les
deux est l'instrument qui tranche**, et il doit être rejoué contre la version corrigée.

**11.2 Les poids de référence ont changé en amont.** Comparaison des empreintes de blobs :

| Fichier | Notre pin | Amont (2026-08-19) |
|---|---|---|
| `cubeless_prob5_512_512_256_128.pt` | `7d8092e1…` | **`7d06460b…`** |
| `cubeful_money_512_512_256_256.pt` | `931a420f…` | **`09e3465c…`** |

Le premier est **le réseau que nous embarquons et mesurons**. Rester sur notre pin est un choix
défendable — reproductibilité — mais c'est un choix, qui doit être écrit ; le subir n'en est pas
un. Migrer implique de rejouer T11 et T12.

**11.3 Les chiffres cités dans `BRIEF.md` §3.1 ne sont plus ceux de l'amont.** La table du README
a été recalculée **deux fois** depuis : sur le générateur corrigé (2026-08-12), puis contre un
gnubg vérifié comme portant la base de bearoff bilatérale (2026-08-13/14). Le `BRIEF.md` annonce
+57,8 mEq/partie et PR 1,06 en 0-ply ; le README courant donne +46,3 mEq/partie pour le prob5, et
+78,8 / PR 0,94 pour son meilleur modèle cubeful. **Le rapprochement ligne à ligne reste à faire**
— les tables n'ont pas la même structure et il n'est pas établi qu'elles décrivent les mêmes
lignes. En attendant, `BRIEF.md` §3.1 doit porter la date de son relevé.

## 12. Sources

- `alexstrehl/backgammon-ai-engine` (MIT) — <https://github.com/alexstrehl/backgammon-ai-engine>,
  README et historique consultés le 2026-08-19 (dernier commit `2026-08-14`).
- Andrew Lin, *Learning Cube Strategy in Backgammon with Neural Networks*, TAAI 2020 —
  <https://doi.org/10.1109/TAAI51410.2020.00014> · <https://ieeexplore.ieee.org/document/9382451/>
  (**non lu** : accès IEEE).
- Manuel GNU Backgammon, *Match Winning Chance* —
  <https://www.gnu.org/software/gnubg/manual/html_node/Match-Winning-Chance.html>
- `wildbg` — <https://github.com/carsten-wenderdel/wildbg>, PR #42 « Implement doubling cube logic
  using Janowski formulas », fusionnée le 2026-07-24.
- Rick Janowski, *Take-Points in Money Games*, 1993 (modèle de référence de T34).
- Nos propres mesures : `docs/mesures/2026-08-08-T39-arbitrage-money.md`,
  `docs/mesures/2026-08-08-T39-fin.md`, `docs/mesures/2026-08-09-t35-repetition.md`,
  `docs/specs/t34-videau-spec.md`.
