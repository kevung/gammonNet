# T21 — à refaire : les gains de vitesse ne se transportent pas dans le navigateur

**Date** : 2026-08-27 · **Statut** : **instrument prêt, mesure non faite** — elle demande une
machine où Emscripten est installé

> **Pourquoi cette fiche existe avant sa mesure.** Tous les gains de vitesse d'août viennent du
> **remplissage des lots** : fusionner les survivants des vingt-et-un jets pour que le noyau
> calcule trente-deux positions utiles au lieu de cinq. En natif cela rend ×6,6 au 2-ply.
>
> **Le lot ne rend pas la même chose dans un navigateur : ×2,21 mesuré par T21, contre ×8,5 en
> natif.** Le gain d'aujourd'hui y sera donc plus faible — de combien, personne ne le sait, et le
> calculer serait exactement l'extrapolation que la règle 3 de `CLAUDE.md` interdit.
>
> **Conséquence directe** : les budgets de temps proposés pour les préréglages navigateur
> (`docs/etudes/2026-08-26-parametrage-navigateur.md`) sont des **projections natives**. Publier un
> artefact en s'appuyant dessus, c'est publier un chiffre qu'on n'a pas mesuré.

## Ce qui est prêt

L'infrastructure de T21 existe et n'a pas bougé : serveur statique, navigateur lancé sur un profil
neuf, page qui renvoie son résultat. Ce qui a été ajouté aujourd'hui :

| | |
|---|---|
| `gnw_load_prune(bytes, length, k)` | charge le réseau d'élagage et fixe `k` ; `k <= 0` l'éteint et rend la recherche d'avant, bit pour bit |
| `gnw_prune_k()` | le `k` réellement en vigueur — la page **vérifie** qu'il est celui demandé |
| `Evaluator.loadPrune()` / `.pruneK()` | la même chose côté JavaScript, avec refus explicite |
| `decision.html` | deux configurations de plus : le point de fonctionnement T35 `(0,1,3)`, avec et sans élagage |

**`gn_wasm.c` compile maintenant sans Emscripten.** Il incluait `<emscripten.h>` sans garde, donc
ne se vérifiait que là où le WASM se construit — une faute de type y survivait jusqu'à ce poste.
Sous garde, `cc -c` le contrôle partout ; seule l'édition de liens WebAssembly reste propre à emcc,
et elle **n'a pas été vérifiée ici**.

## Les références natives, à retrouver dans le navigateur

Position `4HPwATDgc/ABMA`, jet 3-1. La page contrôle l'accord **avant** de chronométrer : un débit
mesuré sur un moteur qui répond faux ne vaut rien.

| configuration | équité | évals du grand réseau | coup |
|---|---|---|---|
| 2-ply `(0,1,3)`, sans élagage | 0,166899 | 38 721 | `sGfwATDgc/ABMA` |
| 2-ply `(0,1,3)`, élagage `k=12` | 0,166899 | 15 142 | `sGfwATDgc/ABMA` |

Le coup et l'équité sont les mêmes des deux côtés : à `k=12` l'élagage ne change pas cette
décision. Le compte d'évaluations, lui, doit différer — s'il ne diffère pas, l'élagage n'est pas
pris, et la page le refuse au lieu de chronométrer.

**Natif, pour comparaison** : 2,0075 s et 0,5588 s par décision, soit ×3,9.

## Comment la faire, sur la machine qui a Emscripten

```bash
git clone <ce dépôt> && cd gammonNet
make setup && make build            # natif : le repère
make wasm                           # scalaire et SIMD
make wasm-parity                    # l'accord AVANT tout chiffre de vitesse

node wasm/harness.mjs --browser chromium --mode decision --build simd
node wasm/harness.mjs --browser firefox  --mode decision --build simd
```

Puis, si un appareil mobile est disponible, la méthode qui a marché en août : publier la page
statique et l'ouvrir depuis le téléphone — le téléphone atteint internet, pas la machine de mesure.

## Ce que la mesure doit trancher

1. **Le gain de l'élagage dans un navigateur.** ×3,9 en natif ; ici, inconnu.
2. **Les budgets des préréglages.** « Normal » vise ~1 min par match ; à valider ou à corriger.
3. **Le mobile**, où la pénalité mesurée était de ×2,12 à ×2,83 — et où le lot compte le plus.

**Tant que 1 n'est pas mesuré, aucun budget de temps navigateur ne doit être publié.**
