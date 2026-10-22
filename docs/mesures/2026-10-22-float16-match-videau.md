# 2026-10-22 — Le float16 en match play et au videau

**Question** (issue #33, point 2) : le constat de `2026-10-22-float16-reseau-servi.md` — le
float16 ne coûte rien de mesurable — portait sur le **money sans videau** (registre T70, 9 786
décisions). Tient-il **au score** et **avec le videau vivant** ?

**Machine** : smith (EPYC), 45 processus, machine **non chargée** par ailleurs. Aucune durée
n'est rapportée comme résultat.

## Le résultat

> **Au score comme en money, le videau vivant, le float16 ne se distingue pas du float32** :
> MWC **49,99 %** [49,95 ; 50,03] sur 50 000 paires de matchs, et **−0,0016 ppg**
> [−0,0063 ; +0,0015] sur 50 000 paires money. Les deux intervalles contiennent zéro. Et la
> raison est visible directement : **99,3 % des paires de matchs et 99,8 % des paires money
> totalisent exactement zéro** — les deux réseaux y ont joué les mêmes parties, coup pour coup et
> videau pour videau.

| | match (7 points, scores échantillonnés) | money (Jacoby, videau vivant) |
|---|---|---|
| paires dupliquées | 50 000 (100 000 matchs) | 50 000 (100 000 parties) |
| **float16 − float32** | MWC **49,99 %** [49,95 ; 50,03] ; victoires nettes par paire −0,0002 [−0,0010 ; +0,0006] | **−0,0016 ppg** [−0,0063 ; +0,0015] |
| paires nulles **exactement** | 49 631 (**99,3 %**) | 49 901 (**99,8 %**) |
| doubles joués | 223 517 (4,47 par paire) | 151 955 (3,04 par paire) |
| tours joués | 11 549 008 | 4 571 166 |

IC 95 %, bootstrap sur les paires (jamais sur les parties : les deux manches d'une paire
partagent leurs dés). Le détail par score de départ — les 49 couples `(away_a, away_b)` de 1 à 7,
et l'après-Crawford séparément — est dans le dépouillement ; aucune case ne dépasse ±0,006
victoire nette par paire, ce qui à ~1 000 paires par case est du bruit.

**Ce que cette mesure dit, et ce qu'elle ne dit pas.** Elle dit que, dans le jeu réel au score
et au videau, la substitution ne change presque jamais une partie, et que l'écart de force qui
en résulte est sous ±0,04 point de MWC et ±0,006 ppg. Elle ne dit pas que les **équités**
affichées sont les mêmes : elles bougent de quelques 1e-4 (`2026-10-22-float16-reseau-servi.md`,
et les références de #33 : 9,4e-4 au plus sur les golds de recherche). Un affichage qui
compare deux analyses à 1e-4 près verra la différence ; une décision, presque jamais.

## Protocole

`bench/run_t35.py --theirs self`, les deux camps au **même réglage** : 2-ply, filtre `(0,1,1)`,
élagage `k = 12`, videau à 2-ply, Jacoby en money, plafond de videau 64. Seuls les poids
diffèrent :

| | grand réseau | réseau d'élagage | empreinte d'évaluation |
|---|---|---|---|
| float16 | `strehl-prob5-512-512-256-256_v1.8.1_2026-10-22.bin16` (`79b27fb6…`) | `strehl-prune-32_v1.8.1_2026-10-22.bin16` (`87c1986d…`) | `35817cb250d5afa3` |
| float32 | `cubeless_prob5_512_512_256_256.bin` (`a84ff7b4…`) | `prune_32.bin` (`9b2ab23d…`) | `c9c11f1c0254dfe2` |

Mêmes dés pour les deux camps (paire dupliquée, sièges échangés), graine `20260810`. En match :
longueur 7, score de départ tiré uniformément sur `(1..7)²`, Crawford joué ou derrière à pile ou
face quand un seul joueur est à 1-away. Build : `main` après `cc1a66c`, `make build` (drapeaux
par défaut).

## Les journaux

`2026-10-22-float16-t35-match.jsonl.xz` et `2026-10-22-float16-t35-money.jsonl.xz` (en-tête de
protocole, puis une ligne par paire). SHA-256 des journaux décompressés :
`84ab9f97…e968` (match), `58dcc722…4443` (money). Pour redépouiller :

    xz -dk docs/mesures/2026-10-22-float16-t35-match.jsonl.xz
    python bench/report_t35.py --journal docs/mesures/2026-10-22-float16-t35-match.jsonl
