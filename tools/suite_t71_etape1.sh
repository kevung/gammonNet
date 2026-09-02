#!/usr/bin/env bash
# T71 étape 1 — la suite qui enchaîne quand l'étiquetage rend la machine.
#
# Elle attend la fin des deux campagnes d'étiquetage (mochy et melbaa),
# rapatrie la part de melbaa, entraîne l'élève, l'exporte, puis le fait juger
# par l'instrument de T70 — contre l'étalon 0,00313 de l'incumbent.
#
# Elle profite du fait que melbaa finit AVANT mochy pour y placer, dans
# l'intervalle, la mesure que T73 attend : le réseau QAT int8 noté sur le même
# registre. Deux fiches avancent au lieu d'une, et la machine ne dort pas.
#
# Ce qu'elle ne fait PAS : elle n'ouvre aucune étape 2. Le palier B1 de DS-14
# est un point d'arrêt — si le candidat ne bat pas l'incumbent à ce volume, la
# donnée supplémentaire ne sauve pas une idée neutre, et c'est un humain qui
# lit ce verdict.
#
# Les gardes comptent les CALCULS, jamais les shells qui les nomment : les
# motifs sont écrits pour ne pas se matcher eux-mêmes (piège du 2026-08-27).
set -u

ROOT="/home/kunger/dev/gammonNet"
LOGS="/home/kunger/dev/gammonNet-logs"
LABELS="$ROOT/build/t71-money"
MELBAA_DIR="~/gammonNet-t71-labels/build/t71-money"
REGISTRY="$ROOT/docs/corpus/t70/money-10000/registre-money.jsonl"
ETALON=0.00313

say() { echo "[$(date '+%m-%d %H:%M:%S')] $*"; }

busy_local()  { [ "$(pgrep -cf 'build_labels_t7[1]\.py')" -gt 0 ]; }
busy_melbaa() { [ "$(ssh melbaa "pgrep -cf 'build_labels_t7[1][.]py'" 2>/dev/null || echo 0)" -gt 0 ]; }

say "═══ suite T71 étape 1 — attente de la fin des deux étiquetages ═══"

# ── 1. melbaa finit en premier : on y place la mesure T73 ────────────────
melbaa_done=0
t73_started=0
while busy_local || busy_melbaa; do
    if [ "$melbaa_done" -eq 0 ] && ! busy_melbaa; then
        melbaa_done=1
        say "melbaa : étiquetage terminé"
        say "── T73 sur melbaa : le réseau QAT int8 noté par l'instrument de T70"
        scp -q "$ROOT/models/qat_int8.bin" melbaa:~/gammonNet-t71-labels/models/ \
            && scp -q "$REGISTRY" melbaa:~/gammonNet-t71-labels/ \
            && ssh melbaa "cd ~/gammonNet-t71-labels && setsid nohup ~/venv-gn/bin/python bench/measure_t70.py \
                    --registry registre-money.jsonl --model models/qat_int8.bin \
                    --ply 2 --prune-model models/prune_32.bin --prune-k 12 \
                    --workers 24 --label 'QAT int8 2-ply' \
                    --out docs/mesures/t73-int8-t70-money.json \
                  > ~/t73-int8-t70.log 2>&1 < /dev/null &" \
            && t73_started=1 && say "  lancée (24 processus, journal ~/t73-int8-t70.log)" \
            || say "  ⚠ lancement refusé — la mesure T73 reste à faire à la main"
    fi
    sleep 300
done

say "les deux étiquetages sont terminés"

# ── 2. rapatrier la part de melbaa ──────────────────────────────────────
say "── rapatriement des étiquettes de melbaa"
mkdir -p "$LABELS"
scp -q "melbaa:$MELBAA_DIR/labels.part-*.jsonl" "$LABELS/" 2>/dev/null
# Les parts de melbaa portent les mêmes numéros que celles de mochy : le scp
# ci-dessus les écraserait. On les reprend donc sous un préfixe distinct.
ssh melbaa "cd $MELBAA_DIR && tar cf - labels.part-*.jsonl manifeste.json" \
    | tar xf - -C "$LABELS" --transform 's/labels.part-/labels.part-melbaa-/' \
                            --transform 's/^manifeste.json$/manifeste.melbaa.json/' \
    && say "  parts de melbaa reprises sous labels.part-melbaa-*"

total=$(cat "$LABELS"/labels.part-*.jsonl 2>/dev/null | wc -l)
say "  corpus réuni : $total étiquettes (avant déduplication)"
if [ "$total" -lt 300000 ]; then
    say "⚠ moins de 300 000 étiquettes : le palier B1 de DS-14 en demande 400 000."
    say "  L'entraînement tourne quand même, et le rapport le dira."
fi

# ── 3. entraîner l'élève ────────────────────────────────────────────────
say "── entraînement de l'élève (GPU 1, from scratch)"
cd "$ROOT" || exit 1
CUDA_VISIBLE_DEVICES=1 python tools/train_t71.py \
    --labels "$LABELS" --out models/t71_b1.pt --bin models/t71_b1.bin
say "entraînement : code $?"

if [ ! -f models/t71_b1.bin ]; then
    say "REFUS — pas de .bin produit, la mesure n'a rien à juger. Arrêt."
    exit 1
fi

# ── 4. le verdict : l'élève sur le registre de T70 ──────────────────────
say "── le candidat B1 sur le registre arbitré (l'étalon incumbent est $ETALON)"
python bench/measure_t70.py \
    --registry "$REGISTRY" --model models/t71_b1.bin \
    --ply 2 --prune-model models/prune_32.bin --prune-k 12 \
    --workers 30 --label 'candidat B1 2-ply' \
    --out docs/mesures/t71-b1-t70-money.json
say "mesure du candidat : code $?"

say "── le même candidat au 0-ply, pour la lecture secondaire"
python bench/measure_t70.py \
    --registry "$REGISTRY" --model models/t71_b1.bin --ply 0 \
    --workers 30 --label 'candidat B1 0-ply' \
    --out docs/mesures/t71-b1-t70-money-0ply.json
say "mesure 0-ply : code $?"

# ── 5. rapatrier la mesure T73 si elle a tourné ─────────────────────────
if [ "$t73_started" -eq 1 ]; then
    scp -q melbaa:~/gammonNet-t71-labels/docs/mesures/t73-int8-t70-money.json \
        "$ROOT/docs/mesures/" 2>/dev/null \
        && say "mesure T73 int8 rapatriée" \
        || say "⚠ mesure T73 int8 non rapatriée — voir ~/t73-int8-t70.log sur melbaa"
fi

say "═══ suite terminée le $(date -Is) ═══"
say "Aucune étape 2 n'est engagée. Le palier B1 est un point d'arrêt de DS-14 :"
say "si le candidat ne bat pas l'incumbent à ce volume, la donnée supplémentaire"
say "ne sauve pas une idée neutre. C'est un humain qui lit ce verdict."
