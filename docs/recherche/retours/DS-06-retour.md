# DS-06 — Entraîner le réseau *pour* la recherche — retour

**Date de la recherche** : 2026-08-26 · **Outil** : Claude, recherche approfondie
**Prompt** : `docs/recherche/DS-06-entrainer-pour-la-recherche.md`, version injectée du 2026-08-27

> **Ce que ce retour décide** : l'hypothèse H1 — notre avantage s'annule sous recherche parce que
> le réseau n'a jamais été entraîné à être bon sous recherche.
> **Ce qu'il conclut** : H1 confirmée et munie d'une recette — la **distillation de sa propre
> recherche 2-ply distributionnelle** (les 5 probabilités, pas l'équité seule) est la seule cible
> dont la survie sous recherche est prouvée (Whittington v1.9.0 : ~52 % contre son champion à
> 1-ply, « ne se lave pas sous la recherche ») et qui reste dans notre licence ; protocole
> chiffré : 1,0–1,5 M labels 2-ply auto-générés (~heures sur notre machine), tête auxiliaire de
> **volatilité exacte sur les 21 jets** (étiquetage gratuit, analogue des têtes KataGo),
> entraînement from scratch à architecture constante, jugé sur **l'intervalle 2-ply par
> décision** (succès = il se déplace au-dessus de zéro) et non au 0-ply. Plafond structurel :
> l'élève ne dépasse pas le maître ; les deux échappatoires non bornées sont SPSA sur la tête de
> sortie et les têtes auxiliaires. Le professeur externe de Whittington (gnubg 2-ply, +7 pts)
> nous est interdit par la règle du dépôt.
> **Ce qu'il ne tranche pas** : aucun classement publié des cibles d'entraînement jugées **à leur
> force sous recherche** (points isolés seulement) ; gain des têtes auxiliaires, de la valeur
> distributionnelle et d'une tête de politique non chiffré au backgammon ; les hyperparamètres
> exacts de la distillation de Whittington (mélange soft/hard, LR, époques) sont à extraire de
> son dépôt.

---
# gammonNet — Entraîner une fonction de valeur pour qu'elle soit bonne *sous recherche*

## TL;DR
- **La distillation de la valeur d'une recherche profonde (2-ply pour vous) est la seule recette dont le gain survit à la recherche et qui reste dans votre périmètre de licence** ; c'est confirmé indépendamment par Whittington (Backgammon-NN v1.9.0, ~52 % vs son champion à 1-ply) et par la littérature générale de « bootstrapping from search » (TreeStrap/TDLeaf, NNUE, Leela, KataGo). [MESURE][DÉCLARÉ]
- **Toute cible bornée par votre propre moteur plafonne à la parité avec lui** (« l'élève ne dépasse pas le maître ») : self-play, rollouts tronqués/complets, distillation 1-ply convergent tous au même point ; seul un signal *de recherche plus profonde que votre jeu à 0-ply* ajoute de la qualité réelle. [MESURE]
- **Deux leviers non bornés par un professeur restent ouverts** : (a) l'optimisation directe de la force (SPSA sur la tête de sortie, branchée sur votre banc), et (b) des **têtes auxiliaires** (volatilité exacte sur les 21 jets, incertitude) qui régularisent la représentation à MACs quasi constants. Aucun n'est chiffré pour le backgammon sous recherche — c'est votre zone d'expérimentation à plus haut rendement. [HYPOTHÈSE]

## Key Findings

1. **Votre diagnostic est correct et déjà reproduit ailleurs.** Whittington a mesuré exactement le même effacement : ses gains 0-ply (v1.7.0, v1.8.0) « s'évaporent à 1-ply », tandis que la distillation 2-ply « ne se lave pas sous la recherche ». [MESURE]
2. **La distillation de recherche est le principe d'AlphaZero/NNUE/Leela**, et elle s'étend aux jeux à hasard via les *afterstates* (Stochastic MuZero, qui égale puis dépasse GNU BG Grandmaster au backgammon). [MESURE]
3. **Le backup exact sur 21 jets (votre phase finale, = celle de Strehl) est un signal « 1-ply »** ; Strehl garde un avantage qui survit au 2-ply en se resserrant (+57,8 → +45,0 mEq/partie), ce qui borne l'espérance de gain d'un pur backup 1-ply. [MESURE]
4. **Les têtes auxiliaires marchent** (KataGo : ownership + score + valeurs à horizons multiples améliorent la value loss et la vitesse d'apprentissage « gratuitement »). Non testé au backgammon. [MESURE pour Go / HYPOTHÈSE pour BG]
5. **Une vraie tête de politique** accélère et guide la recherche dans tous les moteurs modernes, mais au backgammon l'espace de coups dépend du jet ; la solution documentée est une politique **autoregressive sur micro-actions** (Stochastic MuZero) ou un vecteur de sortie fixe indexé par (source, dé). [DÉCLARÉ]
6. **La pathologie minimax dépend de la corrélation des erreurs** entre nœuds ; décorréler/calibrer les erreurs (ensembles, dropout d'évaluation, valeur distributionnelle) est une piste théoriquement fondée mais non chiffrée pour votre cas. [DÉCLARÉ/HYPOTHÈSE]

## Details

### 0. Cadre : pourquoi la recherche efface votre avantage

Le fait que vous mesurez (+0,00247 à 0-ply → +0,00007 à 2-ply, intervalle contenant zéro) est la signature d'un réseau **optimisé pour être précis à profondeur 0 mais pas pour bien se comporter comme feuille d'un arbre**. La théorie de la pathologie minimax l'explique : la qualité d'une recherche minimax/expectiminimax dépend de la **corrélation des erreurs d'évaluation** entre nœuds voisins. Nau (1979–1983) et Beal (1980) ont montré que sous des erreurs *indépendantes* aux feuilles, chercher plus profond peut *dégrader* la décision ; ce qui sauve le minimax en pratique est la corrélation/regroupement des vraies valeurs et le fait qu'un sous-ensemble de nœuds (les nœuds « calmes ») ont une faible erreur (Scheucher/Kaindl ; Luštrek & Gams, IJCAI 2005, https://www.ijcai.org/Proceedings/05/Papers/1223.pdf, consulté le 26/08/2026). [DÉCLARÉ]

Corollaire opérationnel : deux réseaux qui convergent quand on cherche plus profond (votre taux de désaccord 20,8 % → 9,5 %) indiquent que **la recherche est un opérateur qui « ramène » les deux évaluateurs vers la même valeur de référence** ; l'avantage statique se dilue parce qu'il portait sur des différences que la recherche corrige de toute façon. Pour garder un avantage sous recherche, il faut soit (a) que votre feuille encode déjà de l'information que le 2-ply de l'adversaire ne récupère pas, soit (b) que vous cherchiez mieux/plus. (a) est exactement ce que fait la distillation de recherche. [HYPOTHÈSE]

### 1. Reproduire le protocole de Whittington (Backgammon-NN)

Source primaire : rapport de développement, https://whittingtonchess.com/backgammon-report (mis à jour le 21/07/2026, consulté le 26/08/2026) ; page projet https://whittingtonchess.com/backgammon ; dépôt https://github.com/Chris-Whittington-Chess/Backgammon-NN.

**Ce qui est documenté :**
- **Architecture** : réseau unique 198→256→128→5, activation *squared-ReLU*, 5 têtes emboîtées (sigmoïdes). Variante « bucketing » (un corps, 8 têtes par pip-count, softmax-6) et « class-aware routing » (12 têtes race/crashed/contact × pip). Moteur Rust + PyO3, tract-ONNX. [DÉCLARÉ]
- **Signal de base** : TD(λ=1) self-play (~150k parties pour le deep net). [DÉCLARÉ]
- **La recette qui survit à la recherche (v1.9.0)** : « distiller la valeur de recherche 2-ply propre du champion » via un **expectiminimax renvoyant la distribution** (win/gammon/backgammon, pas seulement l'équité). Volume : **1,37 M positions étiquetées à 2-ply**. Résultat : **~52 % vs le champion à 1-ply sur 1000 parties (PPG +0,06)**, parité avec gnubg à 0-ply. « L'arête est petite (~2 %) mais pour la première fois elle ne se lave pas sous la recherche. » [MESURE]
- **Cibles** : la distribution complète à 5 composantes, pas seulement l'équité scalaire — Whittington insiste sur ce point (« carries the win/gammon/backgammon split, not just the equity »). [DÉCLARÉ]
- **Étiquetage** : générateur de coups « step-free » (plateaux de 30 octets), ~57 positions/s pour les rollouts ; l'expectiminimax 2-ply distributionnel est plus cher. [DÉCLARÉ]
- **Critère d'arrêt / validation** : head-to-head à jets miroirs contre le champion incumbent, revérifié à 1-ply (leçon explicite : « vérifier au ply où l'appli joue »). Whittington note qu'une baisse de la validation-loss **cesse de se traduire en parties gagnées** au-delà d'un certain volume — seuls les head-to-heads détectent ce genou. [MESURE]

**Le plafond et comment il l'a contourné :** toute cible produite par son propre moteur (self-play, rollouts, distillation 1-ply *et 2-ply*) plafonne à la parité avec ce moteur (« a student cannot exceed its teacher »). Il l'a franchi par un **professeur externe : gnubg à 2-ply, 22,5 M positions** (v1.10.0). *Cette voie vous est interdite par votre règle de licence.* Il liste aussi, comme leviers restants non bornés par un professeur, **SPSA sur les paramètres de la tête de sortie**, scoré en PPG sur matches à jets miroirs (« pas borné par le professeur », banc à 20 000 parties en ~21 s). [DÉCLARÉ]

**Ce qui manque pour rejouer exactement chez vous :** (i) le détail exact du mélange soft/hard label et du poids par composante dans la distillation 2-ply n'est pas donné numériquement ; (ii) le schéma de learning-rate (il révèle a posteriori qu'un gain attribué au « routing » venait en fait d'une queue de décroissance du LR) ; (iii) le nombre d'époques et la taille de batch de la phase de distillation. Ces trois éléments sont à retrouver dans le dépôt ou à recalibrer. [HYPOTHÈSE]

**Limites mesurées par Whittington, utiles à connaître :** les caractéristiques d'entrée expertes (type gnubg) **n'apportent rien** (neutres au mieux, ~5 points derrière fed en NNUE) ; la **largeur de recherche** est nulle (fenêtre ×3 → 50,5 % sur 2600 parties) ; un réseau 2,7× plus gros n'est **pas distinguable** à movetime égal (d'où l'expédition d'un 256×128). Ces trois négatifs confortent votre contrainte « qualité à MACs constants ». [MESURE]

### 2. La distillation de recherche dans les jeux à hasard

- **Principe général (déterministe)** : TreeStrap (Veness, Silver, Uther, Blair, NeurIPS 2009, https://proceedings.neurips.cc/paper/2009/file/389bc7bb1e1c2a5e7e147703232a88f6-Paper.pdf, consulté le 26/08/2026) met à jour l'évaluateur vers la valeur d'une **recherche profonde** plutôt que d'un pas de temps suivant. Leur programme d'échecs **Meep**, entraîné par TreeStrap(αβ) depuis des poids aléatoires en self-play, **a battu des maîtres internationaux humains dans 13 parties sur 15** (résultat cité par Silver et al., AlphaZero, arXiv:1712.01815) — la meilleure performance d'un programme d'échecs avec heuristique apprise entièrement en self-play. TDLeaf(λ) (Baxter, Tridgell, Weaver, *Machine Learning* 1999, arXiv cs/9901002 ; Springer 10.1023/A:1007634325138) apprend vers les feuilles de la variation principale ; **KnightCap est passé de 1650 à 2150 Elo (niveau maître humain) en 308 parties et 3 jours**, en jeu en ligne (pas en self-play). [MESURE]
- **Les auteurs de TreeStrap indiquent explicitement l'extension aux jeux à hasard** : « *in stochastic domains the evaluation function could be updated towards the value of an expectimax search, or towards the one-sided bounds computed by a \\*-minimax search (Hauk et al., 2004; Veness & Blair, 2007)* » — c'est exactement votre situation. [DÉCLARÉ]
- **NNUE / Leela** : Stockfish NNUE est entraîné sur des positions évaluées à profondeur modérée (data Leela + données Stockfish à profondeur 9 / 5000 nœuds) ; « la construction des données d'entraînement est de plusieurs ordres de grandeur plus chère que l'entraînement lui-même » (cp4space, https://cp4space.hatsya.com/2021/01/08/, consulté le 26/08/2026) — écho exact de la remarque de l'auteur de gnubg que vous citez. [DÉCLARÉ]
- **Jeux à nœuds de hasard — le résultat clé** : **Stochastic MuZero** (Antonoglou, Schrittwieser, Ozair, Hubert, Silver, ICLR 2022, https://openreview.net/pdf?id=X6D9bAHhBQ1, consulté le 26/08/2026) factorise la transition en *afterstate* (déterministe) + pas stochastique, et fait une MCTS avec nœuds de hasard. Au **backgammon**, avec **1600 simulations/coup**, il **égale GNU BG Grandmaster** ; verbatim : « *GNUbg Grandmaster uses a 3-ply look-ahead search over a branching factor of 20 legal moves* », et « *Stochastic MuZero's model scaled well to large searches, and exceeded the playing strength of GNUbg Grandmaster when using more than 10³ simulations* » ; la force **croît avec le nombre de simulations**. Architecture : tour résiduelle **10 blocs, largeur 256** ; les 21 jets modélisés par un **VQ-VAE à codebook de taille 32** (~21 codes effectivement utilisés) ; politique **autoregressive sur micro-actions** (source×6+dé). *Aucun chiffre numérique d'Elo/win-rate n'est donné pour le backgammon — seulement des courbes ; aucun compte de paramètres.* Entraînement : ~27 h sur 1 TPU + 16 TPU acteurs (≈10 j sur un V100). [MESURE/DÉCLARÉ]
- **Précaution documentée (risque de renforcer ses propres erreurs)** : Whittington montre qu'un rollout **entièrement joué (λ=1) sous une politique gloutonne faible est *pire* qu'un rollout tronqué** — étendre une politique faible accumule ses erreurs plus vite qu'une bonne feuille d'éval statique ; le compromis biais-variance favorise la troncature. Corollaire : distiller une recherche 2-ply *dont les feuilles sont votre réseau actuel* n'échappe pas au plafond du réseau ; le gain de la distillation 2-ply vient de ce que le 2-ply corrige des erreurs structurellement invisibles à l'éval statique, pas d'un dépassement du réseau. [MESURE]

### 3. Comparaison des cibles d'entraînement

| Cible | Nature du signal | Variance | Borné par… | Preuve |
|---|---|---|---|---|
| TD(0), 1 jet | échantillon | très haute (plancher ~0,004) | politique courante | Strehl [MESURE] |
| Backup exact 21 jets (votre phase finale = Strehl 1-ply) | espérance sur dés | basse (plancher ~0,0001) | réseau à 0-ply | Strehl [MESURE] |
| n-step / TD(λ) | trajectoire | intermédiaire | politique | Sutton/Barto [DÉCLARÉ] |
| Rollout tronqué | Monte-Carlo tronqué | basse | politique de rollout | Whittington, Tesauro [MESURE] |
| Rollout complet (λ=1) | Monte-Carlo complet | basse mais **biaisée** par politique faible | politique de rollout | Whittington (« pire ») [MESURE] |
| **Valeur de recherche 2-ply distillée** | expectiminimax profond | basse | **la recherche, pas l'éval statique** | Whittington v1.9.0 ; TreeStrap [MESURE] |

**Verdict :** la seule cible pour laquelle il existe une **preuve directe de survie sous recherche 2-ply** est la valeur de la recherche 2-ply distillée (Whittington). Le backup exact sur 21 jets (ce que vous faites déjà, et ce que fait Strehl) donne un réseau qui **garde un avantage se resserrant** sous recherche mais ne l'amplifie pas. Personne n'a publié un classement propre « quelle cible maximise la force à 2-ply » avec intervalles de confiance ; c'est un trou de la littérature (voir « Ce que je n'ai pas trouvé »). [MESURE/HYPOTHÈSE]

Chiffre de calage utile : Tesauro, « On-line Policy Improvement using Monte-Carlo Search » (NeurIPS 1996 ; arXiv:2501.05407, Table 2, consulté le 26/08/2026) — sur un jeu-test de 800 positions, verbatim : « *the TD-Gammon 1-ply base player scores 0.0120 on this test set measure … while TD-Gammon 2-ply base player scores 0.00843* » (unités ppg). C'est l'ordre de grandeur de ce que « un ply de plus » vaut, cohérent avec votre +0,00022 « dans le bruit ». [MESURE]

### 4. La tête de politique

Tous les moteurs modernes apprennent une distribution sur les coups pour ordonner/élaguer. Au backgammon l'ensemble des coups légaux **dépend du jet**, ce qui interdit une tête softmax à taille fixe naïve. Solutions documentées :
- **Politique autoregressive sur micro-actions** (Stochastic MuZero) : un coup = 4 micro-actions, chacune (source ∈ 26, dé ∈ 6) → sortie 26×6 dépliée 4 fois. Indépendant du jet. [DÉCLARÉ]
- **Vecteur de sortie fixe indexé par coup** (SimonG5/BackPolicy : 601 sorties couvrant tous les coups possibles ; on masque les illégaux, https://github.com/SimonG5/BackPolicy) — approche « move-ordering » classique, gain de 20–50 % de nœuds en alpha-bêta hors backgammon (Move Ordering Using Neural Networks, Lines of Action). [DÉCLARÉ]
- **Gain attendu au backgammon** : *non chiffré publiquement*. Whittington affirme même que la **largeur de recherche est nulle** chez lui — ce qui suggère qu'avec votre réseau déjà précis, une tête de politique servirait surtout à *réduire le coût* de la recherche (moins de coups évalués pour la même qualité), pas à augmenter la force. À MACs constants, une tête de politique légère partageant le corps pourrait donc **libérer du budget de recherche** plutôt qu'améliorer la feuille. [HYPOTHÈSE]

### 5. Cohérence / décorrélation des erreurs

- **Fondement théorique** : la valeur de la recherche dépend de la corrélation des erreurs (Nau, Beal, Luštrek & Gams). Zuckerman/Nau (2018, https://www.cs.umd.edu/~nau/papers/zuckerman2018avoiding.pdf, consulté le 26/08/2026) montrent que « tout jeu a des situations pathologiques » et proposent des recherches qui coupent dans les sous-arbres pathologiques (error-minimizing minimax). [DÉCLARÉ]
- **Techniques de décorrélation** : ensembles (moyenne/écart-type des Q), dropout au moment de l'évaluation, valeur **distributionnelle** (C51/QR-DQN), régularisation de calibration (conformal, UNIQ). Ces méthodes quantifient l'incertitude épistémique/aléatoire et sont utilisées pour pénaliser les valeurs peu fiables. [DÉCLARÉ]
- **« Un réseau mieux calibré cherche-t-il mieux ? »** : je n'ai pas trouvé de démonstration directe pour un jeu de plateau. KataGo utilise une tête de **variance de la valeur MCTS** et des **playouts pondérés par l'incertitude** (Uncertainty-Weighted MCTS Playouts, https://github.com/lightvector/KataGo/blob/master/docs/KataGoMethods.md) — un cas où une estimation d'incertitude *améliore effectivement la recherche* — mais ce n'est pas une preuve de calibration→force au sens strict. [DÉCLARÉ/HYPOTHÈSE]
- **Risque pratique pour vous** : un ensemble multiplie le coût d'inférence (interdit par votre contrainte téléphone) ; le dropout d'évaluation aussi (N passes). La valeur distributionnelle, elle, est **quasi gratuite à MACs constants** (mêmes MACs, sortie plus riche) et pourrait décorréler les erreurs le long d'une branche. [HYPOTHÈSE]

### 6. Les têtes auxiliaires

- **Preuve la plus solide** : David J. Wu, « Accelerating Self-Play Learning in Go » (KataGo ; arXiv:1902.10565 v5, Jane Street, consulté le 26/08/2026). Retirer les têtes auxiliaires **ownership + score** (run « NoVAux ») provoque « une baisse notable de l'efficacité d'apprentissage » ; conclusion des auteurs : « *predicting subcomponents of desired targets can greatly improve training* » (valeur de la régularisation par prédiction de sous-composantes). KataGo surpasse ELF OpenGo « after only 19 days on fewer than 30 GPUs » (réduction de calcul d'un facteur ~50). Poids de perte auxiliaires non finement réglés (10–40 % du gradient principal) suffisent à un gain « immédiat et significatif ». KataGo ajoute aussi des **valeurs auxiliaires à horizons multiples** (moyennes exponentielles des valeurs MCTS futures, horizons ~6/16/50 coups) qui « améliorent légèrement la value loss principale, gratuitement ». [MESURE]
- **Transposition au backgammon** : vous pouvez calculer **exactement** la **volatilité** (écart-type de l'équité au prochain point de décision) en développant les 21 jets — c'est déjà ce que fait votre backup exact, donc le signal est *disponible sans coût d'étiquetage supplémentaire*. L'entraîner comme tête auxiliaire est l'analogue direct de la tête « variance » de KataGo, et sert *en plus* aux décisions de cube (Tesauro utilisait la volatilité — écart-type sur les deux prochains jets — pour le doublement ; Scholarpedia, http://www.scholarpedia.org/article/User:Gerald_Tesauro/Proposed/Td-gammon, consulté le 26/08/2026). [HYPOTHÈSE, appuyée sur MESURE Go + DÉCLARÉ Tesauro]
- **Coût** : quelques neurones de sortie partageant le corps → **MACs quasi inchangés**, compatible téléphone. C'est le levier au meilleur rapport risque/rendement respectant *toutes* vos contraintes. [HYPOTHÈSE]

### 7. Le coût, pour votre machine (16c/32t, 94 Gio, GPU optionnel)

- **Distillation 2-ply « à la Whittington »** : générer ~1,3–2,5 M positions étiquetées par *votre* expectiminimax 2-ply distributionnel. À ~50–60 positions/s mono-thread (ordre de grandeur Whittington), ×32 fils → ~1600–1900 pos/s → **~1,3 M positions en ~12–20 min**, quelques heures avec marge. Entraînement supervisé : minutes sur GPU, ~1 h sur CPU. **Tient largement sur votre machine.** [DÉCLARÉ/HYPOTHÈSE]
- **Têtes auxiliaires** : coût nul en étiquetage (volatilité = sous-produit du backup exact) ; ré-entraînement self-play/distillation identique. [HYPOTHÈSE]
- **SPSA sur la tête de sortie** : coût = parties du banc. Whittington : 20 000 parties en ~21 s natif ; quelques milliers d'itérations SPSA = heures. **Tient.** [DÉCLARÉ]
- **Hors de portée** : re-faire Stochastic MuZero (1 TPU + 16 TPU acteurs, ~27 h ; ~10 j sur un V100) — **parc de machines, à exclure** comme recette, à garder comme source d'idées (afterstates, politique autoregressive, codebook de hasard). [MESURE]

## Tableau des recettes

| Recette | Ce qu'elle change | Preuve publiée | Gain attendu sous recherche | Coût de calcul | Risque |
|---|---|---|---|---|---|
| **Distillation 2-ply distributionnel (votre propre moteur)** | Cible = valeur d'un expectiminimax 2-ply renvoyant les 5 probas, au lieu de la valeur statique | Whittington v1.9.0 : ~52 % vs champion à 1-ply, « survit à la recherche » ; TreeStrap/Meep (13/15 vs maîtres) | **Positif et robuste, mais petit (~1–2 %)** ; borné par le fait que la feuille reste votre réseau | ~1,3 M labels en dizaines de min sur votre CPU ; entraînement en min/h | Plafond « élève≤maître » ; nécessite un expectiminimax 2-ply distributionnel correct |
| **Têtes auxiliaires (volatilité exacte, incertitude)** | Ajoute des sorties prédisant l'écart-type d'équité sur 21 jets, l'incertitude | KataGo : ownership/score/variance améliorent value loss « gratuitement » (Go, arXiv:1902.10565) | **Inconnu au BG** ; plausible via meilleure représentation, à MACs ~constants | Nul en étiquetage (sous-produit du backup exact) | Non chiffré au BG ; réglage des poids de perte |
| **Backup exact 21 jets (déjà fait / Strehl)** | Cible = E_dés[max(1−V)] | Strehl : avantage survit au 2-ply en se resserrant (+57,8→+45,0 mEq) | **Conserve un avantage, ne l'amplifie pas** | Plancher de loss ×40 plus bas ; déjà en place | Signal « 1-ply » seulement |
| **Valeur distributionnelle (C51/QR-DQN) de la tête de valeur** | Sortie = distribution, pas moyenne | RL distributionnel ; usage recherche non prouvé au BG | **Hypothétique** : décorréler les erreurs le long d'une branche | MACs ~constants | Aucune preuve force-au-BG ; complexité |
| **Tête de politique (autoregressive ou masquée)** | Distribution sur coups pour ordonner/élaguer | Stochastic MuZero (politique autoregressive) ; move-ordering LOA 20–50 % | **Surtout coût de recherche réduit**, pas force (largeur nulle chez Whittington) | Léger si corps partagé | Peut ne rien rapporter en force |
| **SPSA sur la tête de sortie** | Optimise directement la PPG mesurée | Whittington (proposé, banc 20k parties/21 s) | **Non borné par un professeur** ; gain inconnu | Heures sur votre CPU | Bruit d'optimisation ; sur-ajustement au banc |
| **Distiller gnubg** | Professeur externe world-class | Whittington v1.10.0 : +7 pts, brise le plafond | Fort | Faible | **INTERDIT par votre règle de licence** |
| **Stochastic MuZero complet** | Modèle appris + MCTS de hasard | ICLR 2022 : dépasse GNU BG Grandmaster >10³ sims | Fort, scale avec simulations | **Parc TPU — hors de portée** | Infra ; MCTS « mauvais outil » au BG selon Whittington |

## La recette que je lancerais en premier

**Distillation 2-ply distributionnel de votre propre moteur, avec une tête auxiliaire de volatilité exacte greffée dès le départ.** C'est la seule combinaison qui (i) a une preuve publiée de survie sous recherche, (ii) reste strictement dans votre licence (aucun octet de gnubg), (iii) respecte « qualité à MACs constants », et (iv) se branche directement sur votre banc.

**Protocole précis :**
1. **Générer les labels.** Échantillonner des positions de contact via self-play de votre réseau actuel (biaiser vers les positions où votre désaccord avec un 2-ply est élevé — c'est là que le gain se loge). Pour chaque position, faire tourner **votre expectiminimax 2-ply qui renvoie le vecteur (win, wg, wbg, lg, lbg)**, pas seulement l'équité. Cible = ce vecteur (label « hard » de la recherche), éventuellement mélangé 90/10 avec l'issue de partie réelle. Volume initial : **1,0–1,5 M positions** (Whittington plafonne le rendement au-delà de ~2,5 M).
2. **Tête auxiliaire.** Ajouter 1 sortie prédisant l'**écart-type d'équité sur les 21 jets suivants** (calculé exactement pendant le backup — coût d'étiquetage nul). Poids de perte auxiliaire ~0,15–0,3 du principal (fourchette KataGo).
3. **Entraîner** *from scratch* (Whittington montre que le warm-start *nuit* dès qu'il y a assez de signal de professeur) à architecture **256×128 inchangée** (MACs constants), cross-entropy sur les 5 probas + MSE sur la tête auxiliaire.
4. **Ce qui, en quelques heures, dit si ça marche :** brancher le réseau candidat sur **votre banc à profondeur égale contre vos deux arbitres**, et mesurer la **perte d'équité par décision à 2-ply** sur les 2 400 décisions de contact. Le critère de succès n'est **pas** le 0-ply (qui montera trivialement) mais que l'**intervalle à 2-ply se déplace au-dessus de zéro** (aujourd'hui [−0,00005 ; +0,00019]). Mesure secondaire : le **taux de désaccord à 2-ply** doit *cesser* de tomber vers celui de gnubg (s'il reste > 9,5 % **et** que l'équité 2-ply monte, vous avez ajouté de l'information que la recherche ne récupère pas). Ces deux lectures se calculent en une passe de votre banc, en minutes.

**Décision/seuils :** si à 2-ply l'intervalle reste centré sur zéro après 1,5 M labels, n'augmentez pas le volume (rendement décroissant prouvé) — passez à SPSA sur la tête de sortie (levier non borné) et testez la valeur distributionnelle. Si la tête de volatilité ne bouge ni l'équité 2-ply ni la value-loss, retirez-la (coût nul, donc à tester tôt).

## Ce que je n'ai pas trouvé

- **Aucun classement publié, avec intervalles de confiance, des cibles d'entraînement (TD(0) / backup 21 jets / n-step / rollout tronqué / rollout complet / valeur 2-ply) évaluées *spécifiquement à leur force sous recherche 2-ply*** au backgammon. Whittington et Strehl donnent des points isolés, pas un plan factoriel.
- **Aucune mesure « un réseau mieux calibré cherche mieux »** pour un jeu de plateau à hasard (le plus proche est la variance-head + playouts pondérés de KataGo, en Go, sans isoler la calibration).
- **Aucun chiffre de gain d'une tête de politique au backgammon** (force ou coût de recherche), ni pour l'espace de coups dépendant du jet en dehors de Stochastic MuZero.
- **Les chiffres numériques d'Elo/win-rate de Stochastic MuZero au backgammon** : le papier ne donne que des courbes (« égale à 1600 sims, dépasse au-delà de 10³ »), pas de tableau chiffré ni de compte de paramètres.
- **Le détail exact de la distillation 2-ply de Whittington** (mélange soft/hard, poids par composante, LR, batch, époques) n'est pas dans le rapport ; à extraire du dépôt.
- **Licences confirmées** : bgsage est **MPL-2.0** (idées recevables, pas de copie de code) ; poids gnubg **GPL-3** et réseaux XG/BGBlitz propriétaires (hors périmètre).