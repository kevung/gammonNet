#!/bin/bash
# T96 — la suite de mochy : attendre le tête-à-tête, puis noter l'incumbent
# au MÊME réglage que le candidat (2-ply k=12).
#
# Pourquoi cette note manquait : l'étalon 0,00313 de T70 a été mesuré SANS
# élagage (9,67 h·cœur sur smith, 15,82 sur mochy — le rapport est celui des
# machines, pas celui des réglages). Comparer un candidat élagué à un étalon
# non élagué compare deux moteurs différents.
set -u
cd "$(dirname "$0")/.."
PY=~/venv-gammonnet/bin/python
OUT=docs/mesures/t96-tete-a-tete-0ply.json

# Le tête-à-tête écrit son JSON en dernier : c'est lui le signal, pas un pgrep
# sur un nom de processus (les faux positifs de `pgrep -f` ont déjà coûté une
# campagne à ce dépôt).
while [ ! -f "$OUT" ]; do sleep 60; done
sleep 30

$PY -u bench/measure_t70.py \
    --registry docs/corpus/t70/money-10000/registre-money.jsonl \
    --model models/cubeless_prob5_512_512_256_128.bin \
    --ply 2 --prune-model models/prune_32.bin --prune-k 12 --workers 28 \
    --label "incumbent 2-ply k=12 (contrôle du réglage)" \
    --out docs/mesures/t96-incumbent-k12-t70.json
echo "FINI $(date -Is)"
