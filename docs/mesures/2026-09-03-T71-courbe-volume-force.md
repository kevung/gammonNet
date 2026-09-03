# 2026-09-03 — T71 : la courbe volume → force ne s'aplatit pas

**Fiche** : T71 (P2). **Instrument** : `bench/measure_t70.py` sur le registre money de T70,
10 000 décisions disputées, 2-ply, `prune_k = 12`. **Étalon** : l'incumbent 2-ply, **0,00313**
[0,00298 ; 0,00327].

## Pourquoi cette courbe existe

Le palier B1 a rendu son verdict : à 366 978 étiquettes, l'élève perd 0,00537 et ne bat pas
l'incumbent. DS-14 dit alors « arrêt : la donnée supplémentaire ne sauve pas une idée neutre ».
Encore faut-il savoir si l'idée **est** neutre. Un point isolé ne le dit pas ; une courbe, oui.

Le même élève, même architecture, même graine, même recette, a donc été entraîné sur des
sous-échantillons **tirés au sort** du corpus réuni (mochy, melbaa et smith : 1 544 098 étiquettes
brutes), puis mesuré par le même instrument.

## Le résultat

| Étiquettes | Perte par décision | IC 95 % | Facteur par doublement | Hors registre |
|---|---|---|---|---|
| 100 000 | 0,00745 | [0,00716 ; 0,00774] | — | 8,39 % |
| 200 000 | 0,00628 | [0,00604 ; 0,00653] | 0,843 | 6,81 % |
| 400 000 | 0,00535 | [0,00513 ; 0,00557] | 0,852 | 5,43 % |
| 800 000 | **0,00449** | [0,00430 ; 0,00469] | 0,839 | 4,09 % |
| *étalon* | *0,00313* | *[0,00298 ; 0,00327]* | | *0 %* |

**La courbe ne s'aplatit pas.** Chaque doublement du volume retire 15,5 % de la perte, et le
facteur est constant à un centième près sur trois doublements. L'ajustement en loi de puissance
donne `perte ∝ N^(-0,242)` avec un R² de 0,9997.

Le taux de décisions hors registre tombe en même temps, de 8,39 % à 4,09 % : le candidat joue de
moins en moins des coups que l'arbitrage n'a pas achetés, c'est-à-dire qu'il se rapproche du
comportement des moteurs autour desquels le corpus a été construit.

## Ce que l'extrapolation suggère, et pourquoi ce n'est pas un résultat

Prolongée, la loi croise l'étalon vers **3,6 millions d'étiquettes**, soit 4,5 fois le plus grand
point mesuré.

**Ce nombre est une extrapolation, pas une mesure.** La règle 3 du dépôt est explicite : une
conclusion de performance se mesure et ne se déduit pas. Trois doublements ne garantissent pas le
quatrième, et toutes les courbes d'apprentissage finissent par plier. Ce chiffre ne vaut que
comme **ordre de grandeur du prochain pari**, et il devra être vérifié par un point mesuré.

## Ce que cela change pour le palier B1

Le critère d'arrêt de DS-14 vise à ne pas dépenser sur une idée qui ne bouge pas. **Celle-ci
bouge, régulièrement, et sans signe d'essoufflement.** Le verdict littéral du palier — le candidat
ne bat pas l'incumbent à 400 000 étiquettes — reste vrai et doit être publié tel quel. Mais la
raison d'être du critère n'est pas remplie ici : la donnée supplémentaire fait exactement ce
qu'on attendrait d'elle.

C'est une décision humaine, et elle se pose en ces termes : produire environ 2 millions
d'étiquettes de plus coûte à peu près une nuit sur les trois machines, au débit mesuré cette
nuit (34/s sur smith, 10/s sur mochy, 5/s sur melbaa). Le pari est borné, et son résultat est
publiable dans les deux sens.

## La lecture croisée avec le témoin de T72

Le même jour, six architectures distillées du réseau actuel ont été mesurées. À architecture
**identique** à l'original, apprise sur 800 000 positions étiquetées par le **0-ply** de ce même
réseau, la perte est **0,00990**. Ici, sur 800 000 positions étiquetées par notre **2-ply**, elle
est **0,00449**.

**Les étiquettes issues de la recherche valent 2,2 fois celles de l'évaluation statique**, à
volume et à architecture égaux. C'est la prémisse de T71 — la recherche met dans l'étiquette une
information que le réseau seul n'a pas — vérifiée par une comparaison directe que la fiche
n'avait pas prévue.

Cela corrige aussi une conclusion trop rapide écrite le matin même : le plafond de 0,00990 est
celui de la distillation **depuis le 0-ply**, pas celui de la distillation en général.

## Ce que cette courbe ne dit pas

Elle ne dit pas que l'élève dépassera l'incumbent, seulement où il croiserait son niveau si la loi
tenait. Or **égaler ne suffit pas** : le critère de succès de T71 est que l'intervalle 2-ply par
décision contre l'arbitre gnubg, aujourd'hui [−0,00005 ; +0,00019], se déplace au-dessus de zéro.
Un élève qui vaudrait exactement son maître ne l'aurait pas fait.

Elle ne dit rien non plus du coût en temps de décision, inchangé puisque l'architecture est
constante, ni de ce que donnerait une architecture différente — la fiche l'exclut explicitement.

## Reproduire

```
python tools/train_t71.py --labels build/t71-money --limit 800000 \
    --out models/t71_v800000.pt --bin models/t71_v800000.bin
python bench/measure_t70.py \
    --registry docs/corpus/t70/money-10000/registre-money.jsonl \
    --model models/t71_v800000.bin --ply 2 \
    --prune-model models/prune_32.bin --prune-k 12 --workers 30 \
    --out docs/mesures/t71_v800000-t70.json
```

Le sous-échantillonnage est **tiré au sort** à la graine de l'entraînement, jamais un préfixe : les
parts sont écrites worker par worker, et un préfixe mesurerait le volume **et** un biais de marche
sans qu'on sache lequel des deux bouge.
