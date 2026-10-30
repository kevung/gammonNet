#!/bin/bash
# #34 étape 4 — reprise à 15 workers (2026-10-30, à la demande du propriétaire : mochy libérée,
# smith plafonnée à 15). Les journaux sautent les paires déjà jouées ; journaux de log en ajout.
cd ~/gn34e4
P=/usr/bin/python3.12
COMMON="--theirs self --ours-policy normal --ours-model models/cubeless_prob5_768_768_256_256_256.bin --theirs-model models/cubeless_prob5_512_512_256_256.bin --workers 15"
$P bench/run_t35.py --mode match --match-length 7 $COMMON --seed 20261030 --pairs 35000 --journal journaux/i34-h2h-match.jsonl >> journaux/i34-h2h-match.log 2>&1
$P bench/run_t35.py --mode money $COMMON --seed 20261033 --pairs 100000 --journal journaux/i34-h2h-money-c.jsonl >> journaux/i34-h2h-money-c.log 2>&1
$P bench/run_t35.py --mode money $COMMON --seed 20261031 --pairs 200000 --journal journaux/i34-h2h-money-a.jsonl >> journaux/i34-h2h-money-a.log 2>&1
echo FINI > journaux/i34-smith.done
