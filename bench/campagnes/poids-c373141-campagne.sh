#!/bin/bash
# Réseau par défaut après le rafraîchissement amont c373141 : 768×768 (md5 9ecbc3ee) contre
# 4 couches (md5 84b2293e), et leur float16. À lancer détaché, à la racine d'un worktree de la
# branche adoption/i34-768-c373141, vendor/ relié et `make build model` faits :
#
#   WORKERS=30 setsid nohup bench/campagnes/poids-c373141-campagne.sh > /dev/null 2>&1 &
#
# Relancer reprend à la première étape dont la sortie manque. Relevés dans $OUT.
set -u
cd "$(dirname "$0")/../.." || exit 1
WORKERS=${WORKERS:-16}
OUT=${OUT:-build/poids-c373141}
PY=${PY:-$HOME/venv-gammonnet/bin/python}
R=docs/corpus/t70/money-10000/registre-money.jsonl
M768=models/cubeless_prob5_768_768_256_256_256
M512=models/cubeless_prob5_512_512_256_256
mkdir -p "$OUT"
make "$M768.bin16" "$M512.bin16" || exit 1

run() {  # modèle, nom
  [ -s "$OUT/$2.dump.jsonl" ] && [ -s "$OUT/$2.json" ] && return 0
  "$PY" bench/measure_t70.py --registry "$R" --model "$1" --ply 2 --filter 0,1,1 \
    --filter-extra 0,0,2 --filter-threshold 0,0,0.04 --prune-model models/prune_32.bin \
    --prune-k 12 --workers "$WORKERS" --out "$OUT/$2.json" --dump "$OUT/$2.dump.jsonl" \
    > "$OUT/$2.log" 2>&1
}
run "$M512.bin" 512
run "$M768.bin" 768
run "$M768.bin16" 768-fp16
"$PY" bench/paired_dumps_t70.py "$OUT/512.dump.jsonl" "$OUT/768.dump.jsonl" \
  --out "$OUT/paire-768-vs-512.json" > "$OUT/paire-768-vs-512.txt" 2>&1
"$PY" bench/paired_dumps_t70.py "$OUT/768.dump.jsonl" "$OUT/768-fp16.dump.jsonl" \
  --out "$OUT/paire-768-fp16-vs-fp32.json" > "$OUT/paire-768-fp16-vs-fp32.txt" 2>&1
[ -s "$OUT/fp16-768.json" ] || "$PY" bench/measure_fp16.py --fp32 "$M768.bin" --fp16 "$M768.bin16" \
  --positions 20000 --workers "$WORKERS" --out "$OUT/fp16-768.json" > "$OUT/fp16-768.txt" 2>&1
echo fini > "$OUT/fini"
