# DS-08 — Le videau : au-delà de Janowski, et où la barre de gnubg est basse

**Vague** 1 · **Dépend de** — · **Alimente** DS-13, et la décision d'ouvrir ou non l'axe « videau
appris » déjà instruit dans `docs/etudes/`
**Ce qu'elle décide** : si l'hypothèse H3 tient — le gain le moins cher n'est pas dans le jeu de
pions mais dans le videau — et par quelle voie.

---

═══════════════════ DÉBUT DU PROMPT — copier à partir d'ici ═══════════════════

Tu m'aides sur **gammonNet**, un évaluateur de positions de backgammon : réseau de neurones,
recherche expectiminimax, table d'équité de match, tables de fin de partie exactes. Cible
navigateur (WebAssembly, y compris téléphone) et natif.

**Notre videau aujourd'hui.** Le réseau est *cubeless* et aveugle au score : il rend cinq
probabilités (gain, gain-gammon, gain-backgammon, perte-gammon, perte-backgammon). La conversion
en équité de match se fait ensuite, par une table d'équité de match. La décision de videau repose
sur une formule de type Janowski, avec un coefficient d'efficacité de videau que nous avons
**mesuré nous-mêmes** sur trois classes de position (0,688 / 0,566 / 0,687) plutôt que réglé à la
main.

**Ce que nous avons déjà mesuré, et qui motive cette recherche :**

- En configuration complète, nous sommes **équivalents** à gnubg 2-ply, ni au-dessus ni en
  dessous. Notre avantage cubeless de +0,0400 point par partie **ne se reproduit pas** une fois le
  videau branché — ce qui désigne le videau comme le poste où nous perdons ce que le réseau gagne.
- Notre modèle de videau a **deux défauts nommés et chiffrés** : il sous-double en course et
  sur-double dans une fenêtre fine de contact. Ce sont des défauts **dépendants de la classe de
  position**, qu'un coefficient scalaire ne peut pas corriger par construction.
- Un argument de forme que je veux mettre à l'épreuve : **les cinq probabilités sont une statistique
  de la moyenne, alors que le videau dépend de la dispersion.** Deux positions peuvent avoir les
  mêmes cinq probabilités et des décisions de videau opposées — un jeu de retenue tranquille où le
  videau peut attendre, un blitz volatil où il faut doubler sous peine de perdre son marché.
  « L'efficacité de videau » de Janowski est précisément un scalaire réglé pour approximer cette
  dispersion.

## La question

**Quel est l'état de l'art de la décision de videau — théorie publiée, modèles appris, et mesures
comparatives — et où la décision de videau de GNU Backgammon est-elle documentée comme faible ?**

## Les sous-questions

### A. La théorie publiée

1. **Janowski, en entier.** *Take-Points in Money Games* (1993) et le modèle d'efficacité de
   videau. Donne les formules exactes : point de prise à videau mort, à videau vivant,
   l'interpolation par le coefficient d'efficacité `x`, la valeur de recube. Quelles sont les
   **hypothèses** du modèle, et où sont-elles documentées comme fausses ?
2. **Ce qui a été publié après Janowski.** L'« indice de vie du videau » (*cube life index*), les
   travaux de Woolsey, Trice, Kazaross, Keeler et Spencer, la théorie des « perdants de marché »
   (*market losers*) et de la volatilité. Y a-t-il un modèle publié **strictement meilleur** que
   Janowski, et est-ce mesuré ?
3. **La volatilité, définie précisément.** Comment la littérature la définit-elle et la
   calcule-t-elle ? Existe-t-il une définition opérationnelle — par exemple l'écart-type de
   l'équité au prochain point de décision, obtenu en développant les 21 jets de l'adversaire ?
   Quelqu'un a-t-il mesuré la corrélation entre une telle quantité et l'efficacité de videau
   empirique ?
4. **Le match.** Comment dérive-t-on les points de prise depuis une table d'équité de match ?
   Qu'est-ce que le « prix du gammon » et comment entre-t-il ? Quelles particularités exactes
   imposent le Crawford, l'après-Crawford, le videau mort, le 2-away/2-away, le double match
   point ?

### B. Les modèles appris

5. **Le videau appris par renforcement.** Le dépôt `alexstrehl/backgammon-ai-engine` revendique
   d'avoir appris la décision de videau **en money** sans aucune formule de point de prise —
   simplement en ajoutant les actions (doubler, prendre, passer) et quatre entrées binaires — et
   annonce battre gnubg de +78,8 mEq/partie au 0-ply. Vérifie cette revendication : quels sont les
   chiffres actuels de son README, quel protocole, quel volume, quel intervalle de confiance ?
   A-t-il étendu la chose au **match** depuis (c'était annoncé comme travail futur) ?
6. **Andrew Lin, *Learning Cube Strategy in Backgammon with Neural Networks*, TAAI 2020**
   (DOI 10.1109/TAAI51410.2020.00014). L'article est derrière un péage IEEE. Rapporte tout ce que
   tu peux en établir : architecture, encodage du score, résultats, et si une version accessible
   existe (préprint, thèse, présentation, citations détaillées).
7. **Un réseau peut-il apprendre la valeur du score de match**, c'est-à-dire faire émerger une
   table d'équité de match au lieu de la lire ? Qui a essayé, avec quel résultat mesuré ?

### C. La barre : gnubg et XG

8. **Comment GNU Backgammon décide-t-il de doubler ?** Ce qui est **documenté** de son évaluation
   « cubeful » : récursion aux feuilles, interpolation entre videau mort et videau vivant,
   coefficients par classe de position. Ses auteurs ou des tiers ont-ils publié des mesures de
   **son taux d'erreur de videau**, comparé à des rollouts ou à eXtreme Gammon ?
9. **Les erreurs de videau pèsent-elles plus que les erreurs de coup ?** Y a-t-il des mesures
   publiées de la répartition de l'erreur totale d'un moteur (ou d'un joueur) entre décisions de
   coup et décisions de videau ? C'est la sous-question qui décide de la priorité de tout cet axe.
10. **Les tables d'équité de match publiques.** Kazaross-XG2, Woolsey-Heinrich, Snowie, le modèle
    de Zadeh (1977), et toute autre. Pour chacune : son auteur, sa méthode de génération, où elle
    se trouve, **sous quelle licence ou quelles conditions**, et sa précision relative si elle a
    été comparée. Une table d'équité de match peut-elle être **regénérée de zéro** par rollouts de
    façon reproductible, et à quel coût ?

## Contraintes

- Nous distribuons un module WebAssembly, ce qui **est une distribution**. Tout artefact — table,
  poids, corpus, code — arrive **avec sa licence et son lien**. Hors périmètre, y compris comme
  source d'entraînement : poids de GNU Backgammon (GPL-3), réseaux HedgeHog (clause non
  commerciale), bgsage (AGPL-3).
- **Ne recopie ni code source ni constante réglée à la main** (les coefficients d'efficacité de
  videau d'un moteur sous copyleft en sont l'exemple type : nous les re-mesurons chez nous, nous
  ne les reprenons pas). Décris les mécanismes, cite la littérature — et quand une idée vient de
  Janowski ou de Kazaross, **cite-les eux**, pas le moteur qui l'implémente.
- Distingue clairement ce qui relève de la **théorie money** et ce qui relève du **match** : nous
  avons besoin des deux, mais ce sont deux corps de résultats différents.

## Format du rendu

Un rapport en **français** où :

- Chaque affirmation porte une étiquette : `[MESURE]`, `[DÉCLARÉ]`, `[HYPOTHÈSE]`, `[FOLKLORE]`.
  La théorie du videau est un domaine où beaucoup de chiffres circulent sans source primaire :
  sois particulièrement strict.
- **Les formules sont écrites explicitement**, avec la définition de chaque symbole et sa
  convention (probabilités imbriquées ou disjointes — c'est une source d'erreur classique et je
  veux que ce soit dit).
- Chaque source porte son lien et sa date de consultation.
- **Un tableau des tables d'équité de match** : nom / auteur / méthode / portée (jusqu'à combien
  de points) / lien / licence.
- Un tableau final de décision :

  | Piste d'amélioration du videau | Gain attendu | Coût | Risque | Licence | La mesure qui trancherait |

- Une section **« Ce que je n'ai pas trouvé »**.

═══════════════════ FIN DU PROMPT — copier jusqu'ici ═══════════════════

---

## Note interne — ne pas coller

**Ce dossier existe déjà en partie.** `docs/etudes/2026-08-19-videau-appris-sans-a-priori.md` et
`docs/etudes/2026-08-19-plan-videau-appris.md` instruisent la question du videau appris, avec un
plan conditionnel (fiches T60-T69) et une proposition concrète : une **tête de volatilité**
distillée depuis un développement 1-ply (~390 évaluations, contre 38 721 pour une décision 2-ply).

DS-08 ne refait pas ce travail. Elle sert à trois choses précises :

1. **Vérifier les chiffres amont**, qui ont bougé deux fois depuis leur relevé du 2026-08-19 (le
   +78,8 mEq/partie, la table du README recalculée sur générateur corrigé puis contre un gnubg
   vérifié).
2. **Répondre à la sous-question 9** — la répartition de l'erreur entre coup et videau — qui
   n'est instruite nulle part dans le dépôt et qui décide de la priorité de tout l'axe.
3. **Chercher un modèle publié meilleur que Janowski**, ce que l'étude n'a pas fait : elle est
   partie du principe que Janowski + efficacité mesurée était l'état de l'art accessible.

Le point de licence de la sous-question 10 n'est pas cosmétique : l'artefact embarque aujourd'hui
la table Kazaross-XG2, œuvre d'un tiers, utilisée avec attribution. Une table regénérable chez nous
améliorerait la traçabilité de bout en bout — c'est un gain structurel, pas un gain de force.
