#!/usr/bin/env bash
# T71 — étiquetage sur smith, avec un couvre-feu qui n'est pas négociable.
#
# smith est une machine de laboratoire partagée. Les autres utilisateurs
# arrivent à 9 h : la campagne doit être ARRÊTÉE avant, et pas « normalement
# terminée à peu près à ce moment-là ». Ce script fixe donc une heure limite et
# tue le groupe de processus entier quand elle arrive.
#
# Pourquoi un wrapper plutôt qu'un simple `timeout` : le générateur travaille
# par `ProcessPoolExecutor`. Un SIGTERM au seul parent laisserait 80 orphelins
# tourner jusqu'au bout — exactement ce que le couvre-feu doit empêcher. On
# lance donc dans un groupe de processus dédié (`setsid`) et on tue le GROUPE.
#
# Rien n'est perdu par l'arrêt : chaque worker écrit sa part au fil de l'eau,
# `flush` à chaque ligne, et une relance à mêmes graine et nombre de processus
# reprend là où elle s'était interrompue.
#
# Usage : campagne_smith_labels.sh <heure-limite HH:MM> [count] [workers]
set -u

LIMIT="${1:-08:30}"
COUNT="${2:-1500000}"
WORKERS="${3:-80}"
SEED=20270902          # disjointe de mochy (20260902) et melbaa (20261902)
ROOT="$HOME/dev/gammonNet"
OUT="$ROOT/build/t71-smith"
LOG="$HOME/gammonNet-logs/t71-labels-smith.log"

mkdir -p "$(dirname "$LOG")" "$OUT"
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

deadline=$(date -d "today $LIMIT" +%s)
[ "$deadline" -le "$(date +%s)" ] && deadline=$(date -d "tomorrow $LIMIT" +%s)
remaining=$(( deadline - $(date +%s) ))

say "═══ étiquetage T71 sur smith ═══"
say "  cible $COUNT étiquettes, $WORKERS processus, graine $SEED"
say "  couvre-feu : $(date -d "@$deadline" '+%F %H:%M') — dans $((remaining / 60)) min"

cd "$ROOT" || exit 1
setsid /usr/bin/python3.12 tools/build_labels_t71.py \
    --count "$COUNT" --workers "$WORKERS" --seed "$SEED" --out "$OUT" \
    >> "$LOG" 2>&1 &
child=$!
sleep 2
pgid=$(ps -o pgid= -p "$child" 2>/dev/null | tr -d ' ')
say "  lancé : pid $child, groupe $pgid"

while [ "$(date +%s)" -lt "$deadline" ]; do
    kill -0 "$child" 2>/dev/null || { say "la campagne s'est terminée d'elle-même"; break; }
    sleep 60
done

if kill -0 "$child" 2>/dev/null; then
    say "── COUVRE-FEU : arrêt du groupe $pgid"
    kill -TERM "-$pgid" 2>/dev/null
    sleep 20
    kill -KILL "-$pgid" 2>/dev/null
    say "  arrêté. Les parts écrites sont intactes et reprenables."
fi

produced=$(cat "$OUT"/labels.part-*.jsonl 2>/dev/null | wc -l)
say "  $produced étiquettes produites, dans $OUT"
say "  reste sur smith : $(du -sh "$ROOT" 2>/dev/null | cut -f1)"
say "═══ terminé le $(date -Is) ═══"
