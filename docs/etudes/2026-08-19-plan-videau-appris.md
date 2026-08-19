# Le videau appris — plan détaillé, et la question de l'architecture

**Date** : 2026-08-19 · **Statut** : plan conditionnel. Rien n'est ouvert.
**Compagnon** de [l'étude d'opportunité du même jour](2026-08-19-videau-appris-sans-a-priori.md),
dont il remplace le §7 : les six fiches esquissées T43-T48 y étaient un croquis, celles-ci sont
le plan. **Renumérotées T60-T69** (phase 6) pour ne pas empiéter sur la numérotation des phases 4
et 5, qui restent ce qu'elles sont.

---

# Partie I — L'architecture est-elle en cause ?

## 1. La réponse courte

**Oui, mais le suspect n'est pas celui qu'on désigne d'habitude.**

| Ce qu'on soupçonne spontanément | Verdict | Fondement |
|---|---|---|
| L'encodage à 196 caractéristiques serait trop pauvre pour le videau | **probablement pas** | §2 — une preuve empirique existe déjà |
| Il faudrait un réseau plus gros / plus profond | **probablement pas, et c'est interdit** | §6 — la contrainte est le navigateur |
| La sortie `prob5` suffit à décider du videau | **non — c'est le vrai défaut structurel** | §3 |
| L'endroit où le score entre dans le réseau est un détail d'implémentation | **non — c'est la décision la plus structurante du programme** | §4 |
| Le réseau peut être conçu indépendamment de la recherche | **non** | §5 |

## 2. L'encodage n'est pas le suspect — et on a la preuve

Le réflexe serait d'enrichir les 196 entrées de Tesauro avec des caractéristiques de volatilité :
blots, tirs directs, points bloqués, avance à la course. C'est tentant, et l'évidence disponible
dit que ce n'est pas là que ça coince.

**La preuve** : les réseaux *cubeful* de l'amont utilisent **exactement les mêmes 196
caractéristiques**, plus **4 entrées binaires** de videau (`cube_centered`, `cube_own`,
`cube_opponent_own`, `is_cube_action`) — rien d'autre. Aucune caractéristique de volatilité,
aucune formule. Et ils obtiennent **+78,8 mEq/partie contre gnubg 0-ply, PR XG++ 0,94**.

Autrement dit : **196 entrées suffisent à battre le videau money de GNU Backgammon largement.**
Un plan qui commencerait par réviser l'encodage dépenserait son premier mois sur le seul
composant dont on sait déjà qu'il fait le travail.

*Réserve* : « suffisent en money » n'est pas « suffisent en match ». Mais le match n'ajoute pas de
difficulté **positionnelle** — il ajoute une difficulté **contextuelle**, et le contexte n'est pas
dans le plateau. L'ablation reste au programme (T69, en dernier), pas en tête.

## 3. Le vrai défaut structurel : `prob5` ne peut pas porter une décision de videau

C'est le point central de cette partie, et c'est un argument de forme, pas d'expérience.

Les cinq probabilités sont une **statistique résumée de l'issue** de la partie. L'équité cubeless
en est une fonction linéaire — donc `prob5` est *suffisant* pour l'équité sans videau, et pour la
MWC sans videau via la table. **Le videau, lui, ne dépend pas de la moyenne : il dépend de la
dispersion.**

> Deux positions peuvent avoir les **mêmes cinq probabilités** et des décisions de videau
> opposées : un jeu de retenue tranquille où le videau peut attendre, et un blitz volatil où il
> faut doubler maintenant sous peine de perdre son marché.

Ce que Janowski appelle « efficacité de videau » est précisément un **scalaire réglé à la main
pour approximer cette dispersion**. gnubg fait la même chose par classe de position. Nous faisons
la même chose avec trois valeurs mesurées (x = 0,688 / 0,566 / 0,687).

**Trois conséquences opérationnelles :**

1. Toute architecture qui calcule le videau **en fonction des seules cinq probabilités** a un
   plafond structurel. C'est l'architecture B0 de l'étude — et ce n'est plus une marche de
   l'échelle, c'est **le témoin négatif de l'expérience** (T63).
2. Les deux défauts que T39 a mesurés sont exactement de cette forme : ils sont
   **classe-dépendants** (sous-double en course, sur-double en fenêtre fine de contact). Un
   scalaire par état de videau ne peut pas les corriger — un réseau qui voit la position, si.
3. Il existe une troisième voie, ni « moyenne seule » ni « tout apprendre » : **prédire
   explicitement la dispersion**. C'est T64, et c'est bon marché (§ ci-dessous).

### La tête de volatilité — la proposition la plus concrète de ce plan

La quantité qui manque est calculable, exactement, à un coût connu : à partir d'une position,
développer les **21 jets** de l'adversaire et prendre sa meilleure réponse donne la **distribution
de l'équité au prochain point de décision**. C'est un développement 1-ply : **~390 évaluations**,
contre 38 721 pour une décision 2-ply.

On peut donc **distiller la volatilité** dans le réseau : cible = l'écart-type (ou quelques
quantiles) de cette distribution à 1-ply, apprise par supervision, sans rollout, sans formule.

Ce que ça donne :

- une entrée du videau qui remplace l'efficacité réglée à la main par **une prédiction mesurable
  position par position** ;
- une expérience qui **produit un résultat dans les deux sens** : si la tête de volatilité comble
  l'écart B0 → B, on sait que « efficacité de videau » = « dispersion à 1-ply », ce qui est un
  résultat publiable ; si elle ne le comble pas, on sait que le videau dépend de la structure de
  la position au-delà de sa dispersion immédiate, ce qui l'est tout autant ;
- un **usage secondaire** : la volatilité prédite est un critère naturel d'allocation de
  profondeur (chercher plus loin là où ça bouge). Hors périmètre ici, noté pour plus tard.

## 4. La décision la plus structurante : par où entre le score

C'est ici que l'architecture cesse d'être une question d'apprentissage et devient une question
de **système**. Deux options, et elles ne coûtent pas la même chose.

### Option A — le score entre à l'entrée du tronc

C'est ce que font Lin (TAAI 2020) et la voie naturelle : ~63 entrées de contexte concaténées aux
196 du plateau, le tronc est réentraîné.

**Ce que ça coûte, et qui n'est presque jamais compté** : le tronc devient
**score-dépendant**, donc :

- **le cache d'évaluation se fragmente.** `gn_evalcache` a aujourd'hui pour clé la **position
  seule**, et c'est légitime parce que la distribution rendue est indépendante du score et du
  videau (T3A l'a prouvé au bit). Avec un tronc conscient du score, la clé doit porter le
  contexte. Le cache mesuré rapporte **×3,41 au point de fonctionnement** ; sa fragmentation est
  une perte directe, à mesurer.
- **une même position évaluée sous plusieurs contextes coûte plusieurs passes avant.** Or c'est
  exactement ce que fait une décision de videau : comparer non-double, double-pris, double-passé,
  c'est évaluer la même position sous trois états de videau. Et en match, les deux camps ne
  voient pas le même score.

### Option B — fusion tardive : tronc aveugle, tête consciente

Le tronc ne voit que le plateau et produit un **goulot étroit** ; le score et l'état du videau
n'entrent que dans une petite tête appliquée après.

```
position ──► TRONC (aveugle au score) ──► goulot (5 probs + k auxiliaires) ──┐
                                                                             ├──► TÊTE ──► MWC cubeful
score, videau, Crawford ────────────────────────────────────────────────────┘
```

**L'arithmétique** (comptage d'architecture, pas mesure) : le tronc pèse ~527 000 MACs ; une tête
`(16 + 63) → 64 → 3` en pèse ~5 000, soit **~1 %**. Évaluer une position sous **cinq** contextes
coûte donc `1 tronc + 5 têtes ≈ 1,05 tronc` en fusion tardive, contre **5 troncs** en option A.

> **Un facteur ~5 sur le poste dominant du moteur, pour une décision d'architecture — et le cache
> reste valide, puisque le tronc reste aveugle au score.**

### Le paramètre de conception qui en découle : la largeur du goulot

La tête ne peut pas consommer la dernière couche cachée (128 flottants) sans coût : le cache
devrait alors stocker 128 flottants par position au lieu de 5.

| Goulot | Octets par entrée de cache (clé 29 o + charge) | Ce que la tête peut voir |
|---|---|---|
| 5 (`prob5` seul) | ~49 o | la moyenne — **plafonné, cf. §3** |
| **16** (5 probs + 11 auxiliaires dont la volatilité) | ~93 o | la moyenne **et** la dispersion |
| 128 (dernière couche cachée) | ~541 o | tout, au prix d'un cache 11× plus lourd |

**Recommandation de conception, à trancher par la mesure de T65** : un goulot **étroit et
interprétable** — les 5 probabilités, plus une poignée d'auxiliaires dont la volatilité de T64.
Il garde le cache bon marché, il garde le goulot lisible (donc diagnosticable), et il donne à la
tête ce que le §3 dit qu'il lui manque.

## 5. Le réseau ne se conçoit pas sans la recherche

T36 l'a déjà mesuré pour le jeu de pions : **notre avantage 0-ply s'annule au 2-ply**. Rien ne
garantit qu'un videau appris, excellent en 0-ply, le reste quand on le propage dans l'arbre.

Deux points précis :

- **Un réseau qui rend directement une MWC cubeful change la structure de la recherche** : la
  récursion de videau aux feuilles (T34 phase 2) n'a plus lieu d'être, la feuille rend déjà la
  bonne quantité. C'est une **simplification et une accélération** — et un risque : le piège du
  niveau intermédiaire (`BRIEF.md` §6) disparaît *par construction*, ce qui est exactement le
  genre de propriété qu'il faut vérifier plutôt que croire.
- **La cohérence sous recherche est une propriété à mesurer, pas à supposer.** Un modèle cubeful
  appris à 0-ply peut se dégrader en 2-ply si ses erreurs se corrèlent le long des branches.
  T67 le mesure avec le protocole de T36, qui existe déjà.

## 6. Ce que le navigateur impose — la métrique n'est pas la précision

L'objectif reprécisé le 2026-08-07 met le **3-ply dans le navigateur** au périmètre produit. Le
coût natif actuel est de **60-96 s par décision** en 3-ply.

Donc : **toute proposition d'architecture se juge en précision *par MAC*, jamais en précision.**
Un réseau meilleur et plus lent est un échec, et la contrainte ne vient pas de la machine
d'entraînement — elle vient du client. C'est une règle du `BRIEF.md`, elle s'applique ici sans
adaptation.

Corollaire favorable : la fusion tardive et le goulot étroit ne sont pas seulement des choix
d'apprentissage, ce sont les seuls qui tiennent dans ce budget.

---

# Partie II — Le programme

## 7. La matrice d'ablations — quelle expérience répond à quelle question

C'est le cœur du plan : chaque ligne est une question à laquelle une expérience répond, et dont
la réponse **décide** de la suite. Aucune n'est là pour « voir ».

| # | Question | Expérience | Métrique | Ce que la réponse décide |
|---|---|---|---|---|
| 1 | Le videau se réduit-il aux 5 probabilités ? | **B0** (tête sur `prob5` seul) contre **B** (tête sur goulot enrichi), money | taux d'erreur arbitré sur les 6 000 décisions de T39, mêmes graines | Si B0 ≈ B : la dispersion ne compte pas — surprenant, et tout devient simple. Si B ≫ B0 : Janowski est structurellement plafonné, et le §3 est confirmé |
| 2 | « Efficacité de videau » = « dispersion à 1-ply » ? | **tête de volatilité distillée** ajoutée à B0 | l'écart B0 → B est-il comblé, et de combien | La recette : distiller (bon marché) plutôt qu'apprendre en RL (cher) |
| 3 | Par où entre le score ? | **fusion tardive** contre **entrée du tronc** | erreur par famille de score **et** coût de recherche mesuré (passes avant/décision, taux de succès du cache) | La décision la plus structurante — §4 |
| 4 | La MET s'apprend-elle vraiment ? | extraction de la MET implicite à chaque point de contrôle | écart cellule par cellule à Kazaross-XG2, écarts arbitrés par rollout de match | **La porte de sortie de tout l'axe** |
| 5 | Faut-il plus de capacité ? | variantes de tronc à budget de MACs croissant | erreur / MACs, débit WASM | Le budget navigateur tranche, pas la précision |
| 6 | L'encodage à 196 suffit-il ? | + caractéristiques explicites de volatilité (blots, tirs, blocage) | erreur / MACs | Si oui : résultat publiable — l'encodage de Tesauro est insuffisant pour le videau. **En dernier, cf. §2** |
| 7 | Le videau appris tient-il sous recherche ? | protocole T36 appliqué au modèle appris | perte par décision, 0-ply contre 2-ply | Si l'avantage s'annule au 2-ply, c'est T41 qu'il faut, pas ce plan |

**Les six premières lignes se répondent à tronc gelé** — donc en **heures**, pas en semaines
(cf. le budget de l'étude, §8.3 : 16 h pour un entraînement à tronc gelé). C'est l'argument
décisif de l'ordre choisi : **on peut répondre à presque toute la question d'architecture avant
d'avoir dépensé un seul jour de calcul lourd.**

## 8. Les fiches

### Volet 0 — l'atelier (prérequis, et sans regret)

---

#### T60 — Les instruments de falsification

**Objectif** — pouvoir constater un échec en minutes. Aucun poids entraîné.

**Périmètre**
- Extracteur de **MET implicite** : évaluer la position initiale pour tous les couples d'away,
  rendre la table, la comparer cellule par cellule à Kazaross-XG2.
- Extracteur de **points de prise et de fenêtres de double** : à distribution figée, balayer et
  lire la frontière de décision.
- **Corpus stratifié** par contexte de score, figé et versionné : couples d'away, Crawford,
  post-Crawford, 2-away/2-away, valeurs de videau, possession. Effectif annoncé par famille.
- Extension de l'arbitre T39 aux décisions **de match** (le rollout de match existe déjà).
- Fiche de lecture de **Lin, TAAI 2020** au registre `docs/etudes/`.

**Décisions prises d'avance** — la MET de référence est Kazaross-XG2, employée en **instrument**
et jamais en entrée ; le seuil d'écart déclenchant un arbitrage est fixé **avant** la première
extraction, pas après en avoir vu la tête.

**Critères d'acceptation** — les instruments sont passés sur le **stack classique**, dont la
réponse est connue : la MET extraite de la configuration classique doit rendre **Kazaross-XG2 à
l'identité**, les points de prise extraits doivent rendre **Janowski aux x mesurés**, à l'identité.
Un instrument qui ne retrouve pas la réponse connue n'instrumente rien.

**Porte de sortie** — aucune : prérequis.

**Machine** — bureau. **Coût** — jours-homme, calcul négligeable.

---

#### T61 — L'atelier d'entraînement

**Objectif** — que produire un modèle candidat coûte une commande et une nuit.

**Périmètre**
- Générateur de **self-play de matchs** avec **départs tirés uniformément** sur la grille de
  scores et d'états de videau (*exploring starts* — un schéma d'échantillonnage, pas un a priori).
- **TD traversant la frontière des parties** : en fin de partie, la cible est la valeur de la
  position initiale au **nouveau score**.
- Points de contrôle réguliers, et **la batterie de T60 exécutée automatiquement à chaque point
  de contrôle**, tracée. C'est le mécanisme qui rend une itération ratée visible en minutes.
- Refus explicite hors domaine (longueur de match au-delà de l'entraînement) — jamais
  d'approximation silencieuse.

**Décisions prises d'avance** — longueur de match d'entraînement plafonnée et annoncée ;
Crawford, post-Crawford, *free drop* et plafonnement du videau implémentés comme **règles**, la
stratégie n'en étant jamais dérivée.

**Critères d'acceptation** — contrôle nul (un modèle contre lui-même rend exactement zéro à tout
score, comme le pilote de T35) ; reprise exacte après interruption ; la batterie de diagnostics
tourne et trace sans intervention.

**Machine** — la machine de calcul. **Coût** — jours-homme.

---

#### T62 — Le débit : lot élargi, puis GPU

**Objectif** — faire passer une itération de deux semaines à deux jours. **Cette fiche est utile
même si l'axe du videau appris ne s'ouvre jamais** : elle sert T35, T39 et T3A à l'identique.

**Périmètre**
- **Niveau I (bit-identique)** : largeur vectorielle (`-mprefer-vector-width=256` — vérifié à la
  compilation le 2026-08-19 : ymm apparaît, **aucun FMA n'est émis**, donc l'arithmétique par
  voie est inchangée) ; **élargissement du lot** en rassemblant les feuilles en travers des 21
  jets et des candidats, au lieu du lot par jet de largeur utile ~18,5 sur 32.
- **Niveau II (décision-identique)** : chemin d'inférence **CUDA**, fp32 strict, **TF32
  désactivé**, largeur de lot fixe et algorithme figé pour le déterminisme.
- Ordre imposé : **le rollout d'abord**. C'est le calcul le plus massivement parallélisable du
  dépôt et le seul dont le portage n'a **aucun effet de bord sur l'artefact livré**.

**Décisions prises d'avance** — le niveau I se valide par l'**empreinte d'évaluation inchangée**
(`1d92f0d3…`) ; le niveau II par **zéro basculement de décision** sur le corpus T12, écart
résiduel publié. Aucun build n'est écrasé pendant une campagne en cours.

**Critères d'acceptation** — profil mesuré du partage **génération de coups / encodage / matmul**
(le premier chiffre à obtenir : il fixe le plafond d'Amdahl de tout le reste) ; gain mesuré à
chaque niveau ; empreinte ou corpus, selon le niveau.

**Machine** — la machine de calcul (2× RTX 4090, **à 0 % pendant que 30 processus saturent les 16
cœurs**, constat du 2026-08-19).

---

### Volet 1 — l'architecture, à tronc gelé (bon marché)

---

#### T63 — Le support de la décision : B0 contre B

**Objectif** — répondre à la ligne 1 de la matrice : le videau se réduit-il à `prob5` ?

**Périmètre** — Deux têtes, tronc `prob5` **gelé**, en **money** (Jacoby) :
**B0** = `(5 probs, état du videau) → équité cubeful` ; **B** = `(goulot enrichi, état du videau)
→ équité cubeful`. Rejeu de la campagne d'arbitrage de T39 : mêmes 6 000 décisions, mêmes graines,
deux colonnes de rollout, aucune colonne présentée seule.

**Exclut** — le score, le match, tout réentraînement du tronc.

**Critères d'acceptation** — les **deux défauts nommés** de la voie classique sont examinés
explicitement : la sous-double de course disparaît-elle ? la sur-double des fenêtres fines de
contact ? Le temps-machine est consigné.

**Porte de sortie** — **si B n'améliore pas la voie classique en money, l'axe se referme ici.**
Le match ne rattrapera pas ce que le money ne donne pas.

**Machine** — la machine de calcul. **Coût** — ~16 h d'entraînement par tête (extrapolé du débit
mesuré), plus l'arbitrage.

---

#### T64 — La tête de volatilité, distillée

**Objectif** — répondre à la ligne 2 : « efficacité de videau » est-elle « dispersion à 1-ply » ?

**Périmètre** — Cible calculée par développement 1-ply (21 jets × meilleure réponse ≈ 390
évaluations par position) : écart-type, et quelques quantiles, de l'équité au prochain point de
décision. Apprentissage **par supervision**, sur des positions issues de notre propre self-play.
Puis B0 + volatilité, comparé à B.

**Critères d'acceptation** — l'écart B0 → B est comblé, ou ne l'est pas, **et le chiffre est
publié dans les deux cas**. La volatilité prédite est comparée à la volatilité vraie sur un
corpus tenu à l'écart.

**Machine** — la machine de calcul. **Coût** — la génération des cibles domine : 390 évaluations
par position, donc ~4×10⁸ évaluations pour un million de positions, de l'ordre de l'heure au
débit agrégé mesuré.

---

#### T65 — Par où entre le score : fusion tardive contre entrée du tronc

**Objectif** — répondre à la ligne 3, la décision la plus structurante.

**Périmètre** — Deux modèles conscients du score, entraînés sur le même atelier :
**fusion tardive** (tronc gelé, tête `(goulot, contexte) → MWC cubeful`) et **entrée du tronc**
(~63 entrées de contexte concaténées, tronc réentraîné). Encodage du contexte : one-hot d'away
des deux côtés (plafonné, refus au-delà), Crawford, post-Crawford, valeur du videau, possession,
`is_cube_action`.

**La comparaison porte sur deux axes, et le second n'est jamais oublié** :
1. **précision** — erreur par famille de contexte de score ;
2. **coût de recherche mesuré** — passes avant par décision, taux de succès du cache, octets par
   entrée de cache. C'est là que se joue le facteur ~5 du §4.

**Décisions prises d'avance** — la largeur du goulot est un paramètre de l'expérience, pas un
choix pris en cours de route : trois valeurs (5, 16, 128) sont mesurées.

**Critères d'acceptation** — un tableau à deux entrées précision × coût, et une recommandation
qui **cite les deux**.

**Machine** — la machine de calcul. **Coût** — la branche « entrée du tronc » est la seule qui
demande un réentraînement complet (de l'ordre de la semaine, ou du jour avec T62).

---

#### T66 — La MET implicite : la campagne de diagnostic

**Objectif** — répondre à la ligne 4 : la valeur du score s'apprend-elle vraiment ?

**Périmètre** — Sur chaque modèle candidat conscient du score : MET implicite extraite, comparée
cellule par cellule à Kazaross-XG2 ; identité DMP à 1-away/1-away ; antisymétrie
`MWC(a,b) = 1 − MWC(b,a)` et monotonies (tests de propriété) ; décisions dans le domaine de la
table bilatérale contre l'exact ; *free drop* d'après-Crawford **trouvé par le modèle**, comme la
voie classique le trouve déjà.

**Critères d'acceptation** — les cellules divergeant au-delà du seuil fixé en T60 sont
**arbitrées par rollout de match**, pas expliquées. Un écart n'est pas nécessairement une erreur :
la table est elle-même une mesure, et l'arbitrage peut nous donner raison.

**Porte de sortie** — un écart **structuré** (un biais, pas du bruit) que les rollouts
désavouent : l'échantillonnage ou l'ancrage sont en cause. Deux itérations, puis arrêt.

**Machine** — bureau pour l'extraction (secondes), la machine de calcul pour l'arbitrage.

---

### Volet 2 — vérification et verdict

---

#### T67 — La recherche : propagation, cache, navigateur

**Objectif** — savoir ce que le modèle appris coûte au **moteur livré**, pas au banc.

**Périmètre** — Propagation dans la recherche 2-ply avec feuille rendant directement une MWC
cubeful ; **vérification** que le piège du niveau intermédiaire disparaît bien par construction
(§5) ; clé de cache et taux de succès mesurés avant/après ; débit natif et **débit WASM** dans
l'enveloppe de T21 ; **protocole de T36 appliqué au modèle appris** (ligne 7 de la matrice).

**Critères d'acceptation** — non-régression T12 sur la voie classique, qui reste intacte et
livrable ; débit WASM dans l'enveloppe, ou **le modèle est refusé** ; perte de cache chiffrée.

**Machine** — bureau.

---

#### T68 — L'arbitrage par décision

**Objectif** — l'instrument principal du verdict, parce qu'il est ~100 fois plus efficace en
échantillon que la confrontation par matchs.

**Périmètre** — Corpus stratifié de T60, taux d'erreur arbitré par rollout de match, **deux
colonnes**, résultat ventilé **par famille de contexte de score**.

**Critères d'acceptation** — les contextes où l'appris **perd** sont publiés au même titre que
ceux où il gagne. Aucune colonne présentée seule (discipline T39).

**Machine** — la machine de calcul. **Coût** — ~1,5 à 2,5 jours pour ~3 000 décisions au débit
CPU actuel ; des heures avec T62.

---

#### T69 — La campagne de matchs, l'ablation d'encodage, et le verdict

**Objectif** — le chiffre, et la décision.

**Périmètre**
1. **Campagne de matchs confirmatoire**, matchs dupliqués, contre gnubg à profondeur équivalente,
   volume **pré-enregistré à partir d'une variance mesurée** — la leçon explicite de T35, dont
   l'estimation cubeless avait sous-estimé l'intervalle cubeful d'un facteur ~2,6.
2. **L'ablation d'encodage** (ligne 6 de la matrice), qui n'a de sens qu'ici : si le modèle
   plafonne, on teste si des caractéristiques de volatilité explicites lèvent le plafond.
3. **Verdict**, règle de départage **énoncée avant la mesure** : à égalité statistique on garde
   la voie classique — plus petite, cache mieux, déjà qualifiée.

**Critères d'acceptation** — protocole, volume, intervalle de confiance. Si l'appris gagne :
`THIRD-PARTY.md` et la notice sont mis à jour, **la MET Kazaross-XG2 sort du paquet distribué**
et y reste comme instrument de mesure ; le réseau porte un nom nouveau avec sa mesure propre.

**Coût** — **4,7 jours mesurés** pour 100 000 matchs au débit actuel.

---

## 9. L'ordre et les dépendances

```
        T60 instruments ──┐
                          ├──► T63 B0/B ──► T64 volatilité ──┐
        T61 atelier ──────┘         │                        ├──► T65 où entre le score
                                    │                        │            │
        T62 débit ─────────────────►┘  (accélère tout)       │            ▼
         (sans regret, utile à T35/T39/T3A dès aujourd'hui)  │      T66 MET implicite
                                                             │            │
                                                             └────────────┼──► T67 recherche
                                                                          │        │
                                                                          └──► T68 arbitrage
                                                                                   │
                                                                                   ▼
                                                                          T69 campagne, verdict
```

**Trois portes de sortie, dans l'ordre où elles se présentent** :

| Porte | Fiche | Ce qui la ferme |
|---|---|---|
| 1 | T63 | B n'améliore pas la voie classique **en money** |
| 2 | T66 | La MET implicite diverge de façon structurée et les rollouts nous désavouent |
| 3 | T67 | L'avantage 0-ply s'annule sous recherche — le problème est le tronc, donc T41 |

## 10. Ce que ce plan ne fait pas

- **Il ne réentraîne pas le jeu de pions.** Le tronc reste celui de l'amont, gelé, dans tout le
  volet 1. Réapprendre le tronc sous cibles de recherche est **T41**, un autre chantier ; les
  mélanger multiplierait les deux coûts et rendrait tout résultat inattribuable.
- **Il ne touche pas à la voie classique**, qui reste intacte, livrable et qualifiée à chaque
  étape. Le modèle appris est un **candidat**, jamais un remplacement par défaut.
- **Il ne s'ouvre pas avant que T35 ait conclu.** La moitié money est tombée en égalité
  statistique (−0,0119 [−0,0310 ; +0,0074]) ; la moitié match est en cours. La mesure qui
  déciderait de l'ouverture est **la même configuration en cubeless**, qui isolerait le coût
  propre du videau — quelques jours, et elle vaut d'être faite avant tout le reste.

## 11. Budget révisé

Repris de l'[étude](2026-08-19-videau-appris-sans-a-priori.md) §8, avec les fiches de ce plan :

| Volet | CPU aujourd'hui | Avec T62 |
|---|---|---|
| Volet 0 (T60-T62) | jours-homme | — |
| Volet 1 (T63-T66), **tronc gelé** | **~3-5 jours de machine** | ~1 jour |
| Volet 1, branche « entrée du tronc » de T65 | ~1 semaine | ~1 jour |
| Volet 2 (T67-T69) | ~1 semaine | ~2 jours |
| **Un passage complet** | **~2 à 3 semaines** | **~4 jours** |

Le multiplicateur reste le nombre d'itérations. Il est borné par le fait qu'une idée fausse se
détecte sur la MET extraite en quelques secondes, avant tout rollout et toute campagne.
