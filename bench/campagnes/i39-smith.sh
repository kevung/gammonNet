#!/bin/bash
# #39 — la partie lourde : poids amont ea604e7 (768×768 md5 b8d4306c, 4 couches md5 88b03c1c)
# contre les poids épinglés c373141 (9ecbc3ee, 84b2293e). Mêmes instruments et mêmes seuils
# que #38 et T98, graines et seuils déclarés avant lecture (2026-11-10). 25 workers autorisés
# sur smith par le propriétaire ce jour.
#
# Seuils de non-régression, nouveau 768×768 contre c373141, politique `normal` des deux côtés :
#   match 7 points, 35 000 paires : borne basse de la MWC ≥ 49,5 % ;
#   money, 150 000 paires : borne basse ≥ −0,010 ppg.
#
# Arbre : ~/gn39 (git archive de mesure/i39-ea604e7, vendor relié, poids copiés, `make build`).
# À lancer détaché : WORKERS=25 setsid nohup bench/campagnes/i39-smith.sh > i39-smith.out 2>&1 &
# Relancer reprend : chaque étape saute si sa sortie existe, les journaux cubeful sautent les
# paires déjà jouées.
set -u
cd "$(dirname "$0")/../.." || exit 1
P=${PY:-/usr/bin/python3.12}
W=${WORKERS:-25}
J=${OUT:-build/i39}
R=docs/corpus/t70/money-10000/registre-money.jsonl
OLD768=models/cubeless_prob5_768_768_256_256_256
OLD512=models/cubeless_prob5_512_512_256_256
NEW768=models/candidate_ea604e7_768_768_256_256_256
NEW512=models/candidate_ea604e7_512_512_256_256
mkdir -p "$J"

# 1. Registre T70, 2-ply `normal` (protocole de 2026-11-04-poids-c373141.md).
t70() {  # modèle, nom
  [ -s "$J/$2.dump.jsonl" ] && [ -s "$J/$2.json" ] && return 0
  "$P" bench/measure_t70.py --registry "$R" --model "$1" --ply 2 --filter 0,1,1 \
    --filter-extra 0,0,2 --filter-threshold 0,0,0.04 --prune-model models/prune_32.bin \
    --prune-k 12 --workers "$W" --out "$J/$2.json" --dump "$J/$2.dump.jsonl" \
    > "$J/$2.log" 2>&1
}
pair() {  # a, b — rapporte b − a
  [ -s "$J/paire-$2-vs-$1.json" ] && return 0
  "$P" bench/paired_dumps_t70.py "$J/$1.dump.jsonl" "$J/$2.dump.jsonl" \
    --out "$J/paire-$2-vs-$1.json" > "$J/paire-$2-vs-$1.txt" 2>&1
}
t70 "$NEW768.bin" 768-ea604e7
t70 "$OLD768.bin" 768-c373141
t70 "$NEW512.bin" 512-ea604e7
t70 "$OLD512.bin" 512-c373141
t70 "$NEW768.bin16" 768-ea604e7-fp16
t70 "$NEW512.bin16" 512-ea604e7-fp16
pair 768-c373141 768-ea604e7
pair 512-c373141 512-ea604e7
pair 512-ea604e7 768-ea604e7
pair 768-ea604e7 768-ea604e7-fp16
pair 512-ea604e7 512-ea604e7-fp16

# 2. 0-ply sans arbitre, dés dupliqués, 1 M de parties par affrontement.
rr() {  # moteurs, graine, nom
  [ -s "$J/$3.json" ] || "$P" bench/run_round_robin.py --engines "$1" --pairs 500000 \
    --workers "$W" --seed "$2" --out "$J/$3.json" > "$J/$3.log" 2>&1
}
rr prob5-768x768-0ply,prob5-768x768-b8d4306c-0ply 20261110 tete-a-tete-0ply-768
rr prob5-256-88b03c1c-0ply,prob5-768x768-b8d4306c-0ply 20261111 tete-a-tete-0ply-768-vs-512

# 3. Cubeful, nouveau 768×768 contre c373141.
COMMON="--theirs self --ours-policy normal --ours-model $NEW768.bin --theirs-model $OLD768.bin --workers $W"
"$P" bench/run_t35.py --mode match --match-length 7 $COMMON --seed 20261112 --pairs 35000 \
  --journal "$J/h2h-match.jsonl" >> "$J/h2h-match.log" 2>&1
"$P" bench/run_t35.py --mode money $COMMON --seed 20261113 --pairs 150000 \
  --journal "$J/h2h-money.jsonl" >> "$J/h2h-money.log" 2>&1
echo FINI > "$J/fini"
