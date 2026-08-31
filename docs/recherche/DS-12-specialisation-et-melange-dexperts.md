# DS-12 — Spécialisation par classe, ensembles, mélange d'experts : plus de qualité à MACs égaux

**Vague** 2 · **Dépend de** DS-02 et DS-03 · **Alimente** DS-04, DS-14
**Ce qu'elle décide** : si l'on peut acheter de la qualité **sans** payer de vitesse, en découpant
le problème plutôt qu'en agrandissant le réseau — la seule forme de gain compatible avec les deux
exigences de l'objectif.

---

## À injecter avant de lancer — ne pas coller cette section

**Injections faites le 2026-08-27**, depuis le retour DS-02. **Le prompt est prêt à lancer tel
quel.**

| Marqueur | Rempli depuis |
|---|---|
| `CLASSES-GNUBG` | DS-02, sections A1–A3 : trois réseaux + bases exactes, tailles et frontières |
| `DISCONTINUITÉS` | DS-02, A3 : « transition gaps » déclarés par l'auteur, jamais chiffrés |
| `FAIBLESSES` | DS-02, D11 : backgames/crashed, bear-off avec contact |

---

═══════════════════ DÉBUT DU PROMPT — copier à partir d'ici ═══════════════════

Tu m'aides sur **gammonNet**, un évaluateur de positions de backgammon : réseau de neurones,
recherche expectiminimax, table d'équité de match, tables de fin de partie exactes. Cible
navigateur (WebAssembly, y compris téléphone) et natif.

**Notre situation.** **Un seul réseau** couvre toutes les positions : 196 entrées denses →
512 → 512 → 256 → 128 → 5 sorties, ~527 000 MACs par évaluation. GNU Backgammon, lui, emploie
**trois réseaux de position** — contact (250 entrées → 128 cachées → 5 sorties, ~32 640 MACs),
crashed (même structure, un camp ayant au plus 6 pions « actifs » hors des points 1 et 2 — seuil
que son auteur qualifie lui-même d'arbitraire, choisi non cyclique) et course (214 entrées → 128
cachées présumées → 5 sorties) — plus des bases de fin de partie exactes qui tronquent la
recherche, et de petits réseaux d'élagage (~10 neurones cachés) aux nœuds internes. Ce qui est
documenté sur les discontinuités à ses frontières de classe : leur existence est **reconnue par
ses auteurs** (« transition gaps », qui motivent le critère de frontière non cyclique et l'ajout
de « limiting cases » à l'entraînement), mais **aucune mesure de leur ampleur n'a jamais été
publiée**. Les classes où sa qualité est documentée comme faible : les **backgames et la classe
crashed** (« pathetic play in many backgame situations », dixit son auteur principal, chaque
réseau n'étant entraîné que sur sa propre distribution), et le **bear-off avec contact**.

**La contrainte qui rend la question intéressante.** Nous voulons **plus de qualité sans plus de
coût par évaluation**. Agrandir le réseau est exclu : le budget vient du navigateur d'un
téléphone, et doubler les paramètres double le coût de chaque évaluation, donc le coût d'une
décision 2-ply chez l'utilisateur. En revanche, **plusieurs réseaux spécialisés dont un seul est
consulté par évaluation** ne coûtent rien de plus par évaluation — seulement de la mémoire et un
aiguillage.

C'est la seule forme de gain de qualité qui soit gratuite en temps de calcul. Je veux savoir si
elle marche.

## La question

**La spécialisation d'une fonction de valeur par classe de position, ou par mélange d'experts,
achète-t-elle de la qualité à budget de calcul par évaluation constant — et à quelles conditions ?**

## Les sous-questions

1. **La preuve dans les jeux.** Quels moteurs emploient plusieurs réseaux spécialisés, et quel
   gain **mesuré** en rapportent-ils ? Au backgammon (GNU Backgammon et ses classes et
   ses ensembles ou son mélange d'experts, d'autres), et ailleurs (phases de partie aux échecs,
   réseaux de fin de partie). Je cherche des ablations chiffrées : « un réseau contre trois, même
   nombre total de MACs par évaluation, tel écart ».
2. **Les frontières, et leur coût.** Un aiguillage dur crée une **discontinuité** : deux positions
   voisines évaluées par deux réseaux différents peuvent rendre des valeurs incohérentes, et une
   recherche qui compare des feuilles de part et d'autre de la frontière compare deux échelles.
   Quelle est l'ampleur documentée de ce problème, et quelles parades sont publiées — mélange
   pondéré près de la frontière, réentraînement conjoint, calibration croisée, chevauchement des
   domaines ?
3. **Quelles classes découper au backgammon ?** Au-delà de contact / crash / course : blitz,
   backgame, jeu de conteneur, prime contre prime, course avec contact résiduel, sortie de pions.
   Y a-t-il des travaux qui **mesurent** où l'erreur d'un réseau unique se concentre, par type de
   position ? C'est la sous-question qui dit **où** spécialiser, et je n'ai aucune donnée dessus.
4. **Le mélange d'experts, version apprise.** Plutôt qu'un aiguillage écrit à la main, un routage
   appris. Que sait-on de son application à de **petits** modèles (moins d'un million de
   paramètres) — le coût du routeur, la stabilité de l'entraînement, le risque d'effondrement vers
   un seul expert ? Y a-t-il des résultats hors du domaine des grands modèles de langage, où la
   littérature est abondante mais peu transposable ?
5. **Les ensembles.** Faire la moyenne de plusieurs réseaux améliore en général la calibration et
   décorrèle les erreurs — mais multiplie le coût par évaluation, ce qui est exclu chez nous. Sauf
   dans un cas : **distiller un ensemble dans un réseau unique**. Quel gain une telle distillation
   conserve-t-elle, mesuré ? C'est peut-être la voie la plus intéressante de cette recherche : la
   qualité d'un ensemble au prix d'un seul réseau.
6. **Le partage de tronc.** Un tronc commun et plusieurs têtes spécialisées : que gagne-t-on par
   rapport à des réseaux entièrement séparés, à budget égal ? Quelle largeur de goulot faut-il pour
   que les têtes soient utiles ?
7. **Le coût en mémoire et en téléchargement.** Trois réseaux, c'est trois fois les poids à
   télécharger. Notre réseau pèse ~2 Mio en `float32`. Quels sont les usages en la matière — les
   moteurs spécialisés partagent-ils des couches, quantifient-ils différemment selon la classe,
   chargent-ils à la demande ?

## Contraintes

- **Le critère est la précision par MAC, sur un téléphone.** Une architecture qui n'améliore la
  qualité qu'en augmentant le calcul par évaluation ne nous sert pas. Signale explicitement, pour
  chaque piste, ce qu'elle coûte **par évaluation** et non en tout.
- Tout artefact signalé arrive **avec sa licence et son lien**. Hors périmètre, y compris comme
  source d'entraînement : poids de GNU Backgammon (GPL-3), tout réseau sous clause non commerciale (licence non
  confirmée, réputée non commerciale). bgsage est sous MPL-2.0 : ses idées documentées sont
  recevables, mais ne me recommande pas d'en copier du code. Nous pouvons en revanche distiller
  **notre propre** réseau, et nous le faisons déjà pour notre réseau d'élagage.
- Pas de transcription de code ni de constantes réglées à la main.

## Format du rendu

Un rapport en **français** où :

- Chaque affirmation porte une étiquette : `[MESURE]` (ablation publiée), `[DÉCLARÉ]`,
  `[HYPOTHÈSE]`, `[FOLKLORE]`.
- Chaque source porte son lien et sa date de consultation.
- **Un tableau des découpages candidats** :

  | Découpage | Nombre d'experts | Coût par évaluation | Gain attendu | Risque de discontinuité | Preuve publiée |

- Une section **« Le découpage que je testerais en premier »**, avec le protocole : quelles
  classes, comment on aiguille, comment on entraîne, et **quelle mesure dirait en quelques heures
  si ça marche**.
- Une section **« Ce que je n'ai pas trouvé »**.

═══════════════════ FIN DU PROMPT — copier jusqu'ici ═══════════════════

---

## Note interne — ne pas coller

**Pourquoi cette recherche est peut-être la meilleure affaire du programme.** Les deux exigences de
l'objectif — plus de qualité, pas moins de vitesse — sont en tension partout ailleurs. La
spécialisation est le seul mécanisme qui les satisfait toutes les deux : *n* réseaux dont un seul
est consulté coûtent, par évaluation, exactement ce que coûte un réseau.

**Trois faits du dépôt à confronter au retour :**

1. Nous savons déjà distiller notre propre réseau : le réseau d'élagage 196 → 32 → 5 en est issu,
   avec un corpus de 800 000 positions étiquetées par les sorties brutes du grand réseau, sur des
   positions produites par notre propre moteur. **L'atelier de distillation existe.**
2. Nos mesures distinguent déjà **contact** et **course** et rendent des chiffres très différents
   (le réseau d'élagage met le meilleur coup dans son top-5 dans 94,2 % des décisions de contact,
   mais seulement 83,6 % en course). L'idée que le problème n'est pas homogène est donc déjà
   étayée chez nous.
3. Le point 5 du prompt — distiller un ensemble dans un réseau unique — est la seule voie connue
   pour améliorer la qualité **sans toucher au coût d'inférence ni à l'architecture**. Si le retour
   la chiffre, c'est l'expérience la moins risquée du programme.
