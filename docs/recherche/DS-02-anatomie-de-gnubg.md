# DS-02 — L'anatomie de GNU Backgammon : la barre exacte, et où elle est basse

**Vague** 1 · **Dépend de** — · **Alimente** DS-03, DS-04, DS-06, DS-12
**Ce qu'elle décide** : la cible chiffrée de vitesse (combien de MACs gnubg dépense-t-il vraiment
par décision ?) et les endroits où sa qualité est documentée comme faible.

---

═══════════════════ DÉBUT DU PROMPT — copier à partir d'ici ═══════════════════

Tu m'aides sur un projet d'ingénierie appelé **gammonNet** : un évaluateur de positions de
backgammon (réseau de neurones + recherche expectiminimax + table d'équité de match + tables de
fin de partie exactes), compilé en WebAssembly pour le navigateur, y compris sur téléphone, et en
natif pour les rollouts.

Nous avons mesuré que notre moteur est **statistiquement équivalent à GNU Backgammon en 2-ply**,
et que **notre décision 2-ply coûte 25 à 60 fois plus cher que la sienne** — ~2,0 s contre ~10 ms,
mono-fil. Notre réseau fait 196 entrées denses → 512 → 512 → 256 → 128 → 5, soit environ
**527 000 multiplications-accumulations par évaluation**. Je soupçonne que le réseau de gnubg est
d'un ordre de grandeur plus petit, et que c'est là que passe l'essentiel de l'écart de vitesse —
mais **je n'en ai aucune mesure**, seulement une supposition.

## La question

**Comment GNU Backgammon est-il fait, précisément — et où sa qualité est-elle documentée comme
faible ?**

## Les sous-questions

### A. L'architecture d'évaluation

1. **Les réseaux : combien, de quelles tailles ?** Nombre d'entrées, nombre de neurones cachés,
   nombre de sorties, pour chacun des réseaux de gnubg. On parle couramment de **250 et 214
   entrées** et de classes de position `contact` / `crashed` / `race` : confirme ou corrige, et
   donne les tailles de couche cachée. Je veux pouvoir calculer le **nombre de MACs par
   évaluation** pour chaque classe.
2. **Les entrées, une par une.** gnubg utilise l'encodage de Tesauro plus des caractéristiques
   calculées supplémentaires. Lesquelles ? Comment sont-elles définies et pourquoi ont-elles été
   ajoutées ? (Je cherche la liste et le sens de chacune : exposition des blots, tirs subis,
   force du jan intérieur, timing, comptes de pips, points de conteneur, etc.)
3. **La classification des positions.** Comment gnubg décide-t-il de la classe d'une position, et
   où passent exactement les frontières `contact` / `crashed` / `race` / `bearoff` ? Est-il
   documenté que ces frontières produisent des **discontinuités d'évaluation** ? Si oui, de
   quelle amplitude, et est-ce mesuré quelque part ?
4. **Les réseaux d'élagage** (*pruning networks*). Le manuel les documente. Quelle taille ont-ils,
   comment sont-ils entraînés, et à quel endroit exact de la recherche interviennent-ils ?
   Combien d'évaluations du grand réseau économisent-ils, si c'est chiffré quelque part ?
5. **Le cache d'évaluation.** Quelle est sa clé, quelle est sa taille par défaut, quel taux de
   succès est rapporté ?

### B. La recherche

6. **Les filtres de coups.** Quels sont les réglages par défaut, niveau par niveau, pour les
   modes usuels (0-ply, 1-ply, 2-ply, 3-ply, 4-ply) — combien de candidats sont retenus, et sur
   quel critère (nombre fixe ? seuil d'équité ? les deux) ?
7. **Pourquoi le coût de gnubg est-il presque plat avec la profondeur ?** C'est ce que nous
   observons de l'extérieur. Quelle est l'explication documentée : élagage, filtres, cache,
   réseaux plus petits en profondeur, autre chose ?
8. **L'évaluation « cubeful ».** Comment gnubg calcule-t-il une équité tenant compte du videau —
   récursion aux feuilles, interpolation entre videau mort et videau vivant, autre ? Et comment
   la décision de videau elle-même est-elle prise ?

### C. L'entraînement, tel qu'il est documenté

9. **Comment les poids de gnubg ont-ils été obtenus ?** TD-learning, puis apprentissage supervisé
   sur des bases de positions étiquetées par rollouts ? Quelles sont ces bases (les
   « benchmark databases » évoquées dans les listes de diffusion), quelle est leur taille, comment
   ont-elles été construites, et **sont-elles publiques et sous quelle licence** ?
10. **Les réseaux « supremo » et les variantes.** Que sont-ils, qui les a produits, sont-ils
    distribués, et à quel niveau de force ?

### D. Où gnubg est faible — la sous-question qui décide

11. **Qu'est-ce que les auteurs de gnubg, ou des mesures indépendantes, reconnaissent comme
    faible ?** Je cherche des faiblesses **documentées et si possible chiffrées**, pas des
    impressions. Les candidats que j'ai en tête, à confirmer ou infirmer : la classe `crashed`,
    les backgames, les positions de conteneur, le videau dans certains contextes de score, les
    courses profondes sans base de fin de partie, la discontinuité aux frontières de classe, les
    positions rares hors distribution de son self-play.
12. **Les bogues et limitations connus**, tels qu'ils apparaissent dans les listes de diffusion
    `bug-gnubg` et le suivi de bogues, quand ils touchent la **qualité d'évaluation** et non
    l'interface.

## Contraintes de méthode — importantes

Notre projet s'est donné un protocole strict sur GNU Backgammon, parce que ses poids sont sous
GPL-3 et que nous distribuons un artefact sous licence permissive :

- **gnubg nous sert d'oracle de mesure, jamais de source d'apprentissage.**
- **Ne recopie aucun extrait de code source de gnubg, et aucune constante réglée à la main**
  (seuils de filtre, coefficients d'efficacité de videau, présélections). Ce sont le produit du
  travail de réglage de quelqu'un, et nous ne les reprenons pas. Décris les **mécanismes**, et
  cite la **documentation**.
- Privilégie dans cet ordre : (1) le manuel officiel et la documentation publique, (2) les listes
  de diffusion, les billets et les fils d'archive où les auteurs expliquent leurs choix, (3) les
  articles publiés. Le code source n'est un recours qu'en dernier lieu, et alors uniquement pour
  répondre à une question **structurelle** (« combien de neurones cachés ») et jamais pour en
  rapporter la forme.
- Si une question peut être répondue en **faisant tourner gnubg lui-même** (il est livré avec des
  outils documentés : un interpréteur Python embarqué, `bearoffdump`, des commandes d'inspection),
  dis-le : c'est la voie que nous préférons, parce qu'elle produit une provenance vérifiable.

## Format du rendu

Un rapport en **français** où :

- **Chaque affirmation porte une étiquette** : `[DOCUMENTÉ]` (manuel ou publication officielle),
  `[DÉCLARÉ]` (un auteur l'écrit sur une liste ou un forum), `[MESURÉ]` (un chiffre issu d'une
  mesure publiée, avec son protocole), `[HYPOTHÈSE]`, `[FOLKLORE]`.
- Chaque source porte **son lien et la date de consultation**.
- **Un tableau des tailles de réseau** avec, pour chaque classe de position : entrées, couche(s)
  cachée(s), sorties, **MACs par évaluation calculés par toi**, et le degré de confiance.
- **Un tableau des faiblesses documentées** : où / ce qui est faible / la preuve / son ampleur si
  chiffrée / comment nous pourrions le mesurer nous-mêmes.
- Une section **« Ce que je n'ai pas trouvé »**.
- Un tableau final de décision :

  | Constat | Ce qu'il implique pour nous | Confiance | La mesure qui le confirmerait chez nous |

═══════════════════ FIN DU PROMPT — copier jusqu'ici ═══════════════════

---

## Note interne — ne pas coller

**Pourquoi cette recherche est structurante.** Deux chiffres en dépendent :

1. **La cible de vitesse.** Si le réseau `contact` de gnubg fait bien de l'ordre de 33 000 MACs
   contre nos 527 000, alors l'écart ×25-60 s'explique presque entièrement par la taille du
   réseau, et le programme de vitesse devient « faire tenir notre qualité dans un réseau 4 à 16
   fois plus petit » — ce qui est une question de distillation et de spécialisation (DS-12), pas
   de noyau SIMD. Si au contraire leur réseau est du même ordre que le nôtre, l'écart est ailleurs
   et DS-04/DS-05 deviennent prioritaires. **Ce retour arbitre entre deux programmes différents.**
2. **Les faiblesses documentées** (sous-question 11) sont la liste des endroits où « fortement
   dépasser » est le moins cher. C'est la matière première de la vague 2.

**Attention au protocole d'étude.** `docs/etudes/README.md` fixe trois niveaux de lecture de
gnubg, et note qu'au 2026-08-06 le niveau 3 (le code source) n'a **jamais** été nécessaire : trois
questions qui semblaient l'exiger ont été résolues en interrogeant le programme lui-même. Toute
réponse de ce retour qui reposerait sur une lecture de source est à re-vérifier par cette voie
avant d'être utilisée, et à porter au registre.
