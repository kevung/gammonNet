# Choisir un réglage

Un réglage échange du **temps** contre de la **qualité**. Les deux sont mesurés, et cette page
donne les deux — jamais l'un sans l'autre.

## Les préréglages

| Préréglage | Interne | Coût natif / décision | Coût navigateur / décision | Un match de 7 points *(≈130 décisions)* |
|---|---|---|---|---|
| **Instantané** | 0-ply | 0,0013 s | 0,006 s | ~1 s |
| **Normal** | 2-ply `(0,1,3)`, élagage `k=12` | **0,306 s** | **2,7 s** | **74 s** *(8 workers)* |
| **Approfondi** | 2-ply `(0,1,3)`, sans élagage | 2,01 s | 9,8 s | ~4 min *(8 workers)* |
| **Rollout** | 0-ply, 1 296 essais | 30,5 s / position | non mesuré | — |

Les coûts navigateur sont mesurés sur **Firefox 154, build SIMD**, sur une machine de bureau au
repos. Ils dépendent de l'appareil ; la page de mesure est fournie pour les refaire chez vous.

## Ce que l'élagage coûte, et pourquoi `k = 12`

Le réseau d'élagage trie les coups candidats pour que le grand réseau n'en évalue qu'une poignée.
`k` est le nombre de survivants. Mesuré sur 300 décisions de contact, arbitre = la recherche non
élaguée :

| `k` | Gain de vitesse | Accord avec la recherche non élaguée | Équité perdue par décision |
|---|---|---|---|
| 3 | ×9,05 | 80,0 % | **+0,00389** |
| 5 | ×6,16 | 90,7 % | +0,00182 |
| 8 | ×4,75 | 96,3 % | +0,00031 |
| **12** | ×3,90 | **98,3 %** | **+0,00023** [−0,00000 ; +0,00067] |

```{admonition} Ne baissez pas k sans mesurer
:class: warning

À `k = 3`, l'équité perdue vaut **+0,00389 par décision** — soit **dix-huit fois ce qu'un ply
entier de profondeur supplémentaire rapporte** (+0,00022, mesuré). Ce n'est pas un réglage
« rapide » : c'est un réglage qui joue moins bien.

`k = 12` est le seul point de la courbe où l'on ne paie rien de mesurable.
```

**La course est le point faible** : à `k = 12`, l'accord est de 91,3 % en course contre 98,3 % en
contact. Un `k` par terrain n'a pas été mesuré.

## La profondeur

| Profondeur | Coût natif / décision | Ce qu'elle apporte |
|---|---|---|
| 0-ply | 0,0013 s | le réseau seul |
| 1-ply | ~0,3 s | **le gain décisif** : PR de 1,088 → 0,499 |
| 2-ply | 0,306 s *(élagué)* | PR 0,499 → 0,273 |
| 3-ply | 10,6 s *(élagué)* | **+0,00022 d'équité par décision — dans le bruit** |
| 4-ply | 100 à 257 s | non mesuré en qualité ; instrument de vérification |

```{admonition} La profondeur au-delà du 2-ply n'est pas un levier de force
:class: important

Mesuré deux fois, avec deux arbitres indépendants : passer du 2-ply au 3-ply rapporte
**+0,00022 d'équité par décision** — à l'intérieur du bruit — pour un coût multiplié par quinze.

Le 3-ply et le 4-ply existent pour **vérifier** qu'on reste à hauteur de GNU Backgammon à ses
propres profondeurs, pas pour analyser des parties.
```

## Le parallélisme

Le pool de Web Workers monte à **×6,2 sur huit fils** (26 667 évaluations/s mesurées). C'est ce
qui fait la différence entre **350 s** et **74 s** pour un match. Ne livrez pas une interface sans
lui.

| Workers | Évaluations/s | Accélération |
|---|---|---|
| 1 | 4 301 | ×1 |
| 2 | 7 463 | ×1,74 |
| 4 | 13 333 | ×3,1 |
| 8 | 26 667 | ×6,2 |
