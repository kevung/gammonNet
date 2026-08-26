# DS-06 — Entraîner le réseau *pour* la recherche, et non pour le 0-ply

**Vague** 2 · **Dépend de** DS-01 et DS-02 · **Alimente** DS-10, DS-14
**Ce qu'elle décide** : l'hypothèse H1 — notre avantage s'annule sous recherche parce que le
réseau n'a jamais été entraîné à être bon sous recherche. C'est la recherche la plus proche du
cœur du problème.

---

## À injecter avant de lancer — ne pas coller cette section

| Marqueur | À remplir depuis |
|---|---|
| `⟨DÉJÀ-TENTÉ⟩` | DS-01 — ce qui a déjà été tenté au backgammon en matière d'entraînement sous recherche, et avec quel résultat. Deux lignes suffisent ; l'objectif est d'éviter de faire chercher deux fois la même chose |
| `⟨ENTRAÎNEMENT-GNUBG⟩` | DS-02, sous-question 9 — comment les poids de gnubg ont été obtenus (TD puis supervision sur rollouts ?) |

Si DS-01 rapporte que quelqu'un a **déjà** publié une mesure d'un réseau distillé de recherche au
backgammon, remplace la sous-question 1 par « reproduis le protocole exact de ce travail et dis-moi
ce qui manque pour le rejouer chez nous ».

---

═══════════════════ DÉBUT DU PROMPT — copier à partir d'ici ═══════════════════

Tu m'aides sur **gammonNet**, un évaluateur de positions de backgammon : réseau de neurones,
recherche expectiminimax, table d'équité de match, tables de fin de partie exactes. Cible
navigateur (WebAssembly, y compris téléphone) et natif.

**Le fait mesuré qui est le sujet de cette recherche.** Sur 2 400 décisions de contact, à
profondeur égale, avec deux arbitres indépendants :

| profondeur | notre avantage sur GNU Backgammon, par décision |
|---|---|
| 0-ply | **+0,00247** [+0,00186 ; +0,00310] |
| 1-ply | +0,00154 [+0,00104 ; +0,00207] |
| 2-ply | **+0,00007 [−0,00005 ; +0,00019]** — l'intervalle contient zéro |

**Notre réseau est meilleur que le sien, et la recherche efface cet avantage.** Le taux de
désaccord entre les deux moteurs tombe de 20,8 % à 9,5 % quand on cherche plus profond : les deux
convergent. Nous avons aussi vérifié que ce n'est pas un artefact de notre filtrage de coups
(resserrer la garde change 1,1 % des coups et ne coûte rien de mesurable), et qu'un ply de plus ne
rachète rien (+0,00022, dans le bruit, pour 15 fois plus de calcul).

**Notre réseau a été entraîné entièrement en self-play**, par TD(0) sur un petit réseau puis
expansion progressive de l'architecture, avec une phase finale de raffinement par « backups de
Bellman exacts » : au lieu de `cible = 1 − V(suivant)` sur un seul jet,
`cible = E_dés[max_coup(1 − V(suivant))]` sur les 21 jets. Autrement dit, il a été entraîné à être
bon **à profondeur 0**, avec au mieux un ply de lissage. GNU Backgammon, lui, ⟨ENTRAÎNEMENT-GNUBG⟩.
Une recherche préalable a établi ceci sur ce qui a déjà été tenté au backgammon : ⟨DÉJÀ-TENTÉ⟩.

L'auteur du modèle que nous employons écrit lui-même que la suite évidente est *« des méthodes qui
cherchent plus profond et qui optimisent le modèle pour la recherche »*, et observe que son
avantage sur gnubg se réduit avec la profondeur, en suggérant que *« les réseaux de base de gnubg
sont davantage réglés pour la recherche profonde que les nôtres »*.

## La question

**Comment entraîne-t-on une fonction de valeur pour qu'elle soit bonne *sous recherche*, et non
seulement à profondeur zéro ?**

## Les sous-questions

1. **Le phénomène a-t-il un nom et une littérature ?** Le fait qu'un réseau supérieur à profondeur
   0 cesse de l'être sous recherche. Cherche du côté de l'interaction évaluation-recherche dans
   les jeux : aux échecs (« une évaluation plus forte ne donne pas toujours un moteur plus fort »),
   au go, dans la littérature sur l'apprentissage par différence temporelle avec recherche
   (Baxter, Veness, Silver, Tesauro). **Quelles explications sont proposées, et lesquelles sont
   mesurées ?** Les candidates que j'ai en tête : erreurs corrélées le long d'une branche, biais de
   l'opérateur `max` sur des estimations bruitées, mauvaise calibration aux extrêmes, différence
   entre bien classer les coups et bien estimer une valeur.
2. **La distillation de recherche.** Entraîner le réseau sur les sorties d'une recherche profonde
   ou d'un rollout, au lieu de sa propre valeur. C'est le principe d'AlphaZero et de ses
   descendants. Que sait-on de son application à un jeu à **nœuds de hasard** ? Quels résultats
   publiés, et quelles précautions (le nombre d'échantillons nécessaires, le risque de renforcer
   les erreurs de sa propre recherche) ?
3. **Les cibles d'entraînement.** Compare, avec les preuves disponibles : cible TD(0) à un jet,
   backup exact sur les 21 jets, cible à n pas, cible de rollout tronqué, cible de rollout complet,
   cible « valeur de la recherche à 2-ply ». Laquelle produit le meilleur réseau **sous recherche
   à 2-ply**, et est-ce mesuré quelque part ?
4. **Le réseau de politique.** Les moteurs modernes apprennent aussi une **distribution sur les
   coups**, qui sert à ordonner et à élaguer la recherche. Nous n'en avons pas : nous trions avec
   un petit réseau de valeur distillé. Que gagnerait une vraie tête de politique, et est-ce chiffré
   quelque part pour un jeu à hasard ? Comment définit-on une politique sur un espace de coups qui
   dépend du jet ?
5. **La cohérence des erreurs.** Existe-t-il des techniques explicites pour **décorréler** les
   erreurs d'un réseau le long d'une branche de recherche — ensembles, abandon (*dropout*) au
   moment de l'évaluation, apprentissage de valeur distributionnelle (C51, QR-DQN), régularisation
   de la calibration ? Quelqu'un a-t-il montré qu'un réseau **mieux calibré** cherche mieux ?
6. **Les têtes auxiliaires.** Entraîner le réseau à prédire, en plus des cinq probabilités, des
   quantités utiles à la recherche : la **volatilité** (l'écart-type de l'équité au prochain point
   de décision, calculable exactement en développant les 21 jets), l'incertitude de sa propre
   estimation, la profondeur restante utile. Que sait-on de l'apport des têtes auxiliaires sur la
   qualité de la représentation, dans les jeux ?
7. **Le coût.** Pour chaque recette que tu recommandes, donne l'ordre de grandeur du calcul
   nécessaire : nombre de positions étiquetées, coût d'un étiquetage, nombre d'itérations. Notre
   machine est un 16 cœurs / 32 fils avec 94 Gio et un GPU optionnel. Une recette qui demande un
   parc de machines n'est pas pour nous, et je préfère le savoir avant.

## Contraintes

- **GNU Backgammon nous sert d'oracle de mesure, jamais de source d'apprentissage.** C'est une
  règle que nous nous sommes donnée, plus stricte que le droit : distiller ses évaluations dans
  notre réseau est exclu, même si la FSF considère que la sortie d'un programme n'est en général
  pas couverte par le droit d'auteur sur son code. Une recommandation qui repose là-dessus est
  inutilisable pour nous.
- Tout artefact signalé arrive **avec sa licence et son lien**. Hors périmètre : poids gnubg
  (GPL-3), réseaux HedgeHog (clause non commerciale), bgsage (AGPL-3).
- **La taille du réseau est contrainte par le navigateur d'un téléphone**, jamais par la machine
  d'entraînement. Une recette qui n'améliore la qualité qu'en agrandissant le réseau ne nous sert
  pas ; je cherche une meilleure qualité **à MACs constants**.

## Format du rendu

Un rapport en **français** où :

- Chaque affirmation porte une étiquette : `[MESURE]`, `[DÉCLARÉ]`, `[HYPOTHÈSE]`, `[FOLKLORE]`.
- Chaque source porte son lien et sa date de consultation.
- **Un tableau des recettes** :

  | Recette | Ce qu'elle change | Preuve publiée | Gain attendu sous recherche | Coût de calcul | Risque |

- Une section **« La recette que je lancerais en premier »**, avec le protocole assez précis pour
  être implémenté : ce qu'on étiquette, avec quoi, combien, comment on entraîne, et **quelle
  mesure dirait au bout de quelques heures si ça marche**. Ce dernier point est essentiel : nous
  avons un banc qui mesure la perte d'équité par décision à profondeur égale contre deux arbitres,
  et une expérience qui ne s'y branche pas ne nous apprendra rien.
- Une section **« Ce que je n'ai pas trouvé »**.

═══════════════════ FIN DU PROMPT — copier jusqu'ici ═══════════════════

---

## Note interne — ne pas coller

**C'est la recherche la plus importante du programme, et la plus risquée.** Si elle revient avec
une recette validée ailleurs, elle ouvre la phase 4 (T41, « optimiser le modèle pour la
recherche ») avec un protocole plutôt qu'avec une intention. Si elle revient avec « personne ne
sait », le programme se replie sur la vitesse (DS-04, DS-05) et le videau (DS-08), qui sont des
gains plus modestes mais tenus.

**Le garde-fou à ne pas relâcher au retour.** La phase 4 est fermée depuis T35, et `CLAUDE.md` dit
de ne pas l'ouvrir par enthousiasme. Un retour prometteur n'est pas une ouverture de chantier : la
règle du dépôt est qu'une expérience à tronc gelé, mesurable en heures, précède tout engagement de
semaines de calcul. La sous-question 7 et la dernière ligne du format de rendu sont là pour rendre
ce filtre applicable.
