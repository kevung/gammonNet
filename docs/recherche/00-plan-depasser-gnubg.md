# Dépasser franchement GNU Backgammon — le plan de recherche

**Date** : 2026-08-26 · **Statut** : plan de recherche, **vague 1 rentrée le 2026-08-27** (§11),
**vague 2 rentrée le 2026-08-27 sauf DS-09** (§12). **Aucune fiche de `PLAN.md` n'est ouverte par
ce document.** Il instruit une question, organise quatorze recherches approfondies, et dit ce que
chacune décide.

---

## 1. La question, telle qu'elle est posée

> *« Si nous voulions **fortement dépasser** gnubg en qualité d'analyse tout en étant **aussi voire
> plus rapide**, que faudrait-il faire ? »*

Deux exigences, et elles ne se négocient pas l'une contre l'autre. Le projet a déjà mesuré qu'un
moteur peut acheter de la qualité avec du calcul (notre 3-ply) sans rien gagner, et qu'il peut
acheter de la vitesse avec de la qualité (l'élagage `k=2`). **Ce qui est demandé ici est un
déplacement de la frontière elle-même**, pas un point différent sur la même courbe.

## 2. Le point de départ, en chiffres mesurés

Tout ce tableau est **mesuré** dans ce dépôt, avec fiche et commande de reproduction.

| Fait | Valeur | Source |
|---|---|---|
| Force en configuration complète, 2-ply, money cubeful | **−0,0119 ppg** [−0,0310 ; +0,0074] | T35 |
| Force en match, 7 points, MWC | **50,42 %** [50,16 ; 50,69] | T35 |
| Avantage du réseau par décision, 0-ply | +0,00247 [+0,00186 ; +0,00310] | T36 |
| Avantage du réseau par décision, 2-ply, **arbitre gnubg** | **+0,00007 [−0,00005 ; +0,00019]** | T36 |
| Un ply de plus (notre 3-ply contre leur 2-ply) | +0,00022 — dans le bruit, pour ×15 de coût | T36 |
| Coût d'une décision 2-ply, mono-fil, sans élagage | **2,0075 s** | T3A |
| Idem, réseau d'élagage `k=12` / `k=3` | 0,5588 s / 0,2396 s | T3A |
| Coût d'une décision 2-ply, **gnubg** | **~10 ms** | T38 |
| Calibration de la distribution contre rollout | biais nul sur 4 composantes sur 5 | T37 |
| Trou de fin de partie, une fois la table exacte branchée | **comblé** | T38 |

**Les trois lectures qui organisent tout ce qui suit :**

1. **Notre réseau est meilleur que celui de gnubg — et la recherche efface cet avantage.**
   +0,00247 au 0-ply, +0,00007 au 2-ply. L'information que notre réseau a en plus est
   précisément celle que deux plies de recherche retrouvent tout seuls.
2. **La profondeur n'est pas un levier.** Mesuré deux fois, avec deux arbitres indépendants.
3. **Nous sommes encore ~24× à ~56× plus lents que gnubg par décision**, selon le réglage
   d'élagage — et le réglage rapide paie en qualité (+0,0039 par décision à `k=3`).

## 3. Ce que « aussi rapide » demande, chiffré

Un facteur **×25 à ×60** sur le coût d'une décision, à qualité au moins égale. Il n'existe aucune
mesure dans ce dépôt qui dise d'où il viendrait. Ce qu'on peut poser, c'est sa décomposition
plausible — **arithmétique d'architecture, pas mesure** :

| Poste | Facteur envisageable | Ce qui l'établirait |
|---|---|---|
| Réseau ~16× plus gros que celui de gnubg (527 000 MACs contre ~33 000 supposés) | ×4 à ×16 | DS-02 (leur taille réelle), DS-03 et DS-12 (à quelle taille on tient la qualité) |
| Arithmétique flottante là où l'entier suffirait | ×2 à ×4 | DS-04 (quantification, SIMD, NNUE) |
| Évaluations calculées puis jetées, ou recalculées | ×2 à ×10 | DS-05 (\*-minimax, transpositions, allocation variable) |

**Aucun de ces trois postes n'a été attaqué.** Les ×9 de T3A ont été gagnés sur le **remplissage
des lots** — du travail mort à l'intérieur du noyau — et non sur l'un de ces trois.

## 4. Ce que « fortement dépasser » demande

Le mode d'échec est identifié et mesuré : **notre supériorité 0-ply ne survit pas à la recherche.**
Un réseau meilleur *au sens du 0-ply* n'a donc **aucune raison** de nous faire dépasser gnubg au
2-ply. C'est le résultat le plus important du dépôt pour cette question, et il condamne l'approche
naïve — entraîner plus longtemps, plus gros.

Il reste quatre hypothèses de rupture, et chacune est une ligne du programme de recherche :

| # | Hypothèse | Pourquoi elle est crédible | Qui l'instruit |
|---|---|---|---|
| **H1** | L'avantage s'efface parce que le réseau **n'a pas été entraîné à être bon sous recherche**. Un réseau distillé d'une recherche profonde ou d'un rollout garderait son avance au 2-ply | L'auteur amont le désigne lui-même comme la suite ; c'est la thèse standard depuis AlphaZero | **DS-06**, appuyée par DS-01 |
| **H2** | L'encodage de Tesauro à 196 entrées **plafonne l'information disponible** ; gnubg en met 250, dont des caractéristiques stratégiques calculées | La recherche « retrouve » ce que le réseau ignore ; si le réseau le savait déjà, la recherche n'aurait plus rien à retrouver | **DS-03**, DS-02 |
| **H3** | Le gain n'est pas dans le jeu de pions mais dans le **videau et le match**, où la barre de gnubg est une heuristique non publiée et où nos propres défauts sont déjà nommés | T39 chiffre deux défauts classe-dépendants ; l'amont bat gnubg au videau money de +57,8 mEq/partie [+56,1 ; +59,6] — le +78,8 initialement cité était un chiffre périmé, corrigé par DS-08 | **DS-08**, DS-13 |
| **H4** | La qualité s'achète par **le nombre de nœuds à budget de temps égal** : un moteur 30× plus rapide cherche 30× plus large | T36 a fermé la profondeur *à budget non contraint* ; elle n'a jamais testé « même seconde, plus de nœuds » | **DS-04**, **DS-05**, DS-09 |

**H4 mérite d'être lue deux fois.** T36 a mesuré qu'un ply de plus ne rapporte rien. Elle n'a pas
mesuré qu'un ply **plus large** ne rapporte rien — sa garde `(0,1,1,5)` est justement la réserve
qu'elle nomme. La vitesse a été fermée comme levier de force ; elle ne l'a été que pour la
profondeur, jamais pour la largeur.

## 5. La contrainte qui rend tout cela mesurable — ou pas

`CLAUDE.md` règle n°2 : aucune force n'est affirmée sans mesure. Or **l'instrument actuel ne sait
pas voir un gain modeste** :

- Une campagne T35 coûte **4,9 jours** de machine pour un IC de ±0,020 ppg en money.
- La métrique par décision (T36) est deux ordres de grandeur plus sensible, mais elle mesure
  contre un arbitre dont le biais est connu et non nul.
- **Le PR n'a jamais tourné**, alors que la condition de sortie de la phase 3 est libellée en PR.

Un programme qui viserait « +0,005 ppg » sans refaire l'instrument produirait des modèles qu'on ne
saurait pas départager. **DS-07 passe donc avant tout engagement de calcul** : c'est la seule
recherche de la vague 1 dont le résultat est un prérequis et non un choix.

## 6. Les quatre plafonds, et les quatorze recherches

| Plafond | Question | Recherches |
|---|---|---|
| **A — la qualité du réseau sous recherche** | Que faut-il changer au réseau pour que son avance survive à deux plies ? | DS-01, DS-02, DS-03, DS-06, DS-12 |
| **B — la vitesse** | D'où viennent les ×25 à ×60 ? | DS-04, DS-05, DS-09 |
| **C — le videau et le match** | Où la barre de gnubg est-elle réellement basse ? | DS-08, DS-13 |
| **D — la mesure** | Avec quel instrument affirme-t-on « fortement dépasse » ? | DS-07, DS-11 |
| **Transverse** | Avec quelles données, et pour quel budget ? | DS-10, DS-14 |

## 7. Les vagues, et pourquoi il faut attendre

Les recherches ne sont pas indépendantes. Certaines **façonnent la question** des suivantes ; les
lancer toutes ensemble reviendrait à payer pour des réponses hors sujet.

```
VAGUE 1 — sans dépendance, à lancer ensemble
  DS-01  état de l'art des moteurs et de leurs preuves de force
  DS-02  anatomie de gnubg — la barre exacte
  DS-03  encodage : les entrées qui portent la stratégie
  DS-05  recherche stochastique : *-minimax, transpositions, allocation
  DS-07  mesure : PR, corpus de référence, réduction de variance
  DS-08  videau : au-delà de Janowski
        │
        ├── DS-02 + DS-03 ──► DS-04  NNUE, encodage creux, quantification
        │                     DS-12  spécialisation par classe / mélange d'experts
        ├── DS-01 + DS-02 ──► DS-06  entraîner le réseau *pour* la recherche
        ├── DS-04         ──► DS-09  WebAssembly / WebGPU
        └── DS-07         ──► DS-11  eXtreme Gammon comme référence
                                      │
                                      └── VAGUE 3 — conditionnelles, cf. §8
                                            DS-10  corpus et données librement licenciés
                                            DS-13  exactitude de course et de fin de partie
                                            DS-14  budget de calcul
```

**Le détail des dépendances**, parce que « attendre » doit se justifier :

- **DS-04 attend DS-03.** L'accumulation incrémentale de type NNUE n'a de sens que sur un encodage
  **creux**. Si DS-03 conclut que les caractéristiques utiles sont des grandeurs calculées et
  denses (comptes de pips, tirs, timing), la question NNUE change de forme — et si elle conclut
  l'inverse, DS-04 doit être formulée sur l'encodage précis retenu.
- **DS-12 attend DS-02.** Demander « la spécialisation par classe paie-t-elle ? » sans connaître
  la taille et les frontières des trois réseaux de gnubg produit une réponse générique.
- **DS-06 attend DS-01 et DS-02.** Savoir ce qui a **déjà été tenté** au backgammon (et a échoué)
  évite de faire chercher deux fois la même chose.
- **DS-09 attend DS-04.** On ne mesure pas des noyaux qu'on n'a pas encore choisis.
- **DS-11 attend DS-07.** La question « comment se comparer à XG » n'a de sens qu'une fois la
  métrique fixée.

## 8. Les conditions de déclenchement de la vague 3

| Recherche | Ne se lance que si |
|---|---|
| **DS-10** | DS-06 conclut qu'un entraînement **supervisé** (distillation, corpus étiquetés) est la voie — sinon le self-play suffit et la question des corpus ne se pose pas |
| **DS-13** | DS-07 ou DS-08 montre que la course et la fin de partie pèsent réellement dans le PR — sinon T38 a déjà comblé ce qui comptait |
| **DS-14** | La vague 2 a désigné **une** architecture cible — un budget se chiffre pour un programme, pas pour un éventail |

## 9. Ce que ce plan produira

Chaque retour est classé dans `docs/recherche/retours/DS-XX-retour.md`. Quand les vagues 1 et 2
sont rentrées, ce document est amendé d'une section **« Le programme retenu »**, qui doit tenir en
un tableau : pour chaque changement proposé, le gain attendu, son coût, le risque, la licence, et
**la mesure qui le trancherait**. Ce tableau devient des fiches `PLAN.md` (série T7x), et rien
avant.

## 10. Les garde-fous qui s'appliquent aux retours

Ils ne sont pas négociables, et chaque prompt les répète :

1. **Rien de non libre dans un artefact distribué.** Toute brique rapportée par une recherche doit
   arriver avec sa licence. Poids gnubg (GPL-3) et réseaux HedgeHog (licence non confirmée à la
   source, réputée non commerciale — exclus par prudence) sont hors périmètre — y compris comme
   source d'entraînement. bgsage, d'abord noté AGPL-3, est en réalité sous **MPL-2.0** (LICENSE
   du dépôt, vérifié le 2026-08-27) : ses idées et son benchmark sont réétudiables, mais aucun
   code n'en est repris tant que le dépôt n'a pas statué.
2. **gnubg est un instrument de mesure, jamais une source d'apprentissage.** Le dépôt s'est donné
   cette règle, plus stricte que le droit. Une recherche qui revient avec « distillez gnubg »
   revient avec une réponse inutilisable.
3. **Une conclusion de performance se mesure.** Un retour doit dire, ligne par ligne, s'il énonce
   une mesure publiée, une mesure reproduite, ou une hypothèse.
4. **La contrainte de taille vient du client, jamais de la machine d'entraînement.** Une
   architecture se juge en **précision par MAC**, dans un navigateur mobile.

## 11. La vague 1, rentrée — ce qu'elle change (2026-08-27)

Les six retours (DS-01, 02, 03, 05, 07, 08) sont classés dans `retours/`. Rappel du modèle : un
retour de recherche n'est pas une mesure de ce dépôt — ce qui suit est l'état des hypothèses, pas
un verdict.

### Les quatre hypothèses, réévaluées

| # | État après vague 1 | Ce qui l'a fait bouger |
|---|---|---|
| **H1** (entraîner pour la recherche) | **Renforcée — c'est la voie principale.** | DS-01 : deux projets indépendants convergent — le goulot est la **qualité du signal d'entraînement**, pas l'architecture ni l'encodage. Le seul gain mesuré qui **survit à la recherche** est la distillation, dans l'évaluateur statique, de la valeur d'une recherche 2-ply (Whittington, ~+2 pts à 1-ply) ; les backups exacts 1-ply de Strehl (notre amont) produisent un avantage qui survit au 2-ply en se resserrant. Plafond connu : « l'élève ne dépasse pas le maître » quand on distille sa propre recherche ; l'échappatoire non bornée est l'optimisation directe de la force (SPSA). Notre effacement 0-ply → 2-ply est le comportement **attendu** d'un gain « non issu d'un signal de recherche ». |
| **H2** (encodage) | **Affaiblie, mais pas fermée — contradiction ouverte.** | DS-03 recommande ~20 caractéristiques calculées (+40 entrées, +3,9 % de MACs) et montre que la théorie prédit notre effacement sous recherche. Mais DS-01 rapporte **deux résultats négatifs mesurés** (Strehl : « les features n'aident pas » ; Whittington : nuisibles en entrée, neutres puis négatives en NNUE). Aucune ablation publiée « ± features, jugée au différentiel 2-ply » n'existe — la nôtre trancherait, mais **H2 n'est plus prioritaire**. |
| **H3** (videau et match) | **Confirmée comme levier à haut rendement.** | DS-08 : l'erreur moyenne de videau vaut plus du double d'une erreur de coup (Madsen, 4-ply) ; la barre gnubg est un x fixe (0,6–0,68) que ses auteurs reconnaissent insuffisant. Chemin ordonné : benchmark PR-cube par classe → modèle raffiné (x1, x2) → recalibrage x = f(pip) en course → surcouche volatilité (Higgins α → x local). La corrélation volatilité ↔ efficacité, jamais publiée, est une expérience à notre portée (l'expectiminimax développe déjà les 21 jets). MET maison à régénérer. Correction : +57,8 mEq, pas +78,8. |
| **H4** (largeur à budget égal) | **Affaiblie.** | DS-01 : Whittington mesure « profondeur ≈ +3 points de taux de gain ; **largeur ≈ nulle** ». La réserve de T36 reste formellement ouverte (jamais mesurée chez nous), mais la vitesse se justifie désormais par le **coût client** (navigateur, mobile), plus par un espoir de force. |

### La vitesse, décomposée et confirmée

DS-02 chiffre ce que §3 supposait : le réseau contact de gnubg fait **~32 640 MACs** (~16× moins
que nous) et sa recherche n'en dépense que ~2 550 aux nœuds internes (réseau d'élagage, <1 % de
coups changés) ; s'y ajoutent cache (2¹⁹ entrées) et filtres de coups. Le facteur 25–60× est
expliqué sans reste. DS-05 ferme la profondeur une troisième fois (Hauk-Buro-Schaeffer) et donne
les gisements **compatibles avec le noyau par lots** : regroupement exact des jets équivalents,
cache à clé position+ply avec bornes (−37 % chez Veness-Blair), pré-tri plus discriminant pour
resserrer k. Star2 (−75 à −95 % de nœuds) **sérialise** les évaluations — à traiter en expérience,
pas en évidence. Cible proposée par DS-01 : **≤ 3× gnubg au 2-ply** avant d'investir dans la force.

### La mesure, tranchée

DS-07 confirme §5 et le chiffre : le match dupliqué ne peut pas voir un gain modeste (±0,005 ppg ≈
800 000 paires). L'instrument devient la **perte d'équité appariée par position** contre un arbitre
externe escaladé en trois passes (gnubg 3-ply → rollout tronqué VR → rollout complet, IC < 0,005),
sur corpus figé, stratifié, versionné, ancré sur les bases exactes partout où c'est résoluble —
10⁴–10⁵ décisions disputées, des heures et non des jours. Notre arbitre actuel (rollout par notre
propre politique) est **structurellement complaisant** : à remplacer. Le match dupliqué reste
l'instrument de confirmation finale (≥ 100 matchs, test apparié).

### Licences — deux mises à jour

- **bgsage est MPL-2.0**, pas AGPL-3 (LICENSE du dépôt, vérifié le 2026-08-27). Réétudiable comme
  documentation et repère de benchmark ; pas de copie de code sans décision explicite du dépôt.
- **HedgeHog** : la « clause non commerciale » n'a pas de source primaire vérifiable ; les réseaux
  forts sont côté serveur, propriétaires de fait. Reste exclu, le motif devient « licence non
  confirmée ».

### La suite

La vague 2 se lance avec quatre recherches — **DS-04, DS-06, DS-11, DS-12**, dont les prompts sont
injectés et prêts (DS-04 réordonné vers quantification/noyaux, le verdict « creux » de DS-03 étant
négatif ; la sous-question 1 de DS-06 remplacée par la reproduction du protocole Whittington).
**DS-09 attend le retour de DS-04.** Vague 3 : DS-10 attend DS-06 ; DS-13 attend le benchmark
PR-cube par classe (étape 1 de DS-08) qui dira si la course pèse ; DS-14 attend qu'une
architecture soit désignée. Le tableau « programme retenu » de §9 ne s'écrit qu'une fois la
vague 2 rentrée.

## 12. La vague 2, rentrée sauf DS-09 — ce qu'elle change (2026-08-27)

Les retours DS-04, DS-06, DS-11 et DS-12 sont classés dans `retours/`. Même rappel qu'en §11 :
un retour de recherche n'est pas une mesure de ce dépôt.

### Le fait central : trois retours convergent sur la même recette

DS-06 (entraînement) et DS-12 (spécialisation) désignent **indépendamment le même premier
test** : la **distillation de notre propre recherche expectiminimax 2-ply distributionnelle**
— les 5 probabilités, pas l'équité seule — dans un réseau à architecture constante. C'est la
seule recette dont la survie sous recherche est prouvée par une mesure publiée (Whittington
v1.9.0 : ~52 % contre son propre champion à 1-ply ; « l'arête est petite mais ne se lave pas
sous la recherche »), et DS-12 y ajoute que c'est aussi le seul mécanisme au gain prouvé **à
coût par évaluation strictement constant** (distillation d'un enseignant fort : 53,4 % sur
40 000 parties, même 256×128). DS-04 complète le triangle : la même distillation est le premier
levier de **vitesse** (réduire vers ~60–100k MACs). **Un seul chantier sert donc les deux
exigences de la question initiale — qualité sous recherche et vitesse.**

### Les quatre hypothèses, mises à jour

| # | État après vague 2 | Ce qui a bougé |
|---|---|---|
| **H1** (entraîner pour la recherche) | **Confirmée, et munie d'un protocole exécutable.** | DS-06 : 1,0–1,5 M labels 2-ply auto-générés (~heures sur notre machine, rendement décroissant au-delà de ~2,5 M), cibles = les 5 composantes, tête auxiliaire de **volatilité exacte sur les 21 jets** (étiquetage gratuit — sous-produit du backup exact ; analogue mesuré : têtes KataGo), entraînement **from scratch** (le warm-start nuit), et le juge est **l'intervalle 2-ply par décision** — succès si [−0,00005 ; +0,00019] se déplace au-dessus de zéro. Plafond : l'élève ne dépasse pas le maître ; échappatoires non bornées = SPSA sur la tête de sortie, têtes auxiliaires. Lecture secondaire : si le taux de désaccord 2-ply cesse de tomber **et** que l'équité monte, on a ajouté de l'information que la recherche ne récupère pas. |
| **H2** (encodage) | **Encore affaiblie.** | DS-06 recense un troisième négatif mesuré (Whittington : features expertes neutres au mieux, ~5 pts derrière en NNUE). L'ablation maison au différentiel 2-ply reste la seule qui trancherait, mais rien ne la justifie avant le résultat de la distillation. |
| **H3** (videau et match) | Inchangée depuis §11 — voie DS-08, indépendante de ce qui précède. | Rien de neuf en vague 2 ; DS-13 attend toujours le benchmark PR-cube par classe. |
| **H4** (largeur à budget égal) | **Fermée de fait.** | Deuxième mesure négative (Whittington : fenêtre ×3 → 50,5 % sur 2 600 parties). La vitesse se justifie par le coût client, pas par un espoir de force. |

### La spécialisation, tranchée

DS-12 : l'aiguillage dur race/crashed/contact est **mesuré neutre** à entraînement égal — le
gain apparent de Whittington venait du recuit du taux d'apprentissage, pas du routage. L'ordre
retenu : (1) distillation dans le réseau unique ; (2) si elle plafonne, **tronc partagé + têtes
de sortie par bucket de pip-count** façon NNUE (52,6 %, search-robuste, aucune classe affamée de
données) — jamais des réseaux séparés ; (3) en préalable à toute tête spécialisée, produire la
**carte d'erreur par classe de position** contre nos rollouts profonds (« Test C ») — personne
ne l'a jamais publiée, et sans elle le choix des classes est aveugle. Toute comparaison varie
**une seule chose à la fois** et se juge en head-to-head à dés miroirs, survie au 2-ply exigée.

### La vitesse, architecturée

DS-04 : le ×10 se **compose** — distillation ×2,5–5 (qualité quasi intacte si le maître est
sur-paramétré), **QAT int8/int16 obligatoire** (la PTQ s'effondre sur petit réseau) pour ×2–3
mesurés (pas ×4), noyau GEMM par lots sur produit scalaire fusionné (VPDPBUSD / SDOT /
relaxed-SIMD), SVD ou élagage structuré pour le reste. **NNUE incrémental écarté** : entrées
denses, évaluation par lots, aucun précédent sur un jeu à dés — le lot dense de 32 est jugé
gagnant (hypothèse argumentée, pas mesure). Le bit-à-bit natif↔Wasm **se renforce** en entier,
à trois conditions : ordre de sommation figé, accumulateur int32 sans débordement, arrondi
unique ; et relaxed-SIMD seulement avec poids contraints à 7 bits (sinon non déterminisme
spécifié). Briques permissives : XNNPACK (BSD-3), ruy (Apache-2.0), ggml (MIT) ; **Stockfish
NNUE est GPL-3, inutilisable**. En recherche : mini-réseau d'élagage façon gnubg aux nœuds
internes, Star2 en expérience (déjà noté en §11).

### La comparaison à XG, réglée sans l'exécuter

DS-11 : XG n'a **ni API, ni CLI** — seulement Batch Analysis/Rollout en GUI (Windows ou Wine,
endossé par l'éditeur), verdicts extraits en parsant les `.xg` (format officiellement public,
parseurs libres `xgdatatools`). La voie principale est **indirecte** : composer notre
équivalence gnubg 2-ply, déjà mesurée, avec le calage tiers gnubg↔XG (bgsage « Méthode 3 » : PR
moyen identique 4,36 sur 580 notations de matchs humains, différence +0,002 ±0,03, r = 0,98 —
auto-étude d'un concurrent, non répliquée, à citer avec cette réserve). XG en **contrôle
ponctuel** sur sous-échantillon disputé, jamais en oracle systématique. Toujours **deux
chiffres** : erreur d'équité par décision ×500 à filtre identique, et « PR façon XG »
(exclusion des coups « non obvious ») — jamais un mEMG gnubg ÷ 2. Correspondance de plies :
**XG n-ply ≈ gnubg (n−1)-ply**. Licence : aucun EULA desktop publié — vide documentaire, géré
par prudence (jamais de binaire ni de données XG dans l'artefact) ; les chiffres Depreli 2012
sont arbitrés par XG lui-même, inutilisables comme oracle neutre.

### Les conditions de vague 3, tranchées

- **DS-10 : non déclenchée.** DS-06 retient des labels auto-générés par notre propre recherche ;
  aucun corpus externe n'est requis.
- **DS-13 : toujours en attente** du benchmark PR-cube par classe (étape 1 de DS-08) — une
  mesure du dépôt, pas une recherche web.
- **DS-14 : presque déclenchée.** DS-04 + DS-06 + DS-12 désignent une architecture (réseau
  distillé 2-ply, ~60–100k MACs, QAT int8, tête volatilité, buckets pip en option). Attendre le
  retour de DS-09, qui la confirme ou l'amende pour le navigateur, avant de chiffrer le budget.

### La suite

**Une seule recherche à lancer : DS-09** (injectée le 2026-08-27 depuis DS-04, prête). À son
retour, la vague 2 est complète : écrire alors le tableau **« programme retenu »** de §9 — pour
chaque changement, le gain attendu, le coût, le risque, la licence et la mesure qui le tranche —
et le convertir en fiches `PLAN.md` (série T7x). Rien ne s'engage avant.
