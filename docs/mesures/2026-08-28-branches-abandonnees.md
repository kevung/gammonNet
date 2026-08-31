# Deux routes abandonnées, et pourquoi leurs branches ont été retirées

**Date** : 2026-08-28 · **Branche** : `main`

> Le dépôt ne garde pas de branche orpheline (`CLAUDE.md`, *Worktrees*). Mais une branche
> supprimée emporte ses commits, et une route abandonnée sans trace se re-tente. Cette note est la
> trace : ce que chacune contenait, pourquoi elle n'a pas été fusionnée, et par quoi elle a été
> remplacée.

## `t3a-lots` — le traitement par lot, en module séparé

**5 commits, 1 459 insertions**, dont `src/gn_infer_batch.c` (232 lignes), son en-tête, et deux
suites de tests. Le lot était branché dans la recherche en **opt-in, éteint par défaut**.

**Remplacée, pas rejetée.** Le traitement par lot est bien dans `main` — mais réalisé autrement,
**à l'intérieur de `gn_infer_reference.c`**, à largeur fixe `GN_EVAL_BATCH = 32`. Cette forme-là
s'est révélée supérieure pour une raison qui n'était pas prévue : la largeur fixe est le
**dispositif de correction**, pas une optimisation. Le noyau calcule 32 voies quoi qu'il arrive, ce
qui rend le résultat identique au scalaire au bit près, et c'est ce qui a permis de remplir les
lots à travers les 21 jets — l'optimisation décisive de T3A.

Un module séparé, opt-in, aurait laissé deux chemins d'inférence coexister : celui qu'on mesure et
celui qu'on livre. C'est exactement ce que `CLAUDE.md` §2 interdit.

## `t34-match-v2` — le gel des décisions money v1

**1 commit**, un seul fichier : `docs/mesures/t34-money-v1-reference.json`, 200 distributions
(propriétaire × Jacoby × efficacité, graine 20260807), figées avant la modification §9 de
`src/gn_cube.c` pour prouver *ensuite* que le chemin money n'avait pas bougé d'un bit.

**Un filet de sécurité dont le filet est arrivé après.** La modification a eu lieu, et la garantie
qu'il devait fournir a été apportée plus largement : le corpus de non-régression T12, rejoué à
chaque publication, et les **50 000 paires** de T35 qui mesurent la configuration complète, videau
compris. Le fichier était de surcroît **régénérable** — graine fixe, 200 lignes, déterministe à
build donné.

## Ce qui n'a PAS été touché

Cinq worktrees portent la phase 7 et du travail non fusionné, dont une campagne T70 en cours
d'exécution : `t70-arbitre-escalade`, `t70-arbitrage-reprenable`, `t71-etape0-professeur`,
`t73-qat-int8`, `t76-comparaison-xg`. Ils appartiennent à d'autres fils de travail.

La branche `gh-pages` a été retirée : elle servait la page mobile de T21, désormais hors ligne
depuis que GitHub Pages est passé en source « workflow ». Son `evaluator.mjs` était une copie
ancienne de `wasm/gammonnet.mjs` (181 lignes contre 390), son `model.bin` une copie régénérable des
poids, et sa page a sa source dans `wasm/mobile.html`. Rien d'unique.
