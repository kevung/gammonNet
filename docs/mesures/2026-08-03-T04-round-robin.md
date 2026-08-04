# T04 — Le harnais de round-robin

**Date** : 2026-08-03 · **Machine** : la machine de calcul (voir [T00](2026-08-03-T00-socle.md)) ·
**Branche** : `t04-roundrobin`

> **Aucune force n'est mesurée ici.** On vérifie que **l'instrument est droit**. Un harnais faux
> ne se voit pas dans ses résultats : il rend des ppg parfaitement plausibles. D'où des
> contrôles qui portent sur ses **propriétés**, jamais sur ses valeurs.

## Le choix de conception : les dés dupliqués

Chaque paire de moteurs joue chaque séquence de dés **deux fois, sièges échangés**. Les mêmes
jets, dans l'autre sens.

Cela retire la principale source de variance — les dés eux-mêmes — et ne laisse que l'écart
entre les deux moteurs, seule chose qu'on cherche à mesurer.

Cela donne surtout au harnais son contrôle le plus tranchant. **Un moteur contre lui-même donne
exactement zéro**, pas zéro à l'intervalle près : les deux parties d'une paire sont la même
partie. Un écart signale un harnais faux, pas de la variance.

Le hasard des moteurs est attaché au **siège**, pas au moteur. C'est ce qui fait que le contrôle
nul rejoue vraiment la partie identique.

## Résultats — les quatre critères d'acceptation

### 1. Antisymétrie — ✅ résidu **exactement nul**

`ppg[A][B] == -ppg[B][A]`. **Les deux sens sont réellement joués**, aucune cellule n'est obtenue
en niant l'autre : cela coûte le double et c'est ce qui donne son sens au contrôle. Il vérifie
que l'appariement et la graine sont symétriques, au lieu d'affirmer une identité arithmétique
qu'on se serait imposée.

### 2. Contrôle nul — ✅ **exactement zéro**

Un moteur contre lui-même : `0.0` ppg, sur 200 paires vérifiées une par une, puis sur le résumé
complet, intervalle de confiance contenant zéro.

**Un cas voisin, découvert en écrivant les tests et devenu un test à part entière** : deux
`RandomEngine` portant des noms différents **ne sont pas deux joueurs différents**. Les dés
dupliqués et le hasard par siège les annulent exactement. Mon premier test d'antisymétrie les
opposait et vérifiait donc `0 == 0` — vide. Les tests d'antisymétrie, de sensibilité à la
graine, de largeur d'intervalle et de parallélisme utilisent désormais un moteur réellement
différent, et chacun vérifie explicitement que le résultat n'est pas nul.

### 3. Reproductibilité — ✅

Deux exécutions à graine identique rendent le même objet, au bit près. Une graine différente
rend un résultat différent — sans quoi la reproductibilité serait vide de sens. **Le nombre de
processus ne change rien** : les dés et le hasard de chaque partie dérivent de la graine et de
l'indice de partie, jamais de l'ordre d'exécution.

La dérivation n'utilise pas le `hash` de Python, qui est salé par processus : un harnais dont le
résultat dépendrait du processus qui l'exécute échouerait au critère de reproductibilité **de
façon intermittente**, ce qui est pire que d'y échouer franchement.

### 4. L'intervalle de confiance — ✅ jamais un chiffre nu

Bootstrap par percentiles, déterministe à graine donnée. Le rééchantillonnage porte sur les
**paires** et non sur les parties : les deux parties d'une paire partagent leurs dés et ne sont
pas indépendantes. Les traiter séparément resserrerait artificiellement l'intervalle — la
manière classique de faire paraître une mesure plus fine qu'elle n'est.

Vérifié aussi que l'intervalle **se resserre quand le volume augmente**, faute de quoi il ne
mesurerait rien.

## La matrice produite

3 moteurs, 400 paires par affrontement ordonné (800 parties), graine `20260803`, 16 processus :

```
                  random  first-play  gnubg-0ply
random                 —     -0.3287     -2.6925
first-play       +0.3287           —     -2.3125
gnubg-0ply       +2.6925     +2.3125           —
```

| Affrontement | ppg | IC 95 % | Victoires |
|---|---|---|---|
| random vs first-play | −0,3287 | [−0,4275 ; −0,2325] | 38,5 % |
| random vs gnubg-0ply | −2,6925 | [−2,7287 ; −2,6562] | 0,0 % |
| first-play vs gnubg-0ply | −2,3125 | [−2,3500 ; −2,2738] | 0,1 % |

**Résidu d'antisymétrie maximal : 0,000e+00.**

**4 800 parties en 12,2 s, soit 394 parties/s** sur 16 processus, l'oracle 0-ply étant de loin
le poste coûteux.

Ce tableau ne dit **rien** de la force de gammonNet, qui n'évalue encore rien (T10). Il ne
montre pas non plus de non-transitivité — attendu, avec des écarts aussi grands. C'est
l'instrument, pas la mesure.

## Ce que le harnais ne fait pas encore, et pourquoi

**Parties d'argent sans videau uniquement.** Le videau est T34 et l'équité de match est T32 ;
ni l'un ni l'autre n'existe. Les coutures sont en place, mais rien ne fait semblant de doubler.
Bâtir un mode cubeful sur un modèle de videau non écrit produirait des nombres qui
ressembleraient à des mesures.

**Parallélisation par processus, jamais par fils.** `gnubg-nn` garde le score de match et le
videau dans des globales de processus et n'est pas sûr en multi-thread (T03). Deux fils
évalueraient silencieusement au score l'un de l'autre — résultats plausibles, mesure fausse.

**Les parties trop longues sont abandonnées** à 10 000 coups et **comptées comme telles** dans
le rapport, jamais silencieusement converties en nulles.

## Le volume dont il faudra disposer

`BRIEF.md` §5 le rappelle : en dessous d'environ **1 M de parties par paire**, les écarts entre
bons moteurs ne sortent pas du bruit. Les 800 parties ci-dessus suffisent à séparer un oracle
d'un joueur aléatoire, et ne sépareraient pas deux bons moteurs. **T05** doit chiffrer la durée
réelle d'un round-robin d'un million de parties ; c'est lui qui dira si T11 est un travail
d'heures ou de jours.
