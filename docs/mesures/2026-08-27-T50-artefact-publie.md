# T50 — l'artefact est complet, et chacune de ses cinq conditions est vérifiée

**Date** : 2026-08-27 · **Version** : `v1` · **Branche** : `main`

> **Ce que T50 exige.** Cinq conditions, et `PLAN.md` en fait des conditions, pas des intentions.
> `tools/package_artifact.py` les traite comme telles : il **refuse** de produire un répertoire
> incomplet plutôt que d'en produire un qui aurait l'air fini. Cette fiche les reprend une par une
> avec ce qui les satisfait.

## Les cinq conditions

| Condition | État |
|---|---|
| Poids versionnés, `.wasm` correspondant, somme de contrôle | **✅** — quatre fichiers de poids, quatre modules WebAssembly, `SHA256SUMS` |
| La version publiée rejoue le corpus de non-régression T12 **sans écart** | **✅** — vérifié *avant* d'écrire quoi que ce soit ; le script s'arrête sinon |
| `THIRD-PARTY.md` à jour et notice MIT **dans** l'artefact | **✅** — `NOTICE` porte le texte MIT complet d'Alexander Strehl et l'attribution à Neil Kazaross |
| Nomenclature du `BRIEF` §8 respectée | **✅** — les poids portent `strehl-prob5-512-512-256-128` ; gammonNet nomme la configuration |
| Notes de version citant protocole, volume et intervalle | **✅** — T35, T3E et T3C, repris des fiches |

## Ce que contient `dist/gammonnet-v1`

| fichier | octets |
|---|---|
| `strehl-prob5-512-512-256-128_v1_2026-08-27.bin` | 2 113 592 |
| `strehl-prob5-512-512-256-128_v1_2026-08-27.bin16` | **1 059 640** |
| `strehl-prune-32_v1_2026-08-27.bin` | 25 900 |
| `strehl-prune-32_v1_2026-08-27.bin16` | 13 036 |
| `gammonnet.wasm` / `.mjs` | 56 334 / 61 953 |
| `gammonnet-simd.wasm` / `.mjs` | 64 941 / 61 963 |
| `NOTICE`, `RELEASE.md`, `THIRD-PARTY.md`, `LICENSE`, `SHA256SUMS` | — |

**La traçabilité est vérifiable** : le `sha256` des poids float32 publiés est
`8a68bf30cfde01366c914d9700e6e0e654967ea36c14f2575d6828237d25a601`, **exactement** celui que
`models/cubeless_prob5_512_512_256_128.provenance.json` enregistre depuis le premier jour.

**L'artefact a été rechargé et évalué** depuis le répertoire publié : float32 rend
`0,5135871767997742`, float16 `0,5135868191719055` — écart 3,6e-7, la précision attendue.

## La nomenclature, et pourquoi elle n'a pas été arrangée

`BRIEF.md` §8 : **un réseau ne devient un autre réseau que si ses poids changent.** Ni le couplage
à une table de fin de partie, ni la compilation en WebAssembly, ni une conversion de format n'en
produisent un nouveau.

Les fichiers portent donc **`strehl-prob5-512-512-256-128`**, la paternité d'Alexander Strehl.
**gammonNet** nomme la *configuration* — réseau, recherche, équité de match, fins de partie. La
variante float16 est « le même réseau, quantifié » : même nom, suffixe de format. Les rebaptiser
aurait coûté ce que le critère de succès exige : une provenance traçable.

## Ce que les notes de version disent NE PAS promettre

Elles portent la force telle qu'elle est mesurée — équivalent à GNU Backgammon en 2-ply,
« supérieur » non établi, eXtreme Gammon non mesuré — et le PR reproduisant la référence aux trois
profondeurs. Elles nomment aussi les deux réserves du PR : corpus uniquement de contact, donc
probablement pessimiste, et reproductibilité à ~±0,005 d'un build de gnubg à l'autre.

## Le WebAssembly, et ce qui l'avait bloqué

La cible n'avait plus été construite depuis le 2026-08-03 et **ne compilait plus** : `gn_search.c`
avait gagné des dépendances pendant la phase 3 — cache d'évaluation, tables de fin de partie,
videau — que la liste des sources WebAssembly n'avait pas suivies. Corrigé (`t2x-sources-wasm`).

**Parité vérifiée avant publication** : scalaire exact (`max|Δ| = 0`), SIMD à 6,4e-7 sous la
tolérance de 1e-6, sur le repère de 2 000 positions.

## Reproduire

```bash
make artifact            # build natif, WebAssembly, puis l'assemblage
```

Le script refuse si le corpus T12 bouge, et signale toute pièce manquante.
