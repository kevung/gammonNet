# DS-07 — Instrument de mesure — retour

**Date de la recherche** : 2026-08-26 · **Outil** : Claude, recherche approfondie
**Prompt** : `docs/recherche/DS-07-instrument-de-mesure.md`, version du 2026-08-26

> **Ce que ce retour décide** : le protocole de mesure — prérequis, pas un choix.
> **Ce qu'il conclut** : le match dupliqué ne peut pas voir un gain modeste (±0,005 ppg ≈ 800 000
> paires, impraticable) ; l'instrument est la **perte d'équité appariée par position** contre un
> arbitre externe escaladé en trois passes (gnubg 3-ply → rollout tronqué VR → rollout complet),
> sur corpus figé, stratifié et versionné — 10⁴–10⁵ décisions disputées suffisent pour une
> résolution de 0,001–0,002 d'équité par décision, en heures et non en jours.
> **Ce qu'il ne tranche pas** : l'écart-type par décision (sous-produit gratuit de la première
> campagne), les fréquences réelles des classes de position (à instrumenter nous-mêmes), et le
> rôle d'XG comme second arbitre (renvoyé à DS-11).

---
# Métrologie comparative des moteurs de backgammon : protocole, arbitre et corpus

## TL;DR
- **C'est bien un problème d'instrument** : pour séparer deux moteurs à quelques millièmes d'équité par décision, l'instrument correct n'est pas le match dupliqué (trop bruité : votre ±0,020 pt/partie à 50 000 paires, et il faudrait ~800 000 paires pour descendre à ±0,005) mais la **perte d'équité moyenne par décision, appariée par position, contre un arbitre neutre**, sur un corpus figé et stratifié — deux ordres de grandeur plus sensible.
- **L'arbitre doit être externe et à variable de contrôle, jamais votre propre politique** : utilisez GNU Backgammon (3-ply) et/ou eXtreme Gammon comme oracle de rollout à réduction de variance, en escaladant la profondeur uniquement sur les positions disputées, et ancrez toutes les positions résolubles (bearoff, hypergammon 3 pions) sur les bases exactes pour éliminer le biais auto-référentiel — biais réel et publié.
- **La licence est bloquante mais gérable** : la sortie d'un programme GPL (les évaluations de gnubg) n'est **pas** couverte par la GPL selon la FSF — gnubg est donc utilisable comme **mesure/arbitre**, y compris pour votre module WebAssembly distribué ; mais aucun fichier de corpus ou de poids GPL ne doit servir d'**entrée d'entraînement**. Le seul corpus permissif (MIT/Apache-2) exploitable en entraînement est **wildbg**.

## Key Findings

1. **PR = −(erreur d'équité par décision) × 500.** [MESURE] Formule officielle d'eXtreme Gammon annoncée par l'éditeur (extremegammon.com), BGonline, 23 nov. 2009 : « PR = -(equity error per decision)*500 ». La constante 500 = 1000/2 est un facteur de conversion vers l'échelle historique « Snowie ».
2. **Les échelles ne sont pas interchangeables.** [MESURE] gnubg et XG divisent par les décisions non forcées d'UN joueur ; Snowie divise par tous les coups des DEUX joueurs. Le manuel gnubg mesure : « An investigation of approximately 300 matches showed the on average the GNU Backgammon error rate will be 1.4 times higher than your Snowie 4 error rate. »
3. **Le PR se calcule aussi bien sur un corpus figé qu'en jouant** — et pour votre usage, le corpus figé est préférable. Les campagnes publiées utilisent des milliers de décisions (Depreli, Open Sage).
4. **La réduction de variance par anticipation (control variate = luck-adjusted equity) vaut un facteur ~20–25×** sur les « equivalent games » [MESURE/DÉCLARÉ], soit ~4,5–5× sur l'écart-type — mais s'effondre dans les classes mal évaluées.
5. **Corpus exploitables** : benchmark contact gnubg (~100 000 positions, GPL → mesure seulement), wildbg-training (MIT/Apache → entraînement OK), bases exactes bearoff/hypergammon (vérité de terrain, sans biais possible).
6. **Le biais d'arbitre auto-référentiel est documenté et quantifié** : « a network fitted to its own engine's labels cannot exceed that engine » (Whittington, 2026), confirmé par « it capped at parity — because the labels used the champion as their own rollout leaf ».

## Details

### A. Les métriques

**A.1 — Formules exactes**

*PR d'eXtreme Gammon* (annoncé par l'éditeur, BGonline, 23 nov. 2009) :
> PR = −(equity error per decision) × 500
> Elo = 2240 − (equity error per decision) × 16500, soit Elo = 2240 − PR × 33

L'unité de « equity error per decision » est l'EMG (Equivalent Money Game equity : équité normalisée, exprimée en points de partie d'argent, sans dimension propre). Multipliée par 500, elle donne le PR (nombre pur). En millipoints : PR = 0,5 × (mEMG perdus par décision). XG exclut du dénominateur les coups forcés, les danses et les coups « non pertinents », définis par l'éditeur comme ceux « where the best and worse play equity difference is under 0.001 ». [MESURE]

*Origine de la constante 500* (BGonline, fil « Snowie ER and XG elo ») : « Dividing by 500 is an effective conversion to Snowie mppm error rate; divide by 1000 to get millipoints, then multiply by 2 because Snowie is counting twice the moves of gnubg/XG. » Donc 500 = 1000/2. [MESURE]

*Taux d'erreur de GNU Backgammon* (manuel officiel gnu.org / gnubg.org) :
- **Erreur totale** = somme de l'équité normalisée abandonnée par rapport au meilleur coup selon l'évaluation de référence (le nombre par défaut est ×1000, donc en mEMG). En money, chaque erreur est multipliée par la valeur du videau ; en match, la perte est reportée en MWC (match winning chance).
- **Taux d'erreur par coup** = erreur totale ÷ nombre de coups non forcés.
- **Taux d'erreur par décision** = erreur totale ÷ nombre de décisions non triviales = (coups non forcés) + (décisions de videau proches ou réelles).
- **Taux d'erreur par décision de videau** = erreurs de videau ÷ décisions de videau proches ou réelles.
- Une décision de videau est « proche » si les équités concernées sont à moins de 0,25 l'une de l'autre, ou si la position est *too good*. [MESURE]

*Taux d'erreur Snowie* : ER = 1000 × (somme des erreurs) ÷ (coups du joueur + coups de l'adversaire). Snowie « donne crédit » d'un coup parfait quand on danse ou qu'on roule 6-6 au bearoff. [MESURE]

*mEMG* = milli-Equivalent Money Game = équité perdue normalisée × 1000.

**Traitement videau vs coup :** les deux sont additionnés au numérateur (équité totale abandonnée). Au dénominateur, gnubg met (coups non forcés + décisions de videau proches) ; XG exclut en plus les coups non pertinents et divise pour rester dans le même ordre de grandeur que Snowie. Conséquence documentée et critiquée : à équité perdue égale, un joueur avec beaucoup de coups forcés (souvent sur la barre) obtient un PR gonflé, car son dénominateur est plus petit.

**Comparabilité entre outils** [MESURE] : gnubg/décision ≈ 1,4 × ER Snowie (~300 matchs) ; gnubg/XG comptent les décisions d'UN joueur, Snowie des DEUX ; l'échelle MWC (match) ≠ EMG (money) et varie selon le score — Zare (« Normalizing Errors », GammonVillage/bkgm) montre qu'une même erreur conceptuelle coûte ~2× moins au DMP qu'en money (0,195 vs 0,390 EMG sur l'exemple du 3-1 8/4), d'où sa proposition de renormalisation. **En pratique : ne jamais comparer un PR/ER produit par deux outils différents sans conversion explicite.**

**A.2 — Corpus du PR.** Le PR se calcule sur un ensemble FIXE de positions (chacune évaluée contre le meilleur coup de l'arbitre), pas seulement en jouant — c'est ce que font Depreli et Open Sage. Volumes publiés : Depreli « more than 4500 moves or cube decisions needed to be rolled » (étude gnubg 2010) et « more than 5000 » (étude XG2 2012) ; Open Sage « 500 money games (17,535 decisions) and 130 five-point matches (18,292 decisions) ». Pour comparer deux JOUEURS, la recommandation communautaire est ≥ 100 matchs. Les positions forcées sont exclues du dénominateur (gnubg/XG). [MESURE]

**A.3 — Métriques par décision alternatives** [MESURE/HYPOTHÈSE] :
- **Perte d'équité moyenne contre référence** (= le PR) : la plus sensible et la plus utilisée ; c'est la bonne pour votre problème.
- **Taux d'accord sur le meilleur coup** (top-1/move agreement) : moins sensible car binaire (perd la magnitude) ; utilisé par l'étude Open Sage (« disputed positions ») et la lignée Benjamin/Buro.
- **Décomposition par classe** : indispensable pour localiser une régression (Whittington localise son écart dans le « contact play »).
- **Distillation vs rollout labels** (méthode « test-set » de Tesauro) : la perte d'équité moyenne contre rollout corrèle avec le résultat en partie complète — Tesauro mesure que le joueur 2-ply « scores 0.00843 on this test set measure », en ligne avec le benchmarking en partie complète. C'est la validation empirique que la métrique par décision prédit la force réelle.

### B. Corpus de référence

| Corpus | Taille | Étiquetage | Lien | Licence | Mesure ? | Entraînement ? |
|---|---|---|---|---|---|---|
| Benchmark contact gnubg | ~100 000 positions de contact (déclaration BGonline) | rollouts communautaires, **exclu de l'entraînement** | git.savannah.gnu.org/git/gnubg/gnubg-nn.git | GPL | Oui (sortie non couverte) | **Non** |
| Bases d'entraînement gnubg (contact/race/crashed) | millions de positions | rollouts gnubg | savannah gnubg-nn | GPL | Oui | **Non** |
| wildbg-training | ~300 000 pos./itération (contact+race) | rollouts par nets wildbg successifs | github.com/carsten-wenderdel/wildbg-training | **MIT/Apache-2** | Oui | **Oui** |
| Bases exactes bearoff (1-/2-sided) | jusqu'à n pions | calcul exact (pas de rollout) | gnubg ; crate bungogood/bkgm | GPL (gnubg) / MIT (bkgm) | Oui (vérité) | prudence (régénérer soi-même) |
| Hypergammon 3 pions | espace complet | résolu exactement (perfect hash Benjamin) | github.com/bungogood/bkgm | MIT | Oui (vérité) | Oui |
| Rollouts « 501 Essential Problems » (Chow/Stick) | sous-ensemble | rollouts gnubg/XG | timothychow.net ; bgonline read=55809 | positions d'un livre © | mesure ponctuelle | Non |
| Étude Depreli (bot comparison) | 500 money games, positions disputées | rollouts XG2/gnubg/BGBlitz/Snowie | bgonline read=114338 ; extremegammon.com/studies.aspx | non spécifiée | mesure (référence) | Non |
| Opening rollouts | 15 ouvertures × réponses | gnubg 2-ply, 1296 essais | bkgm.com/openings/rollouts.html | non spécifiée | mesure ponctuelle | Non |

**Stratification (classes gnubg)** : CLASS_OVER, CLASS_HYPERGAMMON, CLASS_BEAROFF, CLASS_RACE, CLASS_CRASHED, CLASS_CONTACT. gnubg utilise 3 réseaux (contact, crashed, race) + bases de bearoff. Un corpus représentatif doit refléter la fréquence réelle de chaque classe en partie ; **ces fréquences empiriques ne sont pas publiées de source sûre [NON TROUVÉ]** — à mesurer soi-même en instrumentant des parties gnubg-vs-gnubg. Contextes de score à couvrir au minimum : money, DMP (double-match-point), et scores où le prix du gammon change fortement (2-away/2-away, post-Crawford).

### La question juridique (bloquante)

[MESURE] Position FSF, explicite : « The output of a program is not, in general, covered by the copyright on the code of the program… The exception would be when the program displays a full screen of text and/or art that comes from the program. » GPLv2/v3 : « the output from the Program is covered only if its contents constitute a work based on the Program. » Une évaluation numérique (équité, meilleur coup) produite par gnubg **ne constitue pas** une œuvre dérivée du code → **utilisable comme mesure/arbitre**, y compris pour un module WASM distribué. C'est cohérent avec votre position de départ.

En revanche, les FICHIERS de benchmark et de poids gnubg sont eux-mêmes sous GPL. Les intégrer, ou intégrer des positions étiquetées distribuées sous GPL, dans un corpus dont dérive votre réseau embarqué crée un risque de contamination copyleft. **Règle opérationnelle** : gnubg = arbitre de mesure uniquement ; entraînement seulement à partir de (a) vos propres rollouts, (b) wildbg (MIT/Apache-2), (c) bases exactes que vous régénérez. wildbg a précisément été placé sous MIT/Apache-2 pour cette raison — son auteur (bug-gnubg, nov. 2023) note que « GPL is not allowed on Apple's App Store because of license issues… This is important when being embedded as a library in another app or in the web (via web assembly). »

### C. Réduction de variance (le cœur)

**C.6 — Techniques** [MESURE, doc gnubg] :
- **Dés quasi-aléatoires (rotation + stratification)** : gnubg garantit une distribution uniforme du 1ᵉʳ jet (n×36 parties), du 2ᵉ (n×1296) et du 3ᵉ (n×46656), et stratifie l'ordre pour que tout sous-échantillon de 36 parties couvre les 36 premiers jets. XG ne fait tourner que le 1ᵉʳ jet.
- **Variable de contrôle = luck-adjusted equity** (gnubg l'active automatiquement dès ≥ 1 ply) : à chaque jet, on calcule l'espérance de l'équité sur les jets possibles *avant* de lancer ; la « chance » du jet = (équité après le jet effectif − espérance). On la soustrait, cumulée, du résultat brut.

*Estimateur à variable de contrôle (formulation explicite, à implémenter tel quel).* Pour une partie simulée de résultat brut R (points money, ou EMG, ou MWC), à chaque coup t où un joueur reçoit le jet dₜ dans la position sₜ :
- espérance pré-jet : **Ē(sₜ) = (1/36) Σ_d V(sₜ, d)**, où V(sₜ, d) est l'équité de la meilleure réponse au jet d (évaluée par le réseau au ply choisi) ;
- équité post-jet : **V(sₜ, dₜ)** ;
- chance du jet : **Lₜ = V(sₜ, dₜ) − Ē(sₜ)**.

Estimateur par partie :

> **X_vr = R − Σₜ (±Lₜ)**  (somme sur tous les jets des deux camps ; le signe suit le camp qui reçoit le jet)

Tous les termes (R, V, Ē, L, X_vr) sont dans la même unité. Comme E[Σ Lₜ] ≈ 0 sous une évaluation non biaisée, X_vr est quasi sans biais et Var(X_vr) ≪ Var(R) dès que l'évaluateur est bon. Le rollout final = moyenne des X_vr sur les N parties ; son erreur-type est écart-type(X_vr)/√N.

**Facteur de réduction obtenu** [MESURE/DÉCLARÉ] : valeur communément citée **~20–25× sur les « equivalent games »**, soit ~4,5–5× sur l'écart-type.
- XG (manuel v2) : « roughly 180 games when variance reduction is equivalent to 3600 without it » → **facteur 20×**.
- Montgomery (« Variance Reduction », GammOnLine fév. 2000, bkgm) : « **Typically variance reduction makes each game worth about twenty-five regular games.** » Données JellyFish concrètes : 864 essais « equivalent of 15,618 » (~18×), « over 18,000 » (~21×), 1800 ≈ 32 000 (~18×).
- **Mise en garde chiffrée** : le même auteur note un exemple à évaluation faible où « a variance reduced rollout of our example position is typically as accurate as a regular rollout done for **eight times** as many games », et prévient qu'avec de mauvaises évaluations « it takes about four variance reduced games to equal one game of a regular rollout » — la technique peut *augmenter* la variance dans les classes mal évaluées (backgames, primes profondes). Le ~20× est donc un ordre de grandeur, pas une constante.

**C.7 — Arithmétique coût-résolution.** Pour une métrique par décision d'écart-type par décision σ_d et N décisions, l'erreur-type de la moyenne est σ_d/√N. Pour distinguer une différence Δ avec puissance ~80 % et α = 5 % bilatéral :

> **N ≈ (1,96 + 0,84)² × 2σ²/Δ² ≈ 15,7 × σ²/Δ²** (deux échantillons *indépendants*)

Le levier décisif : **si les deux moteurs sont mesurés sur LE MÊME corpus figé (comparaison appariée par position)**, σ² est remplacé par la variance de la *différence par position* σ_diff², beaucoup plus petite car les positions faciles (où les deux moteurs jouent pareil) ne contribuent pas.
- Pour Δ = 0,001 EMG/décision, sans appariement, N est colossal (σ_d de l'ordre du centième ⇒ N ~ 10⁶–10⁷). Avec appariement + arbitre commun + concentration sur les positions disputées, l'ordre de grandeur tombe à **10⁴–10⁵ décisions disputées** rollout-arbitrées.
- Pour 0,5 % de MWC en match dupliqué : vous êtes à ±0,020 pt/partie money à 50 000 paires ; descendre à ±0,005 exige ~16× plus (~800 000 paires) — impraticable. **C'est la démonstration arithmétique qu'il faut abandonner le match dupliqué comme instrument fin et passer à la métrique par décision.**

**Écarts-types de référence** [MESURE partielle] :
- SD du résultat du 1ᵉʳ jet ≈ 91 millipoints (tourneygeek, « All That Luck », 2017).
- SD d'une partie money AVEC videau : ordre de 2,5–4+ points [HYPOTHÈSE — **non trouvé de source propre** ; l'exemple « Murat Mutant » (variance 19263, SD ≈ 139) est atypique car délibérément cube-escaladé].
- SD d'un PR sur un seul match ≈ 2,0 mEMG (matchs 5–9 pts) [DÉCLARÉ — **source unique promotionnelle GamesGrid, non corroborée**].

**C.8 — Matchs dupliqués.** Rejouer la même séquence de dés dans les deux sens = common random numbers. La variance de l'estimateur apparié vaut Var(Δ̂_pair) = Var(Δ̂_ind) − (2/n)·Cov(Y₁,Y₀) : la réduction est proportionnelle à la corrélation intra-paire (formalisme classique, corroboré par la littérature poker/RL). **Précaution obligatoire** : les deux manches d'une paire ne sont PAS indépendantes → **test apparié** (la différence par paire est l'observation) ou **bootstrap par paire**, jamais un test à deux échantillons indépendants. Sinon vous sous-estimez l'erreur-type et vous « voyez » des différences inexistantes.

### D. L'arbitre et les pièges

**D.9 — Éviter le biais d'arbitre.** Le biais auto-référentiel est réel et publié : Whittington (2026) montre qu'un réseau entraîné sur ses propres labels de rollout « capped at parity — because the labels used the champion as their own rollout leaf », et l'énonce comme principe : « a network fitted to its own engine's labels cannot exceed that engine ». Wikipédia (Rollout) : une politique faible dans une classe (p. ex. backgame) biaise systématiquement l'équité de cette classe. **Votre arbitre actuel (rollout par votre propre politique) est structurellement complaisant — il faut le remplacer.** Parades publiées :
- **Arbitre externe** (gnubg/XG comme oracle) — choix de Whittington (32 process gnubg en parallèle, via Position ID partagé) et de wildbg (force mesurée « when being analyzed with GnuBG 2-ply »).
- **Arbitrage croisé** multi-moteurs (Depreli : XG + gnubg + BGBlitz + Snowie) pour détecter la non-transitivité.
- **Rollouts très profonds** traités comme vérité (Open Sage : escalade 3 passes jusqu'à IC 95 % < 0,005).
- **Positions à réponse exacte** : bases bearoff 2-sided (gnubg « can estimate the probability of winning from that position with no error at all »), hypergammon 3 pions résolu exactement. **Aucun biais possible** — c'est l'ancre la plus solide.

**D.10 — Pièges statistiques** [MESURE/FOLKLORE] :
- **Non-transitivité** (A>B, B>C, C>A) : ne jamais conclure d'un seul appariement.
- **Sur-ajustement au corpus de test** : le benchmark gnubg est explicitement séparé de l'entraînement (« not used for training, but only for testing »). Faites de même : figez et versionnez votre corpus de mesure, ne l'entraînez jamais dessus.
- **Autocorrélation intra-match** : les erreurs successives d'un même match ne sont pas indépendantes → l'erreur-type d'un PR calculée sous hypothèse d'indépendance est **sous-estimée**. Rééchantillonnez par match (ou par position), pas par décision.
- **MWC biaisé vers le bot analyste** : le manuel gnubg avertit que le « MWC against current opponent … is biased towards the analyzing bot » — utilisez le résultat ajusté par la chance (luck-adjusted result), pas le MWC brut.

## Recommendations

**Le protocole que je recommande (prêt à implémenter).**

1. **Corpus figé, stratifié, versionné.** Générez ~50 000 positions en instrumentant des parties gnubg-2-ply vs gnubg-2-ply (avec un léger bruit pour la diversité), étiquetées par classe (contact/race/crashed/bearoff/videau) et par contexte de score (money + DMP + 2-away/2-away + post-Crawford). Respectez les proportions observées en partie réelle (que vous mesurerez vous-même, faute de source publiée). Ce corpus est un instrument de MESURE : ne l'entraînez jamais dessus. Versionnez-le (hash) pour rendre les campagnes reproductibles.

2. **Arbitre neutre à variable de contrôle, par escalade en 3 passes** (méthode Open Sage) : (a) gnubg 3-ply pour toutes les décisions ; (b) si l'écart meilleur/second < 0,05, rollout tronqué gnubg à réduction de variance ; (c) si encore < 0,02, rollout complet gnubg (VR + quasi-random, 1296 → jusqu'à IC 95 % < 0,005). Doublez l'arbitre avec XG sur un sous-échantillon pour tester la non-transitivité. Pour toute position bearoff/hypergammon résoluble : **vérité exacte, pas de rollout**.

3. **Métrique = perte d'équité moyenne appariée par position.** Pour chaque position, comparez la perte de VOTRE coup et celle du coup gnubg contre la MÊME vérité de terrain. La statistique est la différence par position (votre perte − perte de référence). Testez par **bootstrap par position** (ou par match si vous jouez des matchs) — jamais sous hypothèse d'indépendance intra-match.

4. **Budget concentré sur le signal.** Ne dépensez le calcul de rollout que sur les positions « disputées » (votre moteur ≠ gnubg). Tout le signal y réside. Une itération gagnant 0,002 EMG/décision devient détectable avec ~10⁴–10⁵ décisions disputées rollout-arbitrées — de l'ordre de l'heure, pas du jour. C'est le gain de deux ordres de grandeur que vous cherchiez, obtenu proprement (arbitre neutre) et non par complaisance.

**Tableau coût-résolution (3 protocoles).**

| Protocole | Résolution atteinte | Coût (ordre de grandeur) |
|---|---|---|
| Match dupliqué 7 pts (votre instrument actuel) | ±0,26 pt MWC ; ±0,020 pt/partie money | 50 000 paires ≈ 4,9 j × 30 process |
| Match dupliqué visant ±0,005 pt/partie | ±0,005 pt/partie money | ~800 000 paires (≈ 16×) — **impraticable** |
| **Perte d'équité appariée + arbitre gnubg escaladé** (recommandé) | **~0,001–0,002 EMG/décision** | ~10⁴–10⁵ décisions disputées rollout-arbitrées (heures) |

**Seuils qui changent la décision :**
- Différence appariée moyenne > **+0,002 EMG/décision**, IC 95 % bootstrap excluant 0 → amélioration réelle, gardez l'itération.
- XG et gnubg comme arbitres donnent des signes opposés → suspectez le biais d'arbitre, escaladez la profondeur de rollout ou ajoutez un troisième arbitre.
- Gain concentré dans UNE classe et négatif ailleurs → régression cachée : décomposez avant de conclure.
- Verdict « plus fort que gnubg » publiable → ≥ 100 matchs dupliqués (test apparié) EN COMPLÉMENT de la mesure par décision, pour confirmer que l'avantage par décision se traduit en résultat.

## Caveats
- **Ce que je n'ai pas trouvé de source sûre :** (1) l'écart-type par décision de la perte d'équité — indispensable à l'arithmétique exacte de taille d'échantillon ; **à mesurer sur votre propre corpus** (c'est un sous-produit gratuit de la première campagne). (2) L'écart-type d'une partie money AVEC videau en points (la valeur ~2,5–4 pt reste non sourcée proprement). (3) Les fréquences empiriques publiées d'apparition de chaque classe gnubg en partie réelle. (4) Un chiffre officiel de facteur de réduction de variance signé nominalement par Xavier Dufaure de Citres : le 20× vient du texte du manuel XG, pas d'une déclaration personnelle. (5) La taille exacte, à l'unité près, du benchmark contact gnubg (« about 100,000 » est une déclaration BGonline, pas un décompte officiel).
- Le facteur de réduction de variance ~20× est un ordre de grandeur, pas une constante : il dépend de la qualité de l'évaluateur et **peut s'inverser** (variance-augmentant) dans les classes mal évaluées.
- La SD de PR à 2,0 mEMG/match provient d'une source unique promotionnelle (GamesGrid) non corroborée — indicatif seulement.
- Grokipedia et GamesGrid n'ont servi qu'à recouper des faits attestés ailleurs ; ne pas s'y fier isolément. Les sources primaires fiables du rapport sont : gnu.org/gnubg.org (manuel et doc), extremegammon.com, bkgm.com (Montgomery, Zare), BGonline.org, github.com/carsten-wenderdel (wildbg), whittingtonchess.com et bgsage.ai (études de benchmarking modernes), fsf.org/gnu.org (licences). Dates de consultation : 26 août 2026.