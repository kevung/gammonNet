#!/bin/bash
# T97 — campagne refaite avec l'erreur-type propagée à travers la récursion.
# La précédente garde sa valeur comme échantillon ; ses barres d'erreur, non.
set -u
cd "$(dirname "$0")/.."
while [ ! -f ~/dev/gammonNet-logs/t97-mochy.json ]; do sleep 60; done
sleep 30
~/venv-gammonnet/bin/python -u tools/compute_met.py \
    --games 20000 --games-far 4000 --near 10 \
    --ply 0 --cube-ply 0 --workers 28 --seed 20260924 \
    --name gammonnet-t97-mochy2 \
    --out ~/dev/gammonNet-logs/t97-mochy2.json \
    --table-out ~/dev/gammonNet-logs/t97-mochy2.met
echo "FINI $(date -Is)"
