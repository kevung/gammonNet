#!/bin/bash
# #34 — déporté de melbaa vers mochy le 2026-10-30 à la demande du propriétaire.
# Le 0-ply ne sait pas reprendre : relancé depuis zéro, même graine. Puis money-b plafonné à 50 000.
cd /home/kunger/dev/gammonNet-i34-e4
P=/home/kunger/bin/miniconda3/bin/python3
J=build/i34e4/journaux
$P bench/run_round_robin.py --engines gammonnet-0ply,prob5-768x768-0ply --pairs 500000 --workers 26 --seed 20261030 --out $J/i34-tete-a-tete-0ply.json > $J/i34-0ply.log 2>&1
$P bench/run_t35.py --mode money --theirs self --ours-policy normal --ours-model models/cubeless_prob5_768_768_256_256_256.bin --theirs-model models/cubeless_prob5_512_512_256_256.bin --workers 26 --seed 20261032 --pairs 50000 --journal $J/i34-h2h-money-b.jsonl >> $J/i34-h2h-money-b.log 2>&1
echo FINI > $J/i34-mochy.done
