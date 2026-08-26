# DS-14 — Le budget : ce que le programme retenu coûtera vraiment

**Vague** 3, **conditionnelle** · **Ne se lance que si** la vague 2 a désigné **une** architecture
cible — un budget se chiffre pour un programme, pas pour un éventail.
**Dépend de** DS-04, DS-06, DS-12 · **Alimente** la décision d'engager ou non

---

## À injecter avant de lancer — ne pas coller cette section

| Marqueur | À remplir depuis |
|---|---|
| `⟨ARCHITECTURE⟩` | DS-04 et DS-12 — l'architecture retenue : encodage, tailles, nombre d'experts, arithmétique |
| `⟨RECETTE⟩` | DS-06 — la recette d'entraînement retenue, avec le nombre de positions à étiqueter |
| `⟨PROTOCOLE⟩` | DS-07 — le protocole de mesure retenu, avec son coût par point de comparaison |

---

═══════════════════ DÉBUT DU PROMPT — copier à partir d'ici ═══════════════════

Tu m'aides à chiffrer un programme d'entraînement pour **gammonNet**, un évaluateur de positions
de backgammon (réseau de neurones, recherche expectiminimax, tables de fin de partie exactes),
distribué en WebAssembly pour le navigateur.

**Le programme que je veux chiffrer.** Architecture cible : ⟨ARCHITECTURE⟩. Recette
d'entraînement : ⟨RECETTE⟩. Protocole de mesure : ⟨PROTOCOLE⟩.

**Ma machine** : 16 cœurs / 32 fils, 94 Gio de mémoire, un GPU CUDA optionnel. Une seule machine,
pas un parc. Les campagnes tournent en détaché et peuvent durer des jours — la dernière a pris
4,9 jours sur 30 processus.

**Deux ancres mesurées chez nous**, pour calibrer tes estimations :

- une évaluation de notre réseau (~527 000 MACs) coûte **60 à 90 µs** mono-fil ;
- une décision 2-ply complète coûte **2,0 s** mono-fil sans élagage, **0,24 à 0,56 s** avec.

## La question

**Combien de temps de calcul faut-il réellement pour produire, puis qualifier, un réseau de
backgammon de ce type — et qu'est-ce qui, historiquement, fait exploser ce budget ?**

## Les sous-questions

1. **Ce que les autres ont dépensé.** Pour chaque moteur dont c'est documenté — TD-Gammon, GNU
   Backgammon, les moteurs commerciaux, HedgeHog, `wildbg`,
   `alexstrehl/backgammon-ai-engine` — combien de parties de self-play, combien d'heures ou de
   jours de machine, sur quel matériel, et **à quelle date** (le matériel de 1995 et celui de 2026
   ne se comparent pas sans conversion). Ce sont les seules ancres réelles dont je dispose.
2. **Le débit de génération de parties.** Combien de positions par seconde et par cœur un moteur
   de self-play en C atteint-il, avec une politique 0-ply ? Avec une politique 1-ply ? Quels sont
   les postes de coût — génération des coups légaux, évaluation, gestion de l'arbre ? Y a-t-il des
   chiffres publiés ?
3. **Le GPU : ce qu'il change et ce qu'il ne change pas.** Notre goulot est la génération de
   parties, qui est **liée au processeur** ; la rétropropagation d'un réseau de 528 000 paramètres
   est négligeable devant elle. Quelles architectures de self-play **par lots** permettent de
   remettre le GPU dans la boucle (jouer des milliers de parties en parallèle en vectorisant
   l'évaluation) ? Quel gain réel est publié, et quelle complexité d'implémentation cela
   représente-t-il ?
4. **Le coût de l'étiquetage.** Si la recette demande d'étiqueter des positions par une recherche
   profonde ou par des rollouts, donne l'arithmétique : coût unitaire × volume, et ce que la
   réduction de variance change à ce compte.
5. **Le coût de la qualification.** Une force ne s'affirme pas sans mesure, et la mesure coûte. Pour
   le protocole retenu, combien de temps de machine par point de comparaison ? Combien de points
   de comparaison un programme d'itérations demande-t-il typiquement ?
6. **Ce qui fait exploser les budgets, dans les retours d'expérience publiés.** Les candidats que
   j'ai en tête, à confirmer ou compléter : le nombre d'itérations nécessaire avant qu'une idée se
   révèle mauvaise, le réentraînement complet après chaque changement d'encodage, les campagnes de
   mesure trop peu sensibles qu'il faut refaire, l'instabilité de l'apprentissage par
   renforcement, le réglage d'hyperparamètres.
7. **Les paliers de repli.** Quelles versions **dégradées mais informatives** du programme
   existent — entraînement à tronc gelé, corpus réduit, mesure par décision plutôt que par partie —
   et quel signal donnent-elles pour quelle fraction du coût ? C'est la sous-question la plus utile
   du lot : je veux pouvoir arrêter tôt une mauvaise idée.

## Contraintes

- **Chiffre en heures de machine sur du matériel nommé**, pas en unités abstraites. Quand tu
  extrapoles depuis du matériel ancien, dis le facteur de conversion que tu appliques et sur quoi
  il repose.
- Distingue les trois postes — génération, entraînement, mesure — et donne-les séparément. Chez
  nous, le troisième a longtemps été sous-estimé.
- Une recette qui demande un parc de machines ou un budget d'infonuagique important n'est pas pour
  nous ; dis-le franchement plutôt que de la recommander.

## Format du rendu

Un rapport en **français** où :

- Chaque chiffre porte une étiquette : `[MESURE]` (publiée, avec matériel et date), `[EXTRAPOLÉ]`
  (conversion que tu as faite, avec sa base), `[HYPOTHÈSE]`.
- **Un tableau de budget, poste par poste** :

  | Poste | Volume | Débit supposé | Temps de machine | Base de l'estimation |

- **Trois scénarios chiffrés** : minimal (le signal le moins cher qui dit si l'idée marche),
  nominal, et « ça a mal tourné » (le budget si trois itérations sont nécessaires).
- Une section **« Les paliers d'arrêt »** : à quel moment, et sur quel critère, on arrête si ça ne
  marche pas.
- Une section **« Ce que je n'ai pas trouvé »**.

═══════════════════ FIN DU PROMPT — copier jusqu'ici ═══════════════════

---

## Note interne — ne pas coller

**Pourquoi cette recherche vient en dernier, et pourquoi elle n'est pas une formalité.** Le dépôt a
déjà une estimation de budget pour l'axe « videau appris »
(`docs/etudes/2026-08-19-videau-appris-sans-a-priori.md` §8) qui conclut « des semaines de machine,
pas des années », avec l'observation que **le vrai multiplicateur est le nombre d'itérations**, pas
le coût unitaire. C'est la leçon à réinjecter ici.

**Le fait dur à ne pas perdre de vue** : une campagne de qualification complète coûte 4,9 jours.
Un programme qui demande cinq itérations qualifiées coûte un mois de machine **rien qu'en mesure**.
C'est pour cela que la sous-question 7 — les paliers de repli — est la plus importante du prompt,
et que DS-07 passe en tête de tout le programme.
