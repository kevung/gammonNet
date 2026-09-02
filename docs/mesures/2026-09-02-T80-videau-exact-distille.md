# 2026-09-02 — T80 : le videau de fin de course, appris, contre Janowski

**Fiche** : T80. **Réseau** : `models/bearoff_cubeful_code16_256_128.bin`, code appris par
disposition (16), tronc 256-128, quatre sorties, tanh — le gabarit gagnant de T78 avec trois
sorties de plus. **Bancs** : `bench/cube_at_depth.py` (décision de videau, vérité exacte sans
variance) et `bench/bearoff_distill.py` (décision de coup, le banc de T78).

## Le contrôle qui vient avant tout : l'instrument est préservé

La fiche l'exige avant de demander quoi que ce soit de neuf. À la graine et au nombre de
positions d'origine (2 000, graine 20260808), la version étendue du banc reproduit les taux
publiés **exactement** : 98,3 % au videau possédé, 97,5 % au centré, perte moyenne 0,000723 et
0,001352, pire cas 0,2778. Rien n'a bougé sous les pieds de la mesure.

## Le résultat : le seuil de succès est franchi, et de loin

Seuil écrit avant la mesure : équité perdue par décision de videau **divisée par au moins 10**
dans les deux états de possession, et pire cas **sous 0,05**.

Sur l'échantillon de référence (2 000 positions, la graine de la fiche) :

| Possession | Voie classique (Janowski aux x mesurés) | Réseau distillé | Facteur |
|---|---|---|---|
| Possédé, perte moyenne | 0,000723 | **0,000003** | **241** |
| Possédé, pire cas | 0,2778 | **0,0053** | 52 |
| Centré, perte moyenne | 0,001352 | **0,000001** | **1 352** |
| Centré, pire cas | 0,2778 | **0,0012** | 231 |

L'accord avec la décision exacte passe de 98,3 % à 99,9 % au videau possédé, et de 97,5 % à
**100,0 %** au centré. Aucune décision au-delà de 0,01 d'équité perdue, contre 20 et 31.

**La preuve d'existence est faite** : un réseau *peut* battre Janowski sur une décision de videau,
dans le seul domaine du jeu où la vérité s'écrit sans rollout.

## Le même banc à dix fois le volume, où le seuil se tend

Sur 20 000 positions, la queue s'allonge — c'est ce qu'une queue fait quand on la regarde plus
longtemps, et c'est pourquoi le volume est dit à chaque fois.

| Possession | Voie classique | Réseau | Pire cas du réseau | Seuil |
|---|---|---|---|---|
| Possédé | 0,000928 | 0,000008 | 0,0296 | sous 0,05 ✓ |
| Centré | 0,001654 | 0,000005 | **0,0555** | sous 0,05 ✗ |

Le facteur d'amélioration tient (116 et 331). **Le pire cas au videau centré dépasse le seuil de
11 %.** Un critère sur deux est donc manqué à ce volume, et il est manqué de peu : c'est écrit
ici plutôt que noyé sous le facteur 331 qui l'accompagne.

## Ce que les quatre sorties coûtent

| | Une sortie (T78) | Quatre sorties (T80) | Écart |
|---|---|---|---|
| Paramètres | 264 065 | 264 452 | +387 |
| MACs | 65 664 | 66 048 | +384 |
| Octets (float32) | 1 056 308 | 1 057 856 | +1 548 |

**Quatre sorties coûtent 0,6 % de plus qu'une seule**, pas un second réseau. L'argument de la
fiche est donc mesuré, pas supposé. En float16 le fichier ferait environ 517 Kio — c'est une
**déduction arithmétique et non une mesure** : le conteneur float16 du format `GNBONET1` n'existe
pas encore, T78 l'avait déjà noté comme un manque.

## La colonne cubeless est dégradée, et la cause n'est PAS établie

Le banc de T78, 8 000 décisions de coup, graine 20260806 :

| Réseau | Perte moyenne | Pire cas | Décisions au-delà du repère gnubg (0,0023) |
|---|---|---|---|
| T78, une sortie | 0,00001 | **0,0014** | **0** |
| T80, quatre sorties | 0,00001 | **0,0094** | **12** |

La moyenne tient (0,00001, sous le seuil de 0,00005) ; **la queue est multipliée par 6,7**, et
douze décisions passent au-dessus du pire cas de GNU Backgammon, là où T78 n'en laissait aucune.

La règle de diagnostic de la fiche nomme ce symptôme « interférence entre têtes ». **Cette cause
n'est pas établie, et l'invoquer maintenant serait exactement l'explication qui arrange.** Deux
choses diffèrent entre les deux entraînements, pas une :

1. le réseau a quatre sorties au lieu d'une ;
2. **l'étage d'affinage par décision de coup n'a pas tourné** — il demande un corpus d'un million
   de décisions que les processeurs, pris par la campagne d'étiquetage de T71, ne pouvaient pas
   produire ce jour-là. T78 l'avait, et c'est précisément l'étage qui attaque la queue.

La fiche impose « une seule chose change à la fois ». Le contrôle est donc à faire dans cet
ordre : refaire cet entraînement **avec** l'étage de décision de coup, à graine et à budget
identiques, et relire ce tableau. Si la queue reste à 0,0094, l'interférence entre têtes devient
une cause mesurée et la suite est celle qu'écrit la fiche — têtes séparées, ou pondération des
étages.

## Ce que ce document ne dit pas

Il ne dit rien du **branchement** : ce réseau n'est consulté par rien, ni par `gn_search` ni par
le module WebAssembly. Il ne dit rien du videau **en match**, la table étant money. Il ne touche
pas au modèle de Janowski, qui reste ce qui répond hors du domaine de la table.

Et il ne conclut rien sur le videau appris en général. Ce réseau lit un code appris par
disposition, pas les 196 caractéristiques du tronc ; son gabarit a été choisi sur une régression
cubeless, pas sur une décision de seuil ; son domaine est le plus discrétisé du jeu. T80 est une
preuve d'existence, ce que sa fiche disait déjà avant de connaître le résultat.

## Reproduire

```
python tools/build_bearoff_matrix.py --cubeful
python tools/train_bearoff_net.py --matrix build/ts6x11_cubeful.u16 \
    --sides build/ts6x11_sides.npy --hidden 256,128 --embedding 16 \
    --output tanh --device cuda --steps 40000 --mine-rounds 3 --cube-steps 12000 \
    --out models/bearoff_cubeful_code16_256_128.bin
python bench/cube_at_depth.py --positions 2000 --plies 0,1 \
    --net models/bearoff_cubeful_code16_256_128.bin
python bench/bearoff_distill.py --decisions 8000 \
    --net models/bearoff_cubeful_code16_256_128.bin
```

L'extraction des quatre colonnes prend 2,5 s et se vérifie sur 2 000 paires contre le lecteur de
T38 ; l'entraînement, 7,4 min sur une RTX 4090 — machine par ailleurs saturée par la campagne
d'étiquetage de T71, donc ce temps est un ordre de grandeur et non une mesure de débit.
