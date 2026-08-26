# DS-05 — Recherche stochastique — retour

**Date de la recherche** : 2026-08-26 · **Outil** : Claude, recherche approfondie
**Prompt** : `docs/recherche/DS-05-recherche-stochastique.md`, version du 2026-08-26

> **Ce que ce retour décide** : d'où viennent les évaluations économisables.
> **Ce qu'il conclut** : pas de la profondeur (Hauk-Buro-Schaeffer corroborent T36) ; les gisements
> compatibles avec le noyau par lots sont le regroupement exact des jets équivalents, le cache à
> clé position+ply avec bornes (−37 % chez Veness-Blair) et un pré-tri plus discriminant pour
> resserrer k ; Star2 (−75 à −95 % de nœuds) sérialise les évaluations et menace le débit par lots.
> **Ce qu'il ne tranche pas** : aucun chiffre backgammon pour le regroupement de jets ni pour
> l'échantillonnage clairsemé ; l'interaction Star2 × noyau par lots n'a jamais été publiée — les
> deux sont à mesurer chez nous.

---
# gammonNet — Réduire le nombre d'évaluations par décision dans un arbre à nœuds de hasard

*Rapport de recherche. Date de consultation de toutes les sources : 26 août 2026.*
*Étiquettes : `[MESURE]` = publication avec protocole et chiffres ; `[DÉCLARÉ]` = affirmation d'un auteur/doc sans protocole complet ; `[HYPOTHÈSE]` = mon raisonnement appliqué à votre cas ; `[FOLKLORE]` = savoir de communauté non mesuré.*

## TL;DR

- **Le levier n'est pas la profondeur, c'est le facteur de branchement du hasard.** La littérature *mesurée* qui réduit vraiment le nombre d'évaluations attaque les 21 jets (regroupement de jets équivalents + échantillonnage clairsemé) et la réutilisation par cache/transposition — techniques **compatibles avec votre noyau par lots**. Le gain le mieux documenté sur les *coups* (Star2 de Ballard/Hauk) réduit les nœuds de 75–95 % à profondeur 5 au backgammon `[MESURE]`, **mais sérialise les évaluations et casse donc le calcul par lots** — c'est le point de tension central chez vous.
- **Vos propres mesures sont corroborées par la littérature.** Hauk, Buro & Schaeffer montrent qu'avec un évaluateur fort (les réseaux de gnubg), aller plus profond n'améliore quasiment pas la force de jeu (profondeurs 1/3/5 « quasi identiques ») `[MESURE]`. Votre +0,00022 d'équité pour 15× de calcul en 3-ply est exactement ce phénomène. **Arrêtez d'investir dans la profondeur.**
- **Trois chantiers batch-compatibles à fort rendement** : (1) regrouper les jets à ensemble de coups atteignables identique et échantillonner le reste ; (2) étendre votre cache aux bornes dépendantes de la profondeur (transposition aux nœuds de hasard, −37 % mesuré chez Veness & Blair) ; (3) améliorer l'ordonnancement pour resserrer le filtre `k`. Le `×3,41` de votre cache confirme que la voie « mémoïsation » est la plus rentable chez vous.

## Key Findings

1. **Ballard (1983)** introduit Star1 et Star2. Résultats analytiques : un parcours gauche-droite en profondeur d'abord réduit le coût d'une recherche exhaustive de **25–30 %** ; l'algorithme à sondage (« probing », ancêtre de Star2) sur arbres *-minimax réguliers réduit la recherche de **plus de 50 %** avec ordre aléatoire des successeurs `[MESURE]`.
2. **Hauk, Buro & Schaeffer (2004), backgammon** : Star2 réduit les nœuds/temps de **~75 % à ~95 % à profondeur 5** vs Expectimax (>10× globalement) ; Star1 ne fait « qu'une légère baisse ». Sondage réussi **64,2 %** du temps à profondeur 5 grâce à un meilleur ordonnancement (Ballard ≤45 %) `[MESURE]`. Mais Star2 restait à **~21 s/coup** sur un Athlon-XP 1,8 GHz. L'abstract, verbatim : *« Star2 allows strong backgammon programs to conduct depth-5 full-width searches (up from 3) under tournament conditions on regular hardware without using risky forward-pruning techniques. »* `[MESURE]`
3. **La profondeur n'est pas un levier de force** (Hauk et al.) : avec l'évaluateur fort et cohérent de gnubg, les profondeurs 1/3/5 donnent une force « quasi identique » ; la profondeur ne compte que quand on injecte du bruit dans l'évaluation `[MESURE]`. C'est la validation externe de votre mesure interne.
4. **Transposition aux nœuds de hasard (Veness & Blair 2007)** : stocker une borne *inférieure* et *supérieure* (pas un score unique) avec leur profondeur. Verbatim : *« Empirical results show that these techniques can reduce the search effort of Ballard's Star2 algorithm by 37 percent »* (jeu de dés, profondeur 13) `[MESURE]`.
5. **Le hasard lui-même est compressible** : le regroupement de jets à ensemble de coups atteignables identique est **exact** (aucune perte) ; l'échantillonnage clairsemé (Kearns-Mansour-Ng) est quasi optimal avec un coût **indépendant de la taille de l'espace d'états** mais exponentiel en horizon `[MESURE]`. MCMS (Lanctot et al. 2013) combine les deux, mais n'a **pas** été testé au backgammon.
6. **MCTS ne bat pas l'expectiminimax au backgammon** : Van Lishout, Chaslot & Uiterwijk (2007) — leur programme McGammon trouve 3 bons conseils et 2 ouvertures jouées par ~30 % des pros, mais, verbatim, *« For the other nine initial dice, McGammon plays very strange moves, especially for 1-6 and 2-4 where most of the professional players agree on another move than the one found by our program »* `[DÉCLARÉ]`. L'expectiminimax + réseau reste supérieur ici.
7. **gnubg est plat en profondeur** grâce aux petits réseaux d'élagage (<1 % des coups changent), aux movefilters très serrés, et à un cache d'évaluation — pas grâce au *-minimax `[MESURE]`/`[DÉCLARÉ]`.

## Details

### 1. Les algorithmes *-minimax (Ballard ; Hauk, Buro, Schaeffer ; Veness & Blair ; Lanctot et al.)

**Principe.** Star1 et Star2 étendent l'élagage alpha-bêta aux nœuds de hasard en exploitant le fait que la fonction d'évaluation est **bornée** dans `[L, U]`. À un nœud de hasard, on ne peut pas couper dès qu'un successeur sort de la fenêtre (comme à un nœud min/max) ; il faut prouver que la **somme pondérée** de tous les successeurs sort de `[α, β]`. Star1 rétrécit la fenêtre `[α', β']` de chaque successeur en supposant le pire/meilleur cas `L`/`U` pour les jets non encore développés. Star2 ajoute une **phase de sondage** : il évalue *un seul* coup sous chaque jet pour établir une borne bon marché, ce qui coupe souvent sans développer tous les enfants `[DÉCLARÉ]` (Ballard 1983 ; Lanctot et al. 2013, pseudocode Algorithmes 1 et 2).

**Votre cas `[0,1]` est directement exploitable.** Vos sorties sont des probabilités bornées dans `[0,1]`, donc `L=0, U=1` (ou l'équité correspondante, bornée aussi). C'est exactement l'hypothèse dont Star1/Star2 ont besoin ; Veness & Blair utilisent `U=+1.0, L=-1.0`. `[HYPOTHÈSE]` Plus la fenêtre `[α,β]` est étroite (donc plus l'ordonnancement est bon), plus vous coupez — c'est pourquoi Star2 et l'ordonnancement sont indissociables.

**Chiffres mesurés.**
- Ballard 1983 : gauche-droite en profondeur d'abord **−25 à −30 %** ; sondage **> −50 %** avec ordre aléatoire `[MESURE]`.
- Hauk et al. 2004 (backgammon ; 500 positions de contact issues de la base d'entraînement de GNU Backgammon ; Athlon-XP 1,8 GHz, 512 Mo RAM, Linux Slackware, C compilé `gcc -O3` ; table de transposition 128 Mo à hachage Zobrist ; évaluateur = réseaux de gnubg v0.14, >90 % du CPU) : à **profondeur 5**, économie de nœuds/temps de Star2 de **~75 % à ~95 %** selon la position (>10× globalement) ; **Star1 à peine mieux qu'Expectimax** ; sondage réussi **64,2 %** à profondeur 5 `[MESURE]`. Profondeurs testées : 1, 3, 5 uniquement.
- Veness & Blair 2007 : transposition aux nœuds de hasard **−37 %** sur Star2 (jeu de dés, profondeur 13) `[MESURE]`.
- Lanctot et al. 2013 (MCMS) : compétitif avec MCTS+double progressive widening, surpasse systématiquement les *-minimax classiques à temps de réflexion égal — mais sur Pig, EinStein würfelt Nicht!, Can't Stop et Ra ; **pas de backgammon** `[MESURE]`.

**Pourquoi les moteurs de production ne l'emploient-ils pas ?** Trois raisons documentées/inférées :
- **(a) L'évaluateur domine le coût.** Chez Hauk, l'évaluation neuronale consomme >90 % du CPU ; Star2 réduit le *nombre* d'évaluations mais reste à 21 s/coup. `[MESURE]`
- **(b) La profondeur ne paie pas.** Puisqu'aller de 3 à 5 plies n'améliore quasiment pas la force avec un évaluateur fort (Hauk et al. ; votre +0,00022), l'intérêt de Star2 — qui sert à aller *plus profond* à budget constant — disparaît. `[MESURE]`
- **(c) Star2 sérialise les évaluations.** `[HYPOTHÈSE]` Le sondage et les coupures dépendent du résultat de l'évaluation précédente : c'est un algorithme strictement séquentiel. Sur votre noyau qui évalue par paquets de 32, cette dépendance stricte peut coûter plus qu'elle ne rapporte — exactement le risque que vous signalez. gnubg a préféré les petits réseaux d'élagage + movefilters, qui restent parallélisables/vectorisables.

### 2. L'ordre des coups

**Théorie générale (alpha-bêta).** En ordre parfait, le nombre de feuilles passe de `O(b^d)` à `O(b^(d/2)) = O(√(b^d))` : le facteur de branchement effectif est réduit à sa **racine carrée** (Knuth & Moore 1975) `[MESURE]`. Exemple canonique : à profondeur 4 avec b=36, l'élagage optimal élimine tout sauf ~2000 des >1 000 000 feuilles (−99,8 %) `[MESURE]`. En pratique, transposition + heuristique d'historique + killer + approfondissement itératif atteignent **~99 % de réduction**, proche de l'arbre minimal ; DarkThought rapporte un facteur de branchement effectif ramené à **2–3** et une taille d'arbre à **~55 % de l'arbre minimal** `[MESURE]`.

**Spécifique backgammon.** Hauk et al. ordonnent les coups par une heuristique bon marché (nombre de pions adverses envoyés à la barre, nombre de blots laissés, nombre de points sûrs faits), et sélectionnent les successeurs de sondage en priorité « frappe puis fabrication de point ». C'est ce qui fait passer le taux de sondage réussi de ≤45 % (Ballard) à 64,2 % `[MESURE]`. **Votre réseau d'élagage 196→32→5 joue déjà ce rôle** : c'est un réseau de politique/valeur bon marché qui pré-trie. `[HYPOTHÈSE]` La marge de progrès est de le rendre plus discriminant en tête de liste (pour resserrer `k`) plutôt que plus profond.

**Compatibilité batch.** L'ordonnancement lui-même est batch-compatible (le pré-tri évalue les candidats en un lot, puis on approfondit les survivants en lots). Ce qui casse le batch, c'est l'*usage* de l'ordre dans une coupure alpha-bêta stricte. `[HYPOTHÈSE]`

### 3. Tables de transposition dans un arbre stochastique

**Taux de transposition.** Au backgammon, de nombreuses séquences (jet, coup) convergent : c'est le fondement de votre cache et de son `×3,41`. Je n'ai **pas** trouvé de mesure publiée du *taux* de transposition spécifiquement au backgammon (voir « Ce que je n'ai pas trouvé »).

**Le problème de la profondeur dans la clé.** Votre clé est « la position seule ». C'est correct pour un cache d'évaluation 0-ply, mais **incorrect si la valeur stockée dépend de la profondeur restante** : une entrée calculée à profondeur 1 ne doit pas servir une requête à profondeur 3. La solution standard (Veness & Blair) : stocker **profondeur + borne inférieure + borne supérieure** (aux nœuds de hasard on a besoin des deux bornes, pas d'un score unique + drapeau comme en alpha-bêta), et n'utiliser une entrée que si sa profondeur ≥ la profondeur demandée. Cela donne −37 % `[MESURE]`.

**Ce que fait gnubg.** Le cache d'évaluation de gnubg mémoïse l'évaluation d'une position à un niveau de ply donné ; la documentation et les listes de diffusion montrent que l'évaluation d'une position est faite « au niveau de ply demandé », donc le ply fait partie du contexte d'évaluation. `[DÉCLARÉ]`

**Compatibilité batch.** Élevée : une consultation de cache est indépendante des autres. `[HYPOTHÈSE]` Amélioration recommandée : passer d'une clé « position » à une clé « position + ply » (ou stocker un vecteur par ply), et stocker des bornes plutôt qu'un point si vous adoptez une forme de coupure.

### 4. Le hasard lui-même : ne pas développer les 21 jets

C'est **le** gisement, et il est batch-compatible.

- **Regroupement de jets équivalents (exact, sans perte).** `[HYPOTHÈSE]`/`[FOLKLORE]` Pour une position donnée, deux jets distincts peuvent conduire au **même ensemble de positions atteignables** (fréquent en fin de partie, en course, et quand des points sont bloqués). Fusionner ces jets et sommer leurs probabilités ne change **rien** au résultat exact et supprime des évaluations. Aucune publication chiffrée trouvée au backgammon, mais le principe est exact par construction.
- **Échantillonnage clairsemé (sparse sampling, Kearns-Mansour-Ng 1999/2002).** On échantillonne `C` résultats par nœud de hasard au lieu des 21. Garanties : action quasi optimale, temps **indépendant de la taille de l'espace d'états**, mais **exponentiel en horizon** ; en pratique de petites valeurs de `C` suffisent (confirmé par Lanctot et al.) `[MESURE]`. Le biais/variance décroît quand `C` croît.
- **Échantillonnage préférentiel / variables antithétiques / jets communs (common random numbers).** gnubg réduit la variance de ses *rollouts* par des **dés quasi-aléatoires** (rotation/stratification des 2–3 premiers coups) et une **réduction de variance** par différence d'équité entre plies. Verbatim (*All About GNU*, gnubg.org) : *« This ingenious technique was introduced by Fredrik Dahl, the author of Jellyfish… With it, 100 rolled out games with Variance Reduction can be the equivalent of 5,000 games with no Variance Reduction »* (la version bkgm.com dit « 5 000 – 10 000 games ») `[DÉCLARÉ]`. Ce sont des techniques de rollout, pas de recherche par plies, mais les *jets communs* entre coups candidats (évaluer tous les coups candidats sur le *même* sous-ensemble de jets) réduisent la variance de comparaison — directement applicable à votre filtre. `[HYPOTHÈSE]`
- **MCMS (Lanctot et al. 2013)** unifie sparse sampling + coupures Star : « approche la décision optimale quand le nombre d'échantillons croît ». Conçu pour jeux « densément stochastiques » où l'on ré-échantillonne rarement le même successeur — **le backgammon est à l'opposé** (21 jets, forte répétition), donc l'intérêt du *sampling* y est moindre que celui du *regroupement exact*. `[HYPOTHÈSE]`

**Compatibilité batch : excellente.** Réduire ou regrouper les jets diminue le nombre d'évaluations *sans* introduire de dépendance séquentielle : les évaluations restent indépendantes et se mettent parfaitement en lots de 32. `[HYPOTHÈSE]`

### 5. L'allocation variable de profondeur

- **Filtres de gnubg (movefilter).** Valeurs par défaut documentées : niveau « Normal » (World Class, 2-ply) — au 1-ply : « garder les 0 premiers coups 0-ply + jusqu'à **8** coups de plus dans une équité de **0,16** », pas d'élagage 1-ply au-delà `[MESURE/DÉCLARÉ]`. Niveau « Large » (Supremo) — jusqu'à **16** coups dans **0,32** `[MESURE/DÉCLARÉ]`. Un filtre 3-ply testé par un développeur (liste bug-gnubg) : 0-ply 16@0,32 ; 1-ply 8@0,16 ; 2-ply 4@0,06 → « presque 20 % plus rapide sans changement significatif de force (<1 % sur le benchmark Depreli) » `[MESURE]`. C'est votre filtre `(0,1,3)` / `k=12` / `k=3` sous une autre forme.
- **Coûts relatifs des niveaux gnubg** (unités de temps, message de liste, hypothèses explicites sans élagage/cache) : Expert 0-ply ≈ 20 ; World Class 2-ply ≈ 40 000 ; Supremo 2-ply/large ≈ 80 000 ; Grandmaster 3-ply ≈ 400 000 ; 4-ply ≈ 8 000 000 `[DÉCLARÉ]`. La seule différence World Class↔Supremo est le movefilter (×2).
- **Volatilité / marge entre meilleur et deuxième coup.** gnubg a une notion de **volatilité** pour les décisions de cube (doublement), pas pour l'allocation de profondeur des coups. La littérature générale (recherche sélective, conspiracy numbers, best-first, MTD(f)) existe, mais MTD(f) est un algorithme à fenêtre nulle qui **sérialise** et suppose une valeur scalaire — mal adapté aux nœuds de hasard. `[DÉCLARÉ]`/`[HYPOTHÈSE]`
- **Quiescence dans un jeu à hasard.** Concept peu formalisé au backgammon ; existe pour Stratego. `[DÉCLARÉ]` `[HYPOTHÈSE]` Chez vous, un critère d'arrêt piloté par la marge entre les deux meilleurs coups du niveau précédent (si la marge >> bruit d'évaluation, ne pas approfondir) est un candidat naturel, cohérent avec votre observation que le 3-ply ne rapporte rien.

### 6. MCTS à nœuds de hasard

- **Variantes** : double progressive widening (Couëtoux et al. 2011, `k = ⌈C·v^α⌉`), open-loop MCTS, UCT stochastique, échantillonnage d'un seul résultat par nœud de hasard. `[DÉCLARÉ]`
- **Preuve au backgammon** : Van Lishout, Chaslot & Uiterwijk (2007) — coups d'ouverture « très étranges » pour la plupart des 21 jets (verbatim ci-dessus, §Key Findings) `[DÉCLARÉ]`. **Aucune preuve que MCTS batte l'expectiminimax au backgammon.**
- **Pourquoi l'expectiminimax reste supérieur ici** `[HYPOTHÈSE]` : (a) le facteur de branchement du hasard (21) est petit et *connu exactement* → l'espérance exacte est calculable, l'échantillonnage n'apporte rien ; (b) vous disposez déjà d'un évaluateur fort — MCTS brille surtout *sans* bon évaluateur ; (c) MCTS est intrinsèquement séquentiel (chaque simulation dépend des statistiques accumulées) → **mauvaise mise en lots**. Note : dans Lanctot et al., MCTS est battu par *-minimax justement à Carcassonne, jeu à hasard « régulier » proche du backgammon.

### 7. Pourquoi gnubg est plat en profondeur

Documenté :
- **Réseaux d'élagage.** Un jeu de petits réseaux pré-élague les candidats avant la recherche profonde ; le manuel gnubg rapporte l'analyse de Jim Segrave : **moins de 1 % des coups changent** avec les réseaux d'élagage activés, « et dans la plupart de ces cas le coup n'aurait rien changé à la partie » `[MESURE/DÉCLARÉ]`. C'est votre réseau 196→32→5.
- **Movefilters serrés** (voir §5) : « accepter 0 coup » d'office pour ne pas perdre de temps sur les coups évidents `[DÉCLARÉ]`.
- **Cache d'évaluation** indexé par position + ply `[DÉCLARÉ]`.
- **Pas de *-minimax** : gnubg n'utilise pas Star1/Star2 ; il mise sur élagage neuronal + filtres + cache. `[DÉCLARÉ]`

Conclusion : le « plat en profondeur » de gnubg vient de ce que le movefilter réduit la largeur *avant* d'ajouter un ply, et que le cache absorbe les transpositions. C'est exactement votre architecture — l'écart de 25–60× tient donc au **coût par évaluation** et au **nombre d'évaluations survivant au filtre**, pas à l'algorithme de recherche.

### 8. La réutilisation entre décisions

- **Ce qui l'empêche** : le jet de dés qui tombe entre deux décisions rend une grande partie de l'arbre non pertinente ; seule la **partie position-dépendante** (le cache d'évaluation) survit. `[HYPOTHÈSE]`
- **Ce qui survit** : le cache d'évaluation par position (votre `×3,41`) traverse les décisions successives — c'est déjà de la réutilisation inter-décisions. En alpha-bêta/MCTS, le « ponder » et le tree reuse sont documentés mais leur gain au backgammon est plafonné par l'entropie du jet (36 issues). `[HYPOTHÈSE]`
- **Recommandation** : ne pas persister l'arbre de recherche (faible rendement), mais **persister et grossir le cache d'évaluation** entre décisions et entre parties (c'est là qu'est le rendement mesuré).

### Tableau des techniques (trié par gain attendu **dans votre contexte batch**)

| Technique | Gain publié (facteur, conditions) | Perte de qualité, si mesurée | Compatible calcul par lots ? | Effort d'implémentation | Source |
|---|---|---|---|---|---|
| Regroupement de jets à ensemble de coups identique | Exact ; supprime les jets redondants (aucune publication chiffrée au backgammon) `[HYPOTHÈSE]` | **Nulle (exact)** | **Oui** — évaluations indépendantes | Faible-moyen | Raisonnement ; folklore backgammon |
| Échantillonnage clairsemé des jets (C < 21) | Quasi optimal, coût indépendant de l'espace d'états, exp. en horizon ; petit C suffit `[MESURE]` | Biais→0 quand C↑ | **Oui** | Moyen | Kearns-Mansour-Ng 1999/2002 ; Lanctot et al. 2013 |
| Cache/transposition avec clé incluant le ply + bornes (inf/sup) | **−37 %** de nœuds sur Star2 (dés, prof. 13) `[MESURE]` ; base de votre ×3,41 | Nulle (exact) | **Oui** — consultations indépendantes | Moyen | Veness & Blair 2007 |
| Meilleur ordonnancement (pré-tri par réseau de politique + historique) | Ordre parfait → **√b** (−99,8 % à prof. 4, b=36) ; +TT+historique ≈ −99 % `[MESURE]` | Nulle (change seulement l'ordre) | Oui pour le pré-tri ; l'usage en coupure stricte casse le batch | Faible (vous l'avez déjà) | Knuth & Moore 1975 ; Hauk et al. 2004 |
| Jets communs / réduction de variance entre coups candidats | Rollouts gnubg : 100 parties ≈ 5 000 (voire 10 000) `[DÉCLARÉ]` | Nulle (comparaison plus stable) | **Oui** | Faible | Manuel gnubg (Dahl/Jellyfish) |
| *-Minimax Star2 (élagage aux nœuds de hasard) | **−75 à −95 %** nœuds à prof. 5 (backgammon) `[MESURE]` ; Ballard −25–30 % / >−50 % | Nulle (exact) | **Non — sérialise les évaluations** (risque net négatif chez vous) | Élevé | Ballard 1983 ; Hauk, Buro, Schaeffer 2004 |
| CHANCEPROBCUT (élagage avant aux nœuds de hasard) | *« reduce the search tree significantly without a loss of move quality »* (Stratego, dés) `[MESURE]` | Aucune perte de qualité mesurée ; hausse de force | Partiellement — pré-recherches peu profondes sérialisées | Élevé | Schadd, Winands, Uiterwijk 2009 |
| MCTS + double progressive widening | Compétitif *ailleurs* ; **battu par *-minimax** à Carcassonne ; faible au backgammon | Coups d'ouverture « très étranges » `[DÉCLARÉ]` | Non — séquentiel | Élevé | Van Lishout et al. 2007 ; Couëtoux et al. 2011 ; Lanctot et al. 2013 |
| Réutilisation de l'arbre entre décisions (ponder/tree reuse) | Plafonné par le jet intercalaire ; seul le cache survit `[HYPOTHÈSE]` | — | Oui (cache) | Faible | Littérature TT/ID générale |

## Recommendations

**Étape 0 — Cesser d'investir dans la profondeur.** Vos données et Hauk et al. concordent : avec un évaluateur fort, 3-ply ≈ 2-ply en force. Gelez le 3-ply comme option « analyse hors-ligne » et optimisez le 2-ply. **Seuil de révision** : si vous ajoutez du bruit/une incertitude à l'évaluateur (réseau plus petit pour le WASM mobile), la profondeur redevient utile (Hauk : à bruit n=0,03, un joueur 1-ply perd 64 % contre un joueur 5-ply). Mesurez le bruit effectif de votre réseau compressé avant de trancher.

**Étape 1 — Attaquer les 21 jets (batch-safe, rendement immédiat).**
1. Implémentez le **regroupement exact** des jets à ensemble de coups atteignables identique par position. Gratuit en qualité.
2. Ajoutez un **échantillonnage clairsemé optionnel** des jets (C paramétrable) pour les nœuds profonds seulement.
*Mesure de validation* : nombre d'évaluations par décision et équité perdue vs 2-ply plein, sur votre corpus. **Seuil** : adoptez le regroupement inconditionnellement ; adoptez le sampling si la perte d'équité < votre budget (p.ex. < 0,001/décision, soit le quart de votre perte actuelle à k=3, 0,0039).

**Étape 2 — Muscler le cache (batch-safe, c'est là qu'est votre ×3,41).**
- Passez la clé de « position » à « position + ply » (ou stockez un vecteur par ply) pour pouvoir cacher les valeurs profondes sans corruption.
- Stockez des **bornes inf/sup** si vous adoptez plus tard une coupure.
- **Persistez** le cache entre décisions et parties.
*Mesure* : taux de succès du cache et facteur de gain vs cache position-seule. **Seuil** : conserver si gain net > coût mémoire sur cible WASM mobile (surveillez l'empreinte : c'est votre contrainte dure).

**Étape 3 — Resserrer le filtre via un meilleur pré-tri (batch-safe).** Améliorez la précision *au sommet* de la liste de votre réseau 196→32→5 (distillation depuis le grand réseau, ou tête de classement dédiée) pour pouvoir baisser `k` sans perdre d'équité. *Mesure* : à `k` fixé, l'équité perdue baisse-t-elle ? **Seuil** : viser k=3 avec la perte d'équité de l'actuel k=12 (0 équité perdue mesurable).

**Étape 4 — Star2 : à traiter comme une expérience, pas un défaut.** Le gain nodal (75–95 %) est réel mais il **sérialise** vos évaluations. Ne l'activez que si vous pouvez maintenir le débit du noyau batch (p.ex. en batchant la phase de sondage sur tous les jets simultanément — une variante non standard à prototyper). *Mesure décisive* : temps réel par décision **avec votre noyau batch de 32**, pas nombre de nœuds. **Seuil de rejet** : si Star2 réduit les nœuds mais augmente le temps mur à cause de lots plus petits, abandonnez-le.

**Ne pas faire** : MCTS (aucune preuve de supériorité au backgammon, séquentiel) ; persistance de l'arbre inter-décisions (plafonnée par le jet).

**Artefacts / licences.** Hors périmètre comme demandé : poids de GNU Backgammon (GPL-3, https://www.gnu.org/software/gnubg/), réseaux HedgeHog (clause non commerciale), bgsage (AGPL-3). Utiles pour la *documentation d'algorithme* (movefilters, réseaux d'élagage, réduction de variance) sans transcription de code ni de constantes réglées à la main.

**Sources principales (avec liens, consultées le 26 août 2026) :**
Ballard 1983, *The *-Minimax Search Procedure for Trees Containing Chance Nodes*, Artificial Intelligence 21(3):327–350 — https://www.sciencedirect.com/science/article/abs/pii/S0004370283800150 (PDF : https://www.cs.uleth.ca/~benkoczi/3750/data/ballard83-star_alpha_beta.pdf) ·
Hauk, Buro, Schaeffer 2004, *-Minimax Performance in Backgammon*, CG 2004, LNCS 3846:51–66 — https://link.springer.com/chapter/10.1007/11674399_4 ; thèse Hauk *Search in Trees with Chance Nodes*, Univ. Alberta 2004 — https://era.library.ualberta.ca/items/45d1c4fc-f1f3-4cc7-a881-c794df98c39b ·
Veness & Blair 2007, *Effective Use of Transposition Tables in Stochastic Game Tree Search*, IEEE CIG 2007:112–116 — https://cgi.cse.unsw.edu.au/~blair/pubs/2007VenessBlairCIG.pdf ·
Lanctot, Saffidine, Veness, Archibald, Winands 2013, *Monte Carlo *-Minimax Search*, IJCAI 2013:580–586 — https://www.ijcai.org/Proceedings/13/Papers/093.pdf (arXiv 1304.6057) ·
Schadd, Winands, Uiterwijk 2009, *CHANCEPROBCUT: Forward Pruning in Chance Nodes*, IEEE CIG 2009:178–185 — https://dke.maastrichtuniversity.nl/m.winands/documents/CIG2009.pdf ·
Van Lishout, Chaslot, Uiterwijk 2007, *Monte-Carlo Tree Search in Backgammon*, CGW 2007:175–184 — https://www.researchgate.net/publication/228378473_Monte-Carlo_tree_search_in_backgammon ·
Kearns, Mansour, Ng 2002, *A Sparse Sampling Algorithm for Near-Optimal Planning in Large MDPs*, Machine Learning 49:193–208 — https://www.cis.upenn.edu/~mkearns/papers/sparsesampling-journal.pdf ·
Knuth & Moore 1975, *An Analysis of Alpha-Beta Pruning*, Artificial Intelligence 6(4):293–326 ·
Documentation GNU Backgammon (movefilters, réseaux d'élagage, rollouts/variance) — https://www.gnu.org/software/gnubg/manual/gnubg.html , https://www.gnu.org/software/gnubg/manual/html_node/Pruning-neural-networks.html , http://www.gnubg.org/documentation/doku.php?id=rollouts .

## Caveats

- **Ambiguïté de « profondeur/ply ».** Hauk et al. comptent en « profondeur » (1,3,5) là où gnubg compte en « ply » (0,1,2). La « profondeur 5 » de Hauk ≈ « 2-ply » de gnubg. Traduisez avant toute comparaison directe.
- **Le « −93 % » qui circule est une erreur d'attribution.** Ce chiffre vient de la thèse de Briesemeister sur le jeu **OnTop**, pas du backgammon. Le vrai chiffre backgammon de Hauk et al. est **75–95 % à profondeur 5**. J'ai retenu ce dernier.
- **Force en fonction de la profondeur — chiffres à manier avec soin.** Le résultat vérifiable verbatim (cité par Veness & Blair depuis la thèse de Hauk) est : *« Hauk showed that a 9-ply player wins 65% against a 1-ply player »* `[MESURE]`. Le chiffre souvent répété « 9 plies vs 5 plies → +2,5 % de victoires » figure chez Schadd/Winands/Uiterwijk (2009) attribué à Hauk `[DÉCLARÉ]`, mais le papier backgammon principal ne teste que les profondeurs 1/3/5 ; à traiter comme non confirmé faute de copie lisible de la thèse. Les deux vont dans le même sens : le gain de profondeur est réel contre un adversaire faible (1-ply), marginal entre niveaux forts (5→9).
- **Chiffres de coûts des niveaux gnubg** (20 / 40 000 / … / 8 000 000) proviennent d'un message de liste de diffusion avec hypothèses explicites (sans cache/élagage) : ordres de grandeur, pas mesures contrôlées.
- **Perte de qualité de l'échantillonnage clairsemé au backgammon** : les bornes de Kearns-Mansour-Ng sont théoriques et lâches ; l'erreur *pratique* à petit C n'est pas mesurée au backgammon (Lanctot et al. mesurent sur d'autres jeux). À mesurer chez vous.
- **Valeurs numériques exactes des tables de Hauk et al.** (nœuds par profondeur) : perdues dans les OCR disponibles ; seules les fourchettes (75–95 %, 64,2 %, 21 s) et l'abstract sont vérifiables sur source primaire.

## Ce que je n'ai pas trouvé

- **Un taux de transposition chiffré spécifique au backgammon** (fraction de (jet, coup) convergeant vers la même position). Votre `×3,41` en est une mesure indirecte ; aucune publication ne le donne directement.
- **Une mesure publiée de l'erreur du sparse sampling / du regroupement de jets *au backgammon*** en fonction de C. MCMS le fait ailleurs (Pig, Ra…), pas au backgammon.
- **Un facteur « ordre aléatoire vs bon ordre » chiffré pour le backgammon** dans le papier Hauk (le taux de sondage 64,2 % est le proxy le plus proche ; le facteur net est documenté pour OnTop, pas le backgammon).
- **Un critère de quiescence/volatilité formalisé pour l'allocation de profondeur des *coups* au backgammon** (la volatilité gnubg concerne le *cube*).
- **Une comparaison batch-vs-séquentiel chiffrée pour Star2** : personne n'a publié, à ma connaissance, l'interaction entre *-minimax et un noyau d'inférence neuronale par lots — c'est précisément votre contribution potentielle.