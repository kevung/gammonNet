# Dépasser franchement GNU Backgammon — le plan de recherche

**Date** : 2026-08-26 · **Statut** : plan de recherche. **Aucune fiche de `PLAN.md` n'est ouverte
par ce document.** Il instruit une question, organise quatorze recherches approfondies, et dit ce
que chacune décide.

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
| **H3** | Le gain n'est pas dans le jeu de pions mais dans le **videau et le match**, où la barre de gnubg est une heuristique non publiée et où nos propres défauts sont déjà nommés | T39 chiffre deux défauts classe-dépendants ; l'amont bat gnubg de +78,8 mEq/partie au videau money | **DS-08**, DS-13 |
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
   arriver avec sa licence. Poids gnubg (GPL-3), réseaux HedgeHog (clause non commerciale),
   bgsage (AGPL) sont hors périmètre — y compris comme source d'entraînement.
2. **gnubg est un instrument de mesure, jamais une source d'apprentissage.** Le dépôt s'est donné
   cette règle, plus stricte que le droit. Une recherche qui revient avec « distillez gnubg »
   revient avec une réponse inutilisable.
3. **Une conclusion de performance se mesure.** Un retour doit dire, ligne par ligne, s'il énonce
   une mesure publiée, une mesure reproduite, ou une hypothèse.
4. **La contrainte de taille vient du client, jamais de la machine d'entraînement.** Une
   architecture se juge en **précision par MAC**, dans un navigateur mobile.
