# T21 — Banc de débit navigateur : le volet évaluation

**Date** : 2026-08-03 · **Machine** : bureau (piste B) · **Branche** : `t21-bench`

> **Rapport partiel.** T21 demande un verdict sur le **coût d'une décision**, qui suppose une
> recherche — T30, pas encore écrite. Ce document établit le coût d'une **évaluation**, qui en est
> l'atome, et la **pénalité WebAssembly**, qui était l'inconnue centrale du projet. Les coûts par
> décision cités plus bas sont des **projections à partir d'un nombre d'évaluations**, jamais des
> mesures, et sont marqués comme tels.

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

## Réserves

- **Mesures headless.** Le contrôle croisé en mode fenêtré reste à faire.
- **Une seule machine**, sur secteur, sans contrôle de la gouvernance de fréquence. Un Ryzen 7 PRO
  6850U est un processeur portable : un desktop de bureau ferait mieux, un vieux portable moins
  bien.
- **Rien sur iOS.** Voir T20.
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
  multiplication matricielle relirait les 2 Mio de poids une fois au lieu de vingt. **Hypothèse à
  mesurer**, pas un acquis — mais c'est le levier le plus prometteur, et il est gratuit en
  précision.

## Configuration

AMD Ryzen 7 PRO 6850U (16 fils), 14,4 Gio, pas de GPU, Linux 7.1.5-arch1-2. GCC 16.1.1,
Emscripten 6.0.5-git, Node 26.5.1, Chromium 150.0.7871.186, Firefox 153.0.1.

Reproductible : `make bench-infer` (natif) puis
`node wasm/harness.mjs --browser <chromium|firefox> --mode bench --build <scalar|simd>`.

Suite : **T30**, la recherche — sans laquelle le verdict de T21 reste partiel.
