# Le coût d'une **vraie** décision dans un navigateur

**Date** : 2026-08-04 · **Machine** : bureau (piste B) · **Branche** : `t21-wasm-search`

> **La dernière projection du projet devient une mesure.** T21 avait rendu son verdict en
> multipliant un débit d'évaluations *mesuré* par un nombre d'évaluations par décision — d'abord
> supposé, puis mesuré par T30. Les deux moitiés étaient solides ; leur **produit** restait une
> projection, parce qu'il supposait que rien d'autre ne coûte : ni la génération des coups, ni
> l'encodage, ni le parcours de l'arbre.
>
> La recherche est maintenant compilée en WebAssembly. Une décision entière est faite, et
> chronométrée.

## Le résultat

| Profondeur | Évaluations | **Chromium 150** | **Firefox 153** |
|---|---|---|---|
| 0-ply | 16 | 1,7 ms | 2,0 ms |
| 1-ply | 7 475 | 796,7 ms | 998 ms |
| **2-ply, filtre 1/1** | **12 951** | **1 393,6 ms** | 1 525 ms |

**L'accord avec le natif est exact** : même coup retenu, **même nombre d'évaluations**
(`sameEvaluationCount: true`), et une équité identique à `1e-5` près. La recherche du navigateur
n'est pas une approximation de celle du natif : c'est la même.

Le contrôle passe **avant** le chronomètre. Un débit mesuré sur un moteur qui répond faux ne vaut
rien, et c'est la troisième fois dans ce projet qu'un contrôle de justesse attrape ce qu'un
chronomètre aurait laissé passer.

## Le surcoût hors réseau : ×1,00

> ### ⚠️ Correction du 2026-08-04
>
> Ce rapport annonçait d'abord un surcoût de **×1,20**, obtenu en divisant le coût par évaluation
> à travers une décision (0,1076 ms) par celui mesuré nu en T21 (0,0898 ms). **Ces deux nombres
> viennent de deux exécutions et de deux builds différents** : celui de T21 ne contenait pas la
> recherche. Le comparer au nôtre mesurait la différence entre les deux binaires autant que le
> surcoût.

Mesuré **dans une seule exécution**, banc nu et décision l'un après l'autre sur le même build :

| | ms par évaluation |
|---|---|
| Banc d'évaluations nues | 0,0918 |
| À travers une décision 2-ply complète | 0,0919 |
| **Surcoût** | **×1,001** |

**La génération des coups, l'encodage et le parcours de l'arbre coûtent moins que le bruit de
mesure.** Le coût d'une décision est le nombre d'évaluations multiplié par le coût unitaire, et
rien d'autre — ce que T21 supposait, et qui se trouve vrai.

Le build contenant la recherche est en revanche ~2 % plus lent en évaluation nue que celui de T21
(10 899 contre 11 136 éval/s), ce qui est l'ordre de grandeur attendu pour un binaire deux fois
plus gros.

## La chaîne des corrections, de bout en bout

Un match de 7 points (~300 décisions) en 2-ply filtré 1/1, sur desktop :

| Estimation | Match | Ce qui a changé |
|---|---|---|
| T30 | 1,5 min | ÷4 workers supposés |
| T23 | 1,8 min | ÷3,3 workers mesurés |
| **Ici** | **~1,8 min** | décision réelle chronométrée, surcoût mesuré à ×1,00 |

Une seule des deux corrections envisagées a eu lieu : la mise à l'échelle des workers. Le surcoût
hors réseau, qu'on croyait valoir 20 %, est nul.

Sur les appareils mesurés en T21, en appliquant le surcoût de ×1,20 au coût par évaluation :

| | 2-ply 1/1, par décision | Match de 7 pts, 3,3 workers | avec le lot ×2,2 |
|---|---|---|---|
| iPhone (0,085 ms/éval) | 1,10 s | **~1,7 min** | **~45 s** |
| Chromium desktop | 1,19 s | ~1,8 min | ~49 s |
| Android le plus lent (0,329) | 4,26 s | ~6,5 min | ~2,9 min |

Le 2-ply tient. Les coûts par appareil restent transposés depuis le coût par évaluation mesuré en
T21 ; la page publiée permet de les mesurer directement, ce qui reste à faire.

---

## Un bug que seul WebAssembly pouvait révéler

La première exécution s'est arrêtée sur `memory access out of bounds`, **dès le 0-ply**. Avec
`-sASSERTIONS=2` et `-sSTACK_OVERFLOW_CHECK=2` :

```
Aborted(stack overflow — Attempt to set SP to 0xfffe29c0,
        with stack limits [0x0004eb90 - 0x0005eb90])
```

**Un débordement de pile, pas de tas.** La cause est une différence d'environnement, pas une
erreur de code :

| | pile par défaut |
|---|---|
| Natif (Linux) | **8 Mio** |
| **WebAssembly (Emscripten)** | **64 Kio** |

Deux tampons `static GN_THREAD_LOCAL` — `backend_plays[2048]` dans `gn_rules_reference.c` et
`plays[2048]` dans `gn_choose.c` — pèsent ensemble environ **190 Kio**. Emscripten place le
stockage local de thread du fil principal **dans la région de pile**, où ils ne tiennent pas.

Ce code est correct en natif et l'a toujours été. **La contrainte n'existe que sur la cible qui
compte**, et elle ne s'est manifestée qu'en y allant. Corrigé par `-sSTACK_SIZE=4194304` dans le
`Makefile` — quatre mégaoctets, avec de la marge, puisque ces tampons sont dimensionnés pour le
pire cas du générateur de coups.

**Ce qu'il faut en retenir au-delà de ce bug** : un tampon dimensionné pour une pile native est un
piège qui ne se déclenche que sur la cible embarquée, et **le seul symptôme est un plantage sans
rapport apparent avec sa cause**. T20 ne l'avait pas vu parce qu'il ne compilait que
l'évaluateur ; il a fallu y ajouter la recherche pour toucher ces tampons.

## Taille de l'artefact

| | avant (T20) | avec la recherche et la MET |
|---|---|---|
| `gammonnet-simd.wasm` | 19 290 | **39 904** |

Le moteur double, et **reste 2 % de la charge utile** : les poids pèsent toujours 2,06 Mio. La
conclusion de T20 est inchangée — optimiser la taille du moteur ne servirait à rien, seule la
quantification des poids compte, et le rapport sur la quantification a tranché en faveur du
float16.

## Ce qui n'est pas mesuré ici

- **Le surcoût est mesuré sur desktop.** Il y est nul ; rien ne dit qu'il l'est sur mobile, où
  l'allocation et le parcours mémoire peuvent peser autrement. La page publiée le mesure
  désormais.
- **Money seulement.** Le mode match est exposé par l'API WebAssembly mais n'a pas été chronométré ;
  il ajoute une consultation de table par nœud, négligeable devant une évaluation réseau, et cela
  aussi reste à confirmer plutôt qu'à affirmer.
- **Un seul jet, une seule position.** Le coût varie avec le nombre de coups légaux, dont T31 a
  mesuré que la queue est lourde : la pire décision de son corpus coûte neuf fois la médiane.

## Reproduire

```bash
make wasm
node wasm/harness.mjs --browser chromium --page /wasm/decision.html --build simd
```
