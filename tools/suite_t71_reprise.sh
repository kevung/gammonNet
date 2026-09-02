#!/usr/bin/env bash
# T71 étape 1 — la reprise, après l'incident de rapatriement du 2026-09-02.
#
# Ce que la première suite a fait de travers : un `scp melbaa:.../labels.part-*`
# avant le tar de renommage. Les deux machines numérotent leurs parts de la
# même façon, donc 24 des 30 parts de mochy ont été écrasées par celles de
# melbaa — 224 000 étiquettes perdues, 133 134 doublons créés, aucun message
# d'erreur. L'élève a été entraîné sur 162 864 positions distinctes au lieu de
# ~390 000, et son verdict (0,00661 contre l'étalon 0,00313) ne vaut donc PAS
# pour le palier B1, qui demande 400 000.
#
# Ce script attend la régénération (déterministe : même graine, même nombre de
# processus, mêmes positions), rapatrie CORRECTEMENT, réentraîne et remesure.
# La mesure T73 int8 n'est pas refaite : elle est rendue
# (docs/mesures/t73-int8-t70-money.json, 0,00373).
set -u

ROOT="/home/kunger/dev/gammonNet"
LABELS="$ROOT/build/t71-money"
MELBAA_DIR="~/gammonNet-t71-labels/build/t71-money"
REGISTRY="$ROOT/docs/corpus/t70/money-10000/registre-money.jsonl"
ETALON=0.00313

say() { echo "[$(date '+%m-%d %H:%M:%S')] $*"; }

say "═══ reprise T71 étape 1 — attente de la régénération des parts perdues ═══"
while [ "$(pgrep -cf 'build_labels_t7[1]\.py')" -gt 0 ]; do sleep 300; done
say "étiquetage terminé"

cd "$ROOT" || exit 1

# ── rapatriement, par tar renommant, et RIEN d'autre ────────────────────
if ls "$LABELS"/labels.part-melbaa-*.jsonl >/dev/null 2>&1; then
    say "les parts de melbaa sont déjà là, on ne les reprend pas"
else
    say "── rapatriement des étiquettes de melbaa (tar renommant, jamais scp)"
    ssh melbaa "cd $MELBAA_DIR && tar cf - labels.part-*.jsonl manifeste.json" \
        | tar xf - -C "$LABELS" --transform 's/labels.part-/labels.part-melbaa-/' \
                                --transform 's/^manifeste.json$/manifeste.melbaa.json/'
fi

# ── le garde qui manquait : aucune part de mochy ne doit être un clone ──
for part in "$LABELS"/labels.part-melbaa-*.jsonl; do
    twin="${part/labels.part-melbaa-/labels.part-}"
    if [ -f "$twin" ] && cmp -s "$part" "$twin"; then
        say "REFUS — $(basename "$twin") est identique à $(basename "$part")."
        say "  L'écrasement du 2026-09-02 s'est reproduit. Arrêt."
        exit 1
    fi
done

mochy=$(cat "$LABELS"/labels.part-0*.jsonl 2>/dev/null | wc -l)
melbaa=$(cat "$LABELS"/labels.part-melbaa-*.jsonl 2>/dev/null | wc -l)
say "  mochy : $mochy étiquettes   melbaa : $melbaa   total : $((mochy + melbaa))"
if [ "$((mochy + melbaa))" -lt 380000 ]; then
    say "⚠ moins de 380 000 : le palier B1 en demande 400 000. Le rapport le dira."
fi

# ── entraîner, puis juger ───────────────────────────────────────────────
say "── entraînement de l'élève (GPU 1, from scratch)"
CUDA_VISIBLE_DEVICES=1 python tools/train_t71.py \
    --labels "$LABELS" --out models/t71_b1.pt --bin models/t71_b1.bin
say "entraînement : code $?"
[ -f models/t71_b1.bin ] || { say "REFUS — pas de .bin produit."; exit 1; }

say "── le candidat B1 sur le registre arbitré (étalon incumbent : $ETALON)"
python bench/measure_t70.py \
    --registry "$REGISTRY" --model models/t71_b1.bin \
    --ply 2 --prune-model models/prune_32.bin --prune-k 12 \
    --workers 30 --label 'candidat B1 2-ply' \
    --out docs/mesures/t71-b1-t70-money.json
say "mesure 2-ply : code $?"

say "── le même candidat au 0-ply, pour la lecture secondaire"
python bench/measure_t70.py \
    --registry "$REGISTRY" --model models/t71_b1.bin --ply 0 \
    --workers 30 --label 'candidat B1 0-ply' \
    --out docs/mesures/t71-b1-t70-money-0ply.json
say "mesure 0-ply : code $?"

say "═══ reprise terminée le $(date -Is) ═══"
say "Le palier B1 est un point d'arrêt de DS-14. Si le candidat ne bat pas"
say "l'incumbent À CE VOLUME, la donnée supplémentaire ne sauve pas une idée"
say "neutre — et c'est un humain qui lit ce verdict, pas ce script."
