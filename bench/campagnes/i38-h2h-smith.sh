#!/bin/bash
# #38 — tête-à-tête cubeful, 768×768 (md5 9ecbc3ee) contre 4 couches (md5 84b2293e), poids
# c373141, politique `normal` des deux côtés. Seuils et volumes de T98, graines déclarées
# avant lecture (2026-11-06). 40 workers autorisés sur smith par le propriétaire ce jour.
# Arbre : ~/gn38 (git archive de adoption/i34-768-c373141, vendor relié, poids copiés).
# Relancer reprend : les journaux sautent les paires déjà jouées.
cd ~/gn38 || exit 1
P=/usr/bin/python3.12
J=journaux
mkdir -p $J
COMMON="--theirs self --ours-policy normal --ours-model models/cubeless_prob5_768_768_256_256_256.bin --theirs-model models/cubeless_prob5_512_512_256_256.bin --workers ${WORKERS:-40}"
$P bench/run_t35.py --mode match --match-length 7 $COMMON --seed 20261106 --pairs 35000 --journal $J/i38-h2h-match.jsonl >> $J/i38-h2h-match.log 2>&1
$P bench/run_t35.py --mode money $COMMON --seed 20261107 --pairs 100000 --journal $J/i38-h2h-money-a.jsonl >> $J/i38-h2h-money-a.log 2>&1
echo FINI > $J/i38-smith.done
