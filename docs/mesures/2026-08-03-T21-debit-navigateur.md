# T21 — Banc de débit navigateur : le volet évaluation

**Date** : 2026-08-03 · **Machine** : bureau (piste B) + un Android réel · **Branches** :
`t21-bench`, `t21-verdict`

> **Rapport partiel.** T21 demande un verdict sur le **coût d'une décision**, qui suppose une
> recherche — T30, pas encore écrite. Ce document établit le coût d'une **évaluation**, qui en est
> l'atome, et la **pénalité WebAssembly**, qui était l'inconnue centrale du projet. Les coûts par
> décision cités plus bas sont des **projections à partir d'un nombre d'évaluations**, jamais des
> mesures, et sont marqués comme tels.
>
> **Deux ajouts du même jour**, après la première rédaction :
> - Le volet mobile, annoncé plus bas comme impossible faute d'appareil, a été **mesuré sur un
>   Android réel**. Le seuil réfutable que ce rapport publiait d'avance a été **confronté et
>   confirmé**. Voir *Le mobile, mesuré*.
> - Le traitement par lot, cité comme « hypothèse à mesurer », a été **mesuré** : ×2,21, exact au
>   bit près. Voir *Le lot, mesuré*.

## Le chiffre que le projet attendait

> **La pénalité WebAssembly est de ×1,18 à ×1,29. L'hypothèse de travail ×1,5 à ×2,5 est
> infirmée.**

Mesurée sur la **même machine**, contre une ligne de base **native en C** — pas via la liaison
Python, dont T05 a montré qu'elle coûte un facteur dix, et qui aurait fait mesurer ctypes plutôt
que le navigateur.

| | éval/s | ms/éval | Pénalité |
|---|---|---|---|
| **Natif** (C, `-O3` + réassociation) | **13 143** | 0,0761 | — |
| **Chromium 150, SIMD** | **11 136** | **0,0898** | **×1,18** |
| **Firefox 153, SIMD** | **10 204** | 0,0980 | **×1,29** |

Corpus : 2 000 vecteurs déjà encodés, médiane de 11 répétitions, un tour à blanc écarté.
L'encodage est hors de la zone chronométrée des **deux** côtés — le comparer chronométré d'un côté
et non de l'autre est la façon dont on invente une pénalité au lieu de la mesurer.

## Le second résultat : la passe avant laissait un facteur 4 sur la table

Le débit initial était de **3 279 éval/s en natif**, soit 0,305 ms par évaluation — un chiffre
étonnamment bas pour 528 389 MACs. La cause est dans `nn_eval.c:184` :

```c
for (int j = 0; j < cols; j++) {
    sum += w_row[j] * in[j];
}
```

**Un accumulateur unique.** L'addition flottante n'étant pas associative, le compilateur n'a le
droit ni de dérouler cette boucle en plusieurs accumulateurs ni de la vectoriser : elle avance au
rythme de la latence de l'addition, soit environ un MAC tous les quatre cycles. Ce qui explique
aussi pourquoi `-O2`, `-O3` et `-march=native` donnaient **3 279 / 3 277 / 3 378** — le drapeau
n'y pouvait rien, c'est la sémantique qui bloquait.

Lever l'interdiction :

| Configuration | natif éval/s | gain |
|---|---|---|
| `-O3` | 3 218 | — |
| `-O3` + **réassociation sûre** | **13 143** | **×4,1** |
| `-O3 -ffast-math` | 13 314 | ×4,1 |
| `-O3 -ffast-math -march=native` | 32 699 | ×10,2 |

Et côté navigateur, le SIMD ne servait à rien **tant que la réassociation était interdite** — il
n'y avait rien à vectoriser :

| Chromium | sans réassociation | avec |
|---|---|---|
| build scalaire | 2 907 | 2 872 |
| build SIMD | 2 889 | **11 136** |

Le build SIMD de T20 pesait 10 octets de plus que le scalaire et rendait des résultats
identiques ; on sait maintenant pourquoi, et ce que ça cachait.

### Pourquoi pas `-ffast-math`

`-ffast-math` rend 13 314 éval/s contre 13 143 pour le sous-ensemble retenu — **1,3 % de plus**.
Il ajoute en échange `-ffinite-math-only`, c'est-à-dire la promesse qu'aucun infini n'apparaîtra.

Or la sigmoïde du réseau est `1/(1 + expf(-x))`, et sur une position saturée `expf(-x)` **déborde
vers l'infini par conception** — c'est ainsi qu'elle rend 0. Le corpus en contient : T10 a
documenté une position à `P(gain) = 1,5e-10`. Promettre au compilateur qu'il n'y aura pas
d'infini serait donc un mensonge, pour 1,3 %.

Retenu, et fixé dans le `Makefile` sous `FP_RELAXED` :

```
-fassociative-math -fno-signed-zeros -fno-trapping-math -fno-math-errno
```

### Ce que la réassociation coûte, mesuré

La parité WebAssembly ↔ natif **n'est plus au bit près** : elle passe de `0.000e+0` à
**`4,768e-7`**, sous le seuil de `1e-6` de T20. Les builds scalaires restent exacts au bit près.
L'ordre des sommes change, le résultat pratiquement pas — mais ce n'est plus gratuit, et c'est
consigné.

## Ce que ça donne, en projection — **et ce n'en est pas la mesure**

> **Attention.** Les lignes qui suivent multiplient un coût d'évaluation **mesuré** par un nombre
> d'évaluations **supposé**. La recherche n'existe pas encore (T30) et le filtre de coups non plus
> (T31). Ce sont des ordres de grandeur pour savoir où l'on met les pieds, pas un verdict.

En prenant ~20 coups légaux en moyenne et le coût Chromium de 0,0898 ms :

| Profondeur | Évaluations/décision *(supposées)* | Coût projeté | `BRIEF.md` §6 |
|---|---|---|---|
| 0-ply | ~20 | ~1,8 ms | ~0,1 ms |
| 2-ply **non filtré** | 20 × 21 × 20 ≈ 8 400 | ~0,75 s | — |
| 2-ply **filtré à 8** | 8 × 21 × 20 ≈ 3 360 | ~0,30 s | 245 ms |

Un match de 7 points (~300 décisions) en 2-ply filtré tomberait vers **90 s en mono-fil**, ou
**~23 s sur 4 workers** — dans la fourchette de 30 à 60 s qu'annonçait le `BRIEF`. **Le 2-ply
semble tenir sur desktop.** Le mot *semble* est là parce que T30 n'existe pas.

Le 0-ply reste ~18× plus cher que l'extrapolation du `BRIEF`. L'écart s'explique : les chiffres
publiés par HedgeHog viennent d'un moteur **NNUE à accumulation incrémentale** avec filtre de
coups actif, pas d'un GEMV dense recalculé intégralement. Ce n'est pas le même calcul.

## Le seuil falsifiable, à confronter à un vrai téléphone

Aucun appareil mobile n'est disponible (`PLAN.md` § *Répartition entre machines*). Plutôt qu'une
extrapolation — que la règle n° 3 interdit — voici la **prédiction réfutable** que T21 publie :

> Sur desktop, une décision 2-ply filtrée coûte **~0,30 s** *(projection)*. Un match de 7 points
> tient en **~23 s sur 4 workers**. Pour qu'un match dépasse **5 minutes** sur mobile — le seuil
> au-delà duquel l'usage interactif ne tient plus — il faudrait une pénalité mobile de **×13**.
>
> **C'est ce facteur 13 qu'un vrai téléphone viendra confirmer ou infirmer.** Un écart typique
> desktop/mobile se situe plutôt entre ×3 et ×6, ce qui laisserait le 2-ply praticable — mais
> **cette dernière phrase est une opinion, pas une mesure**, et c'est précisément ce qu'il faut
> aller vérifier.

Une porte est ouverte pour le faire sans câble ni réseau local : publier la page de banc en
statique et l'ouvrir sur le téléphone via sa propre connexion. Le téléphone n'a pas besoin
d'atteindre le PC, seulement internet.

## Le mobile, mesuré — le seuil est confronté et confirmé

La section précédente publiait un seuil réfutable faute d'appareil. Un Android a été trouvé, et la
page de banc publiée en statique (<https://kevung.github.io/gammonNet/>) a permis de le mesurer
**sans réseau local ni câble** : le téléphone n'atteint pas la machine de mesure, il atteint
internet.

| | éval/s | ms/éval | Écart au repère natif | Pénalité |
|---|---|---|---|---|
| Firefox 153 **desktop** | 10 204 | 0,0980 | 4,77e-7 ✅ | — |
| **Firefox 153, Android 16, 8 cœurs** | **4 819** | 0,2075 | **4,77e-7 ✅** | **×2,12** |
| **Firefox 152, Android 14, 8 cœurs** | **3 604** | 0,2775 | **4,77e-7 ✅** | **×2,83** |

> ### La pénalité mobile est de **×2,12 à ×2,83**, sur deux appareils.
> Le seuil publié était : *« il faudrait une pénalité de ×13 pour qu'un match dépasse cinq
> minutes »*. **Mesuré ×2,12 à ×2,83 — la prédiction est confirmée, avec une marge de 4,6 à 6,1.**

L'écart entre les deux téléphones est de ×1,34 : **la dispersion entre appareils est plus faible
que la marge au seuil**. Il faudrait un appareil cinq fois plus lent que le plus lent des deux
pour que le 2-ply cesse de tenir.

### Le résultat qui n'est pas le débit

La colonne de droite porte **exactement le même nombre** sur les trois plateformes — x86-64 sous
Linux, Android 14, Android 16 — soit trois architectures de processeur différentes. Le moteur ne
dérive pas en changeant de machine.

Ce n'est pas un hasard : WebAssembly impose la sémantique IEEE-754 stricte, là où du code natif
s'autoriserait des largeurs de registre ou des contractions différentes d'une cible à l'autre. Le
savoir et le constater sur trois appareils sont deux choses ; c'est constaté.

**La conséquence dépasse la vérification.** Une analyse produite sur téléphone est *identique* à
celle produite sur ordinateur — pas « à peu près », au bit près. Pour un projet dont la raison
d'être est de produire des chiffres qu'on cite et qu'on peut reproduire, c'est une propriété à
garantir explicitement plutôt qu'à découvrir.

**Projections sur ces appareils** *(mêmes hypothèses de recherche que plus haut, donc toujours pas
une mesure)* : une décision 2-ply filtrée à **697 ms** (Android 16) et **932 ms** (Android 14),
un match de 7 points à **~52 s** et **~70 s** sur 4 workers.

**Un signal à ne pas perdre** : les répétitions s'étalent de 79 à 118 ms sur le premier appareil
(facteur 1,5) et de **58 à 95 ms** sur le second (facteur **1,64**), là où le desktop varie de
quelques pour cent. C'est la signature d'un ajustement de fréquence ou d'un échauffement, et elle
**s'aggrave avec la performance de crête**. Sur le second appareil, retenir le meilleur passage
plutôt que la médiane ferait annoncer 6 900 éval/s au lieu de 4 819 — soit 43 % de trop. La
médiane est le bon choix, et sur une analyse soutenue c'est même le haut de la fourchette qu'il
faudrait retenir : un match complet est un travail continu, pas une rafale.

## Le lot, mesuré — ×2,21, exact au bit près

Le rapport citait le lot comme « hypothèse à mesurer, pas un acquis ». Mesuré par
`bench/bench_batch.c`, à drapeaux identiques :

| Lot | éval/s | vs ligne de base | Écart au repère |
|---|---|---|---|
| **1** *(ligne de base réelle)* | **13 550** | — | — |
| 8 | 9 208 | 0,68× | `0` |
| 16 | 17 872 | 1,32× | `0` |
| **32** | **29 942** | **×2,21** | **`0`** |

**L'hypothèse de la bande passante était la bonne.** On relisait 2,0 Mio de poids par évaluation,
soit ~27,6 Gio/s de trafic ; on les relit maintenant une fois pour trente-deux.

**Et c'est gratuit en justesse** : en conservant l'ordre de sommation de chaque sortie, le
résultat est **identique au bit près**, vérifié sur les 2 000 positions du repère. Ce n'est pas
une tolérance, c'est une égalité.

Deux mises en garde :

- **Le banc affiche en interne un « ×24,89 » qu'il ne faut pas citer.** Son lot = 1 traverse le
  code générique avec transposition, un épouvantail à 1 203 éval/s. Comparé au vrai chemin
  optimisé, le gain est **×2,21**.
- **Le lot de 8 est plus lent que la ligne de base.** Le surcoût de transposition n'est amorti
  qu'à partir de 16. Or une recherche a naturellement ~20 coups frères : on est au bon endroit,
  mais **sans marge**. Un filtre de coups agressif (T31) réduirait la largeur et pourrait annuler
  le bénéfice — les deux optimisations se disputent la même ressource, et T30/T31 devront les
  arbitrer ensemble plutôt que séparément.

### Ce qui reste, et ce qui est écarté

| Levier | Gain | Justesse |
|---|---|---|
| **Lot** | **×2,21 mesuré** | **exact au bit près** |
| Dévirtualiser l'activation — 1 408 appels indirects par évaluation | quelques % *(non mesuré)* | exact |
| Parcimonie de l'entrée, accumulation incrémentale | **plafonné à 19 %** | exact |
| Quantification int8 | ×4 sur le trafic ; le modèle passerait de 2,0 Mio à ~530 Kio | **concession — écartée** |

Le plafond de 19 % mérite d'être souligné parce qu'il contredit un réflexe : **l'accumulation
incrémentale de HedgeHog ne rapporterait au mieux que 19 % sur ce réseau**, puisque c'est tout ce
que pèse la couche d'entrée dans les 528 389 MACs. Copier leur architecture pour la vitesse serait
un contresens ici — ce qui rejoint la correction apportée au `BRIEF.md` §3.2.

**Cumul plausible** : ×4,1 acquis par la réassociation, ×2,2 par le lot, soit **×9 depuis le point
de départ**. Sur l'Android mesuré, cela donnerait ~7 900 éval/s, une décision 2-ply vers 420 ms, un
match vers **32 s sur 4 workers**. *Projection d'une projection : ni la recherche ni les workers
n'existent.*

## Réserves

- **Mesures headless.** Le contrôle croisé en mode fenêtré reste à faire.
- **Une seule machine**, sur secteur, sans contrôle de la gouvernance de fréquence. Un Ryzen 7 PRO
  6850U est un processeur portable : un desktop de bureau ferait mieux, un vieux portable moins
  bien.
- **Rien sur iOS.** Voir T20. Le mobile mesuré est un Android sous Firefox ; **la plateforme
  WebKit reste entièrement non couverte**, et c'est celle où les limites mordent le plus.
- **Deux appareils mobiles, un seul moteur de navigateur.** Les deux tournent sous Firefox, donc
  sous Gecko. **Blink sur mobile** — Chrome sur Android — n'est pas couvert, et c'est le
  complément le moins cher qui reste : la même page, dans un autre navigateur, sur les mêmes
  appareils. Un téléphone d'entrée de gamme ou plus ancien reste également non représenté.
- **Rien sur les Web Workers** — T23. Le « /4 workers » ci-dessus suppose une mise à l'échelle
  linéaire, qui n'est pas vérifiée.

## Ce que ça ouvre pour T22

La question du moteur d'inférence se pose maintenant sur des chiffres :

- Une passe avant **écrite** pour être vectorisée, plutôt qu'autorisée à l'être, devrait faire
  mieux que ×4. Le natif avec AVX (`-march=native`) atteint **32 699 éval/s**, soit ×10 — le SIMD
  de WebAssembly est en 128 bits là où AVX2 est en 256, donc une part de cet écart est
  structurelle, mais pas toute.
- **Le lot n'est pas exploité.** `gnw_evaluate_batch` boucle sur des évaluations unitaires. Or une
  recherche évalue naturellement ~20 coups frères d'un coup : les traiter comme une seule
  multiplication matricielle relirait les 2 Mio de poids une fois au lieu de vingt.
  **→ Mesuré depuis : ×2,21, exact au bit près. Voir *Le lot, mesuré*.**

## Configuration

AMD Ryzen 7 PRO 6850U (16 fils), 14,4 Gio, pas de GPU, Linux 7.1.5-arch1-2. GCC 16.1.1,
Emscripten 6.0.5-git, Node 26.5.1, Chromium 150.0.7871.186, Firefox 153.0.1.

Reproductible : `make bench-infer` (natif) puis
`node wasm/harness.mjs --browser <chromium|firefox> --mode bench --build <scalar|simd>`.

## ⚠️ Correction — la projection par décision de ce rapport était fausse

**T30 a mesuré ce que ce rapport supposait, et le compte était décalé d'un cran de profondeur.**

La formule employée ici — `8 × 21 × 20 ≈ 3 360` évaluations pour une décision 2-ply filtrée —
décrit en réalité un **1-ply**. Mesuré depuis : une décision **1-ply** coûte **7 475** évaluations,
et le 2-ply le plus serré (filtre 1/1) en coûte **12 951**. Les configurations de filtre moins
agressives montent à **211 941**.

Ce qui suit dans ce rapport reste valide : **les coûts par évaluation et la pénalité WebAssembly
sont des mesures directes**, indépendantes du compte d'évaluations. C'est leur multiplication par
un nombre supposé qui était fausse.

Le détail, les comptes réels et les trois autres corrections sont dans
[T30](2026-08-03-T30-recherche.md).

## Verdict

**Sur desktop et sur l'Android mesuré, le 2-ply tient.** Les deux inconnues qui pesaient sur la
cible du projet sont chiffrées : pénalité WebAssembly **×1,18 à ×1,29**, pénalité mobile
**×2,83** — l'une et l'autre bien en deçà de ce qui était redouté.

Ce verdict porte sur le **coût d'une évaluation**, mesuré, et sur un **coût de décision projeté**
à partir d'un nombre d'évaluations supposé. Il devient définitif quand T30 remplace cette
supposition par un compte réel. Il ne dit rien d'iOS.

Suite : **T30**, la recherche.
