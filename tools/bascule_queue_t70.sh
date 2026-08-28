#!/bin/bash
# Bascule mochy sur la QUEUE du corpus quand son bloc de tête est fini.
#
# Pourquoi. smith (2× EPYC, 50 ouvriers) monte depuis l'index 3000 à ~950/h ;
# mochy (30 ouvriers, saturée) fait ~260/h. Laissée seule, mochy finirait son
# bloc `index < 3000` puis REFERAIT ce que smith a déjà fait. Elle prend donc
# la queue par l'autre bout, et les deux se rejoignent au milieu.
#
# Ce que ce script tue, et pourquoi les deux. `campagne_t70_v2.sh` enchaîne sur
# la RÉCOLTE des quatre contextes de score une fois le money fini — sept heures
# NON REPRENABLES, à ne surtout pas lancer devant une extinction annoncée. On
# tue donc le script pilote AVANT l'arbitrage, jamais l'inverse.
set -u

WT=/home/kunger/dev/gammonNet-t70b
CORPUS=$WT/docs/corpus/t70/money-10000/corpus-money.jsonl
JOURNAL=$WT/docs/corpus/t70/money-10000/registre-money.jsonl.journal
PY=/home/kunger/venv-gammonnet/bin/python
LOG=/home/kunger/dev/gammonNet-logs/t70-bascule.log
OFFSET=${OFFSET:-23270}     # les 1800 derniers index — ~6,4 h au débit de mochy
FRONTIERE=${FRONTIERE:-3000}

say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }

reste_en_tete() {
    "$PY" - "$CORPUS" "$JOURNAL" "$FRONTIERE" <<'PYEOF'
import json, sys, pathlib
corpus, journal, frontiere = sys.argv[1], sys.argv[2], int(sys.argv[3])
idx = {json.loads(l)["index"] for l in pathlib.Path(corpus).read_text().splitlines() if l.strip()}
done = set()
p = pathlib.Path(journal)
if p.exists():
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "index" in row:
            done.add(row["index"])
print(len({i for i in idx if i < frontiere} - done))
PYEOF
}

say "veille armée : bascule vers offset $OFFSET quand le bloc < $FRONTIERE sera fini"

while true; do
    n=$(reste_en_tete 2>/dev/null)
    case "$n" in
        ''|*[!0-9]*) say "comptage illisible ('$n') — nouvelle tentative dans 5 min" ;;
        0) say "bloc de tête terminé ; bascule" ; break ;;
        *) say "reste $n décisions sous $FRONTIERE" ;;
    esac
    sleep 300
done

# 1. le pilote d'abord — sinon il enchaîne sur la récolte non reprenable
pilote=$(ps -eo pid,args | awk '/campagne_t70_v2\.sh/ && !/awk/ {print $1}')
[ -n "$pilote" ] && { say "arrêt du pilote campagne_t70_v2.sh (pid $pilote)"; kill $pilote; }
sleep 3

# 2. l'arbitrage ensuite
pids=$(ps -eo pid,args | awk '/arbitrate_t70\.py/ && !/awk/ {print $1}')
[ -n "$pids" ] && { say "arrêt de l'arbitrage (pids $(echo $pids | tr '\n' ' '))"; kill $pids; }
sleep 20
restants=$(ps -eo pid,args | awk '/arbitrate_t70\.py/ && !/awk/ {print $1}' | wc -l)
say "processus d'arbitrage restants : $restants"

# 3. relance sur la queue
cd "$WT" || { say "worktree introuvable"; exit 1; }
setsid nohup "$PY" -u bench/arbitrate_t70.py \
    --corpus docs/corpus/t70/money-10000/corpus-money.jsonl \
    --workers 30 --chunk 4 --truncate 9 --deep-truncate 21 \
    --offset "$OFFSET" \
    >> /home/kunger/dev/gammonNet-logs/t70-campagne.log 2>&1 < /dev/null &
disown
say "relancée sur la queue : offset $OFFSET, 30 ouvriers"
