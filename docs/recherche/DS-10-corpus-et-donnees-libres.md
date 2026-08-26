# DS-10 — Les données : corpus librement licenciés, et couverture des positions rares

**Vague** 3, **conditionnelle** · **Ne se lance que si** DS-06 conclut qu'un entraînement
**supervisé** (distillation, corpus étiquetés) est la voie retenue — sinon le self-play suffit et
la question ne se pose pas.
**Dépend de** DS-06, DS-07 · **Alimente** DS-14

---

## À injecter avant de lancer — ne pas coller cette section

| Marqueur | À remplir depuis |
|---|---|
| `⟨RECETTE⟩` | DS-06, section « La recette que je lancerais en premier » — ce qu'on étiquette, avec quoi, et combien |
| `⟨CORPUS-DÉJÀ-VUS⟩` | DS-07, tableau des corpus — ce qui a déjà été recensé, pour ne pas le refaire |

---

═══════════════════ DÉBUT DU PROMPT — copier à partir d'ici ═══════════════════

Tu m'aides sur **gammonNet**, un évaluateur de positions de backgammon (réseau de neurones,
recherche expectiminimax, tables de fin de partie exactes) distribué en WebAssembly pour le
navigateur. **Tout ce que nous distribuons est sous licence permissive**, sans clause d'usage : un
module servi à un navigateur est une distribution.

Nous nous apprêtons à entraîner un réseau selon la recette suivante : ⟨RECETTE⟩. Un premier
recensement de corpus a déjà donné ceci : ⟨CORPUS-DÉJÀ-VUS⟩ — ne le refais pas, complète-le.

## La question

**De quelles données peut-on légalement et pratiquement disposer pour entraîner et évaluer un
moteur de backgammon, et comment couvre-t-on les types de position que le self-play ne visite
presque jamais ?**

## Les sous-questions

### A. Les données existantes

1. **Les archives de parties jouées.** Archives de serveurs de jeu (FIBS et ses miroirs, GammonU,
   les serveurs plus récents), collections de matchs de tournoi, bases de matchs de joueurs
   experts. Pour chacune : ce qu'elle contient, son volume, son format, où elle se télécharge, et
   **sous quelles conditions d'utilisation**. Une archive publiquement accessible n'est pas
   nécessairement librement réutilisable — je veux le texte des conditions quand il existe, et la
   mention explicite « conditions introuvables » quand il n'existe pas.
2. **Les ensembles de positions étiquetées.** Positions accompagnées d'équités de rollout, bases
   d'entraînement de moteurs, jeux de test publiés avec des articles. Même exigence de licence.
3. **Les livres d'ouverture.** Rollouts de coups d'ouverture et de réponses publiés par des
   analystes, et leur statut.
4. **Les formats.** `.mat`, `.sgf` tel qu'employé par GNU Backgammon, XGID, GNU Backgammon
   Position ID, `.xg`. Lesquels sont documentés publiquement, et existe-t-il des implémentations
   tierces de lecture sous licence permissive ?

### B. Ce qu'on peut fabriquer soi-même

5. **La couverture par le self-play.** Un moteur qui joue contre lui-même visite très inégalement
   l'espace des positions : les backgames, les positions de conteneur, les grands videaux, les
   scores de match longs sont rares. Que sait-on de l'ampleur de ce déséquilibre au backgammon, et
   quelles techniques sont publiées pour le corriger — départs explorants (tirer la position ou le
   score de départ dans une distribution choisie), *curriculum*, rééchantillonnage par difficulté,
   génération adverse ?
6. **Le risque de l'entraînement sur sa propre distribution.** Un réseau entraîné sur les positions
   que sa propre politique produit devient excellent là où il joue et aveugle ailleurs — et ce mode
   d'échec est **silencieux** : sur une entrée jamais vue, un réseau rend cinq probabilités
   parfaitement plausibles. Quelles parades sont publiées, et comment **détecte-t-on** qu'un
   réseau est hors distribution ?
7. **Le coût d'un étiquetage par rollout.** Pour un corpus de positions étiquetées par des rollouts
   de qualité : combien d'essais par position pour quelle précision, quel coût en temps de calcul,
   et quelles techniques de réduction de variance changent ce compte ?
8. **La composition d'un corpus.** Quelles proportions de contact, course, crash, backgame,
   fin de partie et actions de videau donnent un corpus d'entraînement équilibré ? Est-ce
   documenté quelque part, ou chaque auteur fait-il à son idée ?

## Contraintes

- **La licence est bloquante.** Pour chaque source : le lien, le titulaire des droits, la licence
  ou les conditions, et **une conclusion explicite** en trois valeurs : utilisable en
  entraînement / utilisable en mesure seulement / inutilisable. Un corpus dont les conditions sont
  introuvables est à classer « inutilisable en entraînement » et je préfère le lire clairement.
- **GNU Backgammon nous sert d'oracle de mesure, jamais de source d'apprentissage.** Un corpus
  étiqueté par gnubg est donc, pour nous, un corpus de **mesure** et rien d'autre — même si le
  droit ne s'y oppose pas. C'est une règle interne, et elle tient.
- Les données personnelles éventuelles des archives de parties (pseudonymes, dates, adversaires)
  ne nous intéressent pas et ne doivent pas entrer dans un corpus : signale si une archive en est
  chargée.

## Format du rendu

Un rapport en **français** où :

- **Un tableau maître des corpus**, la pièce principale du rendu :

  | Corpus | Contenu | Volume | Format | Lien | Titulaire | Licence / conditions | Entraînement ? | Mesure ? |

- Chaque affirmation de licence est **citée**, avec l'extrait pertinent quand il est court.
- Une section **« Ce qu'il faut fabriquer nous-mêmes »**, avec le coût estimé.
- Une section **« Les positions que le self-play ne verra pas »**, et comment les produire.
- Une section **« Ce que je n'ai pas trouvé »**.

═══════════════════ FIN DU PROMPT — copier jusqu'ici ═══════════════════

---

## Note interne — ne pas coller

**Le mode d'échec que la sous-question 6 vise est le mode d'échec central du domaine**, et le
dépôt le porte en règle : *« un réseau à qui l'on donne une entrée qu'il n'a jamais vue retourne
cinq probabilités parfaitement plausibles »*. HedgeHog raconte s'être trompé de 0,5 d'équité sur un
cinquième des positions sans aucun signe extérieur. D'où la règle : un modèle qu'un build ne sait
pas évaluer est refusé, jamais approximé.

Un corpus de distillation mal composé reproduit exactement cette faute, en plus silencieux : le
réseau distillé sera excellent là où le corpus l'a mené et faux ailleurs, et **aucune mesure faite
sur le même corpus ne le montrera**. Le retour de DS-10 doit donc servir autant à composer le
corpus qu'à composer **le corpus de mesure, disjoint**, qui dira si le premier était biaisé.

**Précédent interne à réutiliser** : le corpus de distillation du réseau d'élagage (800 000 lignes)
a été mesuré sur une graine **distincte** de celle qui l'a produit — « mesurer le petit réseau sur
les positions qui l'ont entraîné mesurerait sa mémoire ». Cette discipline est déjà acquise ici,
il faut la garder.
