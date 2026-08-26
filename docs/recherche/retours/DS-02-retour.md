# DS-02 — Anatomie de gnubg — retour

**Date de la recherche** : 2026-08-26 · **Outil** : Claude, recherche approfondie
**Prompt** : `docs/recherche/DS-02-anatomie-de-gnubg.md`, version du 2026-08-26

> **Ce que ce retour décide** : la cible de vitesse chiffrée, et où gnubg est documenté comme faible.
> **Ce qu'il conclut** : réseau contact = 250 → 128 → 5, soit ~32 640 MACs (~16× moins que nous) ;
> nœuds internes servis par un réseau d'élagage ~2 550 MACs (<1 % de coups changés), plus cache
> 2¹⁹ et filtres de coups — le facteur 25–60× est entièrement décomposé ; faiblesses documentées :
> backgames/crashed (« pathetic play », dixit l'auteur), bear-off avec contact, frontières de classe.
> **Ce qu'il ne tranche pas** : les cachées du net race (128 présumé), le taux de succès du cache,
> et l'ampleur des discontinuités de frontière — personne ne l'a publiée, à mesurer nous-mêmes.

---
# GNU Backgammon (gnubg) : architecture, recherche, entraînement et faiblesses documentées

## TL;DR
- **Le soupçon central est confirmé et chiffré.** Le réseau principal de gnubg (classe *contact*) fait **250 entrées → 128 cachées → 5 sorties**, soit **32 640 MACs** par évaluation, contre ~527 000 MACs pour gammonNet : le net de gnubg est **~16× plus petit** en MACs. C'est bien là que passe l'essentiel de l'écart de vitesse, amplifié par des *réseaux d'élagage* d'environ 10 neurones cachés (~2 550 MACs) aux nœuds internes et par un cache d'évaluation. [DÉCLARÉ]/[MESURÉ]
- **gnubg = 3 réseaux de position** (contact / crashed / race) + bases de fin de partie exactes, avec des **frontières de classe explicitement arbitraires** (Joseph Heled) et une classe *crashed* que son propre auteur juge faible en backgames. C'est la faiblesse la mieux documentée et la plus exploitable comme oracle différentiel. [DÉCLARÉ]
- **Voie recommandée : faire tourner gnubg comme oracle**, via le module Python embarqué et les commandes `show`/`set`/`eval`, plutôt que lire le code. Le projet gnubg-nn (bindings Python, poids v1.01) permet de mesurer directement MACs, discontinuités et taux de cache sans recopier aucune constante GPL. [DOCUMENTÉ]

---

## Key Findings

1. **Trois réseaux de position, pas deux.** gnubg utilise `CLASS_CONTACT`, `CLASS_CRASHED` et `CLASS_RACE`, plus des bases de fin de partie (`BEAROFF`) et des cas hypergammon. Les nets contact et crashed partagent le même encodage de 250 entrées ; le net race en a 214. [DOCUMENTÉ]/[DÉCLARÉ]
2. **Tailles : 250/214 entrées, 128 cachées, 5 sorties.** Confirmé par Øystein Schønning-Johansen et Joseph Heled sur bug-gnubg. Les 5 sorties sont win / win-gammon / win-backgammon / lose-gammon / lose-backgammon. [DÉCLARÉ]/[DOCUMENTÉ]
3. **Entrées = Tesauro (~196) + caractéristiques calculées** (exposition de blots, tirs subis, timing, ancres, containment, backgame…), identifiables par leurs noms `I_*` dans `CalculateHalfInputs`. [DÉCLARÉ]
4. **Réseaux d'élagage : ~10 neurones cachés**, mêmes entrées, 5 sorties, un par classe, utilisés aux nœuds internes de la recherche. Coût ~13× inférieur au grand net. « Less than 1 % of all moves come out different with the pruning nets activated » (Jim Segrave). [DOCUMENTÉ]/[DÉCLARÉ]
5. **Cubeful = transformation de Janowski** (interpolation videau mort/vivant via un « cube-life index » x = 0,68 en contact, 0,6 en course longue), et récursion cubeful aux plies supérieurs. [DOCUMENTÉ]
6. **Entraînement = TD-learning puis apprentissage supervisé sur des bases étiquetées par rollouts** (« benchmark/training databases » de Joseph Heled), code et données largement sous GPL. [DÉCLARÉ]
7. **Faiblesse reconnue par l'auteur : les backgames / la classe crashed.** « GNUbg pathetic play in many backgame situations leaves it open to abuse from humans » — Joseph Heled. Autres faiblesses citées : bear-off avec contact, positions hors distribution. [DÉCLARÉ]

---

## Détails

### A. L'architecture d'évaluation

#### A1–A2. Les réseaux : nombre, tailles, encodage

gnubg possède trois réseaux neuronaux de position, exposés dans l'énumération `positionclass` de `eval.h` : `CLASS_RACE` (« Race neural network »), `CLASS_CRASHED` (« Contact, one side has less than 7 active checkers ») et `CLASS_CONTACT` (« Contact neural network »), plus les classes de fin de partie `CLASS_BEAROFF1/2/OS/TS` et trois classes hypergammon. [DOCUMENTÉ — eval.h, https://github.com/mormegil-cz/gnubg/blob/master/eval.h, consulté le 26/08/2026]

Tailles (à confirmer chez soi par mesure) :

- **Contact & Crashed : 250 entrées → 128 cachées → 5 sorties.** Øystein Schønning-Johansen, bug-gnubg, 27/12/2023 : « The normal contact position neural network had 250 inputs, 128 hidden nodes and 5 outputs. » [DÉCLARÉ — https://www.mail-archive.com/bug-gnubg@gnu.org/msg08189.html, consulté le 26/08/2026]. Corroboré en 2002 : « The networks gnubg is using, we have 250 input nodes and 128 hidden nodes. That's 32640 weights. » [DÉCLARÉ — bug-gnubg 2002-09, https://lists.gnu.org/archive/html/bug-gnubg/2002-09/msg00004.html]
- **Race : 214 entrées.** Le changelog 0.13 documente le passage de 216 à 214 : « Remove 2 linearly dependent inputs from race net, and make the 14 'number of checkers off' exact… The net is exactly the same, but smaller and faster to compute. » [DOCUMENTÉ — http://www.gnubg.org/win32/Changes2003_1.html, consulté le 26/08/2026]. Le nombre de neurones cachés du net race **n'est pas confirmé de source primaire** (128 est attesté pour le net contact seulement). [HYPOTHÈSE]
- **Sorties = 5** : `#define NUM_OUTPUTS 5`, avec `OUTPUT_WIN, OUTPUT_WINGAMMON, OUTPUT_WINBACKGAMMON, OUTPUT_LOSEGAMMON, OUTPUT_LOSEBACKGAMMON`. [DOCUMENTÉ — eval.h]

**Tableau des tailles de réseau et MACs (calcul montré)**

Le MAC (multiply-accumulate) par évaluation d'un perceptron dense = Σ(entrées×cachées + cachées×sorties). Les biais ajoutent quelques MACs négligeables.

| Réseau | Entrées | Cachées | Sorties | MACs (calcul) | Confiance |
|---|---|---|---|---|---|
| Contact | 250 | 128 | 5 | 250·128 + 128·5 = 32 000 + 640 = **32 640** | Élevée (« 32640 weights » confirmé par les auteurs) |
| Crashed | 250 | 128 | 5 | idem = **32 640** | Élevée (même encodage/structure) |
| Race | 214 | 128 (présumé) | 5 | 214·128 + 128·5 = 27 392 + 640 = **28 032** | Moyenne (entrées sûres ; cachées présumées) |
| Élagage (contact) | 250 | ~10 | 5 | 250·10 + 10·5 = 2 500 + 50 = **2 550** | Moyenne (10 cachées cité en 2011) |
| Élagage (race) | 214 | ~10 | 5 | 214·10 + 10·5 = **2 190** | Moyenne |
| **gammonNet (réf.)** | 196 | 512·512·256·128 | 5 | 196·512+512·512+512·256+256·128+128·5 = 100 352+262 144+131 072+32 768+640 = **526 976** | — |

**Interprétation.** Le net contact de gnubg est **~16,1× plus petit** en MACs que gammonNet (526 976 / 32 640). Le soupçon « un ordre de grandeur plus petit » est donc exact et même un peu sous-estimé. En 2-ply, gnubg n'appelle en outre le grand net qu'aux feuilles retenues et utilise le net d'élagage (~2 550 MACs, ~13× plus petit encore que le contact et ~207× plus petit que gammonNet) aux nœuds internes ; cumulé au cache, cela explique l'essentiel du facteur 25–60×.

**Les entrées, une par une.** Le profil de `CalculateHalfInputs` (posté par Philippe Michel sur bug-gnubg) révèle les caractéristiques calculées **au-delà** de l'encodage brut de Tesauro (≈196 entrées : 4 unités × 24 points × 2 camps + barre/off). Les entrées additionnelles, une par demi-carte (par camp), sont [DÉCLARÉ — https://www.mail-archive.com/bug-gnubg@gnu.org/msg06912.html, consulté le 26/08/2026] :

- `I_BREAK_CONTACT` : pips nécessaires pour rompre le contact (dépasser le dernier checker adverse), normalisé.
- `I_FREEPIP` : pips « libres » derrière le dernier checker adverse.
- `I_TIMING` : mesure de timing (distribution des pips en excès sur les points intérieurs).
- `I_BACK_CHEQUER` : position du checker le plus arriéré (/24).
- `I_BACK_ANCHOR` : point de l'ancre la plus arriérée (/24).
- `I_FORWARD_ANCHOR` : ancre avancée.
- `I_PIPLOSS`, `I_P1`, `I_P2` : pertes de pips par tir subi et nombre de tirs touchant 1 / ≥2 checkers (exposition des blots).
- `I_BACKESCAPES`, `I_BACKRESCAPES` : nombre de tirs permettant d'échapper (Escapes / Escapes1) derrière le dernier checker adverse.
- `I_ACONTAIN`, `I_ACONTAIN2`, `I_CONTAIN`, `I_CONTAIN2` : force de containment (proportion de tirs bloqués), et son carré.
- `I_MOBILITY` : mobilité pondérée par les échappatoires adverses.
- `I_MOMENT2` : second moment de la distribution des checkers (dispersion).
- `I_ENTER`, `I_ENTER2` : facilité de rentrée depuis la barre.
- `I_BACKBONE` : structure de « colonne vertébrale » du prime (seule entrée non entière/normalisée, cf. remarque de Michel).
- `I_BACKG`, `I_BACKG1` : caractéristiques de backgame (checkers dans la zone 18–24).

Ces entrées ont été ajoutées empiriquement : Joseph Heled « removed some of the input nodes that he believed didn't contribute » et rejetait les entrées dont les poids « don't converge » [DÉCLARÉ — bug-gnubg 2002-09]. **La voie du projet** pour cataloguer ces entrées sans recopier de code : lancer gnubg et inspecter les entrées via le module Python embarqué / `gnubg-nn` (`board_from_position_id`, puis `probabilities(board, ply)`), ou `eval` sur des positions étalons.

#### A3. Classification des positions et discontinuités

La fonction `ClassifyPosition` (dans `eval.c`) décide de la classe. Définition de *crashed* par Joseph Heled : « CRASHED attempts to capture the positions where one side has only a small number of "active pieces". The number of active pieces has been **arbitrarily set at 6**, and the definition requires that you have at most 6 checkers not on points 1 or 2… The most important part… was to use a definition which is **non cyclic** — positions resulting from a crashed position should be crashed. When this is violated, performance deteriorates since each net is trained only on its own kind of positions. » [DÉCLARÉ — bug-gnubg 2012-02, https://lists.gnu.org/archive/html/bug-gnubg/2012-02/msg00022.html, consulté le 26/08/2026]

- Frontière **contact → race** : quand le contact est rompu (plus aucun checker d'un camp derrière un checker adverse).
- Frontière **contact → crashed** : ≤6 checkers « actifs » (hors points 1 et 2), non cyclique.
- Frontière **race → bearoff** : quand la position entre dans une base de fin de partie (15 checkers sur les 6 premiers points → base 1-sided ; positions à 2 camps entrant dans les bases 2-sided).

**Discontinuités.** L'existence de sauts d'évaluation aux frontières est **déclarée** par les auteurs comme motivation même du critère non cyclique et des « limiting cases » : Joseph Heled note qu'« it might be worthwhile to check if adding some "limiting" cases would improve the **transition gaps** » [DÉCLARÉ — bug-gnubg 2002-09]. **Aucune mesure publiée chiffrant l'amplitude** de ces discontinuités n'a été trouvée. [HYPOTHÈSE quant à l'ampleur — à mesurer soi-même : voir Recommandations.]

#### A4. Réseaux d'élagage (pruning networks)

Le manuel les documente : « A new feature in the evaluation is the use of a set of neural networks just to prune away move candidates within a deeper ply search. This increases the speed considerably and it doesn't lose much playing strength… Jim Segrave has just done an analysis of this and found that **less than 1 % of all moves come out different with the pruning nets activated. In most of these positions the move would not have made any difference to the game at all.** » [DOCUMENTÉ — manuel V0.16, https://www.gnu.org/software/gnubg/manual/html_node/Pruning-neural-networks.html + http://www.gnubg.org/documentation/doku.php?id=evaluation_settings, consultés le 26/08/2026]

Structure : origine chez un « very small network with only 5 hidden nodes… used to prune candidates for the real network » [DÉCLARÉ — bug-gnubg 2002-09] ; paramétrage ultérieur évoqué comme « 5 and 10 hidden nodes / 10 moves selected » [DÉCLARÉ — Philippe Michel, bug-gnubg, 16/02/2011, https://www.mail-archive.com/bug-gnubg@gnu.org/msg05763.html]. Une optimisation SSE de 2013 « constrains the size of the pruning nets' intermediate layer to be a multiple of 4 » [DOCUMENTÉ — ChangeLog, https://github.com/mormegil-cz/gnubg/blob/master/ChangeLog]. Les nets d'élagage partagent les entrées des grands nets (Michel les fait tourner « using the current weights file padded with zeroes at the right places »). Un par classe, 5 sorties. **Gain chiffré** : seule la borne « <1 % de coups différents » est publiée ; **aucun facteur de vitesse numérique propre** n'a été trouvé (le manuel dit « considerably »). [DÉCLARÉ / HYPOTHÈSE quant au facteur exact]

#### A5. Cache d'évaluation

`eval.h` : « Evaluation cache size is 2^SIZE entries », `CACHE_SIZE_DEFAULT 19` (soit 2¹⁹ = 524 288 entrées), `CACHE_SIZE_GUIMAX 23`. La clé combine la position et le contexte d'évaluation (cf. `EvalKey`, qui dépend de `evalcontext`, plies, cubeinfo, et cubeful). L'API `EvalCacheStats(pcUsed, pcLookup, pcHit)` expose les statistiques. [DOCUMENTÉ — eval.h]. Le ChangeLog note un relèvement ultérieur du défaut (« bump up evaluation cache size default x4 »). **Aucun taux de succès chiffré n'est publié** ; à mesurer soi-même via `EvalCacheStats`. [Non trouvé — voir « Ce que je n'ai pas trouvé »]

### B. La recherche

#### B6. Filtres de coups

Mécanisme documenté : gnubg génère tous les coups légaux, les évalue à 0-ply, puis à chaque sous-ply applique un **filtre à deux critères combinés** — un nombre de coups toujours acceptés (`Accept`) et un nombre de coups supplémentaires (`Extra`) retenus s'ils sont **dans un seuil d'équité** (`Threshold`) du meilleur. La structure `movefilter` de `eval.h` porte exactement ces trois champs (`Accept`, `Extra`, `Threshold`), avec `MAX_FILTER_PLIES 4`. [DOCUMENTÉ — manuel « Introduction to move filters », https://www.gnu.org/software/gnubg/manual/html_node/Introduction-to-move-filters.html ; eval.h]

Le principe illustré par le manuel : pour un 2-ply « Normal », le filtre 0-ply accepte 0 coup mais **ajoute jusqu'à 8 coups dans un seuil d'équité**, puis aucun élagage au 1-ply. Les présélections « accept 0 » servent à ne pas gaspiller de temps sur les coups évidents. [DOCUMENTÉ]. **Conformément au protocole du projet, les valeurs numériques exactes des présélections World Class / Supremo / etc. ne sont pas reprises ici** : ce sont des constantes réglées à la main. Le mécanisme (seuil + nombre, par sous-ply) suffit à reproduire l'architecture.

#### B7. Pourquoi le coût est-il presque plat avec la profondeur ?

Explication documentée, combinée :
1. **Filtres de coups** : le nombre de coups poussés au ply suivant est petit et borné (souvent ≤ quelques unités), donc la profondeur ne fait pas exploser le facteur de branchement des *coups* (le branchement des *dés*, 21 rolls distincts, reste lui présent). [DOCUMENTÉ]
2. **Réseaux d'élagage** aux nœuds internes (~13× moins de MACs que le grand net). [DOCUMENTÉ]
3. **Cache d'évaluation** (2¹⁹ entrées) : les positions récurrentes entre rolls et sous-arbres sont mémorisées. [DOCUMENTÉ]
4. **Troncature par bases de fin de partie** : dès qu'une branche entre dans une base bearoff, l'équité exacte remplace la descente. [DOCUMENTÉ — http://www.gnubg.org/documentation/doku.php?id=rollouts]

#### B8. Évaluation cubeful et décision de videau

gnubg part de la distribution cubeless (5 sorties) et calcule l'équité cubeful par la **transformation de Janowski** : E(cubeful) = E(dead)·(1−x) + E(live)·x, où E(dead) est l'équité cubeless, E(live) l'équité à videau parfaitement vivant (interpolation linéaire par morceaux entre points de take/cash), et **x le « cube-life index »** (efficacité du videau). [DOCUMENTÉ — manuel « Basic formula for cubeful equities », https://www.gnu.org/software/gnubg/manual/html_node/Basic-formula-for-cubeful-equities.html]

- Valeurs de x : le manuel énonce directement « the range 0.6 and 0.68 that gnubg uses for **long bearoffs and contact play, respectively** » (manuel, « Bearoff databases with GNU Backgammon »). Pour la course, l'interpolation est fondée sur le pip count : « A pip count of 40 gives x=0.6 and 120 gives x=0.7. If the pip count is below 40 or above 120 values of x=0.6 and x=0.7 are used, respectively. » [DOCUMENTÉ — manuel V0.16, « The cube efficiency », https://www.gnu.org/software/gnubg/manual/html_node/The-cube-efficiency.html]. **Ces coefficients sont des constantes réglées ; on décrit le mécanisme sans les reprendre comme base d'apprentissage.**
- **Plies supérieurs** : l'équité cubeful 2-ply se calcule par **récursion** — boucle sur les 21 rolls, meilleur coup, évaluation cubeful (n−1)-ply de la position résultante en tenant compte d'une décision de videau (max de no-double / double-take / pass). Le x n'intervient qu'au niveau 0-ply des feuilles. [DOCUMENTÉ — http://www.gnubg.org/documentation/doku.php?id=appendix]
- **Décision de videau** : `FindCubeDecision` / `FindBestCubeDecision` comparent les équités cubeful *optimal / no-double / take / drop* (énumération `CubefulOutputs`) et renvoient une `cubedecision` (double/take, double/pass, too-good, beaver, etc.). Pour les bases 2-sided, l'équité cubeful money est déjà tabulée. [DOCUMENTÉ — eval.h]

### C. L'entraînement

#### C9. Origine des poids

Méthode documentée en deux temps : **TD-learning** (auto-apprentissage à la TD-Gammon) pour amorcer, puis **apprentissage supervisé sur des bases de positions étiquetées par rollouts**. C'est l'apport signature de Joseph Heled : « The training method of supervised learning on a fixed dataset from rollouts » figure en tête de la liste de ses idées clés dans l'hommage posthume de la liste. [DÉCLARÉ — bug-gnubg, https://www.mail-archive.com/bug-gnubg@gnu.org/msg08480.html, consulté le 26/08/2026]. Heled lui-même : « I intend to add as many possible inputs… train, and then try to prune the non contributing ones… start big and work backwards » et « the importance of the data set used to train the net… nowadays I tend to see it as crucial. It takes me longer to generate it than to train the net. » [DÉCLARÉ — bug-gnubg 2002-09]

**Les benchmark/training databases** : ce sont des ensembles de positions (contact, crashed, race) roulées (rollouts) servant de cibles supervisées. Elles sont référencées explicitement (« the gnubg benchmark databases, which have positions represented as gnubg-nn position strings (20 characters, like JIGHPAABDAOAHDPAABDA) », Mark Higgins, 2023) et distinctes des IDs de position standard. [DÉCLARÉ — https://www.mail-archive.com/bug-gnubg@gnu.org/msg08175.html]. **Licence** : le code de rollout est « more or less Joseph Heled only code… released under GPL » ; le projet complet est GPL-3. Les données/poids (`gnubg.weights`, v1.01, ≈1,1 Mo — précisément 1 097 867 octets d'après gnubg-nn) sont distribués sous GPL. [DÉCLARÉ — https://www.mail-archive.com/bug-gnubg@gnu.org/msg08502.html ; https://github.com/alexstrehl/backgammon-ai-engine]. **La taille exacte** (nombre de positions) des benchmark databases n'a pas été trouvée de source primaire. [Non trouvé]

#### C10. Réseaux « supremo » et variantes

**« Supremo » n'est pas un réseau** mais un **niveau prédéfini** de réglage de recherche/filtres (`SETTINGS_SUPREMO`, entre World Class et Grandmaster ; cf. `NUM_SETTINGS 9` dans eval.h et le manuel « Defining move filters »). Il utilise les mêmes réseaux, avec une politique de filtre plus large (2-ply examinant plus de candidats). [DOCUMENTÉ — eval.h ; manuel]. Les niveaux vont de Beginner à 4-ply/Grandmaster. **Aucun jeu de poids alternatif nommé « supremo »** distribué séparément n'a été trouvé ; les variantes existantes sont les poids historiques par version (0.11 → 1.01) et des expérimentations privées (nets plus larges/profonds testés par des tiers comme wildbg ou Backgammon-NN, hors gnubg). [DÉCLARÉ]

### D. Où gnubg est faible

#### D11. Faiblesses reconnues (auteurs + mesures indépendantes)

- **Backgames / classe crashed** — la faiblesse la plus explicitement reconnue par l'auteur : « GNUbg **pathetic play in many backgame situations** leaves it open to abuse from humans. » [DÉCLARÉ — Joseph Heled, bug-gnubg 2012-02]. Cause structurelle : chaque net n'est entraîné que sur sa propre distribution, et la frontière crashed est « une célébration de décisions arbitraires ».
- **Bear-off avec contact** — « I am beginning to get the impression that GNU has a genuine weakness in bearoff positions WITH contact » (Robert-Jan Veldhuizen), avec exemples de jugements erronés à 2-ply. [DÉCLARÉ — bug-gnubg 2002-10, https://lists.gnu.org/archive/html/bug-gnubg/2002-10/msg00027.html]
- **Qualité des labels vs distribution** — une évaluation indépendante récente localise l'avantage de gnubg surtout dans le **jeu de contact** et attribue sa force aux **labels de rollout à faible variance**, pas à la taille du net : « The champion wins ~43 % (−0.20 PPG) against gnubg at 0-ply… A phase breakdown locates the gap in **contact play**; races and the bear-off are near-even. » [MESURÉ — Backgammon-NN / Whittington, protocole : head-to-head via Position ID partagé, ~32 process gnubg parallèles, https://whittingtonchess.com/backgammon-report, consulté le 26/08/2026]. Ordre de grandeur externe : gnubg 0-ply ≈ parité avec des nets tiers bien entraînés — wildbg « reaches an error rate of roughly 5.9 for 1-pointers when being analyzed with GnuBG 2-ply » (README wildbg, github.com/carsten-wenderdel/wildbg, jan. 2024) ; un net 561k-params bat gnubg 0-ply à 51,84 % en DMP. [MESURÉ — https://github.com/alexstrehl/backgammon-ai-engine]
- **Discontinuités de frontière de classe** — déclarées comme risque de « transition gaps » mais non chiffrées. [DÉCLARÉ]
- **Positions rares hors distribution du self-play** — reconnu implicitement par la démarche « limiting cases » et par les faiblesses backgame/crashed.
- **Efficacité du videau x** — « The cube efficiency is obviously an important parameter, unfortunately there haven't been much investigation carried out, so GNU Backgammon basically uses the values 0.6-0.7 originally suggested by Rick Janowski. » [DÉCLARÉ — manuel/appendix, http://www.gnubg.org/documentation/doku.php?id=appendix]

**Tableau des faiblesses documentées**

| Où | Ce qui est faible | Preuve | Ampleur chiffrée | Comment le projet pourrait le mesurer |
|---|---|---|---|---|
| Backgames / crashed | Jeu et évaluation faibles | Heled, bug-gnubg 2012-02 [DÉCLARÉ] | Non chiffrée | Rollouts longs de positions backgame étalons ; comparer eval 2-ply vs rollout |
| Bear-off avec contact | Jugements erronés à 2-ply | Veldhuizen, 2002-10 [DÉCLARÉ] | 4 erreurs relevées (anecdotique) | Batch d'evals contact-bearoff vs base exacte |
| Frontières de classe | Discontinuité d'équité | « transition gaps », Heled [DÉCLARÉ] | Non chiffrée | Balayer des positions de part et d'autre de la frontière crashed/contact/race et mesurer le saut d'équité |
| Jeu de contact (global) | Léger déficit vs meilleurs nets tiers | Whittington [MESURÉ] | Champion tiers −0,20 PPG vs gnubg 0-ply, ramené à la parité après distillation | Reproduire le head-to-head via Position ID |
| Efficacité videau x | Constante peu étudiée | manuel/appendix [DÉCLARÉ] | x = 0,6–0,68 fixe | Rollouts cubeful vs valeur interpolée |

#### D12. Bogues/limitations touchant la qualité d'évaluation

- **Comportement de `eval` vs profondeur** : `set evaluation chequerplay eval plies N` **n'affecte pas** la commande `eval`, qui calcule toujours la table statique/1-ply/2-ply complète ; c'est « quelle ligne on lit » qui décide de la profondeur. À connaître impérativement si gnubg sert d'oracle. [MESURÉ — Whittington, vérifié par comparaison octet à octet à N=0,2,3]
- **Positions répondues par les bases bearoff** n'impriment que la ligne statique — un parseur comptant les lignes « 2 ply: » échoue silencieusement (biais d'échantillon). [MESURÉ — Whittington]
- La plupart des bogues bug-gnubg/launchpad touchant `gnubg` sont **d'interface** (crashes GTK, mutex) et non la qualité d'évaluation. [DOCUMENTÉ — launchpad #1381751]

---

## Ce que je n'ai pas trouvé (honnête et explicite)

1. **Le nombre exact de neurones cachés du net race** (128 supposé par analogie ; non confirmé de source primaire).
2. **Le taux de succès du cache d'évaluation** — aucune valeur chiffrée publiée ; l'API `EvalCacheStats` existe mais aucun rapport de mesure trouvé.
3. **Un facteur de vitesse numérique propre aux réseaux d'élagage** (seule la borne « <1 % de coups différents » est publiée).
4. **La taille exacte (nb de positions) des benchmark/training databases** de Heled.
5. **Toute mesure chiffrée de l'amplitude des discontinuités aux frontières de classe.**
6. **Le nombre exact d'entrées « Tesauro pures » vs additionnelles** (196 + ~54 est une reconstruction ; le total 250 est sûr, la ventilation exacte reste à établir par inspection).
7. **Le nombre de neurones cachés final des nets d'élagage après la contrainte SSE « multiple de 4 »** (5→10→? ; probablement 8 ou 12, non confirmé).

---

## Recommandations

**Étape 1 — Établir la provenance vérifiable (avant toute conclusion).** Installer `gnubg-nn` (bindings Python, poids v1.01) ou lancer gnubg avec son interpréteur Python. Confirmer soi-même les tailles : charger une position (`board_from_position_id`), appeler l'évaluation et compter les MACs par classe. Cela transforme les [DÉCLARÉ] du tableau en [MESURÉ] locaux, sans recopier aucune constante GPL. **Seuil de décision** : si le net contact mesuré ≠ 250×128×5, réviser tout le calcul de MACs.

**Étape 2 — Mesurer l'écart de vitesse à sa source.** Chronométrer une évaluation 0-ply gnubg (grand net contact) vs une évaluation gammonNet sur la même position. Attendu : ratio MACs ≈ 16×. Si le ratio de temps observé ≫ 16×, l'écart vient d'ailleurs que la taille du net (SIMD, batch, allocations) — piste d'optimisation prioritaire côté gammonNet : batching et largeurs multiples de 8/16/32 (le rapport Whittington documente un gain de 2,5× rien qu'en passant l'inférence par batch).

**Étape 3 — Exploiter gnubg comme oracle différentiel là où il est faible.** Concentrer les mesures comparatives sur : (a) backgames/crashed, (b) bear-off avec contact, (c) positions de part et d'autre des frontières de classe. Générer des batteries de positions, comparer eval 2-ply gnubg vs rollout gnubg vs gammonNet. **Benchmark de bascule** : si gammonNet s'écarte de gnubg de plus que l'écart interne gnubg-2-ply/rollout, c'est gnubg qui est hors-cible (opportunité), pas gammonNet.

**Étape 4 — Mesurer les discontinuités de frontière soi-même** (personne ne l'a publié). Balayer une trajectoire de positions traversant la frontière crashed→contact et race→contact, tracer l'équité ; quantifier le saut. C'est un résultat original et directement utile pour justifier l'architecture à net unique de gammonNet (pas de frontière, donc pas de discontinuité) comme avantage qualitatif.

**Étape 5 — Décision d'architecture.** Ne pas copier le videau x ni les seuils de filtre de gnubg (GPL, réglés main). Réimplémenter les mécanismes (Janowski + filtre seuil/nombre) avec ses propres constantes. Conserver l'avantage « net unique » mais surveiller le coût : viser la parité MACs avec gnubg au niveau des feuilles via un net d'élagage maison (~2–3k MACs) si le 2-ply reste 25–60× trop cher.

**Tableau final de décision**

| Constat | Ce qu'il implique pour nous | Confiance | La mesure qui le confirmerait chez nous |
|---|---|---|---|
| Net contact gnubg = 250×128×5 = 32 640 MACs, ~16× < gammonNet | La taille du net est bien la source dominante de l'écart de vitesse | Élevée [DÉCLARÉ, cohérent avec « 32640 weights »] | Mesurer les MACs/temps d'une eval 0-ply via gnubg-nn et diviser par ceux de gammonNet |
| Nets d'élagage ~10 cachés (~2 550 MACs) aux nœuds internes, <1 % de coups changés | Un net d'élagage maison peut aplatir le coût en profondeur sans perte notable | Moyenne [DÉCLARÉ] | Ajouter un net d'élagage, mesurer coups différents (%) et gain de temps 2-ply |
| Coût plat en profondeur = filtres + élagage + cache + troncature bearoff | Il faut combiner les 4, pas seulement réduire le net | Élevée [DOCUMENTÉ] | Activer/désactiver chaque mécanisme et chronométrer isolément |
| Cubeful = Janowski (x=0,68 contact / 0,6 course) + récursion aux plies | Réimplémenter le mécanisme avec nos propres x ; ne pas copier les constantes | Élevée [DOCUMENTÉ] | Comparer notre cubeful à des rollouts cubeful gnubg |
| Faiblesse backgame/crashed reconnue par l'auteur | Cible prioritaire d'oracle différentiel et de démonstration de supériorité | Moyenne-élevée [DÉCLARÉ] | Rollouts longs sur positions backgame ; écart eval-2-ply vs rollout |
| Frontières de classe = discontinuités non chiffrées | Notre net unique évite le problème → argument architectural | Moyenne [DÉCLARÉ, ampleur HYPOTHÈSE] | Balayage d'équité à travers la frontière, mesurer le saut |
| `eval` gnubg ignore `plies N` ; bearoff n'imprime que le statique | Piège de parsing si gnubg est l'oracle | Élevée [MESURÉ, Whittington] | Comparer octet-à-octet la sortie `eval` à N=0/2/3 |

---

## Caveats

- Les tailles de réseau reposent surtout sur des déclarations d'auteurs sur bug-gnubg (fiables mais [DÉCLARÉ]), pas sur le manuel ; à confirmer par mesure locale (Étape 1). Le chiffre « 32640 weights » est cohérent avec 250×128+128×5 et donne confiance.
- Les extraits de `eval.h`/`CalculateHalfInputs` cités le sont **à des fins structurelles** (combien de neurones, quels noms d'entrées), conformément au protocole ; aucune constante réglée à la main (seuils de filtre, coefficients de videau) n'est reprise comme source d'apprentissage.
- Plusieurs sources tierces (readthedocs gnubg-nn, sites de jeu) parlent de « 250 entrées » pour *tous* les nets et de « six trained networks » — imprécisions probables (le net race a 214 entrées ; « six » mélange sans doute nets de position + nets d'élagage). Fiabilité moindre ; priorité donnée aux auteurs et au code.
- Le rapport Whittington est une source secondaire de haute qualité méthodologique mais externe à gnubg ; ses chiffres [MESURÉ] concernent un net tiers vs gnubg, pas gnubg dans l'absolu.
- Les faiblesses « backgame/crashed » sont anciennes (2002–2012) ; les poids v1.01 actuels peuvent avoir évolué. À revérifier sur la version courante.