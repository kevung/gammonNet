# T34 phase 2, étape 3b — nos choix de coups cubeful contre ceux de GNU Backgammon

**Date** : 2026-08-08 · **Machine** : bureau (12 processus) · **Branche** : `t34-3b`

> **Ce que ce rapport affirme, et ce qu'il n'affirme pas.** L'accord mesuré est une
> **ressemblance** à GNU Backgammon 1.08.003 — aucun des deux moteurs n'est arbitré contre une
> vérité indépendante, et sur les désaccords qui suivent, dire *qui* a raison est exactement le
> travail de T39, pas de ce banc.

## Le résultat, en une phrase

Sur **2 618 décisions de coups non forcées** (2 000 positions de contact + 1 000 de bearoff,
un jet aléatoire par position, 0-ply des deux côtés, money, Jacoby coupé), l'accord des choix
est **stable autour de 81-83 %** quel que soit l'état du videau — mais sur le sous-ensemble
**cube-sensible** (les décisions où au moins un moteur change son propre choix à cause du
videau, 74 à 104 cas selon l'état), l'accord tombe à **26-32 %**, et les deux moteurs ne
plient presque jamais sur les mêmes positions (`both_moved` ≤ 1 partout).

## La sémantique de `findbestmove`, fixée par sonde — et un piège trouvé par refus

- `gnubg.findbestmove(board, cube-info, eval-context, dice)` : le **quatrième argument** (les
  dés) n'apparaît pas dans le `help()` embarqué — l'appel à trois arguments lève, l'appel à
  quatre répond. Tuple par paires `(de, vers)`, points 1..24 du point de vue du joueur au
  trait, 25 la barre, 0 la sortie, `(0, 0)` en bourrage. `(8, 5, 6, 5)` pour le 3-1
  d'ouverture. Documenté dans `tools/gnubg_server.py::op_bestmove`.
- **L'appariement par multiensemble de paires est faux, et le refus du pilote l'a prouvé** :
  sur un coup composé, gnubg et notre générateur peuvent garder deux intermédiaires différents
  du même coup (13/10/8 contre 13/11/8 — même position finale, paires différentes). Le banc
  apparie donc par **résultat** : les paires appliquées dans leur ordre, et la position obtenue
  doit être l'un des résultats de `gn_legal_plays` — qui reste l'autorité sur les règles. Tout
  tuple inappariable **arrête la mesure** ; sur les 2 922 positions jouables du volume final,
  zéro refus.

## Le protocole

Corpus de §6.3 réutilisé (graines 20260807/20260808), un jet par position (graine 20260809),
**0-ply des deux côtés**, réseau d'élagage gnubg désactivé, **Jacoby coupé des deux côtés** —
notre valuation de feuille ne le porte pas (il gouverne la décision de doubler, pas la valeur
d'un coup). Quatre configurations money : cubeless (colonne de base), puis videau centré,
possédé, adverse — notre `x` mesuré par état (0,688 / 0,566 / 0,687), le contexte gnubg
`cubeful=1`, même possesseur. 304 coups forcés exclus des taux.

## Les taux

| configuration | accord | IC 95 % |
|---|---:|---|
| cubeless | 82,6 % | [81,1 ; 84,0] |
| videau centré | 80,9 % | [79,4 ; 82,4] |
| videau possédé | 81,7 % | [80,2 ; 83,1] |
| videau adverse | 81,7 % | [80,1 ; 83,1] |

L'accord de fond (~82 %) est celui de deux réseaux 0-ply différents ; le videau ne le déplace
pas de façon détectable — les quatre intervalles se recouvrent.

## La colonne qui compte : les décisions cube-sensibles

| état | n | accord | IC 95 % | nous avons bougé | gnubg a bougé | les deux |
|---|---:|---:|---|---:|---:|---:|
| centré | 104 | 26,0 % | [18,5 ; 35,1] | 65 | 40 | **1** |
| possédé | 74 | 32,4 % | [22,9 ; 43,7] | 39 | 36 | **1** |
| adverse | 76 | 27,6 % | [18,8 ; 38,6] | 46 | 30 | **0** |

Trois lectures, dans l'ordre de solidité :

1. **L'ampleur de l'effet videau est comparable des deux côtés** : nous changeons 39-65 choix
   sur 2 618, gnubg 30-40. Le videau agit sur ~1,5-2,5 % des décisions de coups, chez les deux
   moteurs. Les cas se répartissent entre contact et bearoff (53/51 au centré) — le contraste
   cubeless→cubeful réordonne aussi en contact, contrairement au contraste possédé↔adverse à
   0-ply (voir le constat de la spec §8 : ce dernier est un décalage constant en région
   linéaire).
2. **Mais presque jamais sur les mêmes positions** : l'intersection est de 0 ou 1 cas. Chaque
   moteur plie ses propres quasi-égalités — celles que SON modèle d'efficacité et SES
   probabilités placent au seuil. C'est cohérent avec la nature de l'effet : un re-classement
   de coups dont les valeurs cubeful sont à quelques millièmes l'une de l'autre.
3. **Sur ces cas-seuils, l'accord tombe à 26-32 %** — en dessous du fond de 82 %, ce qui est
   attendu : le sous-ensemble est défini par « au moins un moteur a bougé », donc il
   sur-échantillonne les quasi-égalités où deux modèles différents départagent différemment.

**Ce qu'on ne conclut pas** : rien ici ne dit lequel des deux plie mieux. Les marges en jeu
sont des millièmes d'équité par décision ; l'arbitrage exigerait le rollout cubeful de T39.

## Réserves nommées

- 0-ply des deux côtés ; l'effet du videau sur le choix à profondeur n'est pas mesuré ici.
- Money seulement ; en match, la sensibilité au videau passe par la MWC et n'est pas couverte.
- Un jet par position : le tirage des jets (graine 20260809) échantillonne, il n'épuise pas.
- `x` transporté du domaine sans gammon, comme partout depuis l'ajustement.

## Reproduire

```bash
python bench/compare_moves.py --contact 2000 --bearoff 1000 --workers 12 \
    --out docs/mesures/t34-comparaison-coups.json
```

Sortie complète : [`t34-comparaison-coups.json`](t34-comparaison-coups.json) (agrégats et les
désaccords, avec Position ID).
