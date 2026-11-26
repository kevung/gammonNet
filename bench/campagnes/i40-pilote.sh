#!/bin/bash
# #40/#41 — pilote : 1 000 paires money de #39 (graine 20261113), cache corrigé,
# jouées deux fois, sans puis avec juge de la chance (768×768 c373141).
set -u
cd "$(dirname "$0")/../.." || exit 1
P=${PY:-/usr/bin/python3.12}
W=${WORKERS:-40}
J=${OUT:-build/i40}
mkdir -p "$J"
COMMON="--mode money --theirs self --ours-policy normal --ours-model models/candidate_ea604e7_768_768_256_256_256.bin --theirs-model models/cubeless_prob5_768_768_256_256_256.bin --workers $W --seed 20261113 --pairs 150000 --indices 0:1000"
{ /usr/bin/time -f "%e s" "$P" bench/run_t35.py $COMMON --journal "$J/pilote-sans-juge.jsonl"; } > "$J/pilote-sans-juge.log" 2>&1
{ /usr/bin/time -f "%e s" "$P" bench/run_t35.py $COMMON --luck-model models/cubeless_prob5_768_768_256_256_256.bin --journal "$J/pilote-juge.jsonl"; } > "$J/pilote-juge.log" 2>&1
echo FINI > "$J/pilote-fini"
