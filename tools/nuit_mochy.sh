#!/usr/bin/env bash
# La nuit du 2026-09-02 sur mochy, une fois les deux suites passées.
#
# Elle fait deux choses, dans cet ordre, et s'arrête.
#
# 1. **La courbe taille → qualité** (préparation de T72). Six architectures ont
#    été distillées du réseau actuel pendant que les processeurs étiquetaient ;
#    ce sont des `.bin` qui n'ont encore aucune force mesurée. Chacun est noté
#    sur le registre de T70, contre l'étalon 0,00313. Sans ces six points, T72
#    n'aurait aucun repère pour juger son propre résultat.
#
# 2. **La courbe volume → force** (le diagnostic que le palier B1 réclame). La
#    première tentative de T71 a rendu 0,00661 sur 162 864 étiquettes, deux fois
#    l'étalon. La question qui suit n'est pas « le candidat est-il bon » mais
#    « manque-t-il du volume ou de la recette », et seule une courbe y répond.
#    On entraîne donc le même élève sur des fractions croissantes du corpus
#    réuni (mochy + melbaa + smith) et on mesure chacune.
#
# Elle n'ouvre aucune étape 2 et ne décide rien : elle produit les points d'une
# courbe qu'un humain lira. Si la courbe s'aplatit loin de 0,00313, c'est la
# recette ; si elle descend encore, c'est le volume. Les deux réponses sont
# publiables, la fiche T71 le dit d'avance.
set -u

ROOT="/home/kunger/dev/gammonNet"
LOGS="/home/kunger/dev/gammonNet-logs"
LABELS="$ROOT/build/t71-money"
REGISTRY="$ROOT/docs/corpus/t70/money-10000/registre-money.jsonl"
SMITH_DIR="~/dev/gammonNet/build/t71-smith"
ETALON=0.00313

say() { echo "[$(date '+%m-%d %H:%M:%S')] $*"; }

busy() {
    [ "$(pgrep -cf 'suite_t71_repris[e]\.sh')" -gt 0 ] ||
    [ "$(pgrep -cf 'suite_t80_control[e]\.sh')" -gt 0 ] ||
    [ "$(pgrep -cf 'build_labels_t7[1]\.py')" -gt 0 ] ||
    [ "$(pgrep -cf 'measure_t7[0]\.py')" -gt 0 ] ||
    [ "$(pgrep -cf 'build_bearoff_decision[s]\.py')" -gt 0 ] ||
    [ "$(pgrep -cf 'train_bearoff_ne[t]\.py')" -gt 0 ]
}

cd "$ROOT" || exit 1
say "═══ nuit mochy — attente des deux suites ═══"
while busy; do sleep 300; done
say "la machine est rendue"

# ── 1. les six réseaux réduits, notés par l'instrument ──────────────────
say "── courbe taille → qualité : les réseaux réduits sur le registre de T70"
for net in models/t72prep_*.bin; do
    [ -f "$net" ] || continue
    name=$(basename "$net" .bin)
    out="docs/mesures/${name}-t70.json"
    if [ -f "$out" ]; then say "  $name : déjà mesuré"; continue; fi
    say "  $name"
    python bench/measure_t70.py \
        --registry "$REGISTRY" --model "$net" --ply 2 \
        --prune-model models/prune_32.bin --prune-k 12 \
        --workers 30 --label "$name 2-ply" --out "$out" \
        >> "$LOGS/t72prep-mesures.log" 2>&1
done
say "courbe taille → qualité : rendue"

# ── 2. rapatrier les étiquettes de smith, par tar renommant ─────────────
# JAMAIS de scp sur des parts homonymes : c'est ce qui a détruit 224 000
# étiquettes le 2026-09-02.
if ls "$LABELS"/labels.part-smith-*.jsonl >/dev/null 2>&1; then
    say "les parts de smith sont déjà là"
else
    say "── attente du couvre-feu de smith, puis rapatriement"
    while [ "$(ssh smith "pgrep -cf 'build_labels_t7[1][.]py'" 2>/dev/null | tail -1)" -gt 0 ] 2>/dev/null; do
        sleep 300
    done
    ssh smith "cd $SMITH_DIR && tar cf - labels.part-*.jsonl manifeste.json 2>/dev/null" \
        | tar xf - -C "$LABELS" --transform 's/labels.part-/labels.part-smith-/' \
                                --transform 's/^manifeste.json$/manifeste.smith.json/' \
        && say "  parts de smith reprises sous labels.part-smith-*"
fi

for part in "$LABELS"/labels.part-smith-*.jsonl; do
    [ -f "$part" ] || continue
    twin="${part/labels.part-smith-/labels.part-}"
    if [ -f "$twin" ] && cmp -s "$part" "$twin"; then
        say "REFUS — $(basename "$twin") est un clone de $(basename "$part"). Arrêt."
        exit 1
    fi
done

total=$(cat "$LABELS"/labels.part-*.jsonl 2>/dev/null | wc -l)
say "  corpus réuni : $total étiquettes (avant déduplication)"

# ── 3. la courbe volume → force ─────────────────────────────────────────
say "── courbe volume → force (étalon incumbent : $ETALON)"
for volume in 100000 200000 400000 800000 1600000; do
    [ "$volume" -gt "$total" ] && { say "  $volume : au-delà du corpus, sauté"; continue; }
    tag="t71_v${volume}"
    out="docs/mesures/${tag}-t70.json"
    if [ -f "$out" ]; then say "  $volume : déjà mesuré"; continue; fi

    say "  $volume étiquettes — entraînement"
    CUDA_VISIBLE_DEVICES=1 python tools/train_t71.py \
        --labels "$LABELS" --limit "$volume" \
        --out "models/${tag}.pt" --bin "models/${tag}.bin" \
        >> "$LOGS/t71-courbe.log" 2>&1
    if [ ! -f "models/${tag}.bin" ]; then
        say "  ⚠ pas de .bin à $volume — on passe au suivant"
        continue
    fi

    say "  $volume étiquettes — mesure"
    python bench/measure_t70.py \
        --registry "$REGISTRY" --model "models/${tag}.bin" --ply 2 \
        --prune-model models/prune_32.bin --prune-k 12 \
        --workers 30 --label "candidat $volume 2-ply" --out "$out" \
        >> "$LOGS/t71-courbe.log" 2>&1
    say "  $volume : $(python -c "
import json;d=json.load(open('$out'));print(f\"{d['loss']:.5f} [{d['ci95'][0]:.5f} ; {d['ci95'][1]:.5f}]  hors registre {d['outside_rate']*100:.2f} %\")" 2>/dev/null || echo 'lecture impossible')"
done

say "═══ nuit terminée le $(date -Is) ═══"
say "Deux courbes sont rendues, aucune décision n'est prise. Si la courbe"
say "volume → force s'aplatit loin de $ETALON, c'est la recette et non le"
say "volume — et c'est un résultat publiable, pas un échec à cacher."
