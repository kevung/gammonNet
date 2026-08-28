---
status: accepted
date: 2026-08-28
portée: l'axe « videau appris », marches 1 et 2 (tronc gelé)
---

# Le score de match entre par une tête, jamais par le tronc

L'axe « videau appris » — remplacer Janowski et la table d'équité de match par une fonction
apprise — a été instruit trois fois (DS-08 sous-question 7 et §B.3 du retour ;
`docs/etudes/2026-08-19-videau-appris-sans-a-priori.md` et son plan compagnon), puis **écarté** le
2026-08-27 au profit de la ligne P6 (T75 : raffiner Janowski, régénérer une MET maison). Nous le
rouvrons partiellement, et **la première décision à prendre est celle par où entre le score** —
parce qu'elle fixe la clé du cache, la structure de la recherche et le budget navigateur, et
qu'elle se défait très cher une fois qu'un entraînement l'a rendue implicite.

**Décision : le tronc reste aveugle au score. Le score, l'état du videau et le drapeau Crawford
n'entrent que dans une tête appliquée après le goulot.**

## Pourquoi ce n'est pas une amputation

« Tronc aveugle au score » ne veut pas dire « moteur aveugle au score ». Le choix de coup est
l'`argmax` de la MWC rendue par la tête, et cette MWC dépend du score : à 1-away/1-away les
gammons cessent de compter, à 2-away/2-away le prix du gammon du leader tombe à zéro, et le moteur
le voit — exactement comme le fait aujourd'hui la pile classique via la MET. Lin retient de son
architecture qu'elle apprend l'influence du score *« not just [on] further cube decisions, but
checker play as well »* : la fusion tardive obtient cette influence aussi, par la valeur.

La raison de fond n'est pas un compromis, c'est une propriété :

> **Pour la partie cubeless, les cinq probabilités sont une statistique exactement suffisante, et
> le score n'entre que dans les coefficients.**

C'est la formule même de la MET — `MWC = Σ pᵢ · MWC(score résultant après l'issue i)`, une somme
pondérée des six issues disjointes où le score ne touche que les poids. Donner le score au tronc
n'ajoute là **aucun pouvoir de représentation** : cela rend score-dépendant un calcul qui ne l'est
pas, au prix du cache et du facteur ~5 ci-dessous.

Là où `prob5` cesse d'être suffisant, c'est le **videau**, dont la valeur dépend de la dispersion
et non de la moyenne. Le risque de la fusion tardive est donc **confiné à la partie cubeful**, et
c'est exactement ce que l'ablation B0 contre B mesure, en heures.

**Ce qu'on perd malgré tout** : un tronc conscient du score pourrait *allouer sa capacité* selon le
contexte — cesser d'estimer finement les gammons à DMP, où ils ne valent rien, et dépenser ces
neurones sur `P(gain)`. C'est un gain de **capacité**, pas de représentation ; il est réel, il
n'est chiffré nulle part, et il ne s'achète qu'au prix du cache. Il attend donc que les marches 1
et 2 aient montré qu'il y a quelque chose à gagner. `[HYPOTHÈSE]`

## L'arbitrage

La voie naturelle, et celle de la seule publication du domaine — Andrew Lin, TAAI 2020, qui
intègre *« the doubling cube and match scoring into the network »* — met le contexte à l'entrée du
tronc. Elle est plus expressive : le jeu de pions lui-même devient conscient du score.

Elle coûte deux choses que personne ne compte :

- **Le cache d'évaluation se fragmente.** `gn_evalcache` a aujourd'hui pour clé la position seule,
  et c'est légitime parce que la distribution rendue est indépendante du score et du videau — T3A
  l'a prouvé au bit. Un tronc conscient du score oblige la clé à porter le contexte. Le cache
  rapporte **×3,41 au point de fonctionnement** `[MESURE, T3A]` ; cette fragmentation est une
  perte directe.
- **Une même position évaluée sous plusieurs contextes coûte plusieurs passes avant.** Or c'est
  exactement ce que fait une décision de videau : comparer non-double, double-pris et
  double-passé, c'est évaluer la même position sous trois états de videau — et en match, les deux
  camps ne voient pas le même score.

L'arithmétique, qui est un **comptage d'architecture et non une mesure** : le tronc pèse
~527 000 MACs, une tête `(goulot + ~63 entrées de contexte) → 64 → 3` en pèse ~5 000, soit ~1 %.
Évaluer une position sous cinq contextes coûte donc `1 tronc + 5 têtes ≈ 1,05 tronc` en fusion
tardive, contre **5 troncs** à l'entrée. Un facteur ~5 sur le poste dominant du moteur, et le
cache reste valide.

La contrainte du dépôt tranche seule : toute proposition d'architecture se juge en **précision par
MAC**, jamais en précision, parce que le client est un navigateur — y compris un téléphone. Un
réseau meilleur et plus lent est un échec.

## Ce que cela suppose, et qui reste à mesurer

La fusion tardive fait porter toute la décision de videau par le **goulot**. Or l'argument de fond
de l'axe est que *les cinq probabilités sont une statistique de la moyenne, alors que le videau
dépend de la dispersion* — deux positions de même distribution peuvent appeler des décisions
opposées. Si le goulot se réduit à `prob5`, la fusion tardive hérite du plafond même qu'on
cherchait à lever. `[HYPOTHÈSE]`

C'est l'ablation qui ouvre la marche 1, et elle décide dans les deux sens : **B0** (tête sur
`prob5` seul) contre **B** (tête sur goulot enrichi — les 5 probabilités plus une poignée
d'auxiliaires, dont la volatilité exacte sur les 21 jets que T71 produit déjà comme sous-produit
gratuit). **L'écart B0 → B mesure exactement ce que vaut « l'efficacité de videau »** : la part de
la valeur cubeful qui dépend de la position et non de la seule distribution. Personne ne l'a
publiée.

La largeur du goulot est le paramètre de conception qui en découle, et elle se paie dans le cache,
pas dans les MACs : ~49 o par entrée à 5 sorties, ~93 o à 16, ~541 o si la tête consommait la
dernière couche cachée. Le choix par défaut est **étroit et interprétable**, donc diagnosticable.

## Conséquences

- **Nomenclature.** Une tête entraînée sur un tronc **gelé** est un composant, pas un réseau
  nouveau : le tronc garde son nom et sa mesure de force (`BRIEF.md` §8). Un tronc réentraîné,
  lui, est un artefact nouveau — nom nouveau, force entièrement à remesurer. La règle est écrite
  ici **avant** le premier entraînement, pour ne pas se trancher au moment gênant où l'on voudra
  annoncer un chiffre.
- **La recherche.** Une feuille qui rend directement une MWC cubeful supprime la récursion de
  videau aux feuilles (T34 phase 2) et fait disparaître le piège du niveau intermédiaire de
  `BRIEF.md` §6 **par construction**. C'est une simplification — donc exactement le genre de
  propriété qu'il faut vérifier plutôt que croire (protocole T36).
- **La marche 3 reste fermée.** Un tronc conscient du score n'est pas écarté pour toujours : il
  est écarté tant que les marches 1 et 2, à tronc gelé et en heures, n'ont pas montré qu'il y a
  quelque chose à gagner. C'est là qu'est tout le coût — self-play de matchs, ~250 000 parties
  pour un seul point de comparaison, et toute la force à remesurer.
- **Kazaross-XG2 reste un instrument, jamais une entrée.** La MET implicite s'extrait du modèle et
  se compare à la table cellule par cellule ; rien de la table n'entre dans les poids ni dans
  l'artefact distribué. C'est le statut que `CLAUDE.md` accorde déjà à GNU Backgammon comme
  oracle.
- **Le gain ne se justifie pas par la MET.** Les tables modernes ne se départagent quasiment plus
  (g11 contre Woolsey ≈ 50,05 % de matchs gagnés ; 0,46 point de pourcentage d'écart au pivot
  -2/-1 Crawford) `[MESURE, DS-08]`. Une MET apprise parfaite ne rapporte à peu près rien en
  force. Le produit, ce sont les points de prise qui varient avec la position ; la MET organique
  est le sous-produit auditable.

## Ce qui la révisera

Une mesure, et une seule : si le coût de recherche de l'option A se révélait **inférieur** au
comptage ci-dessus — parce que le cache rendrait moins que ×3,41 sous charge réelle de match, ou
parce que la tête, seule, n'atteindrait pas la qualité visée quelle que soit la largeur du goulot.
Les deux se mesurent sur le banc existant. La décision est révisable ; ce qui ne l'est pas, c'est
un tronc déjà entraîné avec le score dedans.
