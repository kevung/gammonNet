# DS-12 — Spécialisation par classe, ensembles, mélange d'experts — retour

**Date de la recherche** : 2026-08-26 · **Outil** : Claude, recherche approfondie
**Prompt** : `docs/recherche/DS-12-specialisation-et-melange-dexperts.md`, version injectée du 2026-08-27

> **Ce que ce retour décide** : si l'on peut acheter de la qualité sans payer de vitesse, en
> découpant le problème plutôt qu'en agrandissant le réseau.
> **Ce qu'il conclut** : l'aiguillage dur race/crashed/contact est **mesuré neutre** à
> entraînement égal (Whittington : le gain apparent venait du recuit du taux d'apprentissage) ;
> ce qui marche à MACs constants, dans l'ordre — (1) la **distillation d'un enseignant fort dans
> le réseau unique** (+53,4 % sur 40 000 parties, même 256×128, même coût par coup — converge
> avec DS-06), (2) si elle plafonne, le **tronc partagé + têtes de sortie par bucket de
> pip-count** façon NNUE (52,6 %, search-robuste, aucune classe affamée de données), jamais des
> réseaux séparés ; et le préalable est le **Test C : produire la carte d'erreur par classe de
> position**, que personne n'a jamais publiée. Toute mesure doit varier une seule chose à la fois
> (le piège du calendrier d'apprentissage) et survivre au 2-ply.
> **Ce qu'il ne tranche pas** : l'ampleur des discontinuités de frontière (reconnues par gnubg,
> chiffrées nulle part — lacune centrale), la largeur de goulot minimale d'un tronc partagé, le
> routage appris top-1 contre l'aiguillage manuel (jamais comparés dans un jeu), et
> l'architecture de HedgeHog (la prémisse « ensembles » n'est pas confirmée). Nuance de licence :
> `sage-engine-server` est AGPL-3.0, distinct de la lib `bgsage` MPL-2.0.

---
# La spécialisation par classe de position achète-t-elle de la qualité à budget de calcul par évaluation constant ?

## TL;DR
- **Oui, sous conditions strictes — et le meilleur pari pour gammonNet n'est pas l'aiguillage dur : c'est la distillation d'un enseignant/ensemble fort dans le réseau unique existant.** C'est le seul mécanisme dont le gain est prouvé MESURÉ *à coût par évaluation strictement constant* (cas backgammon récent : +53,4 % sur 40 000 parties, même architecture 256×128, même coût par coup).
- **L'aiguillage dur (plusieurs réseaux, un seul consulté) est « gratuit » en calcul par évaluation, mais son gain propre est faible et non isolé dans la littérature.** Au backgammon, un développeur récent a MESURÉ que le routage race/crashed/contact était « neutre » à entraînement égal, le gain apparent venant du recuit du taux d'apprentissage, pas du routage. En revanche, le **partage de tronc + têtes de sortie multiples** (bucketing à la NNUE, discriminateur pip-count) a montré, lui, un gain net et search-robuste (52,6 %).
- **Les frontières de classe créent une discontinuité réelle, mais aucune mesure de son ampleur n'a jamais été publiée**, au backgammon comme ailleurs — c'est la principale lacune de la littérature, et elle vous concerne directement.

## Key Findings

1. **Le gain « gratuit » d'un aiguillage dur est réel mais petit et rarement isolé.** [MESURE][DÉCLARÉ] Le seul jeu de mesures propres vient d'un moteur de backgammon (Backgammon-NN de Chris Whittington) qui a précisément tenté ce que vous envisagez, avec le même encodage Tesauro que vous.
2. **Le partage de tronc + têtes de sortie multiples (bucketing à la NNUE) est supérieur à des réseaux séparés à budget de données égal**, car aucune tête n'est privée de données. [MESURE]
3. **La distillation d'un ensemble/enseignant fort dans un réseau unique conserve l'essentiel du gain à coût par évaluation identique.** C'est la voie que vous pressentez, et c'est la mieux étayée. [MESURE]
4. **La spécialisation ne « crée » pas de qualité : elle évite la dilution des données.** Un réseau unique suffisamment profond peut égaler des réseaux séparés si sa capacité et son signal d'entraînement ne sont pas saturés. [MESURE]
5. **Où découper : contact (jeu de milieu), crashed et backgame sont les classes documentées comme faibles.** [DÉCLARÉ][FOLKLORE] Aucune étude ne publie de carte chiffrée de l'erreur par type de position pour un réseau unique — lacune majeure.

## Details

### Sous-question 1 — La preuve dans les jeux

**Backgammon.**

*GNU Backgammon* utilise trois réseaux (contact, crashed, race) plus des bases de fin de partie. [DÉCLARÉ] Le manuel officiel le confirme (https://www.gnu.org/software/gnubg/manual/allabout.pdf, consulté le 26/08/2026 ; https://gnubg.readthedocs.io/en/latest/concepts.html, 26/08/2026). Aucune ablation « un réseau contre trois, mêmes MACs » n'a jamais été publiée par le projet. L'auteur Joseph Heled déclare que le critère de frontière crashed est « a celebration of arbitrary decisions » choisi non cyclique — « positions resulting from a crashed position should be crashed. When this is violated, performance deteriorates since each net is trained only on its own kind of positions » — et que « GNUbg pathetic play in many backgame situations leaves it open to abuse from humans » (liste bug-gnubg, 08/02/2012, https://lists.gnu.org/archive/html/bug-gnubg/2012-02/msg00022.html, consulté le 26/08/2026). [DÉCLARÉ] La licence des poids est GPL-3 : **hors périmètre** même comme source d'entraînement.

*Backgammon-NN (Chris Whittington)* est le cas le plus directement pertinent, car il a mené les expériences que vous envisagez avec des mesures head-to-head à coût par évaluation constant (https://whittingtonchess.com/backgammon-report, consulté le 26/08/2026) :
- **Split de phase (réseaux contact/race séparés)** : le réseau race était un gain 0-ply réel (+0,25 ppg) mais « n'a pas aidé le moteur de rollout », donc livré seulement comme adversaire optionnel. [MESURE] Verdict de l'auteur : « partial ». Le rapport localise précisément le déficit vs GNU BG : « A phase breakdown locates the gap in contact play; races and the bear-off are near-even ».
- **Bucketing de sortie (un corps partagé, 8 têtes par pip-count, softmax-6, style NNUE)** : **52,6 % en head-to-head** contre le champion en place. [MESURE] Shipé en v1.7.0.
- **Routage class-aware (race/crashed/contact × pip, 12 têtes, classification gnubg)** : **55,8 % @0-ply**, MAIS l'auteur conclut : « at equal training the routing was neutral; the gain came from a learning-rate-decay tail — a training-recipe win, not a routing win, and it barely survives search (52 % @1-ply) ». [MESURE] C'est le résultat le plus important pour vous : **le routage lui-même n'a rien apporté ; le gain apparent venait du calendrier d'apprentissage.** L'auteur en tire un diagnostic explicite : « Routing was neutral and richer features were negative… That points squarely at training-signal quality: we train on noisy single-game outcomes, while gnubg trains on low-variance rollout labels. »
- **Distillation d'un enseignant externe fort (GNU BG 2-ply, 22,5 M positions)** : le réseau distillé **256×128 — même architecture et même coût par coup que celui qu'il remplace** — bat le champion self-play **53,4 % sur 40 000 parties (z +13,70)**, et atteint la parité avec GNU BG à profondeur égale. [MESURE] Un réseau 2,7× plus grand était « statistiquement indiscernable » à movetime égal → l'auteur garde le petit. C'est la démonstration directe que **la qualité s'achète par le signal d'entraînement, pas par la capacité, à coût constant.**

*wildbg* (Rust, open-source) utilise deux réseaux (contact + race). [DÉCLARÉ] Son README indique : « As of January 2024, it reaches an error rate of roughly 5.9 for 1-pointers when being analyzed with GnuBG 2-ply » (https://github.com/carsten-wenderdel/wildbg, consulté le 26/08/2026) ; l'auteur Carsten Wenderdel a par ailleurs situé le moteur à « roughly 1800 ELO or an error rate mEMG of roughly 7.5 » (bug-gnubg, 22/11/2023). Le repo wildbg-training documente des gains incrémentaux du type « 292 epochs, improvement of roughly 1.5 millipoints over #18 » (https://github.com/carsten-wenderdel/wildbg-training, consulté le 26/08/2026). [MESURE] Note historique utile : à l'itération 9, séparer contact et race a d'abord fait « perdre beaucoup de backgammons car le réseau contact était trop optimiste » — illustration d'un effet de frontière/distribution. [MESURE]

*bgsage / Open Sage (Mark Higgins)* : « stage9 model (19 neural networks, backgame-aware pair strategy) » + base de bear-off une face. [DÉCLARÉ] (https://github.com/customation/sage-engine-server, https://github.com/markbgsage/bgsage, consulté le 26/08/2026.) C'est l'exemple le plus poussé de découpage multi-réseaux, avec une stratégie de paire spécifique aux backgames. **Attention licence** : le serveur `sage-engine-server` est AGPL-3.0 ; la lib `bgsage` est distribuée sur PyPI. Vous mentionnez MPL-2.0 pour bgsage — dans tous les cas : **idées documentées recevables, ne pas copier de code**.

*HedgeHog* : outil d'analyse/jeu par réseau de neurones dans le navigateur (https://hedgehog-bg.com/, consulté le 26/08/2026). Je n'ai trouvé **aucune documentation technique publique** confirmant qu'il utilise un ensemble ou un mélange d'experts, ni de mesure. [HYPOTHÈSE non confirmée] Licence non confirmée, réputée non commerciale : **hors périmètre**.

*TD-Gammon, Jellyfish, Snowie, XG, BGBlitz* : aucune ablation publiée « un réseau vs plusieurs, mêmes MACs ». XG est la référence de rollouts de la communauté mais fermé/propriétaire. [DÉCLARÉ]

**Échecs (transposable car même idée : sous-réseau sélectionné par un discriminateur bon marché).**

*Stockfish NNUE — LayerStacks / output buckets.* C'est l'analogue exact de votre question : après la première couche (l'accumulateur), les paramètres sont **commutés dynamiquement selon le nombre de pièces** (8 buckets via `(piece_count-1)/4`), et **un seul layer stack est évalué par position** → coût par évaluation quasi constant. La doc nnue-pytorch le dit : « only one subnetwork is evaluated… no or marginal speed loss ». [DÉCLARÉ] (https://github.com/official-stockfish/nnue-pytorch/blob/master/docs/nnue.md, https://chessprogramming.org/NNUE, consulté le 26/08/2026.)

Point crucial sur les chiffres : **aucun test fishtest n'isole le gain Elo du bucketing seul.** La PR #3474 (auteur Sopel97 / Tomasz Sobczyk, tweaks de recherche par Joost VandeVondele, mai 2021, https://github.com/official-stockfish/Stockfish/pull/3474) a introduit les 8 layer stacks + 8 buckets PSQT *en même temps* qu'une nouvelle architecture (HalfKAv2), un nouveau trainer et des changements de recherche. Les Elo mesurés — **21,74 ±3,4 en STC (10s+0,1s, 10 000 parties)** et **5,85 ±1,7 en LTC (60s+0,6s, 20 000 parties)** (liens fishtest dans la PR) — décrivent **le paquet entier, pas le bucketing isolé**. [MESURE, mais non isolée] Les auteurs ont même scindé le merge en deux commits « as only the combination of the things have been tested on fishtest ». La caractérisation « gain quasi gratuit en calcul » est, elle, étayée par la source primaire (texte de la PR : « only one subnetwork is evaluated for any position, no or marginal speed loss ») et le wiki (« LayerStacks… a generalization of the traditional output buckets »). [DÉCLARÉ]

Pour situer l'ordre de grandeur de NNUE dans son ensemble (et non du bucketing) : le blog officiel « Introducing NNUE Evaluation » (https://stockfishchess.org/blog/2020/introducing-nnue-evaluation/, 2020) mesurait « > 80 Elo on fishtest » — précisément **92,77 ±2,1 en STC (10+0,1, 60 000 parties)** — et Chess.com titrait « Stockfish Absorbs NNUE, Claims 100 Elo Point Improvement », en notant que Stockfish+NNUE « can look at more than 50,000,000 positions per second which is half the speed of traditional Stockfish » (https://www.chess.com/news/view/stockfish-absorbs-nnue-100-elo, 2020). [MESURE / DÉCLARÉ] Ces chiffres concernent NNUE vs éval classique, **pas** le bucketing.

*Leela Chess Zero* : pas de bucketing par phase dans le réseau ; utilise des tablebases Syzygy externes (analogue à vos bases de fin de partie exactes). L'étude ACG 2021 « On the Road to Perfection? » (https://icga.org/wp-content/uploads/2021/11/ACG_2021_paper_13.pdf, consulté le 26/08/2026) mesure les erreurs de Lc0 vs tablebases 3-4 pièces mais ne teste pas la spécialisation par sous-réseau. [MESURE, hors sujet direct]

### Sous-question 2 — Les frontières et leur coût

**L'ampleur du problème n'est mesurée nulle part.** [DÉCLARÉ] Les auteurs de GNU BG reconnaissent les « transition gaps » et y répondent par (a) le critère non cyclique (Heled, 02/2012) et (b) l'ajout de « limiting cases » à l'entraînement. Aucune mesure de l'amplitude de la discontinuité n'existe. Backgammon-NN observe empiriquement l'effet inverse (le split contact/race a d'abord dégradé le jeu de backgammon par optimisme du réseau contact) sans le chiffrer comme discontinuité de frontière.

**L'effet sur la recherche.** Votre intuition est correcte et c'est le vrai risque : un expectiminimax qui compare des feuilles de part et d'autre d'une frontière compare deux échelles calibrées séparément. La littérature générale sur la calibration confirme que ce risque est réel : Guo, Pleiss, Sun & Weinberger (« On Calibration of Modern Neural Networks », ICML 2017, PMLR 70:1321-1330, arXiv:1706.04599) montrent que « modern neural networks, unlike those from a decade ago, are poorly calibrated » et que « depth, width, weight decay, and Batch Normalization are important factors influencing calibration » — donc des réseaux entraînés séparément, avec des profondeurs/régularisations différentes, ne sont pas mutuellement calibrés par défaut. [MESURE, domaine général] Aucune étude ne quantifie l'effet spécifique d'une discontinuité de fonction de valeur sur un expectiminimax de backgammon. [Lacune]

**Parades publiées :**
- *Entraînement sur limiting cases / chevauchement de domaines* : pratiqué par GNU BG. [DÉCLARÉ]
- *Critère de frontière non cyclique* : garantit qu'on ne fait pas d'aller-retour entre classes en cours de recherche. [DÉCLARÉ] Directement applicable.
- *Têtes multiples sur tronc partagé (soft partitioning)* : la frontière devient une commutation de tête après un tronc commun, donc les deux côtés partagent la même représentation et une échelle largement commune → discontinuité fortement atténuée par construction. C'est l'argument du bucketing NNUE et des HME de Jordan & Jacobs (1994), où le gating induit un « smoothed planar partitioning » (partition lissée) plutôt qu'une frontière dure. [MESURE, domaine général]
- *Mélange pondéré près de la frontière* : c'est exactement ce que fait un gating softmax appris (mélange d'experts) — la sortie est une combinaison continue près de la frontière. [DÉCLARÉ]

### Sous-question 3 — Quelles classes découper au backgammon ?

**Ce qui est documenté comme faible** (donc candidat à spécialisation), par déclaration d'auteurs et folklore, pas par carte d'erreur chiffrée :
- **Backgames** : « pathetic play in many backgame situations » (Heled, GNU BG). [DÉCLARÉ] La doc All About GNU note que le 0-ply « may fail to make the most of the possibilities » en backgame (http://gnubg.org/win32/All%20About%20GNU%20v2.pdf). [DÉCLARÉ] Wikipedia (Rollout) : « if a computer AI's backgame strategy was weak, rollouts starting in a backgame position will skew the equity ». [FOLKLORE/DÉCLARÉ]
- **Classe crashed** : « almost all of crashed net » listé comme faiblesse dans les archives bug-gnubg (https://www.mail-archive.com/bug-gnubg@gnu.org/msg01602.html). [DÉCLARÉ]
- **Jeu de conteneur (containment/holding game)** : listé explicitement comme faiblesse (« containment play ») dans le même message d'archive. [DÉCLARÉ]
- **Bear-off avec contact** : identifié par vous ; cohérent avec le fait que GNU BG bascule sur des bases exactes hors contact mais garde le réseau en contact.
- **Gammon-leaking en contact** : Backgammon-NN a MESURÉ que la fuite de gammons est « a contact-evaluation weakness, not a race-play bug » (un réseau plus profond l'a réduite de ~10 points). [MESURE]

**La carte chiffrée manque.** [Lacune] Il n'existe aucune étude publique qui prenne un réseau unique et mesure la concentration de son erreur (vs rollouts profonds) par catégorie — blitz, prime-vs-prime, holding, backgame, course avec contact résiduel, bear-off avec/sans contact. Les discussions de forums (bgonline, rec.games.backgammon) parlent d'overtraining et de « bot bias » sans tableau d'erreur par classe. C'est précisément la donnée que vous devez générer vous-même (voir protocole).

### Sous-question 4 — Le mélange d'experts appris

**Origines et applicabilité aux petits modèles :** Jacobs/Jordan/Nowlan/Hinton (« Adaptive mixtures of local experts », Neural Computation 1991) et Jordan & Jacobs (« Hierarchical mixtures of experts and the EM algorithm », Neural Computation 1994, DOI 10.1162/neco.1994.6.2.181) ont conçu le MoE pour la **régression et le contrôle** (dynamique robotique) avec des experts *linéaires généralisés* — donc à très petite échelle, exactement votre régime <1 M paramètres. [MESURE] Le gating y induit une partition lissée de l'espace d'entrée. C'est la littérature la plus transposable pour vous, bien plus que le MoE des LLM.

**Coût du routeur :** un gating softmax sur 196 entrées vers K experts coûte 196×K MACs — négligeable devant vos 527 000 MACs. [HYPOTHÈSE chiffrée, calcul direct] Mais **attention** : un MoE *dense* (softmax pondérant tous les experts) évalue TOUS les experts → K× le coût par évaluation, ce qui est exclu. Seul un routage *dur/top-1* (argmax) préserve le coût constant, et il faut alors gérer la non-différentiabilité du routage.

**Effondrement d'experts (expert collapse) et équilibrage de charge :** problème central et bien documenté (NVIDIA glossary ; arXiv:2507.11181 ; https://apxml.com/courses/mixture-of-experts-advanced-implementation, consulté le 26/08/2026). Sans perte d'équilibrage, le routeur envoie tout à un sous-ensemble d'experts, les autres deviennent des « dead parameters ». [MESURE, domaine LLM] Pour vous, le risque est atténué si vous **fixez le routage** par un discriminateur bon marché (classe de position à la GNU BG, pip-count à la NNUE) au lieu de l'apprendre — vous perdez l'adaptativité mais éliminez collapse et instabilité.

**Verdict :** le routage appris top-1 embarqué est faisable à votre échelle mais son bénéfice au-dessus d'un aiguillage écrit à la main n'est démontré nulle part dans les jeux, et Backgammon-NN a trouvé le routage catégoriel « neutre ». [MESURE] Je le classe comme piste de recherche, pas comme gain sûr.

### Sous-question 5 — Les ensembles et leur distillation

**Ensembles bruts : exclus** (K× le coût par évaluation). [DÉCLARÉ]

**Distillation d'ensemble/enseignant dans un réseau unique : la voie la plus prometteuse.** [MESURE]
- Hinton, Vinyals, Dean (« Distilling the Knowledge in a Neural Network », arXiv:1503.02531, 2015) : compresser un ensemble en un modèle unique déployable, avec des « soft targets »/dark knowledge ; résultats MNIST et amélioration significative d'un modèle acoustique commercial très utilisé. [MESURE]
- Born-Again Networks (Furlanello et al., ICML 2018, PMLR 80:1602-1611, arXiv:1805.04770) : un étudiant **de même architecture** que l'enseignant le **surpasse** — verbatim : « we make the surprising discovery that the students become the masters, outperforming their teachers by significant margins… applied to DenseNets, ResNets and LSTM-based sequence models, BANs consistently have lower validation errors than their teachers ». [MESURE] Directement pertinent : vous pouvez distiller votre propre réseau dans un réseau identique et gagner. Nuance honnête : « Revisiting Self-Distillation » (arXiv:2206.08491) mesure que les BAN font **moins bien qu'un ensemble** de modèles entraînés indépendamment — la distillation conserve *l'essentiel* mais pas *tout* le gain d'ensemble. [MESURE]
- Policy distillation en RL (Rusu et al., arXiv:1511.06295) : consolider plusieurs politiques spécifiques par tâche en une seule qui « outperforms the single-task teachers ». [MESURE] Analogie forte avec « distiller plusieurs experts de classe en un réseau unique ».
- Weltevrede et al. (NeurIPS 2025, arXiv:2505.16581) : borne de généralisation prouvant que distiller un *ensemble* de politiques et sur *autant de données que possible* améliore le transfert. [MESURE]

**La preuve backgammon existe déjà chez vous et chez un pair :** Backgammon-NN a distillé (a) sa propre recherche 2-ply dans son éval statique (premier gain « search-robust » du projet), puis (b) un enseignant externe fort. Vous faites déjà de la distillation pour votre réseau d'élagage. **C'est exactement le mécanisme qui achète la qualité d'un ensemble/enseignant au prix d'un seul réseau.** [MESURE]

### Sous-question 6 — Le partage de tronc

**Ce qu'on gagne vs réseaux séparés :** à budget de données égal, un tronc partagé + têtes spécialisées **ne prive aucune tête de données** (le tronc voit toutes les positions), contrairement à des réseaux entièrement séparés entraînés chacun sur sa seule distribution — le défaut même que Heled décrit pour GNU BG. [MESURE, via Backgammon-NN bucketing 52,6 %] C'est l'argument décisif dans votre cas : vos classes faibles (crashed, backgame) sont rares → un réseau séparé y est affamé de données, une tête sur tronc partagé non.

**Largeur de goulot :** aucune règle chiffrée publiée pour le backgammon. [Lacune] La littérature multi-tâches (hard vs soft parameter sharing) documente le **negative transfer** et le **task interference** (gradients conflictuels) quand les tâches sont peu corrélées : en hard sharing, « roughly half of all updates conflict » (OpenReview 7ZvJkafUrd, consulté le 26/08/2026). [MESURE] Vos phases (contact/race) sont modérément corrélées → interférence probable mais gérable ; garder un goulot assez large pour que le tronc encode les concepts communs (course, sécurité de blot, prime) et laisser les têtes gérer le spécifique.

### Sous-question 7 — Coût mémoire et téléchargement

- **Réseaux séparés = poids ×N à télécharger.** Votre réseau ~2 Mio en float32. Trois réseaux séparés ≈ 6 Mio ; un tronc partagé + 3 têtes ≈ tronc + 3× (petites têtes), bien moins. [HYPOTHÈSE chiffrée]
- **Quantification int8/int16 :** réduction ~4× de la taille et de la bande passante, précision « à 1 % ou moins du float32 » pour la plupart des réseaux (arXiv:2004.09602, « Integer Quantization for Deep Learning Inference », consulté le 26/08/2026). [MESURE] NNUE quantifie en int8/int16 précisément pour la vitesse CPU et la taille (chessprogramming ; DeepWiki Stockfish). [DÉCLARÉ] Vous pouvez quantifier différemment par tête si une classe tolère plus de bruit.
- **Chargement à la demande :** faisable en WebAssembly (charger la tête crashed seulement quand la première position crashed survient). Aucune mesure publiée spécifique au backgammon. [HYPOTHÈSE]
- **Le partage de tronc est le meilleur compromis mémoire ET qualité** : un seul gros tronc + têtes légères minimise et le téléchargement et la duplication.

## Tableau des découpages candidats

| Découpage | Nombre d'experts | Coût par évaluation | Gain attendu | Risque de discontinuité | Preuve publiée |
|---|---|---|---|---|---|
| Réseau unique (statu quo) | 1 | 527 000 MACs (référence) | — | Aucun (pas de frontière) | — |
| Aiguillage dur contact/crashed/race (réseaux séparés) | 3 | ~inchangé (un seul consulté) + aiguillage négligeable | Faible ; **routage mesuré « neutre »** hors calendrier d'apprentissage | Élevé (échelles séparées, données affamées en crashed) | Backgammon-NN : routage neutre, 52 % @1-ply [MESURE] ; gnubg [DÉCLARÉ] |
| Tronc partagé + têtes de sortie multiples (bucketing style NNUE, discriminateur pip-count) | 1 tronc + K têtes | ~inchangé (une tête consultée ; têtes minuscules) | **Net et search-robuste** ; pas de données affamées | Faible (représentation commune) | Backgammon-NN bucketing 52,6 % [MESURE] ; Stockfish LayerStacks [DÉCLARÉ] |
| Mélange d'experts appris, routage top-1 dur | 1 routeur + K experts | ~inchangé si top-1 strict ; routeur négligeable | Incertain ; risque collapse/instabilité | Moyen (frontière apprise, potentiellement lissée) | HME Jordan-Jacobs 1994 [MESURE, régression] ; pas de preuve jeux |
| Mélange d'experts dense (softmax pondéré) | K experts | **K× — EXCLU** | Élevé mais interdit par la contrainte | Nul (mélange continu) | MoE classique [MESURE] |
| Distillation d'un ensemble/enseignant fort → réseau unique | 1 (au déploiement) | **strictement inchangé** | **Le mieux prouvé à coût constant** | Nul (un seul réseau) | Hinton 2015, Born-Again 2018, Backgammon-NN 53,4 % [MESURE] |
| Découpage backgame/holding dédié | +1–2 têtes/réseaux | ~inchangé (un consulté) | Potentiellement élevé (classes documentées faibles) mais non chiffré | Élevé (classes rares, frontières floues) | Aucune ablation [Lacune] ; bgsage 19 réseaux backgame-aware [DÉCLARÉ] |

## Recommendations — Le découpage que je testerais en premier

**Deux tests, dans cet ordre. Le premier n'est pas un découpage — c'est le contrôle qui vous dira si le découpage vaut la peine.**

**Test A (priorité 1) — Distiller un enseignant fort dans votre réseau actuel, architecture inchangée.**
- *Pourquoi d'abord :* c'est le seul mécanisme dont le gain à coût par évaluation strictement constant est prouvé (Backgammon-NN, Hinton, Born-Again), et il ne touche ni votre budget MACs, ni votre pipeline WASM, ni votre chargement de poids.
- *L'enseignant :* votre propre recherche expectiminimax 2-ply, retournant la distribution complète (win/gammon/backgammon), pas seulement l'équité — c'est le point que Backgammon-NN identifie comme décisif. Vous le faites déjà pour l'élagage ; étendez-le à l'éval principale. **N'utilisez pas** les poids GNU BG (GPL-3) ni HedgeHog comme enseignant.
- *Entraînement :* labelliser N positions par la sortie 2-ply, entraîner le réseau 196→512→512→256→128→5 à reproduire la distribution (blend soft/hard).
- *La mesure en quelques heures :* head-to-head à dés miroités, réseau distillé (0-ply) vs réseau actuel (0-ply), 2 000–5 000 parties, puis re-vérifier au ply que l'appli joue (2-ply). **Seuil de décision : > 51 % avec barre d'erreur excluant 50 %, ET gain qui survit à 1/2-ply.** Backgammon-NN montre que les gains 0-ply qui s'évaporent en recherche sont sans valeur — c'est votre critère d'élimination.

**Test B (priorité 2, seulement si A plafonne) — Tronc partagé + têtes de sortie multiples, pas d'aiguillage dur de réseaux séparés.**
- *Classes :* commencez par le bucketing par **pip-count** (discriminateur bon marché, bien élevé, style NNUE) plutôt que par la classification catégorielle contact/crashed/race — c'est ce qui a donné un gain net et search-robuste (52,6 %) chez Backgammon-NN, alors que la classification catégorielle s'est révélée neutre.
- *Comment on aiguille :* le tronc (196→512→512→256) est partagé et voit toutes les positions ; seule la dernière transformation (128→5) est dupliquée en K têtes, sélectionnées par bucket de pip-count. Une seule tête est évaluée → coût par évaluation quasi inchangé. Critère non cyclique là où c'est catégoriel, pour éviter les allers-retours en recherche.
- *Entraînement :* conjoint (le tronc reçoit le gradient de toutes les têtes), pour éviter la famine de données des classes rares (crashed, backgame).
- *La mesure :* **variez UNE seule chose à la fois** (l'avertissement explicite de Backgammon-NN : leur « gain de routage » était en fait un gain de calendrier d'apprentissage). Entraînez le réseau mono-tête et le multi-tête avec *exactement* le même budget de données, le même schedule, la même graine, puis head-to-head. **Seuil : > 51 %, barre d'erreur excluant 50 %, survie à 2-ply.** Si le multi-tête n'est pas significativement au-dessus à schedule identique, le découpage n'apporte rien — abandonnez-le.

**Test C (facultatif, mesure de diagnostic, à lancer en parallèle) — Produire la carte d'erreur manquante.** Avant même de spécialiser, générez la donnée que personne n'a publiée : prenez votre réseau unique, échantillonnez des positions par catégorie (contact, crashed, backgame, holding, prime-vs-prime, course avec contact résiduel, bear-off avec/sans contact), et mesurez l'erreur d'équité par catégorie vs vos rollouts profonds. **C'est cette carte qui vous dira OÙ une tête spécialisée peut payer** — sans elle, le choix des classes est aveugle.

**Ce que je NE testerais pas en premier :** l'aiguillage dur de trois réseaux entièrement séparés (famine de données en crashed/backgame + discontinuités + ×3 téléchargement) et le mélange d'experts à routage appris (collapse, instabilité, gain non prouvé dans les jeux).

**Seuils qui changeraient ces recommandations :** si le Test A distille jusqu'à la parité avec votre enseignant sans plafonner, restez sur la distillation et n'ajoutez aucune tête. Si le Test C révèle qu'une catégorie (typiquement backgame ou crashed) concentre >2× l'erreur moyenne ET représente une fraction non négligeable des décisions réelles, alors une tête dédiée à cette classe (sur tronc partagé) devient prioritaire sur le bucketing pip-count générique.

## Caveats — Ce que je n'ai pas trouvé

- **Aucune mesure de l'ampleur des discontinuités de frontière** (transition gaps), ni au backgammon (GNU BG les reconnaît sans les chiffrer) ni ailleurs. Personne n'a publié « voici l'incohérence en équité entre deux réseaux voisins de part et d'autre de la frontière crashed ». [Lacune centrale, elle vous concerne]
- **Aucune carte chiffrée de l'erreur d'un réseau unique par type de position** (blitz, prime-vs-prime, holding, backgame, bear-off avec/sans contact) vs rollouts profonds. Les faiblesses sont *déclarées* (backgame, crashed, containment) mais jamais *mesurées catégorie par catégorie*. Vous devrez la produire vous-même (Test C).
- **Aucune ablation isolant l'Elo du bucketing/layer-stacks seul dans Stockfish** — la PR #3474 mesure le paquet entier (21,74 ±3,4 STC / 5,85 ±1,7 LTC). Le « quasi gratuit en calcul » est déclaré par les auteurs (Sopel97, texte de la PR), pas quantifié en Elo-par-MAC.
- **Aucune documentation technique publique sur l'architecture interne de HedgeHog** (ensemble ? MoE ?) ni de mesure — la prémisse « HedgeHog utilise des ensembles » reste non confirmée.
- **Aucune règle chiffrée sur la largeur de goulot minimale** pour que des têtes spécialisées soient utiles au backgammon.
- **Aucune mesure du routage appris (MoE) vs aiguillage manuel dans un jeu de plateau** à budget constant — Backgammon-NN a trouvé le routage catégoriel « neutre » mais n'a pas comparé un routeur appris top-1.
- **Aucune étude publiée quantifiant l'effet d'une discontinuité de fonction de valeur sur un expectiminimax de backgammon** spécifiquement.

*Sources principales consultées le 26/08/2026 : whittingtonchess.com/backgammon-report ; lists.gnu.org/archive/html/bug-gnubg/2012-02/msg00022.html ; gnu.org/software/gnubg/manual/allabout.pdf ; github.com/carsten-wenderdel/wildbg(-training) ; github.com/official-stockfish/Stockfish (PR #3474) et nnue-pytorch/docs/nnue.md ; chessprogramming.org/NNUE ; stockfishchess.org/blog/2020 ; chess.com/news/view/stockfish-absorbs-nnue-100-elo ; arXiv:1503.02531, 1805.04770, 2206.08491, 1511.06295, 2505.16581, 2004.09602, 1706.04599 ; Jordan & Jacobs 1994 (DOI 10.1162/neco.1994.6.2.181) ; github.com/customation/sage-engine-server et markbgsage/bgsage ; icga.org ACG 2021 ; OpenReview 7ZvJkafUrd.*