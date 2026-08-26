# DS-14 — Le budget de calcul — retour

**Date de la recherche** : 2026-08-26 · **Outil** : Claude, recherche approfondie
**Prompt** : `docs/recherche/DS-14-budget-de-calcul.md`, version injectée du 2026-08-27

> **Ce que ce retour décide** : ce que le programme retenu (§14 du plan) coûtera vraiment — et il
> alimente la décision d'engager ou non les fiches T7x.
> **Ce qu'il conclut** : le programme **tient sur notre machine** — produire un candidat coûte
> des heures (~1 h de self-play 0-ply, ~3–8 h de mur d'étiquetage 2-ply pour 1,0–1,5 M labels,
> ~1 h de QAT, seul usage utile du GPU), et le poste dominant est la **mesure** : des heures par
> point d'arbitre escaladé, 4,9 jours le match dupliqué. Trois scénarios : minimal **~1–3 h**
> (le signal qui dit si l'idée marche), nominal **~6–8 jours** dont 4,9 de match, « ça a mal
> tourné » **~3–5 semaines** — dominées par la mesure répétée, pas par l'entraînement. La règle
> d'or, tirée du piège n°1 documenté (le plafond du professeur) : **mesurer le professeur avant
> d'étiqueter en volume** — le 2-ply doit battre le réseau actuel avec z > 3 sur ≥ 10 000
> décisions appariées, un contrôle qui coûte des minutes. Six paliers de repli P0–P5 avec
> critères d'arrêt chiffrés (prototype à 400–500 k labels ; jamais de rollout pour départager du
> bruit ; le match dupliqué est un événement rare, pas une routine). Les recettes à parc
> (fishtest, ELF, KataGo) sont écartées franchement.
> **Ce qu'il ne tranche pas — et une réserve de conformité** : sa recommandation d'accélération
> centrale — étiqueter par **gnubg 2-ply** (~2 600 positions/s, ~100 000× moins cher qu'un
> rollout) — est **inutilisable ici** : la règle du dépôt fait de gnubg un instrument de mesure,
> jamais une source d'apprentissage (§10 du plan) ; on paie donc nos propres coûts d'étiquetage,
> qui restent de l'ordre d'heures. Introuvables par ailleurs : tout coût d'entraînement publié
> de Jellyfish/Snowie/XG/BGBlitz, le facteur exact de réduction de variance du match dupliqué,
> un débit officiel de gnubg par cœur (mesure tierce seulement, à confirmer chez nous).

---
# Budget de calcul pour entraîner puis qualifier un évaluateur de backgammon par réseau de neurones (gammonNet)

## TL;DR
- **Le poste dominant n'est ni la génération de parties ni la rétropropagation — c'est l'étiquetage par recherche profonde et surtout la MESURE.** Sur votre machine (16 c / 32 fils), produire un réseau distillé de 60–100 k MACs coûte de l'ordre de **quelques heures à ~1 jour** (étiquetage 2-ply + QAT), tandis que la **qualification** (arbitre escaladé + match dupliqué) coûte de l'ordre de **1 à 5 jours par candidat sérieux** — c'est votre 4,9 jours mesurés.
- **La leçon historique la plus coûteuse n'est pas le matériel, c'est le plafond du professeur et la mesure sous-dimensionnée.** Un réseau distillé ne peut pas dépasser le maître qui l'étiquette (démontré empiriquement par le projet Backgammon-NN), et distinguer deux bots proches demande des centaines de matchs — refaire une campagne trop peu sensible est ce qui fait exploser le budget.
- **Restez mono-machine.** Le self-play 0-ply est aujourd'hui quasi gratuit ; le GPU par lots n'aide pas votre goulot (l'étiquetage 2-ply est lié au CPU) ; les recettes type parc/cloud (fishtest, ELF OpenGo, KataGo) sont hors sujet pour une personne seule et doivent être écartées franchement.

## Key Findings

1. **Génération de parties (self-play 0-ply) : négligeable en 2026.** L'ancre historique — TD-Gammon 0.0, 200 000 parties en **deux semaines de CPU sur un RS/6000 de 1991** [MESURE] — se réduit, après conversion, à ~7–20 minutes sur un cœur x86 moderne [EXTRAPOLÉ]. Vos 60–90 µs/évaluation confirment que générer 1,5 M de positions 0-ply est une affaire de minutes à quelques heures mono-fil.

2. **Étiquetage 2-ply : c'est là que passe le temps « de production ».** Avec vos ancres (0,24–0,56 s/décision 2-ply élaguée), 1,0–1,5 M de labels coûtent **~67–233 heures-cœur**, soit **~2–8 h de mur** sur vos 30 processus. 2,5 M de labels : **~167–389 heures-cœur** (~6–13 h de mur).

3. **Un raccourci décisif existe : distiller gnubg 2-ply plutôt que vos propres rollouts.** Une mesure indépendante (projet Backgammon-NN de Chris Whittington) donne **~2 600 positions/s sur 60 processus gnubg** pour l'étiquetage 2-ply, contre **~0,3 s par essai par position** pour un rollout gnubg — un facteur ~100 000. Conséquence : « 2,5 M labels coûtent un quart d'heure » contre « six heures » pour 30 k labels de rollout.

4. **La qualification est le poste historiquement sous-estimé — le vôtre aussi.** Distinguer deux bots séparés de quelques millipoints demande beaucoup de parties : écart-type d'une session d'argent ≈ **3·√N** [MESURE, Chuck Bower]. Établir qu'un joueur A a une espérance de victoire de 55 % contre B au niveau de confiance de 95 % demande **de l'ordre de 400 matchs** [MESURE, Bower : « if player A has a match win expectation of 55% against player B, it would take on the order of 400 matches to establish this at the 95% confidence level »]. Le match dupliqué / dés communs et la réduction de variance rachètent un facteur important (gnubg/Gammonline : « 100 parties avec réduction de variance peuvent équivaloir à 5 000 – 10 000 parties sans »), mais un point de comparaison rollout reste « des heures », et une campagne complète = vos **4,9 jours**.

5. **Le GPU par lots n'attaque pas votre goulot.** Les architectures batched/vectorisées (EnvPool, Brax/Isaac Gym, serveurs d'inférence AlphaZero, SEED RL/Ape-X) accélèrent l'inférence réseau vectorisée, mais votre coût est la recherche 2-ply/rollout côté CPU. La rétropropagation d'un réseau de ~528 k paramètres est déjà « quelques minutes » (Whittington : 400 k labels = « minutes » ; 22,5 M = « moins d'une heure » GPU). Mettre un GPU dans la boucle de self-play a un rapport bénéfice/complexité mauvais pour une personne seule.

6. **Ce qui fait exploser le budget, documenté :** (a) le plafond du professeur — un réseau distillé de ses propres labels converge à la force du professeur quelle que soit la quantité de données ; (b) le réentraînement complet après chaque changement d'encodage ; (c) les gains 0-ply qui s'évaporent sous recherche (non-transitivité) ; (d) la perte de validation qui continue de baisser sans se traduire en force de jeu ; (e) les campagnes de mesure sous-dimensionnées qu'il faut refaire.

## Details

### Sous-question 1 — Ce que les autres ont dépensé (ancres réelles + conversions)

**Facteur de conversion matériel utilisé.** Base : horloge (~25–62 MHz en 1991 → ~4 GHz aujourd'hui ≈ ×100) × largeur/IPC/SIMD (≈ ×10–30) ⇒ **×1 000 à ×3 000 en débit mono-fil** entre un RS/6000 de 1991 et un cœur x86 de 2026 [EXTRAPOLÉ]. C'est délibérément conservateur ; une extrapolation « loi de Moore naïve » sur 34 ans (≈17 doublements) donnerait ~10^5, ce qui surestime les gains mono-fil réels. Les convertis ci-dessous utilisent ×1 000–3 000.

| Moteur / version | Année | Réseau | Parties self-play | Coût machine publié | Converti (1 cœur 2026) |
|---|---|---|---|---|---|
| TD-Gammon 0.0 | 1991 | 40 cachés, 1-ply | 200 000 | 2 semaines CPU sur RS/6000 haut de gamme [MESURE, Tesauro/Scholarpedia] | ~7–20 min [EXTRAPOLÉ] |
| TD-Gammon 1.0 | fin 1991 | 80 cachés, 1-ply | 300 000 | **un mois de CPU sur RS/6000** [MESURE, Tesauro/Scholarpedia] | ~20–60 min [EXTRAPOLÉ] |
| TD-Gammon 2.1 | 1993 | 80 cachés, 2-ply | 1,5 M | non chiffré | — |
| TD-Gammon 3.0 | 1995 | 80 ou 160 cachés (conflit), 3-ply | 1,5 M | non chiffré | — |
| TD-Gammon 3.1 | 1998 | 160 cachés, 3-ply | > 6 M | non chiffré | — |
| gnubg (contact/crashed/race) | ~2000+ | 3 réseaux, 250 entrées | bases de bench ~1,2 M contact / 0,6 M crashed / 0,5 M race | non chiffré | — |
| wildbg | 2023–2024 | contact+race, ~202 entrées | rollouts par lots de 100 000 positions/itération, ~22 itérations | pas de wall-clock publié | — |
| Backgammon-NN (Whittington) | 2026 | 198→256→128→5 puis 22,5 M labels gnubg | ~150 k parties self-play (~16 h) puis distillation | 22,5 M labels gnubg « en moins d'une heure » | mesuré 2026 |
| alexstrehl/backgammon-ai-engine | 2024+ | 561–562 k paramètres | 10 M parties d'évaluation | non chiffré | — |

Remarques : conflit de sources sur TD-Gammon 3.0 (Sutton dit 160 unités cachées ; le tableau Wikipédia dit 80 pour 3.0 et 160 pour 3.1) — à signaler, ne pas trancher. Jellyfish (Fredrik Dahl, ~1994, premier à introduire la réduction de variance), Snowie (Olivier Egger, 1998), eXtreme Gammon/XG (Xavier Dufaure de Citres, 2009, référence mondiale actuelle, multi-cœurs), BGBlitz (Frank Berger, NN, plusieurs titres d'Olympiade) : **aucun coût d'entraînement chiffré publié n'a été trouvé** (voir « Ce que je n'ai pas trouvé »).

### Sous-question 2 — Débit de génération de parties

- **Coûts unitaires (vos ancres).** Évaluation réseau ~527 k MACs : 60–90 µs mono-fil [MESURE, vous]. Décision 2-ply : 2,0 s sans élagage, 0,24–0,56 s avec élagage [MESURE, vous].
- **Coups légaux backgammon.** ~20 coups légaux en moyenne par décision [MESURE, Tesauro « On-line Policy Improvement »], jusqu'à plusieurs centaines pour certains doubles. Une partie dure ~20 décisions par joueur en jeu moderne (~40 total) [MESURE, forum Robertie], parfois > 90.
- **Débit 0-ply.** Une décision 0-ply = générer ~20 coups + ~20 évaluations réseau ≈ 20 × 75 µs ≈ 1,5 ms + surcoût de génération de coups. Soit ~600–700 décisions/s/cœur hors surcoût, réalistement quelques centaines/s/cœur. Une partie complète 0-ply ≈ 0,05–0,1 s ; 1,5 M positions ≈ minutes à ~1 h mono-fil.
- **Débit 1-ply.** ~×21 (moyenne sur les 21 jets) → ~30 ms/décision, quelques dizaines de décisions/s/cœur.
- **Postes de coût.** L'évaluation réseau domine à 0-ply ; à 2-ply c'est l'explosion combinatoire (21 jets × ~20 réponses × réévaluation). La génération de coups légaux est non triviale mais reste minoritaire devant l'évaluation. Référence indépendante : un moteur similaire (Backgammon-NN) atteint **~57 positions/s** en étiquetage rollout tronqué mono-fil, et son inférence par lots a divisé le temps par ~2,5 (4 282 → 1 694 ms pour 400 essais × 9-ply tronqué) [MESURE, Whittington]. wildbg génère ses jeux de rollout par tranches de 100 000 positions [MESURE, dépôt wildbg-training], sans wall-clock publié.

### Sous-question 3 — Le GPU : ce qu'il change / ne change pas

- **Ce qu'il ne change pas.** Votre goulot est la recherche 2-ply/rollout (CPU) et la mesure. La rétropropagation d'un réseau de 60–100 k MACs est déjà négligeable (minutes CPU, « moins d'une heure » pour 22,5 M labels sur GPU) [MESURE, Whittington]. Un GPU n'accélère pas magiquement une recherche expectiminimax séquentielle avec chance-nodes.
- **Ce qu'il pourrait changer, en théorie.** Le self-play **par lots** vectorise l'évaluation réseau sur des milliers de parties en parallèle. Chiffres publiés : EnvPool atteint **1 million d'images/s avec Atari et 3 millions de pas/s avec MuJoCo sur 256 cœurs CPU, soit ×14,9 / ×19,6 la référence gym.vector_env** ; sur 12 cœurs, ×3,1 / ×2,9 (matériel DGX-A100, AMD EPYC 7742) [MESURE, doc EnvPool]. Serveurs d'inférence type ELF OpenGo/AlphaZero (workers CPU + serveur GPU batché), acteurs-apprenants séparés (SEED RL, Ape-X). Gains de parallélisation « maison » : ×3,2 (AlphaZero-Edu, 8 processus) [MESURE], ×15–20 wallclock (3090 + 10 cœurs, après un mois de travail) [MESURE, blog Snowdrop].
- **Verdict pour une personne seule.** La complexité (double niveau de batching, virtual loss, buffers de replay, serveur TCP) est disproportionnée. Le gain réel sur VOTRE goulot (étiquetage 2-ply CPU) est faible. **Recommandation : ne pas remettre le GPU dans la boucle de génération ; l'utiliser uniquement pour la QAT.**

### Sous-question 4 — Le coût de l'étiquetage (arithmétique explicite)

Hypothèse de parallélisation : vous avez tourné 30 processus. L'hyperthreading donne un rendement sous-linéaire (~16–24 cœurs effectifs sur 32 fils) ; je donne les heures-cœur (invariantes) puis le mur sur 30 processus.

| Volume | Coût unitaire 2-ply élagué | Heures-cœur | Mur sur 30 proc. |
|---|---|---|---|
| 1,0 M labels | 0,24 s | 66,7 | ~2,2 h |
| 1,0 M labels | 0,56 s | 155,6 | ~5,2 h |
| 1,5 M labels | 0,24–0,56 s | 100–233 | ~3,3–7,8 h |
| 2,5 M (plafond) | 0,24–0,56 s | 167–389 | ~5,6–13 h |

**Ce que la réduction de variance change au compte.** Pour l'ÉTIQUETAGE par recherche (2-ply distributionnel), la réduction de variance est « gratuite » : le vecteur des 5 probabilités et la volatilité sur les 21 jets sont des sous-produits du backup — pas de trials Monte-Carlo. La variance n'entre en jeu que si vous étiquetez par ROLLOUT : là, réduction de variance (Dahl/Jellyfish), dés quasi-aléatoires stratifiés (gnubg stratifie les 2 premiers jets), rollouts tronqués + troncature sur base exacte, et dés communs (common random numbers) réduisent le nombre d'essais requis. gnubg/Gammonline affiche « 100 parties avec réduction de variance peuvent équivaloir à 5 000 – 10 000 parties sans » [MESURE, doc gnubg ; technique introduite par Fredrik Dahl, auteur de Jellyfish] — mais un essai de rollout gnubg coûte ~0,3 s/position, soit ~100 000× un label 2-ply. **Conclusion chiffrée : étiqueter par 2-ply (ou par distillation gnubg 2-ply) est la seule option raisonnable sur une machine ; le rollout comme source de labels est hors budget mono-machine.**

### Sous-question 5 — Le coût de la qualification

- **Un point de comparaison = des heures** (votre mesure). Décomposition de l'arbitre escaladé :
  - *Passe 1, gnubg 3-ply sur corpus figé (10^4–10^5 décisions)* : gnubg est mono-cœur par évaluation (Berger), le 3-ply est nettement plus lent que le 2-ply (~43 éval 2-ply/s/proc mesuré). Compter des dizaines de minutes à ~1–2 h sur 30 processus pour 10^4 décisions × quelques candidats.
  - *Passe 2, rollout tronqué à variance réduite (IC < 0,005)* : plusieurs centaines d'essais/position ; c'est ici que « un point coûte des heures ».
  - *Passe 3, rollout complet* : réservé aux décisions encore disputées ; ancré sur bases exactes partout où c'est résoluble.
  - *Confirmation finale, match dupliqué ≥ 100 matchs, test apparié* : votre **4,9 jours** mesurés.
- **Combien de points de comparaison par programme d'itérations ?** Par analogie fishtest (Stockfish) : chaque patch = SPRT jusqu'à conclusion (souvent des dizaines de milliers de parties), seuils typiques « +25 Elo : merge / −25 : discard » ; un speed-up doit valoir **~0,25 % en STC et ~0,7 % en LTC pour 50 % de chance de passer, et ~1 % pour 85 %** [MESURE, wiki fishtest]. Transposé à une machine seule, vous ne pouvez pas vous offrir un tel volume : d'où la nécessité d'un corpus figé et de la mesure par décision (voir Paliers).
- **Statistiques de variance backgammon (chiffres publiés) :**
  - Écart-type session d'argent ≈ **3·√N** [MESURE, Bower].
  - Écart-type de la différence entre deux coups ≈ **1,4 × la moyenne** des deux écarts-types [MESURE, Montgomery].
  - Établir une espérance de match de 55 % à 95 % ≈ **400 matchs** [MESURE, Bower].
  - 2-ply vs 1-ply vaut **0,25 ppg**, coups différents dans **24 %** des positions [MESURE, LGammon/TDLeaf].
  - PR d'un match : écart-type ≈ 2,0 mEMG ; comparaison PR fiable ≈ 100+ matchs [source commerciale GamesGrid, à traiter comme indicatif].
  - Le match dupliqué / dés communs réduit la variance car il annule la chance corrélée entre les deux camps ; facteur exact non uniformément publié (voir « Ce que je n'ai pas trouvé »).

### Sous-question 6 — Ce qui fait exploser les budgets (retours d'expérience)

- **Le plafond du professeur (LE plus coûteux).** Backgammon-NN documente qu'un réseau ajusté sur ses PROPRES labels (self-play, rollouts tronqués/non tronqués, distillation 1-ply, distillation 2-ply) **converge tous au même point ~parité avec le champion**, quelle que soit la quantité de données — « a student cannot exceed its teacher ». La sortie n'est venue que d'un professeur externe (gnubg 2-ply), après avoir vérifié que gnubg 0-ply était à parité (donc inutile comme professeur) et gnubg 2-ply nettement plus fort (43,9 %, z −3,86). **Coût évité en mesurant le professeur AVANT d'étiqueter des millions de positions.**
- **Données qui cessent de payer.** 500 k → 2,5 M labels = gain net ; 2,5 M → 17,5 M = z +1,91 non résolu ; 22,5 M → 37,5 M = z −1,44. « La perte de validation continuait de baisser tout du long — elle a simplement cessé de se traduire en parties. Seuls les affrontements directs trouvent ce genou. » [MESURE, Whittington].
- **Non-transitivité / gains qui s'évaporent sous recherche.** Des gains 0-ply (v1.7.0, v1.8.0) disparaissent à 1-ply ; le routage par classe s'est révélé neutre (le gain venait d'un tail de learning-rate decay). Leçon : « vérifier au ply où l'appli joue » et « changer une variable à la fois ».
- **Réentraînement complet après changement d'encodage.** Chaque changement d'entrées force un réentraînement from scratch (les labels 5-prob restent valides si le professeur ne change pas, mais l'accumulateur QAT et la topologie changent).
- **Instabilité RL.** TD-lambda peut diverger ; le fine-tuning supervisé d'un réseau TD convergé « a systématiquement dégradé » le classement appris (Backgammon-NN) ; nécessité d'opponent pool / échelle pour stabiliser (littérature self-play).
- **Mesure sous-dimensionnée.** Une porte de 40 000 parties lisait 54,8 % à 7 000 parties et finissait à 53,6 % — « les affrontements partiels errent plus que les effets mesurés ». C'est exactement le piège « campagne à refaire ».
- **Analogies chess/NNUE/Lc0.** fishtest = millions de parties par patch (parc distribué), « chaque 5 Elo est une épreuve » en RL NNUE, génération de données ~150 M positions à profondeur 8–12, 2–3 semaines de mur pour 2–3 rounds. Ces coûts supposent un parc — **inapplicables tels quels à une machine seule.**

### Sous-question 7 — Les paliers de repli (la partie la plus utile)

Objectif : tuer une mauvaise idée tôt, pour une fraction du coût.

| Palier | Ce qu'on fait | Coût relatif | Signal obtenu |
|---|---|---|---|
| P0 — banc de positions de référence | Comparer les choix de coup du candidat aux bases de bench gnubg (contact ~1,2 M / crashed / race, déjà étiquetées) et aux bases exactes | minutes (aucun rollout) | « L'idée est-elle catastrophique ? » — filtre grossier, gratuit |
| P1 — distillation gnubg 2-ply, corpus réduit | Étiqueter 400 k–500 k positions par gnubg 2-ply (~2,6 k/s sur 60 proc) puis QAT | ~minutes d'étiquetage + minutes de train | Parité approx. atteinte dès ~400 k labels (Whittington) ; dit si l'architecture apprend |
| P2 — tronc gelé, tête réentraînée | Freeze du corps, réentraîner la seule tête (5-prob + volatilité) | fraction d'un train complet | Isole si le gain vient de la tête/aiguillage ou du corps |
| P3 — mesure PAR DÉCISION | Taux d'erreur par décision (equity-loss) vs arbitre sur corpus figé, SANS rollout (gnubg 3-ply seul) | dizaines de minutes | Ordonne les candidats à faible coût ; réserve le rollout aux ex æquo |
| P4 — arbitre escaladé complet | 3-ply → rollout tronqué VR → rollout complet, IC < 0,005 | heures/point | Verdict quasi-final sur un candidat retenu |
| P5 — match dupliqué ≥ 100 | Dés miroirs, test apparié | ~4,9 jours | Confirmation finale, une seule fois |

**Critères d'arrêt chiffrés (STOP si) :**
- P0 : le candidat diffère de gnubg sur > X % des positions de bench avec equity-loss moyen nettement pire que l'incumbent → **arrêt immédiat**.
- P1 : à 400 k–500 k labels, le candidat ne bat pas l'incumbent en tête-à-tête par décision (z < ~1 sur ≥ 10 000 décisions appariées) → l'idée n'apporte rien, **arrêt** (la donnée supplémentaire ne sauvera pas une idée neutre — cf. 2,5 M→17,5 M).
- P3 : si le gain 0-ply/par-décision disparaît à 1-ply (non-transitivité), **arrêt** avant tout rollout.
- P4/P5 : n'engager les 4,9 jours QUE si P3 donne un gain apparié significatif au ply de jeu de l'application. Ne jamais lancer le match dupliqué pour départager du bruit.

## Recommendations

**Étape 1 — Toujours mesurer le professeur d'abord (coût : minutes).** Avant d'étiqueter quoi que ce soit en volume, vérifiez que votre 2-ply distributionnel est réellement plus fort que le réseau actuel au ply de jeu visé. Si votre professeur est à parité avec l'élève, aucun volume de labels ne fera progresser gammonNet — c'est le piège n°1 documenté. Seuil de bascule : gain apparié z > 3 du professeur sur l'élève sur ≥ 10 000 décisions.

**Étape 2 — Prototyper au palier P1 (distillation, 400–500 k labels, coût : ~heure).** Distillez d'abord sur un corpus réduit, QAT comprise, et mesurez PAR DÉCISION (P3) contre gnubg 3-ply sur votre corpus figé. C'est le « signal le moins cher qui dit si l'idée marche ». Décidez d'aller plus loin seulement si le candidat bat l'incumbent au ply de jeu.

**Étape 3 — Étiquetage nominal 1,0–1,5 M (coût : ~2–8 h de mur).** Utilisez votre 2-ply élagué (ou, mieux, distillez gnubg 2-ply si l'accès programmatique est possible — ~100 000× moins cher qu'un rollout). N'allez au-delà de 2,5 M labels que si une porte tête-à-tête (pas la perte de validation) montre un gain non résolu.

**Étape 4 — Qualification escaladée, une seule fois par candidat retenu (coût : heures → 4,9 jours).** Réservez le rollout complet et le match dupliqué au(x) seul(s) candidat(s) ayant passé P3. Budgétez le match dupliqué comme un événement rare, pas comme une routine d'itération.

**Étape 5 — Si plafond (SPSA).** N'engagez SPSA sur la tête de sortie que lorsque la distillation sature (cf. plafond du professeur). Scoré sur banc de parties à dés miroirs — rapide (Whittington : 20 000 parties en ~21 s dans son harnais).

**Ce qu'il faut refuser :** toute recette exigeant un parc de machines, un cloud GPU conséquent, ou des millions de parties par patch (style fishtest/ELF/KataGo). Elles sont inadaptées à une machine unique et n'améliorent pas votre goulot réel (étiquetage + mesure CPU).

### Trois scénarios chiffrés (matériel : votre 16 c / 32 fils, 30 processus)

| Scénario | Génération | Entraînement | Mesure | Total mur |
|---|---|---|---|---|
| **Minimal** (le signal le moins cher) | self-play 0-ply pour 400–500 k positions : minutes ; ou distillation gnubg 2-ply : ~minutes | QAT « minutes » | P0+P3 par décision, sans rollout : dizaines de minutes | **~1–3 h** |
| **Nominal** (votre recette) | 1,0–1,5 M positions self-play 0-ply biaisées désaccords : ~1 h | étiquetage 2-ply 3,3–7,8 h + QAT ~1 h GPU | arbitre escaladé sur qq candidats (heures/point) + 1 match dupliqué | **~6–8 jours** dont 4,9 j de match |
| **« Ça a mal tourné »** (3 itérations) | ré-encodage + relabel à chaque tour | 3× QAT | 3× étiquetage + 3× arbitre + campagnes sous-dimensionnées à refaire + 1–3 matchs dupliqués | **~3–5 semaines** |

Le scénario « ça a mal tourné » est dominé par la mesure répétée, pas par le calcul d'entraînement : c'est la signature de votre problème historique.

## Caveats

- **Étiquettes de fiabilité.** [MESURE] = publié avec matériel/date ; [EXTRAPOLÉ] = conversion faite (base indiquée) ; [HYPOTHÈSE] = raisonnement non sourcé. Le facteur ×1 000–3 000 (RS/6000 1991 → cœur 2026) est une fourchette prudente ; le vrai gain mono-fil dépend fortement du code SIMD et de la mémoire.
- **Parallélisation.** Les « heures de mur » supposent vos 30 processus ; l'hyperthreading rend le facteur effectif sous-linéaire (~16–24×). Les heures-cœur sont l'unité robuste.
- **Volatilité rollout gnubg.** Le ~0,3 s/essai/position et le ~2 600 labels 2-ply/s viennent d'une mesure tierce (Backgammon-NN) sur son propre montage, pas d'un communiqué gnubg officiel — cohérents mais à confirmer chez vous.
- **Conflits de sources signalés :** unités cachées de TD-Gammon 3.0 (80 vs 160) ; « équivalent games » de Jellyfish jugé bogué pour petits écarts-types (Montgomery).

### Ce que je n'ai pas trouvé (honnêtement)
- **Aucun coût d'entraînement chiffré (heures/jours de machine, matériel)** publié pour Jellyfish, Snowie, eXtreme Gammon/XG, ni BGBlitz. Ce sont des logiciels fermés ; les développeurs (Dahl, Egger, Dufaure de Citres, Berger) n'ont pas publié de budgets de calcul.
- **Wall-clock et matériel des rollouts wildbg.** Les fichiers docs/dev/training.md et engine.md existent mais n'ont pu être récupérés dans cette session ; seuls les volumes (tranches de 100 000 positions, ~22 itérations) et l'error rate (~5,9 gnubg-2-ply, janv. 2024) sont publics. Le total de parties/rollouts pour atteindre 5,9 n'est pas documenté.
- **Un débit positions/s officiel de gnubg par cœur** (Heled / Schønning-Johansen) : non trouvé ; seule une mesure tierce existe.
- **Le facteur exact de réduction de variance du match dupliqué / dés communs** en backgammon (chiffre unique publié par Snowie/XG/gnubg) : non trouvé sous forme d'un facteur unique ; seules des affirmations qualitatives et le « ×50 à ×100 » des rollouts gnubg.
- **L'écart-type cubeless par partie unique** (valeur numérique propre, hors « 3√N » qui inclut le cube) : non trouvé sous forme canonique.
- **HedgeHog :** existence confirmée (analyseur NN dans le navigateur) mais aucun détail d'entraînement (parties, matériel, dates) publié.
- **Retours d'expérience nominatifs directs** d'XG (Dufaure de Citres) ou BGBlitz (Berger) sur « ce qui fait exploser le budget » : non trouvés ; les leçons proviennent de gnubg, wildbg, Backgammon-NN et de l'analogie NNUE/Lc0.