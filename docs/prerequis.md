# Prérequis — reproduire ce travail sur une autre machine

> **À quoi sert ce document.** `BRIEF.md` §2 énumère les prérequis du cadrage
> initial. Ils ont bougé depuis, et surtout **la piste calcul en a acquis un
> nouveau et non évident** : GNU Backgammon lui-même, avec son mode Python.
> Quelqu'un qui reprend ce dépôt sur une machine neuve doit pouvoir tout
> réinstaller à partir d'ici, et **vérifier** chaque brique par une commande
> dont il lit la sortie.

## Les deux profils de machine

Le travail se répartit sur deux profils **complémentaires**, pas concurrents.
Le détail des attributions est dans `PLAN.md`, section *Répartition entre
machines*.

| | Piste A — calcul | Piste B — navigateur |
|---|---|---|
| Cœurs | 16 physiques / 32 fils, et ils servent tous | 8 suffisent |
| Mémoire | **≥ 32 Gio.** La mesure T36 tient 60 processus GNU Backgammon simultanés | 4 Gio |
| Disque | **≥ 10 Gio libres** pour les bases de fin de partie seules | 2 Gio |
| GPU | Utile en phase 4 seulement. Sans objet pour les phases 0 à 3 | inutile |
| Indispensable | GNU Backgammon, compilateur C | **un navigateur réel**, Emscripten |

**La séparation est matérielle, pas organisationnelle** : une machine sans
navigateur ne peut pas produire les mesures de la phase 2, et une machine à
4 Gio ne peut pas tenir un round-robin.

## Piste A — la chaîne de calcul

### 1. Compilateur C

C11, rien d'exotique. GCC 8.5 (RHEL 8) suffit et c'est ce qui a servi.

```bash
gcc --version          # attendu : >= 8.5
```

### 2. Python ≥ 3.10, en environnement virtuel

Sur les distributions dont le Python système est plus ancien — RHEL 8 livre
3.6 — passer par un module AppStream, **sans toucher au Python système**.

```bash
python3.12 -m venv ~/venv-gammonnet
source ~/venv-gammonnet/bin/activate
pip install --upgrade pip torch numpy pytest
```

PyTorch n'est requis que pour **exporter** les poids depuis le `.pt` d'origine
et pour la phase 4. L'inférence, la recherche et la mesure n'en dépendent pas.

Sur une machine sans GPU, éviter la build CUDA — environ 5 Gio de paquets
`nvidia-*` inutiles :

```bash
make setup PYTHON_SYS=python3.13 TORCH_CPU=1 ORACLE=0
```

### 3. GNU Backgammon — **avec son mode Python**

> **Le prérequis le moins évident, et celui sans lequel la phase 3 s'arrête.**

`PLAN.md` a désigné GNU Backgammon comme la référence des mesures qui engagent
une conclusion en match ou sur le videau. T36 a ajouté une raison plus brutale :
c'est le **seul** oracle utilisable au-delà du 0-ply.

```bash
gnubg --version                        # mesuré ici : 1.08.003
gnubg --help | grep -- --python        # doit exister
```

Puis le contrôle qui compte réellement — l'interpréteur embarqué répond :

```bash
echo 'import sys; print("PY", sys.version.split()[0])' > /tmp/p.py
gnubg --tty --quiet --no-rc -p /tmp/p.py | grep PY     # mesuré ici : 3.11.13
```

**Une build de GNU Backgammon compilée sans support Python ne convient pas.**
`--python` figure alors dans l'aide mais l'import échoue. Le contrôle ci-dessus
distingue les deux ; la présence du binaire ne suffit pas.

Sources : <https://www.gnu.org/software/gnubg/>. Sur les distributions qui ne
livrent pas le mode Python, il faut recompiler avec `--with-python`.

### 4. `gnubg-nn` — utile, et borné

```bash
pip install gnubg-nn
```

Rapide, en processus, sans table à consulter : **parfait pour les gros volumes
en money au 0-ply**, ce à quoi T11 l'a employé.

> **Deux limites établies par la mesure, à ne pas oublier :**
>
> - **Il plante à partir du 1-ply sur les positions de bearoff.** Segfault
>   reproductible, base de fin de partie unilatérale activée ou non. Trouvé en
>   T36. Il est donc inutilisable pour toute mesure en profondeur.
> - **Sa table d'équité de match n'est pas la nôtre** — `max|Δ| = 2,679e-02`
>   contre Kazaross-XG2, mesuré en T32, quand une décision de videau se joue sur
>   des marges bien inférieures.

### 5. Les bases de fin de partie

Deux fichiers, **2,8 Gio**, non versionnés (`gnu_bearoff_database/` est ignoré) :

| Fichier | En-tête | Portée |
|---|---|---|
| `gnubg_os13.bd` — 1,6 Gio | `gnubg-OS-13-15-1-1-0` | Unilatérale, 13 points, 15 pions |
| `gnubg_ts6x11.bd` — 1,2 Gio | `gnubg-TS-06-11-1` | Bilatérale, 6 points, 11 pions, **cubeful** |

Ils se **régénèrent** par la commande `makebearoff` de GNU Backgammon : c'est un
calcul exact par programmation dynamique, pas une œuvre — deux implémentations
correctes produisent le même fichier. `CLAUDE.md` les autorise à ce titre,
quelle que soit leur origine.

Ce ne sont **pas** des artefacts distribuables : 2,8 Gio ne partent pas dans un
navigateur. Ce sont un actif natif et de mesure. La table embarquée reste celle
que T33 calcule.

### 6. Le modèle de référence

Poids MIT, non versionnés ici (`models/*.bin` est ignoré) :

```bash
make setup      # clone le dépôt de référence à son commit épinglé
make model      # exporte cubeless_prob5_512_512_256_128.bin
```

## Piste B — la chaîne navigateur

| Brique | Vérification |
|---|---|
| Emscripten | `emcc --version` |
| Node ≥ 20 | `node --version` — sert au test de parité WebAssembly |
| Un navigateur **réel** | Pas un émulateur. T21 a mesuré sept plateformes, dont quatre appareils physiques |

```bash
make wasm
make wasm-parity     # sorties WebAssembly contre le repère natif
```

## Le contrôle de bout en bout

Une machine est prête quand ceci passe :

```bash
make build NATIVE_FP=1
make test                 # ~15 min, plus de 1 350 tests
```

Un worktree neuf n'a ni `vendor/` ni `models/` — les deux sont ignorés. Les
lier **en absolu**, jamais en relatif :

```bash
ln -s /chemin/vers/gammonNet/vendor vendor
ln -s /chemin/vers/gammonNet/models/cubeless_prob5_512_512_256_128.bin models/
```

> Le `.gitignore` porte la cicatrice de l'erreur inverse : un lien relatif
> `vendor`, valide sur la machine qui l'avait créé, pointait sur lui-même sur
> l'autre et y a écrasé le vrai répertoire.

## Documentation publiée — *prévu, pas fait*

Quand un modèle pertinent sera arrêté, la documentation sortira sous **Sphinx**,
publiée en GitHub Pages, en quatre volets :

| Volet | Contenu |
|---|---|
| **Scientific guide** | L'architecture du réseau, l'encodage, la recherche, l'équité de match, le modèle de videau, les fins de partie — et pour chaque affirmation de force, le protocole, le volume et l'intervalle de confiance |
| **User guide** | L'API JavaScript et l'API native, les formats de position acceptés, les profondeurs et ce qu'elles coûtent |
| **Developer guide** | La chaîne de build, les deux cibles, le corpus de non-régression, comment ajouter une mesure |
| **Provenance** | Les licences, le registre de `docs/etudes/`, l'attribution — condition de livraison, pas annexe |

**Ce volet n'est pas ouvert.** Le publier avant que la force ne soit mesurée
reviendrait à documenter une affirmation que le dépôt s'interdit de faire.
Le dépôt `gh-pages` existe déjà et sert aujourd'hui la page de mesure de T21.
