# DS-05 — La recherche à nœuds de hasard : ce qui réduit le nombre d'évaluations

**Vague** 1 · **Dépend de** — · **Alimente** DS-04, DS-06, DS-09
**Ce qu'elle décide** : d'où viennent les ×2 à ×10 attendus du poste « évaluations calculées puis
jetées », et si l'hypothèse H4 — plus large à budget égal — a un fondement.

---

═══════════════════ DÉBUT DU PROMPT — copier à partir d'ici ═══════════════════

Tu m'aides sur **gammonNet**, un évaluateur de positions de backgammon : réseau de neurones,
recherche expectiminimax, table d'équité de match, tables de fin de partie exactes. Deux cibles :
WebAssembly (navigateur, y compris téléphone) et natif.

**Notre recherche aujourd'hui.** Un expectiminimax classique. À chaque nœud, les **21 jets
distincts** (6 doubles pondérés 1/36, 15 non-doubles pondérés 2/36) ; pour chaque jet, les coups
légaux (~20 en moyenne en position de contact) ; un filtre de coups qui ne descend en profondeur
que sur les N meilleurs du niveau précédent ; un réseau d'élagage bon marché (196 → 32 → 5,
92 fois moins cher par évaluation) qui pré-trie les candidats ; un cache d'évaluation dont la clé
est la position seule.

**Nos coûts mesurés, mono-fil :**

| | évaluations du grand réseau | temps par décision |
|---|---|---|
| 2-ply, filtre (0,1,3), sans élagage | ~31 000 | 2,0075 s |
| 2-ply, avec élagage `k=12` | ~12 000 | 0,5588 s |
| 2-ply, avec élagage `k=3` | ~3 700 | 0,2396 s (mais +0,0039 d'équité perdue par décision) |
| 3-ply, garde (0,1,1,5), sans élagage | — | 70,55 s |

**GNU Backgammon prend ~10 ms pour la même décision 2-ply.** Nous sommes 25 à 60 fois plus lents,
et son coût est presque **plat avec la profondeur** là où le nôtre explose.

Nous avons aussi mesuré deux choses qui cadrent la question :

- **La profondeur n'est pas un levier de force** : notre 3-ply contre son 2-ply, pour 15 fois plus
  de calcul, rapporte +0,00022 d'équité par décision — dans le bruit.
- **Le cache rapporte ×3,41** au point de fonctionnement, et sa clé est la position seule.

## La question

**Quelles techniques de recherche, publiées et si possible mesurées, réduisent le nombre
d'évaluations nécessaires à une décision dans un arbre à nœuds de hasard — et de combien ?**

## Les sous-questions

1. **Les algorithmes \*-minimax.** Ballard (1983) a introduit Star1 et Star2 : de l'élagage
   alpha-bêta étendu aux nœuds de hasard. Hauk, Buro et Schaeffer ont publié des travaux
   spécifiquement sur leur performance **au backgammon** (années 2000). Que disent ces travaux
   exactement ? Quel facteur de réduction du nombre de nœuds obtiennent-ils, à quelle profondeur,
   et **sous quelles conditions** ? Quelles hypothèses font-ils sur les bornes de la fonction
   d'évaluation (les nôtres sont des probabilités, donc bornées dans [0,1] — est-ce exploitable) ?
   Pourquoi ces techniques ne semblent-elles pas employées par les moteurs de production, si c'est
   le cas ?
2. **L'ordre des coups.** Dans l'alpha-bêta, l'ordre décide de tout. Que sait-on de l'ordonnancement
   des coups au backgammon — un réseau de politique bon marché, des heuristiques (coups qui
   frappent, qui font des points), un « killer move », l'ordre du niveau précédent en
   approfondissement itératif ? Quels gains sont **mesurés** ?
3. **Les tables de transposition dans un arbre stochastique.** Au backgammon, beaucoup de
   séquences (jet, coup) convergent vers la même position. Quel taux de transposition est
   documenté ? Comment stocke-t-on une entrée quand la valeur dépend de la profondeur restante ?
   Y a-t-il des travaux sur les tables de transposition en expectiminimax, avec des chiffres ?
4. **Le hasard lui-même : peut-on ne pas développer les 21 jets ?** Échantillonnage clairsemé
   (*sparse sampling*, Kearns-Mansour-Ng), échantillonnage préférentiel, variables antithétiques,
   « jets communs » entre coups candidats, regroupement de jets équivalents pour une position
   donnée (deux jets différents peuvent avoir le même ensemble de coups atteignables). Que sait-on
   de l'erreur introduite en fonction du nombre de jets développés ?
5. **L'allocation variable de profondeur.** Chercher plus loin là où ça bouge. Existe-t-il des
   travaux sur la profondeur variable pilotée par une **volatilité** estimée, une incertitude
   prédite, ou une marge entre le meilleur et le deuxième coup ? Comment un moteur décide-t-il
   d'arrêter (quiescence dans un jeu à hasard) ?
6. **MCTS à nœuds de hasard.** Quelles variantes existent (élargissement progressif double,
   *open-loop*), et y a-t-il une preuve qu'elles battent l'expectiminimax au backgammon, où le
   facteur de branchement du hasard est de 21 et celui des coups d'environ 20 ? Si l'expectiminimax
   reste supérieur ici, je veux savoir **pourquoi** — c'est aussi une réponse utile.
7. **La question qui explique gnubg.** Pourquoi son coût est-il quasi plat avec la profondeur ?
   Élagage par petits réseaux, filtres très serrés, cache, réutilisation entre décisions
   successives ? Ce qui est documenté m'intéresse plus que ce qui est supposé.
8. **La réutilisation entre décisions.** Entre deux coups consécutifs d'une partie, une partie de
   l'arbre est réutilisable. Quel gain est documenté, et qu'est-ce qui l'empêche (le jet de dés
   qui tombe entre les deux) ?

## Contraintes

- **Chiffre tout ce que tu peux.** « Réduit fortement le nombre de nœuds » ne m'aide pas ; « ×2,3
  à profondeur 4 sur ce corpus » m'aide.
- Toute technique doit être compatible avec un noyau d'inférence **par lots** : notre réseau
  s'évalue par paquets de 32 positions, et une technique qui sérialise les évaluations
  (dépendance stricte entre nœuds, comme l'alpha-bêta pur) peut coûter plus cher qu'elle ne
  rapporte. **Signale explicitement, pour chaque technique, si elle est compatible avec le calcul
  par lots ou si elle le casse.** C'est un critère de premier ordre pour nous.
- Tout artefact signalé arrive **avec sa licence et son lien**. Hors périmètre : poids de GNU
  Backgammon (GPL-3), réseaux HedgeHog (clause non commerciale), bgsage (AGPL-3). Pas de
  transcription de code ni de constantes réglées à la main.

## Format du rendu

Un rapport en **français** où :

- Chaque affirmation porte une étiquette : `[MESURE]` (publication avec protocole et chiffres),
  `[DÉCLARÉ]`, `[HYPOTHÈSE]`, `[FOLKLORE]`.
- Chaque source porte son lien et sa date de consultation.
- **Un tableau des techniques**, trié par gain attendu :

  | Technique | Gain publié (facteur, conditions) | Perte de qualité, si mesurée | Compatible calcul par lots ? | Effort d'implémentation | Source |

- Une section **« Les trois que je mettrais en premier »**, avec pour chacune : ce qu'elle
  suppose, ce qui pourrait la faire échouer chez nous, et **la mesure qui la validerait**.
- Une section **« Ce que je n'ai pas trouvé »**.

═══════════════════ FIN DU PROMPT — copier jusqu'ici ═══════════════════

---

## Note interne — ne pas coller

**Ce que ce retour doit permettre de trancher, précisément.** T36 a fermé la profondeur comme
levier de force, à budget non contraint. Elle n'a jamais testé **la largeur à budget égal** — sa
garde `(0,1,1,5)` au 3-ply est nommée comme une réserve non validée, et le 3-ply large était
estimé intestable (~20 min par décision) avant que T3A ne le ramène vers 3-4 min.

Si DS-05 rapporte des facteurs crédibles sur le nombre d'évaluations, alors le 2-ply **large**
(garde intérieure 5 au lieu de 1) devient abordable, et l'expérience à faire est celle que T36 n'a
pas pu faire : *à une seconde par décision, vaut-il mieux chercher plus profond ou plus large ?*
C'est l'expérience la moins chère du programme et elle n'a jamais tourné.

**Le critère « compatible calcul par lots » n'est pas un détail.** T3A a mesuré que le gain de
l'élagage passait de ×1,36 à ×9 uniquement en **remplissant les lots** : le noyau calcule 32 voies
qu'on lui en donne 5 ou 32. Une technique qui réduit le nombre de nœuds mais vide les lots ne
rapportera rien, et cette erreur a déjà été commise une fois dans ce dépôt.
