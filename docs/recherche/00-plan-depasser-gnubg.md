# Dépasser franchement GNU Backgammon — le plan de recherche

**Date** : 2026-08-26 · **Statut** : plan de recherche, **terminé le 2026-08-27** — vagues 1 et
2 rentrées (§11, §12), programme retenu écrit (§14), budget chiffré (§15). Onze retours sur
quatorze prompts ; DS-10 non déclenchée, DS-13 attend une mesure du dépôt, plus aucune recherche
planifiée (§13). **Aucune fiche de `PLAN.md` n'est ouverte par ce document** — la conversion du
§14 en fiches T7x est la décision d'engagement qui reste à prendre.

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
   arriver avec sa licence. Poids gnubg (GPL-3) et tout réseau sous clause non commerciale (licence non confirmée à la
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
- **Les moteurs à réseaux propriétaires côté serveur** : leurs clauses de licence n'ont pas
  toujours de source primaire vérifiable, et les réseaux forts restent propriétaires de fait. Ils
  restent exclus, le motif étant « licence non confirmée ».

### La suite

La vague 2 se lance avec quatre recherches — **DS-04, DS-06, DS-11, DS-12**, dont les prompts sont
injectés et prêts (DS-04 réordonné vers quantification/noyaux, le verdict « creux » de DS-03 étant
négatif ; la sous-question 1 de DS-06 remplacée par la reproduction du protocole Whittington).
**DS-09 attend le retour de DS-04.** Vague 3 : DS-10 attend DS-06 ; DS-13 attend le benchmark
PR-cube par classe (étape 1 de DS-08) qui dira si la course pèse ; DS-14 attend qu'une
architecture soit désignée. Le tableau « programme retenu » de §9 ne s'écrit qu'une fois la
vague 2 rentrée.

## 12. La vague 2, rentrée — ce qu'elle change (2026-08-27)

Les retours DS-04, DS-06, DS-11 et DS-12 sont classés dans `retours/` ; **DS-09 est rentré à son
tour le même jour** (voir sa sous-section plus bas) — la vague 2 est complète. Même rappel qu'en
§11 : un retour de recherche n'est pas une mesure de ce dépôt.

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

### Le navigateur, tranché (DS-09, rentré le 2026-08-27)

Le socle est un **noyau int8 maison en SIMD128 déterministe** (`i32x4.dot_i16x8_s`) — le seul
chemin universel (Safari iOS 16.4+ compris) qui préserve le bit-à-bit ; gain int8 attendu
modeste en Wasm (~1,3–2×, surtout bande passante — le sous-ensemble déterministe n'a pas de
produit scalaire int8 4-voies). Le **relaxed-dot 7 bits** est relégué en accélération **opt-in**
détectée à l'exécution : absent de Safari stable en août 2026 (Technology Preview 250
seulement), non déterministe par spécification — jamais sur le chemin critique ni dans le repère
bit-à-bit. **WebGPU est écarté** pour l'évaluateur : régime dispatch-bound (24–36 µs par
lancement, gain < 2× sous 512×512) et non bit-exact par la spécification WGSL. Bibliothèques
génériques battues par le noyau maison (repli licence-sûr : ONNX Runtime Web, MIT). Deux
énigmes du dépôt reçoivent une explication : les **3,3 ouvriers effectifs**
(`hardwareConcurrency` plafonné à 4 sur iOS, throttling thermique qui retire les grands cœurs
vers ~50 °C) et le **lot ×2,21 en Wasm contre ×8,5 en natif** (pas de VNNI/FMA en Wasm
déterministe, plafond 128 bits) — avec un test décisif : refaire le banc natif en SSE2 sans
FMA/VNNI. Projection : ~9 400 éval/s → **~60 000–120 000** après distillation + int8
[HYPOTHÈSE — le micro-banc GEMM int8/f32 sur nos sept plateformes serait la première mesure
publiée du genre]. Artefact : int8 + Brotli → sous ~300 Kio, hors chemin critique.

### Les conditions de vague 3, tranchées

- **DS-10 : non déclenchée.** DS-06 retient des labels auto-générés par notre propre recherche ;
  aucun corpus externe n'est requis.
- **DS-13 : toujours en attente** du benchmark PR-cube par classe (étape 1 de DS-08) — une
  mesure du dépôt, pas une recherche web.
- **DS-14 : déclenchée.** La vague 2 complète désigne une architecture unique (réseau distillé
  2-ply ~60–100k MACs, QAT int8, tête volatilité, socle SIMD128 déterministe) ; le prompt est
  injecté le 2026-08-27 depuis DS-04, DS-06, DS-07, DS-09 et DS-12 — **prêt à lancer**.

### La suite

La vague 2 est complète : le tableau **« programme retenu »** annoncé en §9 est écrit — c'est le
**§14**. Sa conversion en fiches `PLAN.md` (série T7x) est l'étape d'engagement suivante ; le
chiffrage préalable est l'objet de **DS-14**, seule recherche restant à lancer.

## 13. Après les quatorze : les passes déclenchées

Les quatorze recherches épuisées, on ne planifie **pas** de vague 4 systématique. La raison est
dans les retours eux-mêmes : la majorité de leurs sections « Ce que je n'ai pas trouvé » ne sont
pas des trous de recherche documentaire mais des mesures que **personne n'a publiées** et que
seul ce dépôt peut produire — l'ampleur des discontinuités de frontière, la carte d'erreur par
classe, le ratio Wasm-int8/natif-int8, l'ablation des caractéristiques au différentiel 2-ply, le
classement des cibles d'entraînement sous recherche. Une deep search relancée dessus rendrait un
rapport qui redit « lacune de la littérature ». Après DS-09, le goulot bascule de l'information
vers la mesure.

Une nouvelle recherche ne s'écrit donc que sur **déclencheur**, et s'injecte avec la mesure qui
la motive — c'est ce qui a fait la valeur des prompts de vague 2, et nos chiffres mesurés, que
personne d'autre ne détient, rendent la question tranchante. Trois déclencheurs :

1. **Un résultat T7x contredit un retour.** Exemple : la distillation 2-ply ne déplace pas
   l'intervalle malgré ~1,5 M labels → « pourquoi la distillation de sa propre recherche
   échoue-t-elle — diagnostic et variantes », injectée avec nos courbes.
2. **Un plafond prévu est atteint.** Exemple : l'élève atteint la parité avec le maître →
   l'échappatoire nommée par DS-06 mérite alors son propre prompt, « SPSA/CLOP et optimisation
   directe de la force sur un banc de parties » — aujourd'hui traitée en deux paragraphes.
3. **Un blocage d'implémentation précis.** Exemple : la recette QAT s'effondre sur le réseau
   réduit → « QAT pour MLP < 100k MACs, recettes et pièges » ; DS-04 en donne les bornes, pas la
   recette d'entraînement fine.

Deux cas particuliers n'appellent **aucune** deep search : les hyperparamètres de distillation de
Whittington sont à extraire de son dépôt (une lecture de code, faisable ici) ; et les conditions
restantes de vague 3 (DS-13, DS-14) sont déjà couvertes par leurs prompts existants.

Chaque prompt déclenché suit le format des quatorze : autonome, ses contraintes et garde-fous
répétés (§10), son tableau « À injecter » rempli depuis la mesure déclenchante, et son retour
classé dans `retours/` selon le modèle.

## 14. Le programme retenu (2026-08-27)

C'est le tableau annoncé en §9, écrit une fois la vague 2 complète. Rappel de son statut : il
synthétise des retours de recherche, pas des mesures de ce dépôt — chaque ligne porte la mesure
qui la tranche, et **rien ne s'affirme avant qu'elle ait tourné**. Sa conversion en fiches
`PLAN.md` (série T7x) est une décision d'engagement distincte, à prendre après le chiffrage
DS-14.

| # | Changement | Gain attendu | Coût | Risque | Licence | La mesure qui tranche |
|---|---|---|---|---|---|---|
| **P1** | **Arbitre externe escaladé** (gnubg 3-ply → rollout tronqué VR → rollout complet, IC < 0,005) sur corpus figé, stratifié, versionné de 10⁴–10⁵ décisions disputées, ancré sur les bases exactes (DS-07) | Instrument sensible en heures et non en jours ; remplace notre arbitre structurellement complaisant | Implémentation + calcul de l'étalon (une fois) | Faible — biais gnubg connu, contrôlé par l'escalade | gnubg = oracle de mesure, jamais source (règle du dépôt) | L'IC de l'étalon lui-même ; **prérequis de tout le reste** |
| **P2** | **Distillation 2-ply distributionnelle** de notre propre recherche (les 5 probabilités) + **tête auxiliaire de volatilité exacte** sur les 21 jets, from scratch, architecture d'abord constante (DS-06, DS-12) | Un avantage qui **survit au 2-ply** (réf. Whittington : ~52 % à 1-ply, « ne se lave pas ») | 1,0–1,5 M labels ≈ heures sur notre machine ; entraînement en minutes/heures | Plafond élève ≤ maître ; gain petit (~1–2 %) ; rendement décroissant > 2,5 M labels | Aucune contrainte — labels auto-générés | L'intervalle 2-ply par décision [−0,00005 ; +0,00019] **se déplace au-dessus de zéro** (banc P1) ; lecture secondaire : le taux de désaccord cesse de tomber |
| **P3** | **Réduction du réseau par distillation** : 527k → ~60–100k MACs (DS-04, DS-09) | ×2,5–6,6 sur toute décision, natif et Wasm — le premier levier de vitesse | Entraînement + banc | Perte de qualité si trop agressif (seuil DS-04 : > 1 pt d'équité → réduire moins) | La nôtre | Équité par décision inchangée dans l'IC (P1) **et** éval/s sur le banc sept plateformes |
| **P4** | **QAT int8/int16 + noyau GEMM par lots SIMD128 déterministe**, relaxed-dot 7 bits en opt-in hors iOS (DS-04, DS-09) | ~1,3–2× en Wasm, 2–3× en natif ; artefact ~500 Kio → < 300 Kio avec Brotli | Noyau maison (quelques centaines de lignes) + pipeline QAT | Falaise de qualité si PTQ (d'où QAT obligatoire) ; seuil d'abandon DS-09 : gain < 1,3× au micro-banc | Maison, ou XNNPACK BSD-3 ; Stockfish NNUE GPL-3 exclu | **Micro-banc GEMM int8 vs f32** sur les sept plateformes (première mesure publiée du genre) + test bit-à-bit natif↔Wasm |
| **P5** | **Mini-réseau d'élagage** aux nœuds internes (~10–20 neurones, façon gnubg) ; **Star2** en expérience (DS-02, DS-04, DS-05) | Resserrer k sans payer les +0,0039/décision de `k=3` ; Star2 : −75–95 % de nœuds mais sérialise | Distillation d'un petit réseau (déjà pratiquée) ; Star2 : réécriture de la boucle | Star2 peut casser le gain du noyau par lots — à traiter en expérience, pas en évidence | La nôtre | Qualité **à budget de temps égal** contre le réglage actuel |
| **P6** | **Videau** : benchmark PR-cube par classe → modèle x1/x2 → recalibrage x = f(pip) en course → surcouche volatilité (DS-08 ; la tête P2 fournit le signal) | L'erreur de videau vaut plus du double d'une erreur de coup — le gain le moins cher en qualité | Benchmark + calibrages successifs | La corrélation volatilité ↔ efficacité n'a jamais été publiée — à établir nous-mêmes | MET maison à régénérer ; Kazaross-XG2 attribuée | **PR-cube par classe** avant/après chaque étape ; déclenche DS-13 si la course pèse |
| **P7** | **Comparaison à XG par voie indirecte** : équivalence gnubg 2-ply (mesurée) × calage tiers gnubg↔XG (bgsage, +0,002 ±0,03, r = 0,98) ; XG en contrôle ponctuel Batch Analysis sous Wine (DS-11) | La moitié « XG » de l'objectif, sans exécuter XG en routine | Faible (voie indirecte) ; banc Wine ponctuel | Calage bgsage non répliqué — à citer avec sa réserve ; jamais de données XG dans l'artefact | Aucun EULA XG publié — prudence documentée | **Deux chiffres** : erreur/décision ×500 à filtre identique, et « PR façon XG » — jamais un mEMG ÷ 2 |
| **P8** | **Carte d'erreur par classe de position** contre rollouts profonds — le « Test C » de DS-12 | Diagnostic : dit **où** une tête spécialisée paierait ; jamais publiée nulle part | Faible — une passe de banc stratifié | Aucun | La nôtre | Si une classe concentre > 2× l'erreur moyenne **et** pèse dans les décisions réelles → tête dédiée sur tronc partagé (sinon : rien) |

**L'ordre.** P1 d'abord (l'instrument, comme toujours) ; puis P2 (la qualité) et P4 (le
micro-banc de vitesse) peuvent courir en parallèle — P2 est jugée par P1 ; P3 vient après P2
(on distille le réseau **déjà** entraîné pour la recherche, pas l'actuel) ; P5–P8 s'ordonnent
selon les résultats. **Ce qui est écarté**, avec la mesure qui l'a écarté : l'aiguillage dur
par classe (neutre, Whittington), la largeur de recherche (nulle, deux mesures), la profondeur
(fermée trois fois), les caractéristiques expertes en entrée (trois négatifs mesurés — H2
dormante), NNUE incrémental (entrées denses, lots), WebGPU pour l'évaluateur (dispatch-bound),
les bibliothèques d'inférence génériques, les corpus externes et tout professeur non libre
(gnubg, XG, et tout autre moteur — règle de licence).

## 15. Le budget et les paliers (DS-14, rentré le 2026-08-27)

Le chiffrage du programme (retour classé dans `retours/DS-14-retour.md`), sur notre machine
(16 cœurs / 32 fils, 30 processus). Une réserve de conformité d'abord : le retour recommande
d'étiqueter par gnubg 2-ply (~100 000× moins cher qu'un rollout) — **rejeté**, la règle du dépôt
fait de gnubg un instrument de mesure, jamais une source d'apprentissage (§10). On paie donc nos
propres coûts d'étiquetage ; ils restent de l'ordre d'heures.

### Les trois scénarios

| Scénario | Génération | Entraînement | Mesure | Total mur |
|---|---|---|---|---|
| **Minimal** — le signal qui dit si l'idée marche | 400–500 k positions, self-play 0-ply : minutes | étiquetage 2-ply réduit + QAT : ~1–2 h | par décision contre gnubg 3-ply, sans rollout : dizaines de minutes | **~1–3 h** |
| **Nominal** — la recette P2 complète | 1,0–1,5 M positions : ~1 h | étiquetage 2-ply ~3–8 h de mur + QAT ~1 h (seul usage utile du GPU) | arbitre escaladé (heures/point) + un match dupliqué | **~6–8 jours**, dont 4,9 de match |
| **« Ça a mal tourné »** — trois itérations | ré-encodage + réétiquetage à chaque tour | 3× | campagnes à refaire + 1–3 matchs dupliqués | **~3–5 semaines** |

Le scénario noir est dominé par **la mesure répétée**, pas par l'entraînement — la signature de
notre problème historique (§5), et la raison d'être des paliers.

### La règle d'or, et les paliers d'arrêt

**Mesurer le professeur avant d'étiqueter en volume** : le piège n°1 documenté est le plafond du
professeur — un élève distillé converge à la force de son maître quelle que soit la quantité de
données. Avant tout étiquetage massif, vérifier que notre 2-ply distributionnel bat le réseau
actuel au ply de jeu : **z > 3 sur ≥ 10 000 décisions appariées** — un contrôle qui coûte des
minutes et peut économiser des semaines.

| Palier | Ce qu'on fait | Coût | On arrête si |
|---|---|---|---|
| **B0** | Banc de positions de référence + bases exactes, aucun rollout | minutes | le candidat est nettement pire que l'incumbent — filtre grossier |
| **B1** | Prototype : distillation sur 400–500 k labels (notre 2-ply), QAT comprise | ~1–2 h | à ce volume, le candidat ne bat pas l'incumbent par décision (z < ~1 sur ≥ 10 000 décisions appariées) — la donnée supplémentaire ne sauve pas une idée neutre |
| **B2** | Tronc gelé, tête seule réentraînée | fraction d'un entraînement | isole tête vs corps — diagnostic, pas un verdict |
| **B3** | Mesure **par décision** contre gnubg 3-ply seul, corpus figé | dizaines de minutes | le gain par décision disparaît au ply de jeu (non-transitivité) — arrêt avant tout rollout |
| **B4** | Arbitre escaladé complet (P1 du §14), IC < 0,005 | heures/point | réservé aux candidats ayant passé B3 |
| **B5** | Match dupliqué ≥ 100, test apparié | 4,9 jours | un événement rare, jamais une routine — ne jamais le lancer pour départager du bruit |

Deux garde-fous chiffrés du retour, à retenir : la validation-loss peut continuer de baisser
sans plus se traduire en force (seuls les head-to-heads voient le genou) ; et un affrontement
partiel erre plus que l'effet mesuré (54,8 % lus à 7 000 parties pour 53,6 % finaux sur 40 000).
Les recettes à parc de machines (fishtest, ELF, KataGo) sont écartées franchement ; le GPU ne
sert qu'à la QAT.

### Le verdict

Le programme du §14 est **engageable sur la machine du projet** : un candidat se produit en
heures, se qualifie en heures par les paliers, et le match dupliqué ne se paie qu'une fois par
candidat retenu. La suite n'est plus de la recherche : c'est la **conversion du §14 en fiches
`PLAN.md` (série T7x)** — une décision d'engagement qui appartient au dépôt, pas à ce document.

**La conversion est faite** — décidée par l'utilisateur et exécutée le 2026-08-27 : les huit
lignes P1–P8 sont devenues les fiches **T70–T77** (`PLAN.md`, phase 7), suivies par les issues
GitHub [#9](https://github.com/kevung/gammonNet/issues/9)–[#16](https://github.com/kevung/gammonNet/issues/16)
sous l'epic [#17](https://github.com/kevung/gammonNet/issues/17). L'implémentation n'est pas
commencée. Ce document a rempli son office ; les décisions vivent désormais dans `PLAN.md`.
