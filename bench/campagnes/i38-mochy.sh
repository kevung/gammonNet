#!/bin/bash
# #38 — sur mochy, après la campagne T70 (poids-c373141-campagne.sh) : tête-à-tête 0-ply sans
# arbitre (500 000 paires, comme l'étape 4 de #34), puis la seconde moitié du money cubeful
# (50 000 paires, graine distincte de smith ; les deux journaux se lisent en commun).
# À lancer détaché à la racine du worktree adoption/i34-768-c373141.
cd "$(dirname "$0")/../.." || exit 1
P=${PY:-$HOME/venv-gammonnet/bin/python}
W=${WORKERS:-30}
J=build/i38
mkdir -p $J
until [ -e build/poids-c373141/fini ]; do sleep 60; done
[ -s $J/i38-tete-a-tete-0ply.json ] || $P bench/run_round_robin.py --engines prob5-256-0ply,prob5-768x768-0ply --pairs 500000 --workers $W --seed 20261108 --out $J/i38-tete-a-tete-0ply.json > $J/i38-0ply.log 2>&1
$P bench/run_t35.py --mode money --theirs self --ours-policy normal --ours-model models/cubeless_prob5_768_768_256_256_256.bin --theirs-model models/cubeless_prob5_512_512_256_256.bin --workers $W --seed 20261109 --pairs 50000 --journal $J/i38-h2h-money-b.jsonl >> $J/i38-h2h-money-b.log 2>&1
echo FINI > $J/i38-mochy.done
