# DS-08 — Videau, au-delà de Janowski — retour

**Date de la recherche** : 2026-08-26 · **Outil** : Claude, recherche approfondie
**Prompt** : `docs/recherche/DS-08-videau-au-dela-de-janowski.md`, version du 2026-08-26

> **Ce que ce retour décide** : si le gain le moins cher est dans le videau.
> **Ce qu'il conclut** : oui — l'erreur moyenne de videau vaut plus du double d'une erreur de coup
> (Madsen, 4-ply, 39 690 positions), la barre gnubg est un x fixe que ses auteurs reconnaissent
> insuffisant, et le chemin est ordonné : benchmark PR-cube par classe, modèle raffiné (x1, x2),
> recalibrage x = f(pip) en course, surcouche volatilité (Higgins α → x local) ; MET maison à
> régénérer par nos rollouts.
> **Ce qu'il ne tranche pas** : la corrélation volatilité ↔ efficacité du videau, position par
> position, n'a jamais été publiée — c'est l'expérience que nous pouvons mener. Noter la
> correction : le +78,8 mEq/partie cité dans le plan est périmé, le README amont courant dit
> **+57,8** [+56,1 ; +59,6].

---
# État de l'art de la décision de videau au backgammon — rapport pour gammonNet

## TL;DR
- La théorie money publiée reste **Janowski (1993)** : interpolation par un coefficient d'efficacité x entre videau mort et videau vivant. Aucun modèle publié n'est prouvé strictement meilleur ; le **modèle à sauts de Higgins (2012)** est la seule alternative fermée sérieuse, et il *retrouve* un indice de vie du videau dans la fourchette 0,65–0,75 — il valide Janowski plutôt qu'il ne le détrône.
- La faiblesse documentée de GNU Backgammon en videau est **structurelle et admise par ses propres auteurs** : coefficients d'efficacité x fixes par classe (0,6–0,7), sans terme de volatilité, avec faiblesses reconnues sur backgames, holding games et positions de contact fin.
- Sur la priorisation : les mesures disponibles (Lasse Hjorth Madsen, GNU BG 4-ply) indiquent que **l'erreur de videau moyenne est plus du double de l'erreur de coup moyenne**, même si la somme des erreurs de coup domine par le volume. Pour un moteur déjà fort, le videau est le levier à plus haut rendement marginal.

## Key Findings

1. **[MESURE]** Le texte original de Janowski est intégralement disponible en source primaire (bkgm.com/articles/Janowski/cubeformulae.pdf, consulté le 26 août 2026), avec toutes les formules, les tables, et la correspondance avec Danny Kleinman en annexe.
2. **[MESURE]** GNU Backgammon documente explicitement son mécanisme : E(cubeful) = E(dead)·(1−x) + E(live)·x, avec x fixé par classe (one-sided bearoff 0,6 ; crashed 0,68 ; contact 0,68 ; race interpolé 0,6–0,7). Ces coefficients sont sous GPL-3 et hors périmètre de reprise.
3. **[MESURE]** Le dépôt alexstrehl/backgammon-ai-engine, sous licence **MIT**, revendique désormais **+57,8 mEq/partie** vs gnubg 0-ply (et non +78,8 comme dans la version antérieure), IC 95 % [+56,1 ; +59,6], sur 10 M parties, cube appris par RL sans aucune formule de point de prise. Le match n'est PAS fait (annoncé « future work »).
4. **[DÉCLARÉ]** Andrew Lin (TAAI 2020) est la première description de l'apprentissage du videau par RL, mais uniquement pour le match, sur de très petits réseaux, sans résultats chiffrés accessibles (péage IEEE).
5. **[HYPOTHÈSE]** L'intuition « les cinq probabilités sont une moyenne, le videau dépend de la dispersion » est confirmée par la littérature (Janowski lui-même lie x inversement à la volatilité, Higgins la quantifie) mais n'a jamais reçu de définition opérationnelle mesurée reliant écart-type d'équité et efficacité de videau empirique position par position.

## Details

### A. LA THÉORIE PUBLIÉE (MONEY)

#### A.1 Janowski (1993) — les formules exactes

Source primaire : Rick Janowski, *Take-Points in Money Games*, publié dans *Das Backgammon Magazin* et le *Hoosier BG Club magazine* en 1993 ; texte complet en PDF sur bkgm.com/articles/Janowski/cubeformulae.pdf (consulté le 26 août 2026). Le même texte a longtemps circulé sur msoworld.com/mindzine.

**Convention de symboles** (identique dans tout le papier) :
- p = probabilité de gain *cubeless*, non imbriquée (probabilité de gagner la partie, tous types de gains confondus).
- W = valeur cubeless moyenne des parties **finalement gagnées** (≥1 ; inclut gammons/backgammons). L = valeur cubeless moyenne des parties **finalement perdues**.
- x = « cube life index » (indice de vie du videau), ∈ [0 ; 1]. x=0 = videau mort (volatilité maximale) ; x=1 = videau vivant (volatilité nulle).
- CV = valeur du videau (niveau d'enjeu).

**Relation W/L avec les cinq sorties (imbriqué → disjoint)** : si le réseau sort P(win), P(win gammon), P(win bg), P(lose gammon), P(lose bg) en probabilités **imbriquées** (comme XG/gnubg), alors W = [P(win single) + 2·P(win gammon disjoint) + 3·P(win bg)] / P(win total). C'est exactement le calcul du manuel gnubg : W=(0,454+0,103+0,001)/0,454=1,229 pour l'exemple documenté, L=(0,556+0,106+0,003)/0,556=1,196. **Attention convention** : gnubg/XG donnent P(g) et P(bg) *imbriquées* dans P(win) ; il faut soustraire pour obtenir les tranches disjointes avant de sommer. Pour une course sans gammon, W=L=1.

**Point de prise à videau mort (dead cube)** — équation (1) :
> TP_dead = (L − 0,5) / (W + L)

Interprétation : le take risque 2L−1 pour gagner 2W+1. Cas sans gammon (W=L=1) : TP=0,25.

**Point de prise à videau vivant (live cube)** — équation (2) :
> TP_live = (L − 0,5) / (W + L + 0,5)

Cas sans gammon : TP=0,20. Dérivation complète en Appendice 5 du papier (modèle infini de redoubles optimaux). Le « bonus » de 1,0 ppg au moment du redouble ajoute le +0,5 au dénominateur.

**Point de prise général** — équation (3) :
> TP_general = (L − 0,5) / (W + L + 0,5·x)

**Équité de prise** (équation 4) : E_take = TP·(W+L) − L.

**Équités selon la position du videau** (équations 5–7), CV = valeur du videau, p = proba cubeless :
> E_owned (videau possédé) : E_O = CV·[ p·(W + L + 0,5·x) − L ]
> E_unavailable (videau indisponible) : E_U = CV·[ p·(W + L + 0,5·x) − L − 0,5·x ]
> E_centred (videau centré) : E_C = (4/(4−x))·CV·[ p·(W+L+0,5·x) − L − 0,25·x ] (non applicable si règle de Jacoby active)

**Table complète des points d'action** (money, colonne « cas général », toutes en fonction de p cubeless) :
- Take-point : TP = (L−0,5)/(W+L+0,5x)
- Beaver-point : BP = L/(W+L+0,5x)
- Racoon-point : RP = (L+0,5x)/(W+L+0,5x)
- Redouble-point : RD = (L+x)/(W+L+0,5x)
- Cash-point : CP = (L+0,5+0,5x)/(W+L+0,5x)
- Too-good point : TG = (L+1)/(W+L+0,5x)
- Initial double-point (sans Jacoby), et versions Jacoby via facteurs k1/k2 (équations 15–19), avec traitement des paradoxes de Kauder (RP≥p≥ID2) et de Latto (ID1≥p≥RD).

**Valeur du recube** : le videau possédé vaut, à l'équité, x·CV au redouble-point (E_owned=+x·CV) et 0,5x·CV côté indisponible. Janowski note qu'à x=2/3, redouble à 0,667 ppg, double initial à ~0,5 ppg — cohérent avec les rollouts main de l'époque.

**Modèle général affiné (refined general model)** — Appendice 2 : deux indices x1 (joueur décideur) et x2 (adversaire). Le take-point ne dépend QUE de x1, le cash-point QUE de x2. Formules (8)–(11). C'est ce modèle qui, en pratique, capture le fait que les deux camps n'ont pas la même efficacité (blitzeur vs blitzé). Janowski estime typiquement x1≈0,75 et x2≈0,60 (lettre à Kleinman, janvier 1994).

**Hypothèses du modèle et où elles sont documentées fausses** :
- (H1) W et L constants sur la vie de la partie. **Nuancé par l'auteur** : Janowski montre (Appendice 5.3) que le résultat TP_live survit même si les taux de gammon varient, à condition d'utiliser des W,L *moyens* et non initiaux — nuance cruciale et souvent ignorée.
- (H2) x constant par position. **Reconnu insuffisant** : la doc gnubg dit verbatim « The cube efficiency is obviously an important parameter, unfortunately there haven't been much investigation carried out, so GNU Backgammon basically uses the values 0.6-0.7 originally suggested by Rick Janowski » et énumère holding games / backgames comme cas à x plus bas non modélisés.
- (H3) Interpolation linéaire dead↔live. Higgins (2012) montre qu'un modèle à sauts donne des points de décision différents et « plus nets » (crisper) ; l'écart est petit mais réel.
- (H4) Redoubles infiniment nombreux et parfaitement efficaces (live). Faux en pratique ; le seul cas réel du modèle à un seul redouble subséquent est « homme sur 6 contre homme sur 6 » (TP=18,75 %), noté explicitement par Janowski.

**Révisions ultérieures de Janowski** : *Match Equity Formula Reviewed and Revised* (bkgm.com/articles/Janowski/MatchEquityFormulaRevised/), où il ajuste ses formules de MET pour coller à Rockwell-Kazaross à ±0,9 % sur 15 points (et ±1,5 % sur 19 points). La « Janowski rule » de MET a été baptisée par les éditeurs d'*Inside Backgammon*.

#### A.2 Ce qui a été publié après / autour de Janowski

- **Keeler & Spencer (1975)**, *Optimal Doubling in Backgammon*, Operations Research 23(6):1063-1071 : modèle continu (mouvement brownien de p) dont le résultat, verbatim, est « the optimal betting strategy for a continuous model of backgammon is to double when you have an 80 percent chance of winning » (et accepter un double seulement si la proba de gain ≥ 20 %). Fondation du « live cube ». Réédité dans Levy (ed.), *Computer Games I*, Springer 1988. Source : bkgm.com/articles/KeelerSpencer/.
- **Zadeh & Kobliska (1977)**, *On Optimal Doubling in Backgammon*, Management Science 23(8):853-858, DOI 10.1287/mnsc.23.8.853 ; et **Zadeh (1977)**, *On Doubling in Tournament Backgammon*, Management Science 23(9):986-993, DOI 10.1287/mnsc.23.9.986 : premier traitement du match et du jeu contre adversaire sous-optimal, en tenant compte de la compétence, du score, de la valeur du videau et des gammons. Texte sur bkgm.com.
- **Higgins (2012)**, *Cube Handling in Backgammon Money Games Under a Jump Model*, arXiv:1203.5692 (5 versions, dernière 23 avril 2012). Remplace la diffusion continue par des sauts de « jump volatility » α. Résultats mesurés par self-play : la volatilité de saut optimale est **9,1 %** (approximation non linéaire), estimation cohérente avec une mesure statistique indépendante de **9,4 %** des sauts de proba de gain d'un tour à l'autre ; l'approximation linéaire donne une valeur de **11,3 %**. Higgins conclut verbatim que cela « is equivalent to a Janowski cube life index in the range 0.65-0.75, depending on W and L » — il **retrouve** donc l'optimum de Janowski. Connexion explicite au refined general model : x1 dépend de la volatilité côté take, x2 côté cash (avec les formules fermées x1, x2 = 1 − α(W+L+½)²/[2(L+1)(W−½)] et symétrique). C'est le résultat le plus proche d'un « modèle supérieur mesuré », mais il **confirme** Janowski plus qu'il ne le bat.
- **Blog Computational Backgammon (compgammon.blogspot.com, 30 mars 2012)** : mesure indépendante par self-play (1 M parties, checker play « Player 3.3 »). L'auteur écrit verbatim « I found the optimal cube life index is 0.7 », avec cette remarque fine : « the probability of win continues to increase to x=0.95 even though the average score decreases, due to the asymmetric market windows of the two players ». Autrement dit, l'optimum de x pour la proba de gain et celui pour l'équité moyenne diffèrent.
- **Volatilité et market losers** : Kit Woolsey, *Volatility* (GammOnLine, oct. 2003, bkgm.com/articles/GOL/Oct03/volat.htm) définit la fenêtre de double 50–75 % (money, sans gammon) et pose que la décision correcte est de sommer, sur les 1296 séquences (mon jet, son jet), le coût/gain du double vs no-double : « in fact, this is exactly what they do when making a 3-ply analysis ». **Règle de Woolsey** : en cas de doute sur take/pass adverse, doubler. **O'Hagan's law** : doubler si ≥ 1/4 (≈9/36) des séquences sont des market losers. Ce sont des règles heuristiques [FOLKLORE], non des modèles mesurés.
- **Y a-t-il un modèle publié strictement meilleur que Janowski ?** Non, pas de façon mesurée. Higgins est plus fondé théoriquement et donne des points « plus nets », mais l'auteur ne revendique qu'un gain marginal et retrouve x∈[0,65 ; 0,75]. Aucune publication ne démontre un gain de PR reproductible d'un modèle fermé sur Janowski.

#### A.3 La volatilité, définie précisément

- **[FOLKLORE/DÉCLARÉ]** Définition intuitive (Woolsey) : ampleur probable du changement d'équité sur le prochain échange ; opérationnellement, nombre/poids des market losers parmi les 1296 séquences.
- **[HYPOTHÈSE]** Définition opérationnelle proposable (et cohérente avec Woolsey) : écart-type de l'équité au prochain point de décision, obtenu en développant les 21 jets adverses (ou 1296 séquences). Janowski (lettre à Kleinman) anticipe explicitement que « les ordinateurs peuvent estimer la volatilité en regardant les swings d'équité sur les 1296 combinaisons ».
- **[MESURE — indirecte]** Higgins fait le lien quantitatif : sa « jump volatility » α *est* la mesure opérationnelle, et il donne la table de correspondance α↔x. À α=10 %, x≈0,69–0,78 selon W,L ; à α=20 %, x tombe à 0,38–0,55 ; à α=5 %, x≈0,84–0,89. C'est la relation quantitative volatilité↔efficacité de videau la mieux fondée dans la littérature, et son estimation empirique de α (9,1–9,4 %) tombe pile dans la zone x≈0,70.
- **Personne n'a publié** de corrélation mesurée entre l'écart-type d'équité calculé sur 21 jets et l'efficacité de videau empirique par rollout, position par position. C'est un trou dans la littérature — et exactement l'expérience que gammonNet peut mener, votre expectiminimax développant déjà les jets nécessaires.

### B. LE MATCH

#### B.1 Points de prise depuis une MET

Mécanisme (doc gnubg, consulté le 26 août 2026) : la MWC cubeless se calcule par
> MWC(cubeless) = P(w)·MWC(w) + P(l)·MWC(l) + P(wg)·MWC(wg) + P(lg)·MWC(lg) + P(wbg)·MWC(wbg) + P(lbg)·MWC(lbg)

où MWC(·) sont les équités de match aux scores résultants (lus dans la MET). Les points de prise en match découlent du risque/récompense en unités de MWC, pas de ppg. gnubg calcule les take-points live par récursion sur la valeur du videau :
> TP(live, cube n) = TP(dead, cube n) · (1 − TP(live, cube 2n))

**Prix du gammon (gammon price/value)** : rapport marginal entre gagner un gammon et gagner simple, exprimé en MWC. Formellement, gammon value = [MWC(win gammon) − MWC(win single)] / [MWC(win single) − MWC(loss single)] (normalisé). Il entre dans W et L : en match, W et L sont recalculés avec les MWC des scores résultants au lieu de 1/2/3. Le NEMG de gnubg linéarise : NEMG = 2·(MWC−MWC(l))/(MWC(w)−MWC(l)) − 1. Exemple documenté : une distribution 0 100 100 − 0 0 0 donne NEMG=+3 alors que l'équité money n'est que +2, car le prix du gammon est élevé à ce score.

**Particularités exactes** :
- **Crawford** : pas de videau dans la partie de Crawford ; le trailer ne peut pas doubler.
- **Post-Crawford / free drop** : à 1-away/2-away post-Crawford, le leader a un « free drop » valant +0,02 de MWC (Tom Keith). Le free drop n'existe que quand le trailer est à un nombre PAIR de points, et ne s'utilise qu'une fois — d'où sa contribution négligeable dès que le trailer est à ≥4.
- **Videau mort (dead cube)** : à certains scores, le videau est mort ; le double initial coïncide avec le cash-point.
- **2-away/2-away** : le prix du gammon est nul pour le leader mais le double reste automatique ; après acceptation on retombe sur du DMP.
- **DMP (double match point, 1-away/1-away)** : videau, gammons et backgammons non pertinents ; take-point = 50 %, seule la proba de gain simple compte. Blitz déconseillé, backgames valorisés.
- **Take-point de référence** : 25 % money (dead, sans gammon), 20 % live ; en match il s'ajuste par le recube vig et le prix du gammon.

#### B.2 Le tableau des tables d'équité de match

Méthode de génération de MET (Tom Keith, bkgm.com/articles/met.html) : calcul **à rebours** depuis la fin du match. Hypothèses classiques : taux de gammon 20 % constant, doubles parfaitement efficaces, free-drop vig +0,02. La propriété clé est que, à score et videau fixés, la MWC est linéaire en proba de gain de la partie. Une MET peut être **régénérée de zéro par rollouts** — c'est ce qu'ont fait Rockwell-Kazaross (chaque score d'un match en 15 points roulé 38 880 fois avec GNU 2-ply Supremo, soit 19 440 par camp sur roll, puis extrapolation calculée jusqu'à 25). Coût : plusieurs semaines-machine ; Kazaross parle d'un « projet de plusieurs mois » pour refaire mieux en XG 3-ply.

| Nom | Auteur(s) | Méthode | Portée | Lien | Licence / conditions |
|---|---|---|---|---|---|
| Woolsey (Woolsey-Heinrich) | Kit Woolsey (+ Hal Heinrich, base de matchs) | Analyse math + empirique sur base de matchs de tournoi | 15-away+ | Reproduite dans Turner, *Calculating and Using Match Equities* (bkgm.com) | Publiée en livre (*How to Play Tournament Backgammon*, 1993) ; largement rediffusée, statut copyright livre |
| Rockwell-Kazaross | David Rockwell & Neil Kazaross | Rollouts XG jusqu'à 9pts + GNU 2-ply Supremo jusqu'à 15pts, extrapolé à 25 | 25-away | bkgm.com/articles/Kazaross/RockwellKazarossMET/ | Publiée librement sur bkgm ; pas de licence explicite — demander l'auteur avant redistribution |
| Kazaross-XG2 | Neil Kazaross / X. Dufaure de Citres | Rollouts moteur XG2, quasi identique à Rockwell-Kazaross | 25-away | Intégrée à eXtreme Gammon | Propriété du logiciel XG — NE PAS redistribuer le .met |
| Zadeh (1977) | Norman Zadeh | Modèle analytique / calcul | ~15+ | bkgm.com/articles/Zadeh/ | Article académique (Management Science) |
| Zadeh-Kobliska | Zadeh & Kobliska | Modèle d'optimisation, gammon 20 % | — | DOI 10.1287/mnsc.23.8.853 | Académique, copyright INFORMS |
| Jacobs-Trice | Jake Jacobs & Walter Trice | Publiée dans *Can a Fish Taste Twice as Good?* | 15+ | .met livré avec XG/gnubg | Copyright livre ; .met livré avec les logiciels |
| Snowie | Oasya/Snowie | MET propriétaire du logiciel Snowie | 15+ | .met livré avec logiciels | Propriétaire |
| g11 / GnuBG-11-point | équipe gnubg | Calculée par le moteur gnubg | 11-away | Livrée avec gnubg (GPL-3) | GPL-3 — hors périmètre de reprise |
| Mec26 / Mec27 | Claude Landry (formule MEC) | Formule paramétrique (gammon rate ajustable) | quelconque | rec.games.backgammon / bgonline | Formule publiée ; ré-implémentable |
| Turner | Stephen Turner | Formule de calcul rapide | quelconque | bkgm.com/articles/Turner/ | Article publié |

**Précision relative mesurée** : le point pivot d'une MET est -2/-1 Crawford ; Rockwell-Kazaross y donne 32,31 % (trailer) vs 31,85 % pour g11, différence vérifiée par plusieurs rollouts indépendants (Kazaross, XG 3-ply → 32,32 %). Kazaross rapporte qu'un test massif g11 vs Woolsey donnait g11 gagnant ≈50,05 % des matchs — l'écart pratique entre METs modernes est minime. Rockwell-Kazaross et Kazaross-XG2 sont « le benchmark universel » aujourd'hui.

**Recommandation licence pour gammonNet** : régénérer votre propre MET par rollouts de votre moteur (reproductible, sans dette de licence), ou ré-implémenter une formule paramétrique publiée (Janowski revised, Turner, MEC) — jamais copier le .met de XG (Kazaross-XG2) ni g11 (GPL-3).

#### B.3 Un réseau peut-il apprendre la valeur du score de match ?

- **Andrew Lin (TAAI 2020, pp. 29–34, DOI 10.1109/TAAI51410.2020.00014)** : oui, c'est l'objet exact du papier. Le score de match et le videau sont intégrés en entrée du réseau, qui apprend comment les différences de score influencent à la fois les décisions de videau ET le jeu de pions. Abstract IEEE verbatim : « We integrate the doubling cube and match scoring into the network. In doing so, our network learns how differences in match scores and cube circumstances influence not just further cube decisions, but checker play as well. » Architecture (nombre d'entrées/couches/sorties), encodage précis du score, et résultats chiffrés (win rate, PR, comparaison baseline, nombre de parties) restent **inaccessibles** : péage IEEE, aucun préprint arXiv, aucune version ResearchGate, aucune page auteur trouvée (Lin est affilié « Washington Technology University » d'après le programme TAAI 2020 ; référencé sur DBLP). Décrit par Strehl comme « très petits réseaux », cube appris comme actions supplémentaires, sans traiter les décisions de videau comme transitions état-action propres et sans feature is_cube_action. Portée : **match seulement, pas money**.
- **alexstrehl (money)** : montre que le complément (money, pas match) marche aussi ; match annoncé comme « future work », pas encore fait. Chiffres du README (consulté le 26 août 2026) : meilleur modèle cubeful 562k paramètres, **+57,8 mEq/partie** vs gnubg 0-ply (IC [+56,1 ; +59,6], 10 M parties), PR XG++ 1,06 à 0-ply, tombant à 0,50 à 1-ply et 0,22 à 2-ply ; en H-H 1-ply vs 1-ply, +47,1 mEq/partie ; 2-ply vs 2-ply, +45,0 mEq/partie. Licence MIT. Réserve de méthode signalée dans le README : la baseline gnubg-nn n'implémente pas l'équité money pour les décisions de videau, approximée via un match 21 points simulé à 0-0 — donc le +57,8 est à lire avec cette précaution.
- **Constat général** : personne n'a publié de mesure propre (win rate, PR) d'un réseau qui *fait émerger* une MET au lieu de la lire. C'est faisable (Lin le fait) mais non benchmarké publiquement. Pour gammonNet, garder la MET en table lue (reproductible, auditable) est le choix conservateur ; l'apprentissage du score est une piste de recherche ouverte mais non validée.

### C. LA BARRE : GNUBG ET XG

#### C.1 Comment gnubg décide de doubler (documenté)

Source : doc gnubg (gnubg.org/documentation, appendix, et manuel V0.16), consultée le 26 août 2026. Mécanisme :
1. Sorties du réseau : 5 probabilités cubeless (comme gammonNet).
2. E(cubeful) = E(dead)·(1−x) + E(live)·x (Janowski, généralisé aussi à MWC en match : MWC(cubeful) = MWC(dead)·(1−x) + MWC(live)·x).
3. E(live) : interpolation linéaire par morceaux entre (0 %,−L), (TP,−1), (CP,+1), (100 %,+W).
4. Récursion n-ply : boucle sur 21 jets, meilleur coup, évalue n−1 ply ; à chaque nœud, compare no-double / double-take / double-pass. Le x n'est utilisé qu'au niveau 0-ply des feuilles ; un x effectif est reconstitué par x_eff = (E_2ply_cubeful − E_2ply_dead)/(E_2ply_live − E_2ply_dead). gnubg **ne calcule pas** le take-point/double-point explicitement : il compare les équités.
5. Coefficients x par classe : one-sided bearoff 0,6 ; crashed 0,68 ; contact 0,68 ; race interpolé linéairement — doc verbatim : « A pip count of 40 gives x=0.6 and 120 gives x=0.7. If the pip count is below 40 or above 120 values of x=0.6 and x=0.7 are used, respectively » ; two-sided bearoff = table exacte (pour le money, l'équité cubeful est lue directement dans la base).

Ces valeurs sont sous **GPL-3** ; la mesure maison de gammonNet (0,688 / 0,566 / 0,687) est légitime et à conserver telle quelle — vous re-mesurez, vous ne reprenez pas. Auteurs impliqués : Joseph Heled, Øystein Schønning-Johansen, Jørn Thyssen, Ian Shaw, Christian Anthon (archives bug-gnubg, lists.gnu.org).

#### C.2 Faiblesses documentées de gnubg en videau

- **Aveu des auteurs (doc officielle, verbatim)** : « There is obviously room for improvements. For example, holding games should intuitively have a lower cube efficiency… backgames will often have a low cube efficiency, whereas blitzes may have a higher cube efficiency. » Le modèle à x fixe par classe **ne capture ni la volatilité ni la structure fine**.
- **[DÉCLARÉ, experts]** Neil Kazaross et d'autres (rec.games.backgammon) : gnubg est « really screwed up in developing backgame situations » et exploitable en session money sur les décisions de videau dans backgames massifs et positions de snake ; gnubg tend à évaluer certains doubles comme « pas tout à fait assez bons ».
- **[MESURE, tiers]** Le dépôt bgsage (markbgsage/bgsage, XG_COMPARISON.md) a construit un benchmark de 17 535 décisions sur 16 889 positions (7 652 réglées à 3-ply, 5 977 par rollout), scorant PR checker et PR cube séparément vs XG et vs rollout (PR = erreur moyenne × 500). C'est la comparaison tierce la plus rigoureuse trouvée — mais bgsage est **AGPL-3, hors périmètre** comme source ou corpus.
- **Effet impair/pair et instabilité** : des fils bug-gnubg/rgb montrent gnubg changeant de décision de videau entre niveaux (Beginner ND/T, Expert D/T, World Class ND/T…) et qualifiant sa propre décision de « very bad » (>0,16) — signe d'un modèle de videau bruité près des seuils.
- **XG lui-même** : XG2 a des faiblesses reconnues en containment/backgame ; le développeur Xavier Dufaure de Citres l'admet et dit que le moteur v3 en développement fait mieux (bgonline).

#### C.3 Erreurs de videau vs erreurs de coup — la mesure décisive

- **Définitions** : gnubg et XG comptent l'erreur sur les décisions du seul joueur noté, hors coups forcés ; PR ≈ erreur moyenne ×500 (XG divise par ~2 vs gnubg, qui donne des chiffres > 2× Snowie). Snowie compte sur les deux joueurs (≈ moitié du chiffre gnubg). Une décision de videau est « close » chez gnubg si les équités sont à moins de 0,25 l'une de l'autre ou si la position est too-good.
- **[MESURE — la meilleure trouvée]** Lasse Hjorth Madsen, *Mistake, errors and statistics* (publié le 25 avril 2026, lassehjorthmadsen.github.io ; analyse GNU BG 4-ply de 39 690 positions, 892 parties, 343 matchs, 9 460 erreurs). Constat verbatim : « The average cube error is more than double of the average checker play error » — la somme des erreurs de coup dépasse néanmoins largement la somme des erreurs de videau, à cause du volume de petites erreurs de coup. Le plus gros contributeur aux erreurs de videau, verbatim : « the single biggest contributor to my cube mistakes, is me doubling or re-doubling when the position isn't strong enough… I lose more by incorrectly taking, than by incorrectly passing ». Conclusion opérationnelle de l'auteur : cibler d'abord les blunders de coup fréquents, puis établir des benchmarks de videau (double minimal, take minimal, too-good).
- **[DÉCLARÉ]** Douglas Zare (GammonVillage, *Normalizing Errors*) : la métrique Snowie (qui minimise l'erreur *totale*) est théoriquement supérieure pour prioriser, car minimiser l'erreur par-décision gnubg peut être trompeur (ex. doubler tôt pour simplifier ses futures décisions augmente le nombre de décisions et peut dégrader le taux gnubg tout en réduisant l'erreur totale).
- **Implication pour gammonNet** : votre avantage cubeless de +0,0400 ppg qui « s'évapore » une fois le videau branché est cohérent avec cette structure — l'erreur de videau, rare mais lourde (moyenne > 2× celle d'un coup), mange le gain de coup. C'est le point de plus haut rendement à travailler, et vos deux symptômes (sous-double en course, sur-double en contact fin) sont les deux faces exactes du problème identifié par Madsen (doubler quand ce n'est pas assez fort / manquer un bon double).

## Recommendations

**Étape 1 — Diagnostiquer où le videau perd (avant de changer le modèle).**
Construire un benchmark maison façon bgsage : quelques milliers de positions de décision de videau, vérité = vos rollouts profonds, et scorer votre PR cube par classe (course / contact / backgame / holding / prime-vs-prime / ace-point). Seuil qui tranche : si votre PR cube en course est significativement pire que votre PR cube en contact, votre sous-double en course est un problème d'x (étape 3) ; si c'est le contact fin qui domine, c'est un problème de volatilité (étape 4).

**Étape 2 — Adopter le refined general model (x1, x2) plutôt qu'un x unique.**
Janowski Appendice 2 : take-point dépend de x1, cash-point de x2. Coût faible (formules fermées, déjà dérivées ci-dessus), gain attendu réel sur les positions asymétriques (blitz, backgame) exactement là où gnubg est faible. Benchmark qui tranche : PR cube sur positions asymétriques avant/après.

**Étape 3 — Recalibrer x par classe sur VOS rollouts, avec dépendance au pip en course.**
Votre sous-double en course suggère un x trop bas en course (vous croyez le videau moins vivant qu'il ne l'est ; votre 0,687 en course pourrait être sous-estimé pour les courses longues). Refaire la mesure de x en course comme fonction du pip et de la régularité (wastage/EPC), pas une constante. Reproductible, sans dette de licence.

**Étape 4 — Tester le modèle à sauts de Higgins comme surcouche de volatilité.**
Pour la « fenêtre fine de contact » où vous sur-doublez : calculer une volatilité locale α (écart-type d'équité sur les 21 jets, développement déjà fait par votre expectiminimax) et convertir en x local via les formules fermées de Higgins (x1, x2 = 1 − α(W+L+½)²/…). C'est la seule voie publiée reliant quantitativement volatilité et efficacité, et l'estimation empirique de α (9,1–9,4 %) est un point de départ crédible. Gain attendu : correction du sur-double en contact volatile. Coût : modéré (un calcul de plus par nœud de décision de videau). Benchmark qui tranche : corrélation mesurée entre α calculé et efficacité de videau empirique par rollout — si elle est forte (>0,5), brancher α ; sinon, s'en tenir à x par classe.

**Étape 5 — Match : garder la MET en table lue, régénérée maison.**
Régénérer votre MET par rollouts de votre moteur (méthode Keith à rebours + rollouts, façon Rockwell-Kazaross) : reproductible, auditable, zéro dette de licence. Ne pas copier Kazaross-XG2 (propriétaire XG) ni g11 (GPL-3). L'apprentissage du score façon Lin est une piste R&D, pas un choix de production tant que non benchmarké.

**Ce qui ferait changer ces recommandations** : si l'étape 1 montre que votre PR cube est déjà proche du plancher (≈0,3–0,5 comme alexstrehl à 1-ply), le rendement marginal du videau chute et il faut revenir au checker play / à la profondeur de recherche.

## Tableau final de décision

| Piste d'amélioration du videau | Gain attendu | Coût | Risque | Licence | La mesure qui trancherait |
|---|---|---|---|---|---|
| Refined general model (x1,x2) au lieu de x unique | Moyen-élevé sur positions asymétriques | Faible (formules fermées) | Faible | Idée Janowski, libre de ré-implémenter | PR cube avant/après sur blitz/backgame |
| Recalibrer x par classe sur vos rollouts (course = f(pip)) | Moyen (corrige le sous-double en course) | Faible-moyen | Faible | Vos mesures, libres | PR cube en course vs pip |
| Surcouche volatilité (Higgins, α→x local) | Élevé sur contact volatil (corrige sur-double) | Moyen | Moyen (α mal estimé) | arXiv, libre de ré-implémenter | corrélation α↔efficacité empirique par rollout |
| Réseau cubeful direct (à la alexstrehl) | Incertain ; supprime le besoin de x | Élevé (ré-entraînement) | Élevé (perte d'auditabilité) | MIT (méthode réutilisable) | H-H mEq/partie vs baseline Janowski |
| Apprendre la MET (à la Lin) | Incertain, non benchmarké | Élevé | Élevé | méthode publiée, libre | PR match réseau vs MET lue |
| Régénérer MET maison par rollouts | Neutre (parité benchmark) + zéro dette | Élevé (semaines-machine) | Faible | 100 % maison | écart vs Rockwell-Kazaross au pivot -2/-1C (cible ≈32,3 %) |

## Caveats
- **Distinction money/match maintenue** : les formules A.1 sont money ; en match, W et L sont recalculés en MWC et il n'existe pas de formule fermée simple (redoubles limités) — gnubg le dit explicitement (« For match play there is no simple formula »).
- **Étiquettes** : beaucoup de « règles » de videau (Woolsey, O'Hagan, 8-9-12 de Trice) sont [FOLKLORE] utile mais non des modèles mesurés ; les seuls résultats [MESURE] sur l'efficacité sont Higgins (α≈9,1–11,3 %, x∈[0,65 ; 0,75]) et les benchmarks d'erreur (Madsen, bgsage). Le blog compgammon (x≈0,7) est [MESURE] mais auto-publié.
- **Convention probabiliste** : toujours vérifier imbriqué vs disjoint avant de calculer W/L — gnubg/XG sortent P(g),P(bg) imbriquées dans P(win). Source d'erreur classique, à documenter explicitement dans votre code.
- **Chiffre alexstrehl** : le +57,8 mEq/partie repose sur une baseline gnubg-nn approximée en money (via match 21 points simulé) — la revendication du prompt (+78,8) correspond à une version antérieure et périmée du README ; le chiffre courant est +57,8.
- **Licences** : gnubg (GPL-3), HedgeHog (clause non commerciale), bgsage (AGPL-3), Kazaross-XG2 (propriétaire XG) sont **hors périmètre** comme source, poids ou corpus. alexstrehl est MIT (réutilisable). Janowski, Higgins, Keeler-Spencer, Zadeh, Tom Keith sont de la littérature librement ré-implémentable (les articles académiques restent sous copyright éditeur ; ce sont les *idées et formules* qui sont libres, pas le texte).

## Ce que je n'ai pas trouvé
- Les chiffres exacts du papier Andrew Lin (architecture, encodage du score, win rate/PR, nombre de parties) — péage IEEE, aucun préprint accessible ; seul l'abstract est public.
- Une corrélation *publiée et mesurée* entre écart-type d'équité sur 21 jets et efficacité de videau empirique par rollout — ce trou est précisément l'expérience que gammonNet peut mener.
- Un modèle de videau publié *prouvé strictement meilleur* que Janowski par gain de PR reproductible.
- Le taux d'erreur de videau chiffré de gnubg vs XG vs rollout dans une publication formelle (seules des mesures de blog/dépôt existent : Madsen, bgsage).
- Le second modèle « non publié » de Janowski (redéfinition intuitive de l'efficacité calculable par rollout), mentionné par la doc gnubg mais jamais diffusé.