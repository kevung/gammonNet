# T37 — La distribution est calibrée, à un biais de gammon près qui ne pèse pas sur le videau

**Date** : 2026-08-07 · **Machine** : la machine de calcul · **Branche** : `t37-calibration`

> **Le résultat, en une phrase.** Sur quatre des cinq composantes, le biais du réseau contre un
> rollout non tronqué est **indiscernable de zéro**. Sur la cinquième — `P(gain-gammon)` — le
> réseau sous-estime de **−0,0024** [−0,0041 ; −0,0006], un écart statistiquement réel mais qui ne
> déplace un point de prise que d'environ **0,05 point de pourcentage** : trop petit pour être la
> raison de ne pas construire un videau dessus.

## Le résultat

500 positions de **contact**, graine `20260807`, chacune lue trois fois : les cinq probabilités du
réseau, les fréquences d'un rollout **non tronqué** (324 essais, politique 0-ply, dés communs par
position), et les cinq probabilités de GNU Backgammon au 0-ply. Biais = modèle − fréquence du
rollout ; IC 95 % par bootstrap (10 000 rééchantillonnages).

| composante | biais **nous** [IC 95 %] | MAE nous | biais **gnubg** [IC 95 %] | MAE gnubg |
|---|---|---|---|---|
| `win` | +0,00003 [−0,00227 ; +0,00230] | 0,02026 | −0,00083 [−0,00327 ; +0,00162] | 0,02238 |
| `win_gammon` | **−0,00238 [−0,00411 ; −0,00063]** | 0,01412 | −0,00200 [−0,00397 ; +0,00001] | 0,01620 |
| `win_backgammon` | −0,00036 [−0,00086 ; +0,00014] | 0,00339 | +0,00045 [−0,00016 ; +0,00105] | 0,00380 |
| `lose_gammon` | −0,00064 [−0,00223 ; +0,00093] | 0,01208 | −0,00093 [−0,00273 ; +0,00085] | 0,01383 |
| `lose_backgammon` | −0,00009 [−0,00050 ; +0,00030] | 0,00266 | −0,00005 [−0,00054 ; +0,00041] | 0,00297 |

**Un seul intervalle exclut zéro : le nôtre, sur `win_gammon`.** Celui de gnubg sur la même
composante le frôle (borne haute +0,000006) sans le franchir — les deux moteurs penchent du même
côté sur les gammons gagnés, le nôtre un peu plus fort. Les quatre autres composantes, des deux
côtés, ne se distinguent pas du bruit à ce volume.

**La MAE est plus basse chez nous que chez gnubg sur les cinq composantes**, sans exception. Ce
n'est **pas** présenté comme une preuve de supériorité : le rollout de référence est conduit par
notre propre politique à 0-ply, donc toute régularité de notre jeu se retrouve à la fois dans le
jeu et dans l'arbitre qui le juge — un avantage structurel, pas gagné. Ce que l'écart montre
honnêtement, c'est que **gnubg n'est pas mieux calibré que nous contre notre propre référence** ;
ça n'établit pas qu'il le soit moins contre une référence neutre.

## Traduction en termes de videau

Une décision de videau vit sur le **point de prise** (TP), pas sur une probabilité isolée. Sa
forme money, cube mort (sans valeur de recube) :

```
TP = (L − 0,5) / (W + L)

W = valeur moyenne d'un gain  = (P(gain) + P(gain-gammon) + P(gain-bg)) / P(gain)
L = valeur moyenne d'une perte = (P(perte) + P(perte-gammon) + P(perte-bg)) / P(perte)
```

`W` et `L` sont calculés depuis les probabilités *imbriquées* — exactement la convention de
`Evaluation.as_tuple()`. Le biais mesuré (−0,00238 sur `win_gammon`) entre uniquement dans `W`. On
l'applique à trois positions représentatives, du contact typique au blitz marqué :

| type de position | `P(gain)` | `P(gain-g.)` | TP (biaisé, ce que le réseau calculerait) | ΔTP |
|---|---|---|---|---|
| contact typique | 0,50 | 0,22 | 31,01 % | **+0,052 pt** |
| prise/déjà serrée | 0,42 | 0,30 | 22,28 % | **+0,043 pt** |
| blitz marqué | 0,62 | 0,45 | 25,37 % | **+0,031 pt** |

Sur les trois profils, l'effet mesuré déplace le point de prise de **trois à cinq centièmes de
point de pourcentage** — trois ordres de grandeur en dessous de la précision à laquelle une
décision de videau se discute d'ordinaire (les marges qui font débat sont de l'ordre du point de
pourcentage entier). Le sens du biais rend le réseau *légèrement plus conservateur* qu'il ne
devrait l'être sur les positions à fort gammon (il exigerait un TP un peu plus haut, donc dropperait
un chouïa plus souvent qu'un modèle non biaisé) — mais l'ampleur ne sépare aucune décision réelle.

Chiffres reproductibles :
```
W(win, wg, wbg) = (win + wg + wbg) / win
L(win, lg, lbg) = (1 - win + lg + lbg) / (1 - win)
TP = (L - 0.5) / (W + L)
```
appliqué avec `wg_biaisé = wg + biais` (biais négatif ⇒ `wg_biaisé < wg`).

## Le verdict

**La distribution porte une décision de videau, avec une réserve nommée, pas une réserve qui
bloque.**

- Quatre composantes sur cinq n'ont **aucun** biais mesurable à ce volume.
- La cinquième (`win_gammon`) a un biais réel mais dont l'effet chiffré sur le point de prise
  est **négligeable devant la granularité à laquelle une décision de videau se prend**.
- **Conformément à `CLAUDE.md` et `PLAN.md`** : ce biais n'est **pas corrigé par un facteur ajusté
  à la main**. Il est consigné ici comme observation, candidate à une **entrée de la phase 4** (un
  réseau entraîné pour ce projet pourrait viser une calibration plus fine des gammons) — mais la
  phase 4 reste fermée tant que T35 ne l'ouvre pas (`PLAN.md`, décision du 2026-08-04).
- Le palier A (`PLAN.md`) est donc franchi côté calibration : rien ici ne dit qu'il faut suspendre
  la construction de T34.

## Les réserves, nommées

- **La référence est un rollout conduit par notre propre réseau au 0-ply.** Les deux camps jouent
  pareil — la pratique standard — mais un biais de politique de jeu reste possible et se
  répercuterait à la fois dans la partie jouée et dans le jugement porté sur elle. gnubg est
  mesuré contre la **même** référence, ce qui rend la comparaison relative (biais nous vs biais
  gnubg) honnête, mais **pas** la comparaison absolue de chacun contre une vérité indépendante :
  ce banc ne peut pas distinguer « le réseau évalue mal » de « la politique qui a produit la
  référence joue mal, dans une classe de positions que ce réseau évalue justement mal ».
- **Le corpus est du contact uniquement**, réutilisé de `bench/decision_loss.corpus` (T36). `PLAN.md`
  décrit T37 avec un périmètre plus large — « contact, course et bearoff » — mais la fiche de
  tâche transmise pour cette mesure restreint explicitement au contact et impose la réutilisation
  de ce corpus. C'est un **écart assumé** au texte de `PLAN.md`, pas un oubli : la course et le
  bearoff ont leurs propres instruments (T33, T38) avec un arbitre exact, quand le contact n'en a
  aucun — c'est précisément le trou que ce banc comble.
- **Rollout non tronqué, 324 essais.** Le pilote (30 positions, débit mesuré) projetait 6,1 min
  pour le volume complet sur 26 processus — largement sous le budget de 40 min — donc les essais
  n'ont **pas** eu besoin d'être réduits à 216.
- **Cubeless, money, une seule profondeur (0-ply) des deux côtés.** Le videau réel et le match sont
  T34 et T35 ; ce banc ne calcule pas de TP réel, il illustre l'ordre de grandeur de l'effet d'un
  biais mesuré.

## Reproduire

```bash
python bench/calibration.py --positions 500 --trials 324 --workers 26
```

**Mesuré, pas extrapolé** : pilote de 30 positions à 19,08 s/position en série (projection 6,1 min
pour 500 positions sur 26 processus) ; volume complet exécuté en **9,0 min** (538 s) sur 26
processus. Durée totale de la commande (pilote + volume) : **~18,5 min**, sous le budget imposé de
40 min.

Sortie : [`t37-calibration.json`](t37-calibration.json).
