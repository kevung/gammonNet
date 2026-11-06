#!/bin/bash
# T97 — la derniere variable non testee du plateau : la profondeur du JEU DE
# PIONS, pas celle du videau. L arbitrage du 18 septembre a varie cube_ply
# (0 -> 1) et le plateau a tenu ; ply est reste a 0 dans les deux cas.
set -u
cd ~/gn97
C="pre-14-21,pre-16-23,pre-16-25,pre-14-25,pre-12-22,pre-13-21,pre-2-3,pre-3-5,pre-4-7,pre-5-5"
/usr/bin/python3.12 -u tools/compute_met.py --from-table base-t97.json --cells "$C" \
    --games 4000 --workers 35 --seed 20261005 --ply 1 --cube-ply 1 \
    --name arbitrage-pions-1ply --out ~/t97-plypions.json
echo "FINI $(date -Is)"
