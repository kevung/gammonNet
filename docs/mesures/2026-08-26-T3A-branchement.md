# T3A branché — le réseau d'élagage dans la recherche, et ce qu'il rapporte vraiment

**Date** : 2026-08-26 · **Machine** : la machine de calcul · **Branche** : `t3a-branchement`

> ⚠️ **Le verdict de cette fiche est périmé — voir
> [`2026-08-26-T3A-regroupement.md`](2026-08-26-T3A-regroupement.md).** Elle conclut « ne pas
> activer » parce que le gain (×1,36) ne dépendait pas de `k`. La cause du plafond a été trouvée
> depuis : le noyau calcule 32 voies quoi qu'il arrive, et l'élagage vidait les lots du grand
> réseau au lieu de les supprimer. Lots remplis, le gain passe à **×3,9 à ×9,3** et dépend de `k`.
> **Les mesures de cette fiche restent exactes** ; c'est la conclusion qu'on en tirait qui ne l'est
> plus.

> **La question.** La fiche du 2026-08-07 a construit le petit réseau et l'a mesuré **au tri** :
> 92,5× moins cher par évaluation, top-1 du grand dans son top-5 dans 94,2 % des décisions de
> contact. Elle en tirait une **projection** — ×4,3 sur la facture à `k=5` — en la marquant comme
> telle et en nommant les trois suppositions qu'elle faisait. Cette fiche le branche dans
> `gn_search` et le mesure dans la vraie recherche.
>
> **La réponse.** Le mécanisme marche : la facture d'évaluations du grand réseau baisse
> **jusqu'à ×12,2 — mesuré**, au-delà de la projection. Mais **le temps par décision ne baisse
> que de ×1,33 à ×1,36, et ce chiffre ne dépend presque pas de `k`.** La projection supposait que
> le temps suivait la facture. Il ne la suit pas, et cette fiche mesure pourquoi : à ce point de
> fonctionnement, **les évaluations du grand réseau ne sont plus ce qui borne une décision.**

## Le résultat

Recherche 2-ply, filtre `(0,1,3)` — le point de fonctionnement de la campagne T35, donc le seul
dont le coût soit publié. 300 décisions de contact et 150 de course, graine 20260826 (distincte
de celle du corpus de distillation : mesurer le petit réseau sur les positions qui l'ont entraîné
mesurerait sa mémoire). 26 ouvriers, build par défaut `-O2`.

**Contact** — 300 décisions, 20,4 coups légaux en moyenne. Sans élagage : **3,135 s/décision,
31 391 évaluations du grand réseau**.

| `k` | s/déc. | grand | petit | ×temps | ×évals | accord | perte/déc. | IC 95 % |
|---|---|---|---|---|---|---|---|---|
| 2 | 2,362 | 2 579 | 31 089 | **×1,33** | ×12,17 | 79,3 % | +0,00406 | [+0,00245 ; +0,00608] |
| 3 | 2,348 | 3 732 | 30 959 | ×1,33 | ×8,41 | 80,0 % | +0,00389 | [+0,00232 ; +0,00585] |
| 5 | 2,337 | 5 874 | 30 802 | ×1,34 | ×5,34 | 90,7 % | +0,00182 | [+0,00061 ; +0,00353] |
| 8 | 2,323 | 8 761 | 29 830 | ×1,35 | ×3,58 | 96,3 % | +0,00031 | [+0,00002 ; +0,00083] |
| **12** | 2,301 | 12 061 | 27 973 | **×1,36** | ×2,60 | **98,3 %** | **+0,00023** | **[−0,00000 ; +0,00067]** |

**Course** — 150 décisions, 17,8 coups légaux. Sans élagage : **2,629 s/décision, 19 994
évaluations**.

| `k` | s/déc. | grand | petit | ×temps | ×évals | accord | perte/déc. | IC 95 % |
|---|---|---|---|---|---|---|---|---|
| 2 | 2,212 | 2 299 | 19 592 | ×1,19 | ×8,70 | 70,0 % | +0,00175 | [+0,00093 ; +0,00271] |
| 3 | 2,200 | 3 240 | 19 293 | ×1,20 | ×6,17 | 70,7 % | +0,00162 | [+0,00084 ; +0,00250] |
| 5 | 2,183 | 4 864 | 18 758 | ×1,20 | ×4,11 | 77,3 % | +0,00126 | [+0,00060 ; +0,00207] |
| 8 | 2,143 | 6 850 | 18 080 | ×1,23 | ×2,92 | 84,0 % | +0,00085 | [+0,00028 ; +0,00159] |
| 12 | 2,094 | 8 923 | 16 276 | ×1,26 | ×2,24 | 91,3 % | +0,00023 | [+0,00006 ; +0,00046] |

L'arbitre est la recherche **non élaguée** elle-même : l'élagage est une approximation d'elle, et
la question est ce que l'approximation coûte. Les deux coups en désaccord sont évalués à la
profondeur de la référence, par le calcul même qui les aurait départagés dans la passe profonde.
Cette fiche ne dit pas si la recherche non élaguée a raison ; ce n'est pas sa question.

## Le fait qui commande tout le reste

**De `k=2` à `k=12`, les évaluations du grand réseau varient d'un facteur 4,7 et le temps par
décision de moins de 3 %.** En contact, `k=12` fait *plus* d'évaluations chères que `k=2` et
s'exécute pourtant *plus vite*. Aucun modèle de coût n'est nécessaire pour lire cela : à
l'intérieur d'une seule mesure, la facture d'évaluations et le temps ne sont pas liés.

Le gain réel — ×1,33 en contact — vient du **changement de structure** (remplacer la passe
superficielle du grand réseau par celle du petit), et il **sature immédiatement**. Élaguer plus
fort ne rapporte rien de plus et coûte de la qualité : c'est le pire côté d'un compromis.

**Ce que cela corrige.** `PLAN.md` (2026-08-04) affirme : *« Notre moteur est ~330 fois plus lent
que gnubg au 2-ply. 3,29 s contre ~10 ms, entièrement expliqué par 38 244 évaluations à 86 µs —
pas de gaspillage caché. »* Cette comptabilité était juste **avant l'inférence par lot**. Le lot a
rendu une évaluation ~8,5× moins chère, et la conclusion « pas de gaspillage caché » n'y a pas
survécu : ce qui reste d'une décision, une fois les évaluations rendues bon marché, est la
génération des coups légaux, les copies de positions, les tris et la récursion. Ce n'est plus
minoritaire, et c'est désormais **ce qui borne une décision**.

## Pourquoi la projection s'est trompée — deux mesures, dans l'ordre où elles sont tombées

**1. Ce n'est pas l'encodage.** Première hypothèse, et fausse : le petit réseau paierait un coût
fixe d'encodage que le ratio de T3A excluait. Mesuré (`make bench-encoding`, 20 000 positions de
vraie partie) : **0,00037 ms**, négligeable pour les deux réseaux.

**2. C'est le traitement par lot.** Le même banc, sur le chemin que la recherche emprunte
réellement :

| | scalaire | par lot | |
|---|---|---|---|
| grand réseau | 0,35026 ms | **0,04119 ms** | ×8,5 plus rapide |
| petit réseau | 0,00426 ms | 0,00641 ms | ×1,5 plus **lent** |

Le lot amortit la lecture des poids : 2 Mio pour le grand, 25 Kio pour le petit — qui ne quittent
jamais le cache et n'ont donc rien à amortir. **Le ×92,5 de T3A a été mesuré sur le chemin
scalaire** (`bench_infer.c` le dit : l'encodage y est exclu, et le chemin y est scalaire). Sur le
chemin par lot, l'écart tombe à **×6,4**. Les deux optimisations de T3A — l'inférence par lot et
le réseau d'élagage — attaquent le même coût et s'annulent en grande partie.

**Un corollaire, et une leçon.** Ce constat suggérait d'écrire la passe d'élagage en scalaire.
Mesurée **dans la recherche**, à comptes d'évaluations identiques (48 décisions de contact,
8 ouvriers, `k=5`), la variante scalaire est **plus lente** : 1,720 s contre 1,582 s par décision.
Le micro-banc isolé a prédit le mauvais sens. C'est la deuxième fois dans cette fiche qu'un
chiffre par évaluation ne survit pas au contact de la vraie recherche ; le code porte la
remarque.

## Ce qui est branché, et les trois pièges traités

- **Éteint par défaut.** `prune_k = 0` laisse la recherche **bit pour bit** identique. Les 1 448
  tests existants passent inchangés, corpus de non-régression T12 compris. Ce mécanisme change ce
  que le moteur joue : il se choisit, il ne s'active pas tout seul.
- **Le cache d'évaluation reste neutre.** La passe d'élagage n'a droit qu'à la table exacte,
  jamais au cache. Un candidat noté par le *grand* réseau quand le cache le contient et par le
  *petit* sinon rendrait le classement — donc le coup joué — dépendant de l'historique
  d'évaluation. C'est exactement la propriété qui permet à une campagne T35 d'être segmentée,
  interrompue et reprise en restant identique à un run d'une traite.
- **Le cache n'est jamais écrit par le petit réseau.** Une seule de ses distributions stockée
  serait servie comme celle du grand pour le reste du processus, à toutes les recherches
  suivantes, sans un signe.
- **Le filtre reste respecté.** `prune_k` est relevé à `filter[depth]` quand il est plus petit.
- **La recherche élaguée ne rend que les survivants.** Les recalés portent les probabilités du
  petit réseau, et cinq nombres plausibles venus du mauvais réseau ne sortent pas d'ici.

Compteur `gn_search_prune_evaluations` séparé : tous les coûts publiés par ce projet sont en
évaluations du grand réseau, et confondre deux unités distantes d'un facteur 6 à 92 selon le
chemin les rendrait toutes incomparables.

## Le verdict, et ce qu'il faut en faire

**Ne pas l'activer par défaut en l'état.** Le seul réglage défendable est `k=12`, où la perte est
dans le bruit en contact (+0,00023 [−0,00000 ; +0,00067]) — et il rend ×1,36. Tous les `k` plus
serrés achètent la même vitesse en payant de la qualité : à `k=5` la perte devient significative
(+0,00182 [+0,00061 ; +0,00353]) pour ×1,34, c'est-à-dire pour rien.

**L'échelle de la perte, pour la situer** : T36 a mesuré ce qu'un ply entier de profondeur
supplémentaire rapporte — **+0,00022 d'équité par décision**. La perte de `k=12` est du même ordre.
Autrement dit, le réglage le plus prudent de l'élagage coûte à peu près ce qu'un ply rapporte.

**La course est le point faible**, comme T3A l'annonçait (rappel top-5 de 83,6 % contre 94,2 %) :
à `k=5` l'accord n'est que de 77,3 %, et il faut `k=12` pour atteindre 91,3 %. Un `k` par terrain
— ou pas d'élagage du tout en course — serait à mesurer avant tout usage.

**Ce que cette fiche redirige.** T3A visait à fermer l'écart de vitesse ×330 avec gnubg. Le
réseau d'élagage n'y parvient pas, et la mesure dit maintenant pourquoi : **l'essentiel d'une
décision n'est plus du réseau**. Le prochain levier de vitesse n'est pas un réseau plus petit,
c'est la recherche elle-même — génération des coups légaux, copies, tris, récursion. Ce n'est pas
mesuré ici, et c'est la fiche suivante.

## Ce que cette fiche ne mesure pas

- **La force réelle.** La perte est chiffrée en équité par décision contre la recherche non
  élaguée, pas en ppg ni en MWC. Une partie n'est pas la somme de ses décisions vues isolément.
  Un round-robin élagué contre non élagué le dirait ; il n'a pas tourné.
- **Le build de campagne.** Tout est mesuré sur `-O2` par défaut. `NATIVE_FP=1` change les temps
  absolus ; les rapports mesurés ici sont internes à un même build, mais leur valeur sous
  `NATIVE_FP` n'a pas été vérifiée.
- **Le navigateur.** Le lot y a été mesuré à ×2,21, pas ×8,5. L'équilibre entre réseau et
  recherche y est donc différent, et le verdict de cette fiche ne s'y transporte pas.
- **Un `k` par profondeur ou par terrain.** Un seul `k` s'applique partout ici.

## Reproduire

```bash
make bench-encoding          # le coût d'une évaluation pour une RECHERCHE
python bench/prune_search.py --contact 300 --race 150 --ks 2,3,5,8,12 --workers 26
```

Sortie : [`t3a-prune-search.json`](t3a-prune-search.json).
