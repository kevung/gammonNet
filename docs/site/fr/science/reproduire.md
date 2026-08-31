# Reproduire chaque mesure

Toute affirmation chiffrée de ce volet a une commande. Les voici, avec leur coût.

## Préparer

```sh
make setup     # environnement Python, sources vendorées au commit épinglé
make build     # la bibliothèque native
make model     # les poids, exportés depuis la source vendorée
```

Les poids **ne sont pas dans le dépôt** : ils viennent du travail d'Alexander Strehl, à un commit
épinglé. Les reconstruire vérifie du même coup que la chaîne d'export fonctionne encore.

## La force

```sh
# money — ~5 jours à 24 ouvriers
python bench/run_t35.py --mode money --pairs 50000 --workers 24 \
    --journal docs/mesures/t35-money.jsonl \
    --ours-ply 2 --ours-filter 0,1,3 --gnubg-ply 2 --gnubg-filter 0,1,3

# match — ~4,9 jours à 30 ouvriers
python bench/run_t35.py --mode match --pairs 50000 --workers 30 \
    --journal docs/mesures/t35-match-v2.jsonl \
    --ours-ply 2 --ours-filter 0,1,3 --gnubg-ply 2 --gnubg-filter 0,1,3

python bench/report_t35.py --journal docs/mesures/t35-match-v2.jsonl
```

Les campagnes sont **segmentables** : `Ctrl-C`, une extinction ou un `--minutes` les
interrompent, et relancer la même commande reprend. Un run segmenté est **identique bit à bit** à
un run d'une traite — testé.

## Le taux d'erreur (PR)

```sh
# ~15 min : arbitrage parallèle, puis quatre configurations
python bench/pr.py --decisions 600 --plies 0,1,2,2@0 --arbiter-ply 3 --workers 24
```

`2@0` désigne un 2-ply **sans** élagage : plusieurs configurations dans le même passage, donc un
seul arbitrage. L'arbitre est mis en cache — il ne dépend que du corpus et de sa profondeur.

## L'analyse d'un match

```sh
python bench/analyse_match.py --match test.sgf --ply 2 --prune-k 12 --max-decisions 400
```

## Les optimisations

```sh
make bench-decision                    # le coût d'une décision, sans Python dans le cadre
make bench-encoding                    # ce qu'une évaluation coûte à une RECHERCHE
python bench/prune_search.py --contact 300 --race 150 --ks 2,3,5,8,12 --workers 26

# le remplissage des lots, par réseau
make CFLAGS="-O2 -std=c11 -Wall -Wextra -fPIC -DGN_BATCH_FILL_STATS" bench-decision
```

## Le navigateur

```sh
make wasm && make wasm-parity          # la parité AVANT tout chiffre de vitesse
node wasm/harness.mjs --browser firefox --page /wasm/decision.html --build simd
node wasm/harness.mjs --browser firefox --page /wasm/workers.html  --build simd
```

Le harnais lance un serveur statique et un navigateur sur un **profil neuf** — ni extension ni
cache d'un profil de développement dans une mesure.

## Vérifier l'artefact publié

Sans rien construire, depuis l'archive de la release :

```sh
node verify/parity.mjs
```

Attendu : `max|Δ| = 0` en scalaire, ~6,4e-7 en SIMD, sur le repère de 2 000 positions.

## Les tests

```sh
python -m pytest tests/ -q       # ~1 500 tests, ~10 min
```

Ils incluent le **corpus de non-régression** : tout changement de poids ou d'encodage qui déplace
une sortie le fait **visiblement**.
