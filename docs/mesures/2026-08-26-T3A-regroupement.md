# T3A — remplir les lots : l'élagage passe de ×1,36 à ×9, et la contraction FMA en embuscade

**Date** : 2026-08-26 · **Machine** : la machine de calcul · **Branche** : `t3a-regroupement`

> **La question.** La fiche du branchement mesurait l'élagage à ×1,36 et concluait à ne pas
> l'activer : tous les `k` achetaient la même vitesse, donc les plus serrés payaient de la qualité
> pour rien. Elle laissait ouverte la raison du plafond. La voici, et elle change le verdict.
>
> **La réponse.** L'élagage retirait 82 % des évaluations et seulement **26 % du travail**, parce
> que le noyau calcule **32 voies quoi qu'il arrive** : chaque nœud faisait toujours son appel, avec
> cinq positions au lieu de vingt. En mettant ensemble les survivants des vingt-et-un jets, le
> remplissage passe de **14,5 % à 80,5 %** et l'élagage rend **×3,9 à ×9,3**. Au passage, la
> vérification bit à bit a débusqué autre chose : la **contraction FMA** rendait l'exactitude du
> moteur otage de la forme du code.

## Le fait qui explique le plafond

Instrumentation du remplissage **par réseau**, 20 décisions 2-ply filtre `(0,1,3)` :

| | appels du grand réseau | voies vivantes | remplissage | **voies calculées** |
|---|---|---|---|---|
| sans élagage | 35 201 | 684 874 | 60,8 % | **1 126 432** |
| `k=5`, un lot par jet | 25 973 | 120 834 | **14,5 %** | **831 136** |
| `k=5`, **lots fusionnés** | **4 691** | 120 834 | **80,5 %** | **150 112** |

L'élagage ne réduisait pas le nombre d'**appels**, seulement leur contenu. Un appel à cinq
positions coûte exactement ce qu'un appel à trente-deux coûte.

## Ce que ça donne

Machine calme, mono-fil, `bench/bench_decision.c` :

| | s/décision | gain |
|---|---|---|
| sans élagage | 2,0075 | — |
| `k=12` | 0,5588 | **×3,6** |
| `k=8` | 0,4557 | ×4,4 |
| `k=5` | 0,3528 | ×5,7 |
| `k=3` | 0,2396 | **×8,4** |

Au volume — 300 décisions de contact, 150 de course, 26 ouvriers, `bench/prune_search.py` :

| `k` | ×temps | accord | perte/décision | IC 95 % |
|---|---|---|---|---|
| 2 | ×9,32 | 79,3 % | +0,00406 | [+0,00245 ; +0,00608] |
| 3 | ×9,05 | 80,0 % | +0,00389 | [+0,00232 ; +0,00585] |
| 5 | ×6,16 | 90,7 % | +0,00182 | [+0,00061 ; +0,00353] |
| 8 | ×4,75 | 96,3 % | +0,00031 | [+0,00002 ; +0,00083] |
| **12** | **×3,90** | **98,3 %** | **+0,00023** | **[−0,00000 ; +0,00067]** |

**Les colonnes de qualité sont inchangées, au chiffre près, par rapport à la mesure du
branchement.** C'est attendu et c'est la vérification : le regroupement ne touche pas au jeu, il
ne touche qu'au coût.

**Le verdict de la fiche précédente est révisé.** Elle disait : ne pas activer, parce que tous les
`k` achetaient la même vitesse. Ce n'est plus vrai — la vitesse dépend maintenant de `k`, et
`k=12` rend ×3,9 pour une perte dans le bruit en contact. Ce qui reste vrai : **la course est le
point faible** (91,3 % d'accord à `k=12` contre 98,3 % en contact), et **la force réelle n'est
toujours pas mesurée** — la perte est en équité par décision contre la recherche non élaguée,
pas en ppg ni en MWC.

## Ce qui a été essayé et qui n'a rien donné

**Garder le petit réseau au chaud n'était pas la bonne piste, et la mesure l'a dit.** L'hypothèse
de départ était que les 2 Mio de poids du grand réseau évincent les 25 Kio du petit à chaque
alternance — appuyée sur un fait réel : le petit réseau coûte 0,00199 ms par évaluation quand il
tourne seul dans la recherche et 0,0227 ms interleavé. Le regroupement des passes a donc été
écrit pour supprimer l'alternance. **Il rend les choses 2,2 % plus lentes** (1,5237 s contre
1,4902 s à `k=5`). L'hypothèse est réfutée, pas amendée.

Ce refactor n'a pourtant pas été jeté : c'est lui qui rend la fusion des lots possible, en
séparant `rank_plays` en trois phases. La bonne idée est venue de la mauvaise.

## La contraction FMA, et pourquoi elle méritait un drapeau

La comparaison bit à bit du résultat élagué, groupé contre non groupé, **a échoué** : les coups et
les classements étaient identiques, mais les équités bougeaient de ~3e-9. Ce qui a été écarté, en
mesurant :

| écartée | comment |
|---|---|
| composition des lots | les probabilités sont identiques partout ; `gn_evaluate_batch` est bit-identique par item, et `tests/test_batch.py` le tient |
| mémoire non initialisée | valgrind : aucune lecture non initialisée, aucun accès invalide |
| non-déterminisme | deux exécutions du même build : identiques |

Restait la **contraction**. `gcc` fusionne `a*b + c` en un FMA — **un** arrondi au lieu de deux —
sous `-ffp-contract=fast`, qui est son défaut ; et il le fait ou non **selon la forme du code
autour**. À entrées identiques et ordre de sommation identique, réarranger une boucle déplaçait le
résultat. Vérifié : avec `-ffp-contract=off`, groupé et non groupé sont **identiques bit à bit** à
`ply=1` comme à `ply=2`.

**Le drapeau est posé sur `gn_search.c`, et sur lui seul.** Ce dépôt fait reposer beaucoup sur
l'exactitude bit à bit — l'empreinte d'évaluation qui verrouille un journal T35, la reprise d'une
campagne segmentée, le corpus de non-régression T12. La laisser dépendre de la forme du code,
c'est la perdre au premier refactor, sans un signe. L'appliquer à l'inférence, en revanche,
déplacerait les sorties du réseau — donc l'empreinte — pour un bénéfice nul, la divergence n'étant
pas là. Empreinte vérifiée inchangée (`3f5f3c8a1ffad278` sur le build par défaut, des deux côtés).

**Coût mesuré : 1 %** (2,0355 s contre 2,0151 s par décision).

**Ce que le drapeau déplace quand même** : les équités du moteur, y compris non élagué, bougent
de l'ordre de 1e-9 par rapport au build sans drapeau. C'est visible, c'est nommé ici, et le corpus
de non-régression T12 passe.

## Le 3-ply, qui redevient testable

La même fusion, mesurée à la profondeur que T36 avait dû renoncer à explorer — garde `(0,1,1,5)`,
mono-fil :

| | s/décision | |
|---|---|---|
| 3-ply, sans élagage | **70,55** | T36 publiait 60–96 |
| 3-ply, élagage `k=12` | **20,15** | ×3,50 |
| 3-ply, élagage `k=5` | **12,23** | **×5,77** |

**Ce que cela rouvre.** T36 nommait sa réserve : sa garde `(0,1,1,5)` a deux niveaux intérieurs à
un seul candidat, configuration jamais validée, et un 3-ply **large** aurait coûté ~20 min par
décision — intestable. À ×5,8, ce même 3-ply large tombe vers 3–4 min : **encore cher, mais plus
hors d'atteinte**. La réserve de T36 devient une mesure à faire plutôt qu'une impossibilité.

**Ce que cela ne change pas** : T36 a mesuré qu'un ply de plus rapporte +0,00022 d'équité par
décision, dans le bruit. La profondeur reste fermée comme *levier de force*. Ce qui s'ouvre est la
possibilité de **vérifier** qu'au 3-ply on reste à hauteur — un critère de non-régression, pas un
gain.

## Ce qui a été essayé ensuite, et qui ne paie pas

**Fusionner aussi les lots du petit réseau.** Ils restaient remplis à 65,6 %, et au 3-ply le petit
réseau fait 1 012 885 évaluations contre 478 995 pour le grand — il domine. La même technique lui
a donc été appliquée : générer les vingt-et-une fratries d'abord, ne montrer au petit réseau que
les jets où l'élagage doit mordre, en un seul passage.

Écrit, vérifié **identique bit à bit**, et mesuré :

| | main | lots du petit fusionnés |
|---|---|---|
| 3-ply `k=12` | 20,15 s | 19,97 s |
| 3-ply `k=5` | 12,23 s | 12,14 s |
| 2-ply `k=3` | 0,2396 s | 0,2369 s |

**0,7 à 0,9 % — dans le bruit.** Environ cent cinquante lignes délicates (génération séparée,
compaction des seuls jets élagués, remise en place) pour un gain qu'on ne sait pas distinguer de
zéro. **La branche a été abandonnée**, et la mesure consignée ici pour que personne ne la refasse.

La leçon rejoint celle du regroupement : le remplissage des lots ne compte que **là où le coût par
voie est élevé**. Le grand réseau paie 2 Mio de poids par appel, le petit 25 Kio — remplir les lots
du second ne rachète presque rien.

## Ce que cette fiche ne mesure pas

- **La force.** Un round-robin élagué contre non élagué le dirait ; il n'a pas tourné. L'élagage
  reste **éteint par défaut**, et aucun appelant ne l'active.
- **Un `k` par terrain.** La course demanderait un `k` plus large, ou pas d'élagage du tout.
- **Le petit réseau.** Ses lots restent remplis à 65,6 % ; les fusionner à leur tour est la suite
  évidente, non faite ici.
- **Le navigateur.** Le lot y rend ×2,21 et non ×8,5 ; l'équilibre y est différent.

## Reproduire

```bash
make bench-decision
python bench/prune_search.py --contact 300 --race 150 --ks 2,3,5,8,12 --workers 26
make CFLAGS="-O2 -std=c11 -Wall -Wextra -fPIC -DGN_BATCH_FILL_STATS" bench-decision   # remplissage
```

Sortie : [`t3a-prune-search.json`](t3a-prune-search.json).
