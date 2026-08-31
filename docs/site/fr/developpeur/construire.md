# Construire, tester, mesurer

## Le natif

```sh
make setup     # venv, sources vendorées au commit épinglé
make build     # build/libgammonnet.so
make test      # ~1 500 tests
```

Aucune dépendance système exotique : la cible est « ça compile avec un compilateur et rien
d'autre ». `ORACLE=0` évite d'installer GNU Backgammon quand on ne mesure pas.

## Les variantes de build, et ce qu'elles changent

| | Effet |
|---|---|
| par défaut (`-O2`) | le build de développement ; sorties **bit-identiques** au chemin scalaire |
| `NATIVE_FP=1` | ~4× plus rapide, sorties déplacées d'environ 6e-7. Le build des campagnes |
| `-ffp-contract=off` | posé d'office sur `gn_search.c` — voir les [invariants](invariants) |
| `-DGN_BATCH_FILL_STATS` | instrumente le remplissage des lots |

L'**empreinte d'évaluation** diffère entre ces builds, et un journal de campagne le refuse : c'est
voulu.

## Le WebAssembly

```sh
make wasm         # scalaire et SIMD
make wasm-parity  # la parité AVANT tout chiffre de vitesse
```

`gn_wasm.c` compile **sans** Emscripten (le `#include` est sous garde), donc `cc -c` le contrôle
partout ; seule l'édition de liens demande `emcc`.

## L'artefact

```sh
make artifact VERSION=v1
```

Le script **refuse** de produire un répertoire incomplet : il rejoue le corpus de non-régression
avant d'écrire quoi que ce soit, et signale toute pièce manquante.

## Les worktrees

Toute tâche non triviale démarre par un worktree, et se termine par un merge et un nettoyage :

```sh
git worktree add ../gammonNet-<tâche> -b <branche>
# … travail, tests verts …
git merge --no-ff <branche> && git worktree remove ../gammonNet-<tâche>
```

```{admonition} Un piège qui coûte une heure
:class: warning

`git merge` lancé **depuis le worktree de la branche** rend « Already up to date » et ne fait rien.
Le merge se fait depuis le worktree principal.
```

## Écrire un banc de mesure

Les bancs de ce dépôt suivent tous la même forme, et ce n'est pas un style :

1. **Le protocole en tête du fichier**, avec ce que la mesure ne dit pas.
2. **Deux colonnes quand un arbitre est en jeu**, jamais une seule.
3. **Un intervalle de confiance**, par bootstrap sur l'unité indépendante — les paires, pas les
   parties.
4. **Un pilote avant le volume.** Une répétition sur un petit échantillon attrape les défauts
   d'échelle avant qu'ils ne coûtent des jours.
5. **Un refus explicite** quand une entrée est hors domaine.
6. **`--workers`**, et il doit être vrai : un banc dont la documentation annonce le parallélisme
   sans l'implémenter a coûté 68 minutes là où 6 suffisaient.
