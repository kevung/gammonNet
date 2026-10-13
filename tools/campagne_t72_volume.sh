#!/usr/bin/env bash
# T72 — la courbe volume -> perte de la distillation 0-ply, une file par GPU.
#
#   GPU 0 : la forme du professeur (512,512,256,256) — le volume referme-t-il
#           l'écart de méthode à taille égale (0,00990 contre 0,00313) ?
#   GPU 1 : la forme cible de T72 (256,128,64, 91 456 MACs).
#
# Même corpus, même graine, même validation (4 parts tirées en premier) pour
# tous les points. Lancer détaché :
#   setsid nohup tools/campagne_t72_volume.sh > ~/dev/gammonNet-logs/t72-volume.log 2>&1 &
# Un point déjà produit (son .summary.json existe) est sauté : relancer reprend.
set -u
cd "$(dirname "$0")/.."
CORPUS=build/t72-distill
OUT=models/t72v
mkdir -p "$OUT" ~/dev/gammonNet-logs

file() {  # $1 = gpu, $2 = forme, $3 = étiquette de forme
    for rows in 800000 3200000 12800000 51200000; do
        name="$OUT/t72v_$3_$((rows / 100000))h"
        if [ -f "$name.summary.json" ]; then
            echo "déjà fait : $name"; continue
        fi
        echo "=== GPU $1 forme $2 lignes $rows $(date +%H:%M:%S)"
        CUDA_VISIBLE_DEVICES=$1 python3 tools/distill_volume_t72.py \
            --corpus "$CORPUS" --rows "$rows" --shape "$2" --out "$name.bin" \
            > ~/dev/gammonNet-logs/"$(basename "$name")".log 2>&1
        echo "    fin $(date +%H:%M:%S), code $?"
    done
}

file 0 512,512,256,256 prof &
file 1 256,128,64 cible &
wait
echo "campagne terminée $(date +%H:%M:%S)"
