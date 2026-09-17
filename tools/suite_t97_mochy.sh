#!/bin/bash
# T97 — deuxième échantillon indépendant, graine disjointe.
#
# Trois campagnes à graines disjointes plutôt qu'une seule trois fois plus
# longue : les trois tables se moyennent (l'erreur-type tombe d'un facteur
# racine de trois) ET se comparent entre elles. Une campagne unique ne se
# réplique pas elle-même.
set -u
cd "$(dirname "$0")/.."
ATTENDU=../gammonNet-poids/docs/mesures/t96-incumbent-k12-t70.json
while [ ! -f "$ATTENDU" ]; do sleep 60; done
sleep 30

~/venv-gammonnet/bin/python -u tools/compute_met.py \
    --games 20000 --games-far 4000 --near 10 \
    --ply 0 --cube-ply 0 --workers 28 --seed 20260919 \
    --name gammonnet-t97-mochy \
    --out ~/dev/gammonNet-logs/t97-mochy.json \
    --table-out ~/dev/gammonNet-logs/t97-mochy.met
echo "FINI $(date -Is)"
