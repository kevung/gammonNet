# T79 — Ce que la fin de partie pèse réellement : 0,0008 PR

**Date** : 2026-08-28 · **Machine** : `melbaa`, 14 cœurs / 28 fils · **Branche** :
`t79-poids-du-domaine`

> T78 a mesuré ce que le réseau perd **par décision de bearoff**, et ce que le distillé y ramène
> — 0,0919 de queue contre 0,0014. Il manquait le multiplicateur : **quelle part des décisions
> d'une partie tombe dans ce domaine ?** Sans lui, « facteur 65 sur la queue » ne se convertit en
> rien. `BRIEF.md` §9 avertit exactement de cela : un corpus riche en fins de partie flatte qui a
> une table.

## Le domaine, en fréquence

**200 000 parties d'argent sans videau**, 8 795 521 décisions de coup, jouées à 0-ply :

| | |
|---|---|
| décisions de coup par partie | 43,98 |
| **dont dans le domaine de la table** | **4,28 %**, soit **1,88 par partie** |
| parties qui atteignent le domaine | 42,7 % |
| pions restants à l'entrée dans le domaine | médiane 9, moyenne 8,3 |

Un peu plus d'une décision sur vingt-cinq. Ce n'est ni négligeable ni dominant, et c'est le
nombre qui manquait.

## Ce que chaque profondeur y perd

**2 500 parties, 4 511 décisions du domaine**, chacune notée **exactement** par la table
bilatérale. La partie est jouée à 0-ply ; les profondeurs supérieures sont **jugées** sur les
seules décisions du domaine — vingt-trois fois moins cher que de les faire jouer, pour la même
quantité.

| moteur | accord | perte / décision | si désaccord | p99,9 | **pire** | équité / partie |
|---|---|---|---|---|---|---|
| gammonNet 0-ply | 94,6 % | 0,000278 | 0,00514 | 0,0301 | 0,0538 | 0,000501 |
| gammonNet 1-ply | 95,8 % | 0,000176 | 0,00421 | 0,0211 | 0,0370 | 0,000318 |
| **gammonNet 2-ply** *(le réglage servi)* | 97,8 % | 0,000043 | 0,00200 | 0,00833 | **0,0170** | **0,000078** |
| **le distillé de T78** | **99,1 %** | **0,000003** | **0,00036** | **0,00076** | **0,00217** | **0,000006** |

Et le gain du branchement, en **équité par partie**, sur l'intervalle **apparié** — les deux
moteurs tranchent les mêmes décisions, donc la variance des parties s'annule au lieu d'être
comptée deux fois :

| contre | gain par partie | IC 95 % | en PR |
|---|---|---|---|
| 0-ply | 0,000496 | [0,000376 ; 0,000616] | 0,0056 |
| 1-ply | 0,000312 | [0,000232 ; 0,000393] | 0,0036 |
| **2-ply** | **0,000073** | **[0,000039 ; 0,000107]** | **0,00083** |

*(PR = 500 × équité perdue par décision, sur les 43,98 décisions d'une partie — la convention de
`bench/pr.py`.)*

## Le verdict, et il tempère T78

**Le gain est réel : l'intervalle exclut zéro à quatre écarts-types.** Il est aussi **petit** :
**0,00083 PR** contre un PR mesuré de **0,273** au 2-ply (T3E), soit **trois pour mille de
l'erreur restante du moteur**.

La raison est dans le tableau, et T38 l'avait annoncée sans qu'on en tire la conséquence : **la
recherche comble déjà l'essentiel du trou**. De 0 à 2 plis, la perte par décision de fin de
partie tombe de 0,000278 à 0,000043 — un facteur 6,5 — et le distillé ne peut plus reprendre que
ce qui reste. Le chiffre de 0,000552 par partie que le premier passage a rendu **ne vaut que pour
un moteur 0-ply**, et le publier seul aurait été juste et trompeur.

**Ce qui, en revanche, ne se comble pas par la recherche, c'est la queue.** La pire décision de
fin de partie du 2-ply vaut **0,0170** ; celle du distillé, **0,00217** — un facteur huit. Dans un
outil d'analyse, où une erreur visible sur une position que l'utilisateur regarde compte plus
qu'un millième de PR moyen, c'est le seul argument de qualité qui tienne encore.

## Deux contrôles croisés que la mesure a rendus gratuitement

**Le tirage de T78 était représentatif.** Il tirait uniformément dans la table ; le jeu réel
donne, au 0-ply, 0,000296 par décision sur 200 000 parties et 0,000278 sur 2 500, contre
**0,00028** pour le tirage uniforme de T38/T78. Les trois s'accordent à 6 % près. C'était une
hypothèse, elle est vérifiée.

**Et T38 se reproduit en jeu.** Sa mesure du 2-ply (garde 1-5) sur tirage uniforme donnait
**0,00004** par décision ; ici, en jeu, **0,000043**. Deux distributions, deux campagnes à trois
semaines d'écart, le même chiffre.

## Ce que cela décide

- **Le branchement ne se justifie plus par le PR.** Trois millièmes de l'erreur du moteur ne
  paient pas, à eux seuls, un module C, un portage WebAssembly et 528 Kio d'artefact.
- **Il garde deux arguments, et ils sont à mesurer, pas à supposer** : la **queue** (facteur huit
  sur la pire décision, ce qui se voit dans une analyse) et la **vitesse** — 4,28 % des décisions
  passeraient de 526 976 à 65 664 MACs par feuille. Ce second point est un compte d'opérations,
  **pas une mesure de vitesse** (règle 3), et il n'est pas chiffré ici.
- **La suite naturelle n'est pas là.** Le videau perd, dans ce même domaine, **0,00072 à 0,00135
  d'équité par décision** contre 0,000043 pour le coup au 2-ply — dix à trente fois plus. C'est
  T80.

## Reproduire

```bash
# la fréquence, sur un gros volume à 0-ply
python bench/bearoff_in_play.py --games 200000 --workers 26 --ply 0

# les profondeurs jugées sur les seules décisions du domaine
python bench/bearoff_in_play.py --games 2500 --workers 10 --ply 0 --measure-plies 1,2
```

Sorties : [`t79-poids-domaine-0ply.json`](t79-poids-domaine-0ply.json) et
[`t79-poids-domaine-plies.json`](t79-poids-domaine-plies.json).

## Ce que cette mesure ne dit pas

- **Le videau n'y est pas.** Parties d'argent **sans videau** : ni les décisions de videau, ni
  leur effet sur la valeur des erreurs de coup.
- **La fréquence est celle d'un joueur 0-ply.** Un moteur plus fort atteint des fins de partie un
  peu différentes ; l'écart porterait sur la fréquence, pas sur la perte par décision, qui est
  jugée position par position. Il n'est pas mesuré.
- **Rien sur la vitesse.** Aucun temps n'est publié ici : la machine portait aussi deux
  entraînements.
