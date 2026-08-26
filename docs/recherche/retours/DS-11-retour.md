# DS-11 — eXtreme Gammon comme référence — retour

**Date de la recherche** : 2026-08-26 · **Outil** : Claude, recherche approfondie
**Prompt** : `docs/recherche/DS-11-extreme-gammon-comme-reference.md`, version injectée du 2026-08-27

> **Ce que ce retour décide** : comment se comparer à XG — ou, si c'est impraticable, par quoi le
> remplacer honnêtement dans l'énoncé de l'objectif.
> **Ce qu'il conclut** : XG est praticable comme instrument mais **sans API ni CLI** — uniquement
> Batch Analysis/Rollout en GUI sous Windows ou Wine, verdicts extraits en parsant les `.xg`
> (format officiellement public, parseurs libres `xgdatatools`) ; la voie principale recommandée
> est **indirecte** : composer notre équivalence gnubg 2-ply, déjà mesurée, avec le calage tiers
> gnubg↔XG (bgsage « Méthode 3 » : PR moyen identique 4,36 des deux côtés sur 580 notations,
> différence +0,002 ±0,03, r = 0,98), XG ne servant qu'en contrôle ponctuel sur sous-échantillon ;
> et toujours rapporter **deux chiffres** — erreur d'équité par décision ×500 à filtre identique,
> et « PR façon XG » (exclusion des coups « non obvious ») — jamais un mEMG gnubg ÷ 2. À plies
> appariés (XG n-ply = gnubg (n−1)-ply), l'écart XG/gnubg mesuré est petit et les chiffres
> favorables à XG (Depreli 2012) sont arbitrés par XG lui-même.
> **Ce qu'il ne tranche pas** : l'architecture interne d'XG (folklore, rien d'éditeur), le
> facteur chiffré de sa réduction de variance, l'ordre exact des champs XGID (implémentations
> tierces, à valider contre gnubg avant usage) ; **aucun EULA desktop publié** — un vide
> documentaire à gérer par prudence, pas une autorisation ; l'étude bgsage n'est répliquée par
> aucun tiers.

---
# eXtreme Gammon (XG) comme instrument de mesure pour gammonNet : ce qu'on sait, comment on compare, et si c'est praticable

## TL;DR
- **XG peut servir d'oracle de mesure, mais uniquement en mode « GUI piloté par lot » (Batch Analysis / Batch Rollout) sous Windows ou Wine ; il n'existe ni API, ni CLI, ni mode serveur.** Le chemin praticable est exactement celui déjà exécuté publiquement par l'étude Open Sage vs XG (bgsage.ai, 2026) : exporter les positions en texte importable, lancer Batch Analysis à un niveau personnalisé, puis parser les fichiers `.xg` produits avec la bibliothèque libre `xgdatatools`. C'est faisable chez le demandeur sans jamais intégrer de données XG dans l'artefact.
- **La question « XG plus fort que gnubg, de combien ? » a une réponse mesurée et modeste** : à profondeur appariée la différence est petite et se joue surtout sur le videau ; l'étude Open Sage 2026 trouve XG et un moteur moderne « statistiquement indiscernables » sur 290 matchs de tournoi (PR moyen identique de 4,36 ; différence moyenne +0,002, IC 95 % ±0,03, p = 0,90, r = 0,98). Attention : la plupart des chiffres « XG bat gnubg » proviennent d'études arbitrées **par XG lui-même** (circularité).
- **Aucun EULA formel du produit desktop n'existe en ligne** ; le format de fichier `.XG` est officiellement documenté et « peut être librement redistribué », et des parseurs tiers sous licence libre (GPL/LGPL, MIT) existent. Le PR d'XG et le taux d'erreur de gnubg **ne sont pas directement comparables** sans réaligner la définition de « décision ».

*(Étiquettes : [ÉDITEUR] documentation officielle ; [MESURE] mesure tierce avec protocole décrit ; [DÉCLARÉ] affirmation d'une personne identifiée sans protocole publié ; [FOLKLORE] croyance répandue sans source primaire traçable. Sources consultées le 26 août 2026.)*

---

## A. Ce qu'est XG, techniquement

### A1. Architecture

**Origine et langage.** [DÉCLARÉ — Xavier Dufaure de Citres, GameSite 2000, rec.games.backgammon, groups.google.com/g/rec.games.backgammon/c/JmceUc8UYl0] « In 2001 when the first version of XG was put on GammonSite, I got a jump start on how to program a Neural Network from Gary Wong's gnubg 0.02. However since then it was completely reprogrammed (using Delphi). That's one of the reason is it playing quite differently than GnuBG and is much faster. » Le moteur est donc écrit en Delphi (Pascal), initialement inspiré de gnubg 0.02 puis entièrement réécrit.

**Type de réseau.** [FOLKLORE] La communauté suppose un perceptron multicouche (MLP) à une couche cachée, comme TD-Gammon/gnubg/BGBlitz ; un intervenant technique sur 2+2 (forumserver.twoplustwo.com/.../how-good-extreme-gammon-1784439) écrit : « GnuBG, TD_Gammon and BGBlitz I'm sure about that architecture. XG, Snowie and Jellyfish most probably do the same ». **Aucune source primaire éditeur** ne confirme le nombre de couches, la taille des couches cachées, ni l'encodage des entrées d'XG. La page Grokipedia avance « ~150 unités d'entrée, 5 sorties » : **à écarter comme source** (générée par IA, non vérifiable). Le seul élément robuste est la structure de sortie documentée par l'éditeur (extremegammon.com/xgformat.aspx) : `TResult = array [0..6] of single` = *lose bg, lose G, lose S, win S, win G, win BG, équité normalisée* — soit les 5 probabilités sans videau standard + l'équité.

**Classes de position.** [FOLKLORE] La distinction contact / course (race) / crashed est standard dans gnubg et communément supposée pour XG, mais **non documentée publiquement par l'éditeur**.

**Tables de fin de partie (bearoff).** [ÉDITEUR — bannière « About » du programme, reproduite sur bgonline.org/.../read=50584] « Bearoff Database: One-Sided: 15 checkers over 6 points ; Two-Sided: 6 checkers over 6 points ». [ÉDITEUR — manuel/Manualzz] L'utilisateur peut générer des bases plus grandes (jusqu'au 13e point en one-sided) mais ne peut en charger en mémoire que jusqu'au 11e point ; au-delà elles ne servent qu'à l'affichage de l'EPC (Effective Pip Count : « For displaying EPC, eXtreme Gammon will always use the largest database on file »). Le two-sided (exact) embarqué est donc modeste (6 pions / 6 points), nettement en deçà de ce que gnubg peut générer (jusqu'à 8×6 exact, 15/10 one-sided).

**Modèle de videau (cubeful equity).** [ÉDITEUR — structure de fichier] La structure `EngineStructDoubleAction` stocke les équités « No Double / Double-Take / Double-Drop » (`equB`, `equDouble`, `equDrop`) et une MWC, confirmant une gestion cubeful complète avec table d'équité de match paramétrable (le manuel expose le choix de la Match Equity Table).

### A2. Les niveaux d'analyse

[ÉDITEUR — table PLAYERLEVEL du format officiel, xgformat.aspx] Niveaux internes numérotés : 0 = 1-ply, 1 = 2-ply, 2 = 3-ply, 12 = 3-ply red, 3 = 4-ply, 4 = 5-ply, 5 = 6-ply, 6 = 7-ply, 100 = Rollout, 1000 = XGRoller, 1001 = XGRoller+, 1002 = XGRoller++ (plus 999/998 = Opening Book v1/v2).

[ÉDITEUR — documentation XG2 / extremegammon2.pdf] Niveaux « joueur » et Elo relatif publié par l'éditeur : XG Roller (rollout tronqué à 6 ply) ; eXtreme Gammon 3-ply (Elo 2254) ; Champion = 3-ply Reduction (sampling), ~2× plus rapide, 2249 ; Professional = 2-ply, 2228 ; Expert = 1-ply, 2201 ; Advanced/Intermediate/Beginner/Distracted = 1-ply avec bruit croissant (2201→1435).

[ÉDITEUR — extremegammon.com/Searchinterval.aspx] Le « search interval » (équivalent du move filter de gnubg) : en 3-ply, l'intervalle Normal analyse jusqu'à ~4 coups dans les 0,160 d'équité du meilleur ; « Huge » monte à 8 coups. L'éditeur chiffre l'effet : en XG2, l'intervalle Normal ne coûte que 0,95 Elo (0,03 PR) par rapport à un intervalle infini en 3-ply, et 0,59 Elo (0,018 PR) pour XGR++.

[MESURE — étude Open Sage 2026, bgsage.ai/botperformance] Décomposition observée des « Roller » : **XG Roller++ = rollout tronqué à décisions 3-ply, troncature à 7 coups ; XG Roller+ = décisions 2-ply ; XG Roller = décisions 1-ply, troncature 5 coups, 42 chemins**. Correspondance de profondeur importante : [DÉCLARÉ — Xavier & Neil Kazaross, cité sur twoplustwo] « XG 3-ply = gnubg 2-ply » (les plies d'XG sont décalés de 1 par rapport à gnubg).

**Temps par décision.** [ÉDITEUR — studies.aspx] Les tests de vitesse (Core i7, session money + match) sont publiés par GameSite 2000 mais **l'éditeur précise lui-même** : « The speed test were performed by GameSite 2000 ltd and are not from an independent source. » Ils donnent des rapports relatifs (« XGR+ plus rapide que Snowie 3-ply »), pas des temps absolus par décision reproductibles.

### A3. Réduction de variance

[ÉDITEUR — manuel XG2 / Manualzz] « Variance Reduction is a system where the luck of each roll is calculated and added to the final result. Each game will take longer to evaluate (for instance, for a 1-ply rollout, each position needs to be evaluated in 2-ply to determine the luck of each roll, so the rollout will take about 21 times longer). On the other hand, because the results of each game will be very close, the standard deviation will be much smaller and fewer games will be needed. » L'éditeur recommande la VR **systématiquement** en 3-ply, et note qu'en 1-ply le surcoût la rend peu intéressante (« ~15 % d'amélioration sur le temps »). **L'éditeur ne publie pas de facteur de réduction de variance chiffré** (type « efficacité ×N »).

[DÉCLARÉ — Neil Kazaross, bgonline.org/.../read=164612, 2014] Sur une position de containment : « XG needs approximately threefold trials to achieve similar reported accuracy to gnubg » — à IC rapporté égal, XG demanderait ~3× plus d'essais. Ceci mêle réduction de variance ET mode de calcul de l'IC ; à interpréter comme une **impression outillée**, pas comme une mesure de la VR seule. Le cadre théorique de référence (VR par correction de chance à moyenne nulle) est celui décrit par David Montgomery (bkgm.com/articles/GOL/Feb00/var.htm), identique en principe à la VR de gnubg.

---

## B. La comparaison telle qu'elle se pratique

### B4. XG plus fort que gnubg, de combien ?

**Étude Depreli 2012 (référence historique).** [MESURE, avec forte réserve de circularité — extremegammon.com/studies.aspx ; source primaire bgonline.org/.../read=114338] « Published on BGonline.org (on January 28th 2012)… Using 500 money games any difference of opinion is analyzed very deeply using a rollout… more than 5000 moves or cube decisions… (Rollout parameters: 3-ply Checker, XGRoller For cube, Roll until the 95% confidence of the equity is less than 0.005, minimum 1296 trials). » **Les rollouts d'arbitrage sont faits avec XG2 lui-même.** Résultats (équité normalisée → PR) :

| Programme / niveau | Total équité perdue | PR |
|---|---|---|
| XG2 XGRoller++ | 4,097 | 0,11 |
| XG2 XGRoller+ | 6,487 | 0,18 |
| XG2 5-ply | 8,969 | 0,25 |
| XG2 4-ply | 11,936 | 0,33 |
| GnuBG 1.00 4-ply | 12,536 | 0,35 |
| XG2 XGRoller | 14,887 | 0,41 |
| XG2 3-ply | 16,231 | 0,45 |
| GnuBG 1.00 3-ply | 16,775 | 0,46 |
| GnuBG 1.00 2-ply | 20,951 | 0,58 |
| XG2 3-ply Red | 23,173 | 0,64 |
| BGBlitz 2.8 4-ply | 32,485 | 0,90 |
| Snowie 4 3-ply | 45,003 | 1,24 |

**Lecture critique :** à plies appariés (XG 3-ply ≈ gnubg 2-ply ; XG 4-ply ≈ gnubg 3-ply), XG apparaît devant, mais l'écart gnubg 4-ply (0,35) vs XG 4-ply (0,33) est minuscule. Surtout, **l'arbitre est XG** : tout moteur jugé par ses propres rollouts est avantagé. Ce tableau ne peut donc pas servir d'oracle neutre — c'est précisément le piège que le protocole du demandeur cherche à éviter.

**Étude Open Sage vs XG (bgsage.ai, 2026) — la plus proche méthodologiquement du protocole du demandeur.** [MESURE] Elle exécute presque exactement le protocole visé par gammonNet : vérité-terrain en trois passes escaladées — accepter le 3-ply quand l'écart meilleur/second > 0,05 ; sinon rollout tronqué 3T (écart > 0,02) ; sinon rollout complet « run in batches of 1,296 paths until the 95% confidence band on the equity falls under 0.005 — or a ceiling of 20,736 paths (16 × 1,296) is reached ». PR = erreur moyenne d'équité par décision × 500. Composition money : 7 652 décisions réglées en 3P, 3 260 en 3T, 5 977 par rollout complet (16 889 positions / 17 535 décisions). Point décisif : la comparaison est **reconstruite en prenant tour à tour la vérité-terrain de Sage PUIS celle de XG**, pour neutraliser l'avantage du terrain. Résultats money :

| Niveau | Sage | XG |
|---|---|---|
| Rollout tronqué fort (3T / Roller++) | 0,21 | 0,32 |
| 2T / Roller+ | 0,26 | 0,41 |
| 1T / Roller | 0,50 | 0,53 |
| 4-ply | 0,41 | 0,46 |
| 3-ply | 0,58 | 0,57 |

En match 5 points (18 292 décisions) : Sage 3T 0,19 vs Roller++ 0,35. Scoré contre **la propre vérité-terrain de XG**, Sage 3T reste devant (0,26 vs 0,33) ; en 3-ply, « effectively tied — XG 3-ply ahead by 0.01 PR » (0,57 vs 0,58). Sur les positions « disputées » (1 357 désaccords checker arbitrés par les DEUX rollouts) : « Matched the best move — by XG's own rollout : 44.4 % [Sage 3T] vs 39.3 % [XG Roller++] vs 16.3 % [Neither] », erreur d'équité moyenne Sage 3T 0,0027 vs XG Roller++ 0,0048 (PR 1,34 vs 2,39). **Réserve honnête** : c'est l'auto-étude d'un produit concurrent (Backgammon Sage Pro) ; le moteur Open Sage est libre (MPL-2.0, github.com/markbgsage/bgsage) et le pipeline reproductible, mais les chiffres n'ont **pas** été répliqués par un tiers indépendant.

**Le résultat le plus directement transposable pour gammonNet** [MESURE — bgsage.ai « Méthode 3 »] : sur **290 matchs de tournoi 7-points de 2026** (UBC Texas 100, UBC Istanbul 146, UBC Japan 44, fournis par Máté Fehér), déjà analysés dans XG puis ré-analysés dans Sage, le PR attribué à chaque joueur (580 notes) : PR moyen **identique de 4,36** des deux côtés ; différence moyenne **+0,002 PR** (« statistically indistinguishable from zero… 95% confidence interval ±0.03, p = 0.90 »), écart-type 0,37, corrélation **r = 0,98**. Un moteur moderne fort et XG donnent donc des PR pratiquement identiques sur des matchs humains — exactement le type de preuve d'équivalence que le demandeur cherche à produire.

**Consensus qualitatif.** [DÉCLARÉ] Sur bgonline (« Should I switch from GNUbg to XG? »), l'avis dominant : « XG+ beats the opposition by a clear amount, with Snowie and GnuBG basically tied » — mais daté (gnubg 3-ply mal réglé pour le videau y était pénalisé). [DÉCLARÉ — F. Ariis / liste gnubg, cité sur twoplustwo] « On average XG thinks that GNUbg plays with a 0.5 PR and GNUbg that XG does with an error rate of 1 or thereabouts. On a small sample of more haphazard human play the discrepancies may be larger. » Les deux moteurs se jugent mutuellement très forts ; l'écart réel est faible.

### B5. L'échelle de PR d'XG et sa comparabilité avec gnubg

**Définition PR.** [ÉDITEUR — Wikipedia citant XG + manuel] PR = équité normalisée perdue par décision **× 500** ; « Only decisions not considered to be 'obvious' are counted ». [ÉDITEUR — Xavier, rec.games.backgammon] Formule Elo : approximation `Elo = 2240 − performance × 16500` ; formule exacte `result := 1/(1+exp(−performance×40−1.12))×2000+732`, où performance = « equity lose / number of decision ».

**Définition de « décision ».** [ÉDITEUR — bgonline.org/forums/.../read=56787] « A decision is a checker move or a cube double that is considered non obvious by the computer » — les coups forcés ET « non obvious » sont exclus du dénominateur ; seuil de blunder 0,084. Grille officielle : World Champ 0,0–2,5 (Elo 2162-2240) ; World Class 2,5–5,0 ; Expert 5,0–7,5 ; Advanced 7,5–12,5 ; Intermediate 12,5–17,5 ; etc.

**Pourquoi la comparaison directe avec gnubg est piégée.** [MESURE/DÉCLARÉ — manuels gnubg + liste bug-gnubg] Trois normalisations coexistent :
- **Snowie ER** = erreurs du joueur / nombre de coups des **deux** joueurs.
- **gnubg mEMG** (« error rate per decision ») = erreurs / coups **non forcés du seul joueur**, ×1000 par défaut ; d'où « gnubg error rates will be about double the Snowie error rate » (facteur ~2 ; ~1,4× pour l'ER par coup sur ~300 matchs).
- **XG PR** : Xavier a calculé l'erreur « à la manière de gnubg » (coups non forcés du joueur) **puis divisé par 2** pour retomber sur l'échelle Snowie familière — d'où le ×500 (au lieu du ×1000 de gnubg). MAIS XG **retire en plus** du dénominateur les décisions « non obvious » (courses décidées, etc.), si bien que son dénominateur est un peu plus petit que celui de gnubg.

**Conversion pratique.** Un PR XG et l'« error rate mEMG » de gnubg **ne sont pas la même quantité** : diviser un mEMG gnubg par ~2 donne un ordre de grandeur du PR, mais l'égalité exacte échoue parce que (a) la définition de « décision » diffère et (b) les conventions de normalisation d'équité diffèrent. [DÉCLARÉ — Tim Chow, timothychow.net/cg/…/197598] « Replicating PR would require some additional programming since it's not quite the same as GNU's native error rate calculation » ; la définition XG de la décision a des « pathologies ». **Conséquence pour gammonNet** : pour produire un nombre directement comparable au PR d'XG, il faut soit reproduire le filtre de décision d'XG (exclusion des coups « non obvious »), soit — plus propre — comparer sur une base « erreur moyenne d'équité par décision » avec un filtre de décision **identique appliqué aux deux moteurs** et le même ×500, ce que fait l'étude bgsage.

### B6. Usages d'XG comme référence dans la littérature technique

[MESURE] Quand un auteur écrit « PR 0,22 mesuré par XG », la chaîne typique est : match transcrit en `.mat`/format Snowie → importé dans XG → **Analyze** à un niveau nommé (manuel : « Quick / Standard / Thorough = 3-ply, XGR++ sur erreur ou différence de cube / Extensive = 3-ply + rollout sur erreurs »), l'analyse pouvant se faire en une ou deux passes (la 2e, plus forte, déclenchée quand le choix du joueur diffère du choix machine) → PR lu dans le rapport, exportable en HTML/texte. [MESURE — github.com/alexstrehl/backgammon-ai-engine] Des projets de recherche récents rapportent des « XG++ PR » comme métrique de force de réseaux (valeurs 0-ply, IC bootstrap), en scorant des parties de self-play. **À retenir** : « PR mesuré par XG++ » n'est fiable que si le niveau d'analyse, le format d'import et la passe (simple/double) sont précisés ; beaucoup de chiffres cités ne le font pas.

---

## C. La praticabilité

### C7. Faire tourner XG comme oracle, en lot et sans GUI ?

[ÉDITEUR + MESURE] **Il n'existe ni API, ni interface en ligne de commande, ni mode serveur.** L'étude bgsage l'affirme explicitement : « the XG desktop app exposes no programmatic interface, so feeding positions and moves between the two engines is a manual, click-through process… Because XG has no API, we ran its Batch Analysis. » Ce qui existe :
- [ÉDITEUR — Majorfeatures.aspx] **Batch Analysis** et **Batch Rollout** : fonctions GUI qui analysent/roulent en une passe non surveillée des centaines de parties transcrites, avec option « Save Games after analyze » écrivant un `.xg` par partie.
- [ÉDITEUR] **Import** des formats standard : `.mat` (Backgammon Match), texte Snowie, Jellyfish, SGG (GridGammon) ; **export** HTML/texte ; copier-coller d'XGID.
- [DÉCLARÉ — éditeur, bgonline.org/.../read=172306, 18 janvier 2015] Wine/Linux/Mac : « It came to my attention… that the latest version of CrossOver (or Wine) now run XG2 correctly… I am looking for feedback… before officialy endorsing that as a viable solution for Mac and Unix users. » Tutoriels tiers documentant l'installation sous Wine/CrossOver (Medium, Thomas Koch) ; fiche CodeWeavers/CrossOver dédiée. **Aucune fiche WineHQ AppDB spécifique à XG n'a été trouvée.**

**Le mécanisme d'oracle praticable** consiste à piloter la GUI en lot : alimenter XG en milliers de positions via des transcriptions importables, lancer Batch Analysis/Rollout à un niveau personnalisé, puis récupérer les verdicts en parsant les `.xg` — exactement le pipeline reproductible publié par bgsage (scripts `benchmark_pr_xg.py`, `xg_benchmark_report.py`). Une automatisation de l'IHM (type `pywinauto`/`pyautogui`) est possible : le projet libre **AnkiGammon** (MIT) intègre un moteur d'analyse XG « via UI automation, Windows only, experimental », pilotant `eXtremeGammon2.exe`.

### C8. Ce que la licence permet

[ÉDITEUR — recherche dédiée] **Aucun EULA/Terms of Use formel du produit desktop n'a été trouvé en ligne** : ni sur extremegammon.com (pas de page « Terms/Legal/License » dans la navigation), ni dans le manuel PDF officiel (aucune section licence), ni dans les fiches App Store/Google Play (seul le boilerplate de plateforme). Le seul texte à caractère contraignant publié est la section « Register » du manuel :
- « GameSite 2000 Ltd. reserves the right to void any activation key in case of improper use. » (« improper use » n'est **pas défini**).
- Règles d'activation par ordinateur, transférables ; « Do not give out your activation key. »

Sur les points précis demandés, **le texte publié est muet** :
1. **Analyser des positions et publier les chiffres** : aucune clause ne l'autorise ni ne l'interdit. Le manuel encourage au contraire la publication (fonction « Export To HTML… to print or publish the match on a web site » ; bannière de diffusion).
2. **Usage automatisé/en lot** : aucune clause. Le programme fournit lui-même Batch Analysis/Rollout ; aucune interdiction de pilotage externe n'est écrite.
3. **Rétro-ingénierie** : aucune clause d'interdiction. Au contraire, l'éditeur a **publié volontairement** le format `.XG/.XGP` — « (c) 2009-2014 GameSite 2000 Ltd; This information can be freely redistributed » (xgformat.aspx) — et salué le parseur tiers de Michael Petch (« I finaly made the XG (and XGP) file format public », bgonline.org/.../read=152155).
4. **Benchmarking publié** : aucune clause. XG publie lui-même des comparaisons (« Independent Studies »).
5. **Redistribution** : aucune clause sur le binaire ; la seule mention « freely redistributed » vise la **documentation du format de fichier**, pas le logiciel.

**⚠️ Grokipedia** affirme des « licensing terms restrict use to personal, non-commercial purposes… prohibiting redistribution » : **non vérifiable, aucun texte XG réel ne contient ce libellé** — à ne pas citer comme source. **Implication opérationnelle** : en l'absence d'EULA publié interdisant l'analyse, la publication de chiffres, l'automatisation ou le benchmarking, le risque documentaire est faible ; il reste prudent de vérifier un éventuel clic-through présenté par l'installateur (non reproduit en ligne) et de ne jamais redistribuer le binaire ni des poids/tables XG. Cela respecte la contrainte impérative : XG reste un instrument, jamais une source de données pour l'artefact.

### C9. Les formats

**Format binaire `.XG/.XGP`** [ÉDITEUR — xgformat.aspx] : entièrement documenté (fichier `XG_format.pas` + structures Pascal `TRichGameHeader`, `TSaveRec`, `EngineStructBestMove`, `EngineStructDoubleAction`, `TRolloutContext`), avec la mention « This information can be freely redistributed ». Le fichier est un RichGameFormat (en-tête magique `RGMH`) contenant des flux compressés zlib (`temp.xg`, `.xgi` index, `.xgr` rollouts, `.xgc` commentaires RTF). La structure expose tout ce dont un oracle a besoin : position (`PositionEngine = array[0..25] of ShortInt`), niveau d'analyse (table PLAYERLEVEL), équités 5-sorties + équité normalisée, choix machine (`Choice0` 1-ply, `Choice3` 3-ply), index de rollout, et contexte de rollout complet (`TRolloutContext` : troncature, VR on/off, seed, IC 95 % `Error1/Error2`, nombre d'essais).

**Parseurs tiers sous licence libre** [MESURE] :
- **xgdatatools** (Michael Petch) — Python, lit/parse `.xg/.xgp`. Sources GPL-3.0 (`xgstruct.py`, `extractxgdata.py`) et LGPL-3.0 (`xgimport.py`) ; miroirs GitHub `oysteijo/xgdatatools` (LGPL-2.1), `zkitX/xgdatatools`, `EvanMKO/xgdatatools`. **Outil de référence pour extraire les verdicts d'XG en lot.**
- **bgfparser** (`kevung/bgfparser`, Go, MIT) — parse et expose XGID, équités cubeful/cubeless, décisions de videau (MWC, EMG).
- **AnkiGammon** (`Deinonychus999/AnkiGammon`, MIT), **xgid2anki** (`ngvlamis/xgid2anki`), **ankigammon** (PyPI) — lecteurs XGID + import `.xg`.
- **bglab** (R, `lassehjorthmadsen/backgammon`) — convertisseur d'ID gnubg ↔ XGID (`gnuid2xgid`).

**Structure de l'XGID** [MESURE — reverse-engineering communautaire ; PAS documenté par l'éditeur] : chaîne `XGID=<26 caractères de position>:<champ1>:…:<champ9>`. Exemple : `XGID=---BBBBAAA---Ac-bbccbAA-A-:1:1:-1:63:4:3:0:5:8`. Les 26 caractères encodent les points (tiret = vide ; majuscules A,B,C… = pions du joueur au trait par nombre croissant ; minuscules a,b,c… = pions adverses). Les 9 champs séparés par `:` encodent, dans l'ordre communément implémenté (AnkiGammon, apbg.net, bglog.org) : valeur du videau (log2), position/possession du videau (0 centre, +1/−1), joueur au trait (1/−1), dés, score joueur bas, score joueur haut, drapeau Crawford/Jacoby, longueur du match, videau maximal. **Réserve** : cet ordre provient d'implémentations tierces, non d'une spéc éditeur ; à valider contre gnubg (qui reconnaît nativement l'XGID) sur un jeu de positions test avant usage en production.

**Convertisseurs XG → .mat/.sgf** : [DÉCLARÉ — Michael Petch, groups.google.com] `extractxgdata` n'était « pas un utilitaire mat » mais une base pour bâtir d'autres outils ; un script AWK tiers convertit sa sortie texte en `.mat`. **Il n'existe pas d'outil « extremegammon-to-gnubg » packagé et maintenu de référence** — la conversion passe en pratique par gnubg (qui lit XGID) ou par les parseurs ci-dessus.

### C10. S'il est impraticable, par quoi le remplacer ?

XG **est** praticable comme instrument (C7), mais fragile (GUI, Windows/Wine, pilotage IHM non officiel). Substituts et compléments honnêtes, tous compatibles avec la contrainte « rien de non libre dans l'artefact » :

1. **Chaîne indirecte via un moteur commun (recommandée en premier).** gammonNet mesure déjà son équivalence à gnubg 2-ply. Il suffit de mesurer, une fois, **gnubg vs XG par un tiers** (ou de réutiliser un ancrage publié) pour transporter la mesure. C'est ce que fait la Méthode 3 de bgsage (PR quasi identiques XG/moteur moderne, différence +0,002). Combiné à « gammonNet ≡ gnubg », cela borne l'équivalence à XG **sans jamais exécuter XG chez le demandeur**.
2. **Positions de référence rollées et publiées.** Rollouts de référence de la communauté (bgonline.org, « benchmark positions », rollouts d'ouvertures/réponses de Stick & Depreli) : vérité-terrain indépendante d'XG. **Vérifier les conditions d'usage** de chaque jeu (souvent partageables sur bgonline, mais à confirmer au cas par cas).
3. **Corpus analysés par XG et publiés par des tiers** (ex. matchs `.xg` de finales de championnat diffusés) : utilisables comme points de calage **de mesure**, jamais comme données d'entraînement.
4. **Moteurs forts et libres/accessibles comme oracles alternatifs** : **gnubg** (rollouts 3-ply/4-ply, base two-sided exacte, VR) reste l'oracle libre de référence ; **Open Sage** (MPL-2.0, `markbgsage/bgsage`) est un moteur moderne libre au pipeline de benchmark reproductible et déjà calé sur XG. Utiliser gnubg comme arbitre principal et XG comme **contrôle ponctuel** est la stratégie la plus robuste et la plus défendable.

**Conclusion de praticabilité :** faire d'XG un oracle automatisé est possible mais coûteux et non officiellement outillé ; le meilleur rapport rigueur/effort est **gnubg comme arbitre reproductible + un calage ponctuel gnubg↔XG (ou la réutilisation du calage bgsage) + XG en Batch pour un sous-échantillon de contrôle**.

---

## Le chemin praticable (résumé opérationnel)

La façon la plus simple, chez le demandeur, de produire une comparaison chiffrée à XG :
1. **Figer un sous-corpus de contrôle** (par ex. les 10⁴–10⁵ décisions « disputées » où gammonNet et gnubg divergent), déjà stratifié par classe de position/contexte de score et versionné.
2. **Exporter ces positions/parties** au format `.mat` ou texte Snowie (formats qu'XG importe nativement).
3. **Installer XG2 sous Wine/CrossOver** (endossé par l'éditeur) sur une machine de mesure isolée.
4. **Lancer Batch Analysis** à un niveau personnalisé calqué sur le protocole (3-ply partout, escalade XGR++ sur désaccord ; Batch Rollout pour les positions restant sous 0,02), « Save Games after analyze » activé.
5. **Parser les `.xg`** avec `xgdatatools` (libre) pour extraire, par position, le coup choisi et l'équité XG.
6. **Scorer** avec le même filtre de décision et le même ×500 appliqués à gammonNet et à XG, bootstrap par position ; pour la comparabilité au « PR » d'XG, reproduire l'exclusion des coups « non obvious ».
7. **Alternative sans exécuter XG** : composer « gammonNet ≡ gnubg 2-ply » (déjà mesuré) avec un calage gnubg↔XG tiers (Depreli, en corrigeant la circularité ; ou la Méthode 3 de bgsage).

XG n'entre jamais dans l'artefact distribué : il n'est qu'instrument de mesure, et aucune donnée/poids/table XG n'alimente l'entraînement.

---

## Ce que je n'ai pas trouvé

- **Architecture exacte du réseau XG** : nombre et taille des couches cachées, encodage précis des entrées, nombre de réseaux par classe de position — **non publiés par l'éditeur** ; les affirmations trouvées sont du folklore ou de l'IA non vérifiable (Grokipedia).
- **Facteur de réduction de variance chiffré** par l'éditeur (type « efficacité ×N ») : non publié ; seulement la description qualitative et le « ~21× plus lent en 1-ply ».
- **Temps absolus par décision** reproductibles à chaque niveau, sur matériel spécifié : l'éditeur ne publie que des ratios relatifs et prévient qu'ils ne sont pas indépendants.
- **Spécification éditeur de l'XGID** (la chaîne, pas le fichier binaire) : introuvable ; seules des implémentations tierces la décrivent, avec un risque d'erreur sur l'ordre exact des champs.
- **EULA/Terms formels du produit desktop** : inexistants en ligne d'après une recherche dédiée ; impossible donc de citer une clause explicite sur l'analyse/publication/automatisation/benchmarking. Le texte éventuel du clic-through de l'installateur n'a pas été retrouvé.
- **Fiche WineHQ AppDB dédiée à XG** avec rapports de test versionnés : non trouvée (seulement l'endossement de l'éditeur, des tutoriels Medium et la fiche CodeWeavers/CrossOver).
- **Round-robin moteur-contre-moteur récent, tiers et non circulaire, incluant XG** avec chiffres bruts : hors l'auto-étude bgsage 2026 et l'étude Depreli (arbitrée par XG), aucune compétition inter-bots indépendante récente n'a été localisée.
- **Réplication indépendante** des chiffres bgsage par un tiers : non trouvée à ce jour.

---

## Recommandations

1. **Adopter gnubg comme arbitre principal reproductible, et positionner XG en instrument de contrôle ponctuel — pas en oracle systématique.** L'absence d'API rend XG trop fragile pour être dans la boucle à chaque itération. Bénéfice : chaîne d'arbitrage 100 % scriptable et libre, cohérente avec l'équivalence gnubg déjà mesurée.
2. **Produire immédiatement, à faible coût, la « moitié XG » de l'objectif par voie indirecte.** Composer « gammonNet ≡ gnubg 2-ply » (déjà établi) avec un calage gnubg↔XG. Réutiliser d'abord le calage Méthode 3 de bgsage (différence de PR +0,002, r = 0,98) comme borne publiée ; le citer avec sa réserve de circularité. C'est le résultat le plus rapide et défendable.
3. **En parallèle, monter un banc XG-en-lot pour un sous-échantillon de contrôle** (quelques milliers de décisions disputées) : XG2 sous CrossOver, Batch Analysis niveau personnalisé (3-ply → XGR++ sur désaccord ; Batch Rollout sous 0,02), extraction via `xgdatatools`. Valider d'abord le parseur XGID/`.xg` sur ~200 positions croisées gnubg pour verrouiller l'ordre des champs.
4. **Rapporter DEUX chiffres, jamais un seul PR converti.** (a) « erreur moyenne d'équité par décision × 500 » avec filtre de décision *identique* appliqué aux deux moteurs (comparable, propre) ; (b) un « PR façon XG » reproduisant l'exclusion des coups « non obvious », pour dialoguer avec la communauté. Ne jamais présenter un mEMG gnubg ÷2 comme un PR XG.
5. **Neutraliser la circularité systématiquement** : pour toute mesure « X vs XG », scorer aussi contre la vérité-terrain d'XG *et* contre une vérité-terrain indépendante (rollouts gnubg/Open Sage), et ne conclure que si les deux références concordent — la méthode « deux rollouts » de bgsage est le modèle à suivre.
6. **Documenter la conformité licence dans le dépôt** : noter que le format `.XG` est officiellement « freely redistributed », qu'aucun EULA desktop publié n'interdit l'analyse/benchmark/automatisation, et graver la règle « XG = instrument, jamais source de poids/tables/entraînement ». Conserver une capture d'un éventuel clic-through d'installateur.

**Seuils qui changeraient ces recommandations :** si une réplication tierce indépendante de bgsage paraissait, le point 2 deviendrait une citation de premier rang (retirer la réserve de circularité). Si XG exposait un jour une CLI/API, le point 3 passerait d'un contrôle ponctuel à un arbitre secondaire permanent. Si un EULA desktop explicite apparaissait interdisant benchmark ou automatisation, basculer entièrement sur le substitut indirect (points 1–2) et les rollouts de référence publiés.

## Caveats
- Les chiffres de force les plus favorables à XG (Depreli 2012) sont **arbitrés par XG** : à ne jamais utiliser comme oracle neutre.
- L'étude bgsage 2026, la plus proche du protocole visé, est une **auto-étude d'un concurrent**, non répliquée ; ses chiffres sont crédibles et le pipeline est libre/reproductible, mais à présenter comme [MESURE] tierce non indépendante.
- L'architecture interne d'XG et le facteur de VR restent **non documentés** ; toute affirmation détaillée circulant en ligne est du folklore ou de l'IA (Grokipedia) — ne pas s'y fier.
- L'ordre des champs XGID vient d'implémentations communautaires, pas de l'éditeur : **valider empiriquement** avant production.
- L'absence d'EULA publié n'équivaut pas à une autorisation illimitée : c'est un vide documentaire, à gérer par prudence (pas de redistribution du binaire ni des données XG dans l'artefact).