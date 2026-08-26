# DS-07 — L'instrument : prouver « fortement dépasse » sans y passer des mois

**Vague** 1 · **Dépend de** — · **Alimente** DS-11, DS-13, et **tout le reste du programme**
**Ce qu'elle décide** : le protocole de mesure. C'est un **prérequis**, pas un choix : sans lui,
aucun modèle produit par les autres recherches ne pourra être départagé.

---

═══════════════════ DÉBUT DU PROMPT — copier à partir d'ici ═══════════════════

Tu m'aides sur **gammonNet**, un évaluateur de positions de backgammon (réseau de neurones,
recherche expectiminimax, table d'équité de match, tables de fin de partie exactes), pour le
navigateur et le natif.

**Le problème que je te soumets est un problème d'instrument, pas de modèle.**

Nous venons de mesurer que notre moteur est équivalent à GNU Backgammon en 2-ply. La campagne qui
le dit a coûté **4,9 jours de calcul sur 30 processus** — 50 000 paires de matchs de 7 points,
avec dés dupliqués — et rend un intervalle de confiance de ±0,26 point de chances de gain de match.
En money, 50 000 paires rendent ±0,020 point par partie.

Nous voulons maintenant **dépasser franchement** gnubg. Le problème : un gain réaliste par
itération d'ingénierie est de l'ordre de **0,002 à 0,010 point d'équité par décision**, et
l'instrument ci-dessus ne le voit pas. Nous avons construit une métrique **par décision** (perte
d'équité moyenne contre un arbitre commun, sur un corpus figé de positions) qui est deux ordres de
grandeur plus sensible ; mais notre arbitre est un rollout conduit par **notre propre politique**,
donc structurellement complaisant envers nos propres régularités.

## La question

**Quel protocole permet d'établir qu'un moteur de backgammon est plus fort qu'un autre, à la
résolution de quelques millièmes d'équité, pour un coût de calcul raisonnable — et avec quel
arbitre neutre ?**

## Les sous-questions

### A. Les métriques

1. **Le PR (*performance rating*) et le taux d'erreur.** Donne les **définitions exactes** : la
   formule du PR d'eXtreme Gammon (le « XG++ PR »), celle du taux d'erreur de GNU Backgammon, la
   notion de mEMG, et les constantes de normalisation employées. Comment sont traitées les
   décisions de videau par rapport aux décisions de coup ? Ces échelles sont-elles comparables
   entre outils, et si non, en quoi diffèrent-elles ?
2. **Sur quel corpus un PR se calcule-t-il ?** Faut-il jouer des parties, ou peut-on l'évaluer sur
   un ensemble fixe de positions ? Quelles sont les conventions publiées (nombre de décisions
   nécessaires pour un PR stable, traitement des positions forcées, pondération) ?
3. **Les métriques par décision.** Quelles alternatives publiées existent — perte d'équité moyenne
   contre référence, taux d'accord sur le meilleur coup, perte au pire cas, décomposition par
   classe de position ? Laquelle est la plus sensible à volume donné, et est-ce mesuré quelque
   part ?

### B. Les corpus de référence

4. **Quels ensembles de positions de référence existent publiquement ?** Positions étiquetées par
   rollouts, bases d'entraînement de moteurs (les « benchmark databases » évoquées dans la
   communauté GNU Backgammon), corpus de tournoi, collections de positions de test.
   **Pour chacun : sa taille, comment il a été étiqueté, où il se télécharge, et sous quelle
   licence ou quelles conditions.** La licence est bloquante pour nous — voir les contraintes plus
   bas.
5. **Comment un corpus de référence doit-il être stratifié ?** Contact, course, crash, backgame,
   fin de partie, actions de videau, contextes de score. Quelles proportions donnent une mesure
   représentative de la force en partie réelle, et est-ce documenté quelque part ?

### C. La réduction de variance — le cœur du sujet

6. **Les techniques employées dans les rollouts de backgammon.** Dés dupliqués et dés communs,
   variables antithétiques, dés quasi-aléatoires (*quasi-random dice*), et surtout la technique de
   **réduction de variance par anticipation** (*variance reduction* / *lookahead*) employée par
   eXtreme Gammon et GNU Backgammon : explique le principe (variable de contrôle fondée sur
   l'équité attendue du jet ?), et **chiffre le facteur de réduction de variance obtenu** s'il est
   publié.
7. **Combien d'essais pour quelle résolution ?** Donne l'arithmétique : pour séparer deux moteurs
   de 1 millième d'équité par décision, combien de décisions faut-il, avec et sans réduction de
   variance ? Pour séparer 0,5 % de chances de gain de match, combien de matchs ?
8. **Les matchs dupliqués.** Quel gain apporte le fait de rejouer la même séquence de dés dans les
   deux sens ? Est-ce chiffré ? Quelles précautions statistiques impose l'appariement (les deux
   manches d'une paire ne sont pas indépendantes — comment la communauté traite-t-elle cela) ?

### D. L'arbitre

9. **Comment éviter le biais d'arbitre ?** Si l'on juge une décision par un rollout conduit par sa
   propre politique, on se juge soi-même. Quelles parades sont publiées : rollout par un tiers,
   rollout à politique neutre, arbitrage croisé par plusieurs moteurs, rollouts très profonds
   traités comme vérité de terrain, positions à réponse exacte (fins de partie) ?
10. **Les pièges statistiques documentés** dans les comparaisons de moteurs de backgammon :
    non-transitivité (A bat B, B bat C, C bat A), sur-ajustement au corpus de test, comparaisons
    multiples, effets de style, dépendance des décisions à l'intérieur d'une partie.

## Contraintes

- Nous distribuons un module WebAssembly, ce qui **est une distribution**. Tout corpus, poids ou
  code que tu signales doit arriver **avec sa licence et son lien**. Un corpus sous GPL ou sous
  conditions restrictives peut éventuellement servir de **mesure** mais **jamais** d'entrée
  d'entraînement — précise donc, pour chaque corpus, si son usage comme corpus de **mesure** est
  possible, et sous quelles conditions.
- GNU Backgammon nous sert d'oracle de mesure — c'est explicitement permis, la sortie d'un
  programme n'étant en général pas couverte par le droit d'auteur sur son code — mais **jamais**
  de source d'apprentissage.
- Pas de transcription de code ni de constantes réglées à la main.

## Format du rendu

Un rapport en **français** où :

- Chaque affirmation porte une étiquette : `[MESURE]`, `[DÉCLARÉ]`, `[HYPOTHÈSE]`, `[FOLKLORE]`.
- Chaque source porte son lien et sa date de consultation.
- **Les formules sont écrites explicitement** (PR, taux d'erreur, estimateur à variable de
  contrôle), avec leurs constantes et l'unité de chaque terme. C'est la partie du rendu que je
  vais implémenter, donc l'approximation n'y est pas admissible.
- **Un tableau des corpus** : nom / taille / étiquetage / lien / licence / utilisable en mesure ?
  / utilisable en entraînement ?
- **Un tableau coût-résolution** : pour trois protocoles que tu recommandes, la résolution
  atteinte et le coût en décisions ou en parties.
- Une section **« Le protocole que je recommande »**, en une page, prêt à être implémenté.
- Une section **« Ce que je n'ai pas trouvé »**.

═══════════════════ FIN DU PROMPT — copier jusqu'ici ═══════════════════

---

## Note interne — ne pas coller

**Pourquoi cette recherche passe avant les autres, malgré son air d'intendance.** `CLAUDE.md`
règle n°2 : le harnais de mesure se construit avant le modèle. Le dépôt a déjà payé cette leçon
deux fois — une campagne de 4,8 jours perdue faute de sonde, et une conclusion de T36 qui a failli
s'inverser sur 52 décisions de bruit.

**Ce qui manque nommément aujourd'hui** :

1. **Le PR n'a jamais tourné**, alors que la condition de sortie de la phase 3 est libellée en PR
   (1,06 → 0,50 → 0,22). C'est un trou identifié dans la fiche T35 et dans la mémoire du projet.
2. **L'arbitre est complaisant** : le rollout de référence de T37 est conduit par notre propre
   politique 0-ply, et la fiche le dit elle-même.
3. **La réduction de variance existe déjà** dans le dépôt (T39, `t39-vr-gain.json`), mais son
   facteur n'a jamais été rapproché de ce que la littérature obtient.

Si ce retour donne la formule exacte du PR et un corpus de référence utilisable, il débloque à lui
seul une fiche `PLAN.md` qui traîne depuis la phase 3.
