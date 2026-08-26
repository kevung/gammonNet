# DS-01 — État de l'art des moteurs — retour

**Date de la recherche** : 2026-08-26 · **Outil** : Claude, recherche approfondie
**Prompt** : `docs/recherche/DS-01-etat-de-lart-des-moteurs.md`, version du 2026-08-26

> **Ce que ce retour décide** : où est réellement la barre, et si quelqu'un l'a déjà franchie.
> **Ce qu'il conclut** : la barre praticable est la parité gnubg/XG à profondeur appariée — déjà
> atteinte — et le seul gain d'évaluation qui survit à la recherche vient de la qualité du signal
> d'entraînement (distillation de sa propre recherche 2-ply) ; caractéristiques expertes et
> largeur de recherche sont mesurées inopérantes par deux projets indépendants.
> **Ce qu'il ne tranche pas** : aucun match direct à grand volume contre XG n'est possible (pas
> d'API) ; la licence des réseaux HedgeHog reste introuvable ; la contradiction bgsage AGPL/MPL
> qu'il signale a depuis été tranchée à la source : **MPL-2.0** (fichier LICENSE du dépôt
> `markbgsage/bgsage`, consulté le 2026-08-27).

---
# État de l'art des moteurs de backgammon en 2026 — rapport pour le projet gammonNet

## TL;DR
- En 2026, **eXtreme Gammon (XG) reste la référence commerciale de facto**, mais la barre « qualité d'analyse » n'est plus tenue par XG seul : deux moteurs indépendants publient des mesures les plaçant **à parité, voire légèrement devant XG à niveaux de recherche appariés** — Open Sage (bgsage.ai) et, contre GNU Backgammon, le projet Backgammon-NN de Chris Whittington. La preuve la plus solide (protocole + volumes) vient de ces projets et de `alexstrehl/backgammon-ai-engine`, pas de XG lui-même.
- La cause du plus grand écart **documenté et expliqué** entre deux moteurs neuronaux modernes n'est ni la taille du réseau, ni l'encodage, ni la profondeur : c'est la **qualité du signal d'entraînement** (labels de qualité rollout / distillation de la valeur d'une recherche plus profonde). Deux projets indépendants (Whittington, Strehl) y convergent — ce qui explique directement pourquoi ton avantage 0-ply (+0,00247) s'annule sous recherche (+0,00007).
- « Quelqu'un a-t-il dépassé XG ? » : **oui, sur mesure publiée avec protocole** (Open Sage, à niveaux appariés), mais l'écart est petit (≈ 0,1–0,16 PR) et jugé partiellement contre les propres rollouts du challenger ; **non, sur un match direct à grand volume**, qui n'existe pour personne car XG n'expose aucune API.

## Key Findings

1. **Le classement 2026, par qualité de preuve.** XG (Xavier Dufaure de Citres / GameSite 2000, sorti en juin 2009) est universellement traité comme référence, mais sa suprématie repose surtout sur une étude auto-arbitrée (Depreli 2012, rollouts faits *par XG lui-même*) et sur du marketing (Financial Times 2023). Les mesures les plus rigoureuses de 2026 viennent de challengers : Open Sage se dit à parité/légèrement devant XG, `alexstrehl` bat gnubg-nn 0-ply avec IC serrés sur 10 M de parties, et Whittington atteint la parité avec gnubg.
2. **Le plus grand écart expliqué** : ~7 points de pourcentage de taux de gain (43 %→~50 %) / ~0,1–0,2 point par partie, entre un réseau auto-appris et GNU Backgammon, **causé par la qualité des labels d'entraînement**, corrigé par distillation de recherche 2-ply — pas par l'architecture.
3. **Dépasser XG** : preuve publiée oui (Open Sage), mais petite et partiellement auto-référencée ; aucun match direct à grand volume n'existe.
4. **Littérature académique** : depuis TD-Gammon, l'essentiel est Tesauro (rollouts, 1996), Hauk-Buro-Schaeffer (*-Minimax, 2004-2006), Andrew Lin (cube + réseau, TAAI 2020), Papahristou-Refanidis (variantes, 2011-2015). Peu d'articles post-2015 sur le backgammon standard ; l'innovation récente est dans les dépôts, pas les revues.
5. **Conventions de mesure** : PR (équité perdue par décision non triviale × 500), taux d'erreur Snowie, mEMG, matchs dupliqués (dés en miroir), rollouts de référence. Volumes concluants : de 500 parties (avec rollouts en escalade) à 10 M de parties (0-ply).
6. **Folklore** : « XG est le plus fort du monde », « gnubg 2-ply = XG 3-ply », « le 4-ply apporte beaucoup » — tous répétés sans preuve contrôlée à grande échelle.

## Details

### 1. Recensement des moteurs et qualité des preuves

**eXtreme Gammon (XG) — [MESURE FAIBLE] pour sa force, [FOLKLORE] pour sa « suprématie ».**
Auteur : Xavier Dufaure de Citres, société GameSite 2000 Ltd (fondée en janvier 2000 par Xavier et Michelle Dufaure de Citres) ; le moteur apparaît d'abord en 2002 comme adversaire en ligne sur GammonSite, avant la sortie du logiciel autonome en juin 2009 ; Windows + versions mobiles (sources : Wikipedia « EXtreme Gammon » et Grokipedia, consultés le 26 août 2026 ; https://en.wikipedia.org/wiki/EXtreme_Gammon). XG a été racheté par Travis Kalanick en 2024 (Grokipedia). PR = équité moyenne perdue par décision « non évidente » × 500. La revendication « meilleur joueur du monde » vient d'Oliver Roeder, « Backgammon's AI super-brain is for sale », *Financial Times*, 28 juillet 2023 (récupéré le 1er août 2023), où XG est décrit comme *« the best backgammon player in the world today »* et *« the near-exclusive tool for serious players to analyze, study, and practice the game »* — **aucun protocole ni volume**, donc [FOLKLORE]. XG n'expose aucune API, ce qui rend tout match direct à grand volume impraticable — fait répété par plusieurs sources techniques indépendantes (bgsage.ai, gammonrants).

L'unique corpus de mesures quantifiées largement cité est **l'étude Michael Depreli 2012** (publiée sur BGonline le 28 janvier 2012, reprise sur extremegammon.com/studies.aspx, consulté le 26 août 2026). Protocole : 500 parties d'argent, tout désaccord d'opinion entre moteurs départagé par rollout XG2 (3-ply damier, XGRoller pour le cube, jusqu'à IC 95 % < 0,005, min. 1296 essais), >5000 décisions roulées. Équité normalisée totale et PR :

| Programme / niveau | Total équité perdue | PR |
|---|---|---|
| XG2 XGRoller++ | 4,097 | 0,11 |
| XG2 XGRoller+ | 6,487 | 0,18 |
| XG2 5-ply | 8,969 | 0,25 |
| XG2 4-ply | 11,936 | 0,33 |
| GnuBG 1.00 4-ply | 12,536 | 0,35 |
| XG2 XGRoller | 14,887 | 0,41 |
| XG2 3-ply | 16,231 | 0,45 |
| GnuBG 3-ply | 16,775 | 0,46 |
| GnuBG 2-ply | 20,951 | 0,58 |
| BGBlitz 2.8.0 4-ply | 32,485 | 0,90 |
| BGBlitz 2.8.0 3-ply | 37,487 | 1,04 |
| Snowie 4 3-ply | 45,003 | 1,24 |

Limites de preuve : c'est une étude **auto-arbitrée** (le juge — rollout XG2 — est l'un des concurrents), **publiée par le vendeur**, **sans IC sur les PR agrégés**, et datant de 2012 (matériel et gnubg d'alors). Donc [MESURE FAIBLE] : protocole et volume existent, mais le biais de référence est structurel. Enseignement transférable néanmoins : le décalage de convention de profondeur « gnubg 2-ply ≈ autres bots 3-ply » y est explicite (légende de l'étude), corroboré par un post de Neil Kazaross cité sur les forums — mais reste [FOLKLORE] faute de mesure contrôlée dédiée.

**GNU Backgammon (gnubg) — [MESURE] comme oracle, licence GPL-3.**
Réseau de neurones en C ; auteurs principaux Joseph Heled, Øystein Johansen, Jørn Thyssen, Gary Wong. Version courante 1.08.003 (installeur Windows daté du 28 avril 2024 ; source : playboardgames.org, 10 août 2026), **mono-thread** — faiblesse répétée par Backgammon Galaxy et d'autres. Distingue « error rate mEMG » (décisions non forcées + décisions de cube proches/réelles du seul joueur noté) et « Snowie error rate » (toutes décisions des deux joueurs) ; le manuel gnubg indique que le taux gnubg vaut en moyenne ~1,4× le taux Snowie 4 sur ~300 matchs (gnu.org/software/gnubg/manual, consulté le 26 août 2026). Bases de fin de partie : **two-sided (exactes)** et **one-sided (approchées)** ; 15 pions sur 6 points = 294 458 696 positions en two-sided contre 54 264 en one-sided (manuel gnubg, section bearoff). Contrainte projet : gnubg sert d'oracle, jamais de source d'apprentissage — les poids sont GPL-3 (distribution WebAssembly = distribution).

**Open Sage / Backgammon Sage Pro — [MESURE], licence MPL-2.0 (dépôt markbgsage/bgsage).**
Étude quantitative « Bot Performance — Open Sage vs eXtreme Gammon » (bgsage.ai/botperformance, consulté le 26 août 2026). Trois méthodes : (a) PR contre vérité-terrain en escalade sur 500 parties d'argent (17 535 décisions) et 130 matchs en 5 points (18 292 décisions) ; (b) positions litigieuses roulées par les deux moteurs ; (c) 290 matchs de tournoi réels (2026, tournois UBC Texas/Istanbul/Japan, fournis par Máté Fehér, 580 notes de joueurs). Résultats saillants (PR, plus bas = meilleur) :
- Argent, référence Sage : **Sage 3T 0,21 vs XG Roller++ 0,32** ; Sage 4P 0,41 vs XG 4-ply 0,46 ; 3-ply quasi nul (XG devant de 0,01).
- Argent, **référence XG** (miroir, pour ôter le biais) : Sage 3T 0,26 vs XG Roller++ 0,33 ; **Sage 4P 0,37 vs XG 4-ply 0,45** (le 4-ply est le test le plus propre car aucune ligne n'y est jugée contre elle-même).
- Match 5 points : Sage 3T 0,19 vs XG Roller++ 0,35.
- Positions litigieuses (damier) : sur 1 357 désaccords notés, Sage 3T plus proche des deux rollouts (44,4 % vs 39,3 % selon le rollout XG lui-même).
- 290 matchs réels : différence moyenne de PR **+0,002 (IC 95 % ±0,03, p = 0,90, r = 0,98)** — indiscernable de zéro.
Qualité de preuve : protocole détaillé, volumes explicites, reproductible (scripts publics), biais de self-référence partiellement retiré par le miroir XG. Reste [MESURE] (fort), avec réserve : publié par le vendeur, et XG scoré via Batch Analysis (pas de vraies parties têtes-à-tête).

**alexstrehl/backgammon-ai-engine (PureTD) — [MESURE], licence MIT.**
Auteur Alexander Strehl. RL pur par self-play (TD, backups de Bellman échantillonnés puis exacts 1-ply). Chiffres (IC 95 % bootstrap ; github.com/alexstrehl/backgammon-ai-engine, consulté le 26 août 2026) :
- DMP, réseau 561k : **51,84 % vs gnubg 0-ply (10 M parties, IC [51,8 ; 51,9])** ; avantage **maintenu sous recherche** : 51,5 % @1-ply, 51,4 % @2-ply.
- Money cubeful, 562k : **+57,8 mEq/partie (0,058 pt/partie, 10 M parties, IC [+56,1 ; +59,6])** ; PR XG++ 1,06 (1500 parties, IC [1,01 ; 1,11]).
- Cubeful 1-ply vs 1-ply : +47,1 mEq/partie ; 2-ply vs 2-ply : +45,0 mEq/partie (l'avantage **se resserre** en profondeur).
Constat clé de Strehl : **« Les features d'entrée supplémentaires n'aident pas… le goulot est la qualité du signal d'entraînement, pas les features »** (pip counts, gating de phase, 25 features expertes de gnubg testés, aucun gain sur l'encodage de base à 196 features). Contraste direct avec ta mesure : chez Strehl l'avantage 0-ply **survit** au 2-ply (mais rétrécit), suggérant que « les réseaux de base de gnubg sont peut-être plus réglés pour la recherche profonde, ou gnubg a une recherche plus sophistiquée ».

**wildbg — [MESURE FAIBLE], licence Apache-2.0 OU MIT (permissive).**
Auteur Carsten Wenderdel, Rust, 2023, stade alpha. Deux réseaux (contact + course). Force : **~5,9 de taux d'erreur (analyse GnuBG 2-ply) pour les 1-pointers (janvier 2024)** ; auparavant ~7,5 mEMG / ~1800 ELO annoncés sur la liste bug-gnubg. Entraînement : rollouts money cubeless + apprentissage supervisé (pas de TD), pipeline public (github.com/carsten-wenderdel/wildbg + wildbg-training, consulté le 26 août 2026). **C'est la meilleure référence à licence propre et code ouvert pour toi** (permissive, entraînable de zéro, pas de poids GPL).

**Backgammon-NN (Chris Whittington) — [MESURE], la plus pertinente pour ton problème.**
Rust + PyO3, tract-ONNX (whittingtonchess.com/backgammon-report, mis à jour 21 juillet 2026, consulté le 26 août 2026 ; dépôt github.com/Chris-Whittington-Chess/Backgammon-NN). Découvertes mesurées (têtes-à-têtes dés en miroir) :
- **Un réseau ajusté sur les labels de son propre moteur ne peut pas dépasser ce moteur** — une douzaine d'expériences (self-play, rollouts tronqués/complets, distillation 1-ply/2-ply) convergent toutes vers la même parité.
- **La profondeur bat la largeur** ; les features expertes ajoutées (à l'entrée) nuisent, (à la NNUE) sont neutres puis ~5 points derrière le réseau sans features.
- **Les gains 0-ply s'évaporent sous recherche** (v1.7.0, v1.8.0) — sauf la **distillation de la valeur d'une recherche 2-ply**, premier gain « search-robust » (v1.9.0, ~52 % vs champion à 1-ply).
- Percée : distiller **22,5 M de positions labellisées par GNU Backgammon 2-ply** (v1.10.0) → bat le champion self-play **53,4 % sur 40 000 parties à 1-ply, à coût d'inférence identique** ; **à profondeur égale, à parité avec gnubg** (49,1 % sur 3000 parties money ; 48,5 % sur 400 matchs 7 points au videau).
- vs gnubg : le champion self-play faisait **~43 % (−0,20 pt/partie) à 0-ply**, écart localisé dans le **jeu de contact** ; gnubg 0-ply est un « professeur à parité » (inutile), gnubg 2-ply est nettement plus fort (43,9 %, z −3,86) → seule une recherche 2-ply fait un bon professeur.
- **Profondeur de recherche ≈ +3 points de taux de gain ; largeur de recherche ≈ nulle.**
- Base de fin de partie one-sided exacte : 54 264 positions.
- Verdict d'architecture pour toi : **« MCTS/PUCT est le mauvais outil pour le backgammon — les nœuds de hasard diluent les simulations sur 21 lancers par ply et le réseau de valeur est trop précis pour qu'une recherche sélective profonde paie. Expectiminimax + rollouts est le paradigme, ce qui explique qu'aucun moteur fort n'utilise MCTS. »**
Réserve licence : Whittington a franchi son plafond **en apprenant de gnubg (GPL)** — voie **interdite** pour toi par ta règle interne. Le reste (architecture, distillation de ta propre recherche) est transférable.

**BGBlitz — [MESURE FAIBLE], propriétaire (freemium).**
Frank Berger, Java, RL pur, multiple vainqueur des Computer Olympiads (bronze au 18e, 2015). Depreli 2012 : PR 0,90 (4-ply), 1,04 (3-ply) — donc mesurablement derrière XG et gnubg à l'époque. Présentation technique publique (bgblitz.com/download/blog/Aachen_BGBlitz.pdf). Propriétaire : hors périmètre comme source, utile comme repère historique.

**Snowie — historique.** Olivier Egger, 1998 ; PR 1,24 (Snowie 4 3-ply, Depreli). Supplanté par XG en 2009. Pas de développement moderne.

**HedgeHog / Aureus / Fox (OpenGammon) — [FOLKLORE] pour la force, licence non identifiée.**
Développeur anonyme (pseudo « Yzqw »). **Revendique un moteur serveur (« Aureus ») « légèrement supérieur à eXtreme Gammon 2 » / « le plus fort de la planète » — sans aucun protocole, volume ni IC publiés** (sites SPA non extractibles ; revendication seulement capturée en seconde main via gammonrants.org, 5 août 2026, verbatim : *« what they claim to be the strongest engine on this planet, even outperforming Extreme Gammon 2 slightly »*). Seule mesure indépendante : gammonrants trouve **Aureus à PR 1,6 (analyse XG2 Roller++) / 1,9 (BGBlitz 4-ply) sur 63 parties** (et « PR 1,9, confiance moyenne, 26 parties » dans sa table), avec avertissement explicite de faible échantillon ; Fox 0.32 à PR 5,9. **Licence introuvable** : aucun dépôt public pour les réseaux Aureus/Fox ; la clause « non commerciale » supposée n'a pas pu être confirmée sur une source primaire — mais les réseaux forts sont serveur-only et propriétaires de fait. Le fork permissif `gammonx/gammonx-wildbg` (Apache/MIT) concerne le petit moteur dérivé de wildbg, pas Aureus. Aucune preuve ne relie Michael Depreli (contributeur de BGBlitz et auteur du benchmark 2010/2012) à HedgeHog. **Inutilisable pour toi faute de licence identifiée.**

**Palamedes — académique.** Nikolaos Papahristou & Ioannis Refanidis (Univ. Macédoine) ; or au 16e Computer Olympiad (2011). Variantes (Portes, Plakoto, Fevga…), NN + TD + features expertes + bases de fin de partie. Thèse et articles publics (nikpapa.com). Pertinent pour la méthodologie, pas comme moteur backgammon standard SOTA.

### 2. Le plus grand écart documenté, et sa cause (sous-question centrale)

Il faut distinguer trois « écarts » :
- **Écart générationnel** (grand mais peu instructif) : Snowie 4 (PR 1,24) → XG2 XGRoller++ (PR 0,11), soit un ordre de grandeur, mais entre générations 1998 vs 2009 [MESURE FAIBLE, Depreli].
- **Écart à niveaux appariés entre moteurs modernes** (petit) : Open Sage devance XG de **0,11–0,16 PR** aux niveaux de rollout tronqué [MESURE, bgsage] ; `alexstrehl` devance gnubg-nn 0-ply de **+57,8 mEq/partie** mais l'écart **rétrécit** sous recherche [MESURE, Strehl]. Ces écarts sont réels mais faibles.
- **Écart le mieux expliqué mécaniquement** : le réseau auto-appris de Whittington vs GNU Backgammon — **~7 points de pourcentage de taux de gain (43 %→~50 %), ~0,1–0,2 pt/partie** — dont la **cause est isolée expérimentalement** : ni l'architecture, ni les features, ni la profondeur, mais **la qualité du signal d'entraînement** (labels de qualité rollout / distillation de la valeur d'une recherche 2-ply). [MESURE]

**C'est la réponse la mieux sourcée à ta question de cause.** Elle est corroborée indépendamment par Strehl (« le goulot est la qualité du signal d'entraînement, pas les features ») et cadre exactement avec le résultat de Hauk-Buro-Schaeffer, dont le verbatim est : *« empirical evidence is presented that with today's sophisticated evaluation functions good checker play in backgammon does not require deep searches. »* Autrement dit, un bon évaluateur **ne laisse rien à corriger à la recherche**, donc un avantage d'évaluation qui n'est pas lui-même issu d'un signal « de qualité recherche » s'évapore quand les deux camps recherchent. C'est précisément ton observation (+0,00247 au 0-ply → +0,00007 au 2-ply).

Corollaire décisionnel pour gammonNet : **ton gain d'évaluation 0-ply n'est pas « faux », il est simplement du type qui se fait rattraper par la recherche.** Pour obtenir un gain qui **survit** au 2-ply, la littérature de dépôt converge sur une seule voie efficace : **distiller dans l'évaluateur statique la valeur d'une recherche plus profonde que le jeu courant** (backups exacts 1-ply chez Strehl ; distillation 2-ply chez Whittington). Attention : distiller **sa propre** recherche plafonne à son propre niveau (Whittington : « l'élève ne peut dépasser le maître ») ; les deux seuls échappatoires observés sont (i) un professeur externe plus fort — **interdit chez toi** (gnubg GPL, XG propriétaire) — ou (ii) l'optimisation directe de la force de jeu (SPSA sur les sorties, scorée en pts/partie), non bornée par un professeur.

### 3. Quelqu'un a-t-il dépassé XG ?

- **Sur mesure publiée à niveaux appariés : oui, marginalement** — Open Sage 3T/4P devant XG Roller++/4-ply de 0,04–0,16 PR, y compris jugé contre les propres rollouts de XG [MESURE, bgsage.ai/botperformance]. Réserve : petit écart, vendeur, pas de vraies parties têtes-à-tête (XG sans API).
- **Contre gnubg (proxy de XG) : parité atteinte** par Whittington après distillation de labels gnubg [MESURE].
- **Sur match direct à grand volume contre XG : non documenté pour personne** — l'absence d'API de XG l'empêche structurellement. La revendication HedgeHog « plus fort que XG2 » est [FOLKLORE] (aucun protocole).
- Fichiers de benchmark publics servis par un moteur : `bgsage` fournit `data/money_benchmark/benchmark.json.gz` et des scripts reproductibles ; `alexstrehl` fournit un dossier `benchmarks/` et des modèles `.pt` ; `wildbg-training` publie ses rollouts et réseaux. Ce sont les trois corpus reproductibles réels que j'ai trouvés.

### 4. Littérature académique depuis TD-Gammon

- **Tesauro, TD-Gammon** (1992-1995) : TD(λ), self-play, niveau expert sans lookahead, surhumain avec lookahead court. **Tesauro & Galperin (1996)** : amélioration de politique par rollout Monte-Carlo (ancêtre direct des rollouts modernes).
- **Contexte historique : Berliner, BKG 9.8** — le 15 juillet 1979 à Monte-Carlo, BKG 9.8 (Hans Berliner, Carnegie-Mellon, PDP-10) bat le champion du monde fraîchement titré Luigi Villa **7-1** dans un match en 7 points (enjeu 5 000 US$, ~200 spectateurs), Villa jouant globalement mieux mais BKG bénéficiant des dés (Berliner, *ACM SIGART Bulletin* / *Artificial Intelligence* 1980 ; bkgm.com ; Wikipedia « Luigi Villa »). Premier programme à battre un champion du monde à un jeu.
- **Hauk, Buro, Schaeffer, « *-Minimax Performance in Backgammon » / « Rediscovering *-Minimax »** (Computers and Games 2004, LNCS 3846, 2006) : réhabilitation des algorithmes Star1/Star2 de Ballard (1983) pour élaguer les arbres à nœuds de hasard. Verbatim : *« Star2 allows strong backgammon programs to conduct depth 5 full-width searches (up from 3) under tournament conditions on regular hardware without using risky forward pruning techniques. »* Conclusion majeure et directement pertinente : *« with today's sophisticated evaluation functions good checker play in backgammon does not require deep searches. »* [MESURE, académique]
- **Winands et al., ChanceProbCut** (IEEE CIG 2009) : élagage avant (forward pruning) dans les nœuds de hasard.
- **Andrew Lin, « Learning Cube Strategy in Backgammon with Neural Networks »** (TAAI 2020, pp. 29-34 ; IEEE Xplore doc. 9382451) : intègre le videau **et le score de match** dans le réseau, de sorte que le réseau apprend l'influence du score et du cube non seulement sur les décisions de cube mais aussi sur le jeu de damier. Article derrière péage IEEE ; d'après le résumé et les reprises (README alexstrehl), l'approche « équité normalisée par la valeur du cube » y est décrite, mais les résultats publiés portent sur de **très petits réseaux en match play, pas en money**, et ne traitent pas les décisions de cube comme des transitions état-action propres — limite reconnue par Strehl qui étend l'idée.
- **Papahristou & Refanidis** (2011-2015) : entraînement TD de réseaux pour variantes, features expertes, bases de fin de partie « pin » pour Plakoto.
Constat : **la littérature revue post-2015 sur le backgammon *standard* est mince** ; l'innovation récente (distillation, expansion progressive, backups exacts) vit dans les dépôts et blogs techniques, pas dans les revues.

### 5. Conventions de mesure de la communauté

- **PR (Performance Rating)** : équité perdue par décision **non triviale** × 500 (méthode gnubg/XG). Plus bas = meilleur. Grille XG : 0–2,5 « World Champ », 2,5–5 « World Class », 5–7,5 « Expert », etc.
- **Snowie error rate** : erreurs du joueur ÷ décisions des **deux** joueurs (dont forcées) → environ **la moitié** du chiffre gnubg (gnubg ≈ 2× Snowie ; ÷500 pour convertir PR→mppm Snowie). XG écarte en plus les coups non forcés « sans intérêt » et divise par 2.
- **mEMG** : millipoints d'équité perdue par décision normalisée (gnubg).
- **Matchs dupliqués / dés en miroir** : chaque paire rejoue la même séquence de dés côtés inversés → réduction de variance ; convention communautaire pour comparer deux moteurs (utilisée par Whittington, Strehl, et ta propre méthode de 50 000 paires).
- **Rollouts de référence** : nombre multiple de 36, premier lancer uniformément réparti ; « vérité terrain » quand roulés à IC serré (bgsage : jusqu'à IC 95 % < 0,005, plafond 20 736 chemins).
- **Volumes jugés concluants** : 500 parties **avec escalade en rollout** (bgsage) ; 10 M parties pour un écart 0-ply de ~0,05 pt (Strehl) ; 40 000 parties à 1-ply, 3000 money, 400 matchs 7-pts (Whittington). Ta méthode (50 000 paires, IC ~±0,27 % sur le taux de gain de match) est **dans les standards hauts de la communauté**.
- **Non-transitivité** : *rien de documenté* sur un cycle A>B>C>A entre moteurs de backgammon modernes dans mes sources (voir « Ce que je n'ai pas trouvé »).

### 6. Ce qui est répété sans avoir jamais été mesuré [FOLKLORE]

- **« XG est le plus fort joueur du monde. »** Aucune preuve contrôlée à grande échelle ; repose sur FT 2023 + marketing + l'étude auto-arbitrée Depreli. Vraisemblable mais non établi par tête-à-tête à volume.
- **« gnubg 2-ply = XG 3-ply » (décalage d'un ply).** Répété partout, origine = post Kazaross + légende de l'étude XG ; jamais mesuré isolément et proprement.
- **« Le 4-ply apporte beaucoup. »** Les données (Depreli : chaque ply ≈ 0,1 PR ; Whittington : profondeur ≈ +3 points, largeur ≈ nulle) montrent un gain **réel mais modeste**, souvent surestimé dans les discussions.
- **« XG et gnubg jouent à peu près pareil pour progresser. »** Semi-vrai : Axel Reichert (rec.games.backgammon) et bkgm.com le disent, mais c'est une affirmation sur l'usage pédagogique, pas une équivalence de force mesurée.

## Les contradictions entre sources

1. **Licence de bgsage : AGPL-3 (ton brief) vs MPL-2.0 (source primaire).** Ton cahier des charges range « bgsage (AGPL-3) » hors périmètre. Or la page d'étude et le dépôt `github.com/markbgsage/bgsage` déclarent explicitement **MPL-2.0** (« Open Sage is licensed under MPL-2.0 », consulté le 26 août 2026). Ce qui les départagerait : inspecter le fichier `LICENSE` du dépôt et l'en-tête des fichiers sources. Si c'est bien MPL-2.0, le moteur Open Sage **n'est pas** copyleft fort et pourrait être réétudié (MPL = copyleft de fichier, compatible avec distribution d'un binaire propriétaire sous conditions) — mais **ne recopie aucun code**, décris seulement.
2. **L'avantage 0-ply survit-il à la recherche ?** Strehl : oui (51,5 % @1-ply, 51,4 % @2-ply, il se resserre). Whittington : non, sauf si le gain vient d'un signal « de qualité recherche ». Ta mesure : non (+0,00007 au 2-ply). Ce qui les départagerait : la **nature** du signal d'entraînement — Strehl fait des backups exacts 1-ply (donc un signal déjà « de recherche »), ce qui pourrait expliquer que son avantage tienne, tandis qu'un réseau purement 0-ply/supervisé (comme le tien pourrait l'être) verrait son avantage s'évaporer. Test décisif : entraîne une variante avec cible 2-ply distillée et re-mesure l'écart au 2-ply.
3. **« Dépasser XG » : Open Sage (oui, mesuré) vs communauté (XG indétrônable).** Départage : un match direct têtes-à-têtes à grand volume — impossible tant que XG n'a pas d'API ; à défaut, un round-robin sur corpus de positions communes roulées par un tiers neutre.

## Ce que je n'ai pas trouvé (absences documentées)

- **Aucune non-transitivité mesurée entre moteurs de backgammon modernes** (cycle A bat B, B bat C, C bat A). La littérature « non-transitif » trouvée est générique (pierre-feuille-ciseaux, dés de Efron, DeepMind « spinning tops »). Si le phénomène existe entre XG/gnubg/Sage/wildbg, il n'est pas publié avec protocole. À vérifier toi-même par round-robin.
- **Aucun benchmark public tête-à-tête XG vs un challenger à grand volume** (barrière technique : pas d'API XG). Tous les « XG vs X » passent par Batch Analysis sur positions, pas par des parties jouées.
- **Aucune licence identifiable pour les réseaux HedgeHog/Aureus/Fox** ; la clause « non commerciale » supposée n'a pas de source primaire vérifiable (sites SPA non extractibles). À confirmer dans l'app en session navigateur.
- **Le texte intégral de l'article d'Andrew Lin (TAAI 2020)** est derrière le péage IEEE ; je n'ai que le résumé, les citations et les reprises. Résultats chiffrés précis non vérifiés directement.
- **La présentation technique de BGBlitz (PDF Aachen)** est citée mais je n'en ai pas extrait de chiffres de force avec protocole.
- **La licence exacte du dépôt Backgammon-NN de Whittington** n'a pas été confirmée (à lire dans le dépôt avant tout emprunt de méthode/code).

## Recommendations

**Étape 0 — cadrer la barre (avant tout calcul).**
La « barre » réaliste n'est pas « battre XG en tête-à-tête » (infaisable à mesurer) mais **« atteindre la parité gnubg/XG à profondeur appariée, puis gagner sur le coût par décision »**. Tu es déjà à parité gnubg 2-ply avec un réseau meilleur au 0-ply — donc **ta barre restante est essentiellement la vitesse et un gain d'éval qui survit à la recherche**, pas la force brute. Benchmark de décision : reproduis le protocole bgsage (corpus de positions + escalade rollout) pour te situer face à des niveaux appariés.

**Étape 1 — attaquer le coût, pas d'abord la force (ton facteur 25–60× est le vrai problème).**
Ton réseau est à parité mais 25–60× plus cher au 2-ply. Priorité : inférence par lots (batch) sur tous les coups légaux d'un ply en une passe SIMD (Whittington : ×2,5 de rollouts/s), largeurs multiples de 8/16/32, élagage Star2/*-Minimax (Hauk-Buro-Schaeffer : profondeur 5 plein-largeur en tournoi) et un filtre de coups. Seuil de décision : viser **≤ 3× gnubg** au 2-ply avant d'investir dans la force.

**Étape 2 — transformer ton avantage 0-ply en avantage « search-robust ».**
Distille dans ton évaluateur statique la valeur de ta **propre** recherche 2-ply (cible de distribution win/gammon/backgammon, pas seulement l'équité) — c'est la seule voie qui, chez Whittington, a produit un gain survivant à la recherche, et elle est **licence-propre** (tu distilles ton moteur, pas gnubg). Benchmark : re-mesure l'écart au 2-ply ; passe le cap si le gain 2-ply devient significativement > 0 (IC excluant zéro).

**Étape 3 — si le plafond « élève ≤ maître » se manifeste, bascule sur l'optimisation directe.**
Comme tu t'interdis gnubg/XG comme professeurs, la seule échappatoire non bornée est l'**optimisation directe de la force** (SPSA sur les paramètres de sortie, scorée en pts/partie sur matchs dupliqués) — approche que Whittington identifie comme non bornée par un professeur. Ta harnais 50 000 paires est déjà l'outil de scoring.

**Étape 4 — ne gaspille pas d'effort sur ce qui ne paie pas (résultats négatifs déjà établis).**
Deux projets indépendants (Strehl, Whittington) montrent que **les features d'entrée expertes n'aident pas** et que **la largeur seule n'aide pas** ; la profondeur du réseau et surtout la qualité du signal paient. N'investis pas de semaines dans un encodage plus riche.

**Étape 5 — hygiène de licence (dure, car WebAssembly = distribution).**
Références utilisables telles quelles : **wildbg (Apache/MIT)** et **alexstrehl (MIT)** comme sources d'inspiration/comparaison à licence propre ; **gnubg (GPL-3) uniquement comme oracle de mesure**, jamais dans le binaire ni comme professeur. Vérifie la licence de Backgammon-NN avant tout emprunt. Écarte HedgeHog (licence inconnue) et bgsage tant que la contradiction AGPL/MPL n'est pas tranchée. Ne transcris aucune constante réglée à la main d'un moteur copyleft.

### Tableau de décision

| Piste | Gain attendu (chiffré si possible) | Coût d'implémentation | Risque | Licence | La mesure qui trancherait |
|---|---|---|---|---|---|
| Inférence par lots + SIMD (largeurs 8/16/32) | ×2,5 rollouts/s (Whittington) ; vise ≤3× gnubg au 2-ply | Moyen | Faible | Ton code | Coût par décision 2-ply vs gnubg, même matériel |
| Élagage *-Minimax / Star2 + filtre de coups | Profondeur 5 plein-largeur en tournoi (Hauk-Buro-Schaeffer) sans forward-pruning risqué | Moyen | Faible-moyen | Académique (méthode) | Décisions/s à qualité de coup constante |
| Distillation de ta propre recherche 2-ply dans l'éval statique | 1er gain « search-robust » chez Whittington (~+2 pts @1-ply) | Moyen-élevé (labelliser + réentraîner) | Moyen (peut plafonner à ton niveau) | Ton moteur (propre) | Écart au 2-ply : IC excluant zéro |
| Optimisation directe SPSA des sorties | Non borné par un professeur ; gain inconnu | Élevé | Moyen-élevé (bruit d'optimisation) | Ton code | pts/partie sur matchs dupliqués, IC |
| Bases de fin de partie exactes (one-sided) | 54 264 positions (gnubg/Whittington) ; ~0 gain 0-ply, paie en profondeur et comme labels exacts | Faible-moyen | Faible | Recalcule-les toi-même (programmation dynamique) | Gain d'équité en fin de partie sous recherche |
| Réseau plus profond (pas plus large) | La profondeur bat la largeur (Whittington, Strehl) | Moyen | Faible | Ton code | Tête-à-tête réseau profond vs actuel, dés miroir |
| Encodage d'entrées plus riche (features expertes) | **≈ 0** (Strehl et Whittington : n'aide pas) | Moyen | Élevé (temps perdu) | — | Déjà tranché négatif : ne pas prioriser |
| Réétudier Open Sage comme référence | Repère apparié le plus fort publié | Faible (lecture) | Dépend licence | MPL-2.0 (à confirmer vs AGPL du brief) | Lecture du fichier LICENSE du dépôt |

## Caveats
- Presque toutes les mesures « X bat Y » proviennent d'acteurs impliqués (vendeurs, auteurs) : XG (Depreli, auto-arbitré), Open Sage (bgsage), Strehl, Whittington. Aucune n'est une évaluation tierce indépendante à grand volume. Traite les écarts petits (≤ 0,2 PR) comme suggestifs, pas définitifs.
- L'absence d'API de XG rend impossible tout match direct à grand volume ; tous les classements « vs XG » passent par des positions analysées, pas des parties jouées — biais méthodologique commun à toutes les sources.
- Les grilles PR→ELO et les libellés (« World Class », etc.) diffèrent entre XG, gnubg et Snowie ; ne compare jamais des PR issus de moteurs/conventions différents sans conversion.
- La contradiction de licence bgsage (AGPL-3 dans ton brief vs MPL-2.0 dans la source) doit être tranchée par lecture directe du dépôt avant tout usage.
- Le fait que ton avantage 0-ply s'annule au 2-ply est **normal et attendu** au vu de la littérature ; ce n'est pas un défaut de ton réseau mais la signature d'un gain d'évaluation « non issu d'un signal de recherche ». La recommandation d'étape 2 vise exactement ce point.