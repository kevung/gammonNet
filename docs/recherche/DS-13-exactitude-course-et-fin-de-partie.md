# DS-13 — L'exactitude au-delà du bearoff : jusqu'où le calcul exact peut remplacer le réseau

**Vague** 3, **conditionnelle** · **Ne se lance que si** DS-07 ou DS-08 montre que la course et la
fin de partie pèsent réellement dans l'erreur totale — sinon les tables déjà branchées ont comblé
ce qui comptait.
**Dépend de** DS-07, DS-08 · **Alimente** DS-14

---

## À injecter avant de lancer — ne pas coller cette section

| Marqueur | À remplir depuis |
|---|---|
| `⟨POIDS-COURSE⟩` | DS-07 (répartition de l'erreur par classe de position) ou DS-08 (répartition coup / videau) — la part de l'erreur totale imputable à la course et à la fin de partie |

Si `⟨POIDS-COURSE⟩` est négligeable, **ne lance pas cette recherche** : elle instruirait un poste
qui ne pèse pas.

---

═══════════════════ DÉBUT DU PROMPT — copier à partir d'ici ═══════════════════

Tu m'aides sur **gammonNet**, un évaluateur de positions de backgammon : réseau de neurones,
recherche expectiminimax, table d'équité de match, tables de fin de partie exactes. Cible
navigateur (WebAssembly, y compris téléphone) et natif.

**Ce que nous avons déjà.** Des tables de fin de partie exactes, calculées par programmation
dynamique : une base unilatérale (distribution du nombre de jets pour sortir) et une base
bilatérale pour les positions où les deux camps sont dans leur jan intérieur. Nous avons mesuré
que le branchement de la table exacte comble **0,00028 point d'équité par décision de bearoff**,
avec des pires cas à 0,0919 sur une seule décision — c'est la queue de distribution qui coûte, pas
la moyenne. Ces tables partent en natif ; leur transport vers le navigateur est une question
ouverte (taille).

**Ce qui reste au réseau.** Toute la course avec contact résiduel, et toute la course longue hors
du domaine des tables. Une part de l'erreur totale de notre moteur y est imputable :
⟨POIDS-COURSE⟩.

**L'idée que je veux instruire.** Une position de course est un objet **beaucoup plus simple**
qu'une position de contact : sans contact, l'issue ne dépend plus que de deux distributions de
temps de sortie. Si une part significative des décisions pouvait être tranchée par un calcul
exact ou quasi exact plutôt que par le réseau, on gagnerait **deux fois** : en qualité (exactitude
au lieu d'approximation) et en vitesse (une table s'interroge en nanosecondes).

## La question

**Jusqu'où le calcul exact peut-il remplacer le réseau au backgammon — en course, en fin de
partie, et pour les décisions de videau qui s'y rattachent — et à quel coût de génération et de
stockage ?**

## Les sous-questions

1. **Les bases existantes.** Bases unilatérales et bilatérales, leurs domaines usuels (combien de
   points, combien de pions), leurs tailles, leur méthode de génération. Jusqu'où la communauté
   est-elle allée, et qu'est-ce qui l'a arrêtée — le temps de calcul, la taille, ou l'utilité
   marginale ?
2. **Le videau dans les tables.** Une table donne une équité cubeless. Existe-t-il des tables
   **cubeful**, donnant directement la décision de videau exacte, et à quel surcoût de taille ?
   C'est important pour nous : la fin de partie est le seul endroit où une décision de videau
   admet une réponse **sans variance**, donc le seul étalon parfait dont nous disposions.
3. **La course longue, hors du domaine des tables.** Que valent les formules publiées — compte de
   pips ajusté, EPC (*effective pip count*), compte de Kleinman, compte de Thorp, formules de
   Trice ? Existe-t-il des mesures de leur erreur d'équité contre des rollouts ou contre un calcul
   exact ? Une formule est-elle **meilleure qu'un réseau** dans son domaine, et si oui lequel ?
4. **Les bases de course.** Peut-on calculer exactement une course **sans contact** de bout en
   bout, quel que soit le nombre de pips, par convolution des distributions de temps de sortie ?
   Quelle est la complexité, quelle est la taille de l'état, et pourquoi cela n'est-il pas fait
   partout si c'est faisable ? Je veux comprendre où est le mur.
5. **La frontière contact / course.** Comment détecte-t-on qu'il n'y a plus de contact possible, et
   quelle proportion des décisions d'une partie réelle tombe après cette frontière ? Ce chiffre
   décide de l'intérêt de tout l'axe.
6. **Le transport vers le navigateur.** Quelles tailles de table sont acceptables dans une
   application web, quelles techniques de compression sont employées pour ce type de données
   (tables d'équités quantifiées, indexation combinatoire, chargement à la demande par blocs) ?
   Est-il documenté qu'un moteur embarque une base de fin de partie dans un navigateur ?
7. **L'indexation.** Les schémas d'indexation combinatoire des positions de fin de partie (rang
   d'une combinaison), leur coût de calcul, et les pièges d'implémentation connus.

## Contraintes

- **Une table de fin de partie est un calcul exact reproductible**, pas une œuvre de création :
  deux implémentations correctes produisent des fichiers identiques. C'est notre fondement pour
  employer ce type de données quelle que soit leur origine. En revanche, **le code qui les génère**
  reste soumis à sa licence, et nous ne le reprenons pas : nous redérivons les formules et les
  vérifions exhaustivement contre le programme de référence.
- Signale, pour chaque outil ou fichier, **sa licence et son lien**.
- Chiffre les tailles et les temps de génération.

## Format du rendu

Un rapport en **français** où :

- Chaque affirmation porte une étiquette : `[MESURE]`, `[DOCUMENTÉ]`, `[HYPOTHÈSE]`, `[FOLKLORE]`.
- Chaque source porte son lien et sa date de consultation.
- **Un tableau des domaines d'exactitude** :

  | Domaine | Ce qu'on peut calculer exactement | Taille de la table | Coût de génération | Gain d'équité attendu | Transportable au navigateur ? |

- Une section **« La frontière que je viserais »** : jusqu'où pousser l'exactitude, et pourquoi
  s'arrêter là.
- Une section **« Ce que je n'ai pas trouvé »**.

═══════════════════ FIN DU PROMPT — copier jusqu'ici ═══════════════════

---

## Note interne — ne pas coller

**Pourquoi cette recherche est conditionnelle, et pas facultative.** T38 a mesuré le déficit de
bearoff et l'a comblé — le sujet a donc l'air clos. Il ne l'est que dans le domaine des tables
existantes. Deux choses restent ouvertes et pourraient peser :

1. **La course longue** est jouée par le réseau, sans qu'aucune mesure du dépôt ne dise ce qu'elle
   coûte. Le seul indice est indirect : notre réseau d'élagage place le meilleur coup dans son
   top-5 dans 94,2 % des décisions de contact mais **83,6 %** en course — le terrain se comporte
   différemment.
2. **La vitesse.** Une décision tranchée par table est essentiellement gratuite. Si une fraction
   notable des décisions d'une partie tombe dans un domaine exact, cela allège la facture moyenne
   **et** supprime une source d'erreur, ce qui est la combinaison que tout ce programme cherche.

**Le garde-fou de la conditionnalité.** `CLAUDE.md` interdit d'élargir le périmètre par
enthousiasme. Si l'erreur de course ne pèse pas dans le PR, cette recherche instruit un poste qui
ne rapporte rien, et le programme a mieux à faire.
