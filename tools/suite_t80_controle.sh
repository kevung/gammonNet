#!/usr/bin/env bash
# T80 — le contrôle à une seule variable, quand les processeurs se libèrent.
#
# Le premier entraînement T80 a dégradé la colonne cubeless au banc de T78
# (pire cas 0,0014 → 0,0094). La règle de diagnostic de la fiche nomme ce
# symptôme « interférence entre têtes » — mais DEUX choses avaient changé, pas
# une : quatre sorties au lieu d'une, ET l'étage d'affinage par décision de coup
# absent, faute de processeurs pour produire son corpus.
#
# Ce script rétablit la condition « une seule chose change à la fois » : même
# gabarit, même graine, même budget, l'étage de décision de coup EN PLUS. Si la
# queue reste à 0,0094, l'interférence devient une cause mesurée ; si elle
# revient sous 0,0023, elle n'a jamais existé et c'était l'étage qui manquait.
#
# Il attend que la suite T71 ait rendu la machine : deux campagnes en parallèle
# divisent le débit et fausseraient les deux.
set -u

ROOT="/home/kunger/dev/gammonNet"
LOGS="/home/kunger/dev/gammonNet-logs"
CORPUS="$ROOT/build/bearoff_decisions.npz"
NET="$ROOT/models/bearoff_cubeful_code16_256_128_dec.bin"

say() { echo "[$(date '+%m-%d %H:%M:%S')] $*"; }

# Les motifs ne peuvent pas se matcher eux-mêmes : le garde compte les calculs,
# jamais les shells qui les nomment (piège du 2026-08-27).
busy() {
    [ "$(pgrep -cf 'suite_t71_etape[1]\.sh')" -gt 0 ] ||
    [ "$(pgrep -cf 'build_labels_t7[1]\.py')" -gt 0 ] ||
    [ "$(pgrep -cf 'measure_t7[0]\.py')" -gt 0 ]
}

say "═══ contrôle T80 — attente de la fin de la suite T71 ═══"
while busy; do sleep 300; done
say "la machine est rendue"

cd "$ROOT" || exit 1

# ── 1. le corpus de décisions de fin de partie ──────────────────────────
if [ -f "$CORPUS" ]; then
    say "corpus de décisions déjà présent : $CORPUS"
else
    say "── corpus de décisions de bearoff (1 M décisions, 30 processus)"
    python tools/build_bearoff_decisions.py --decisions 1000000 --workers 30 \
        --matrix build/ts6x11_cubeful.u16 --out "$CORPUS"
    say "corpus : code $?"
fi
[ -f "$CORPUS" ] || { say "REFUS — pas de corpus, rien à contrôler."; exit 1; }

# ── 2. le même entraînement, l'étage de décision en plus ────────────────
say "── réentraînement : même gabarit, même graine, l'étage de décision EN PLUS"
CUDA_VISIBLE_DEVICES=1 python tools/train_bearoff_net.py \
    --matrix build/ts6x11_cubeful.u16 --sides build/ts6x11_sides.npy \
    --hidden 256,128 --embedding 16 --output tanh --device cuda \
    --steps 40000 --mine-rounds 3 \
    --decision-corpus "$CORPUS" --decision-steps 8000 \
    --cube-steps 12000 \
    --out "$NET" --log "$LOGS/t80-controle-train.log"
say "entraînement : code $?"
[ -f "$NET" ] || { say "REFUS — pas de réseau produit."; exit 1; }

# ── 3. les deux bancs, aux graines et volumes de la première mesure ─────
say "── banc de T78 : la colonne cubeless a-t-elle retrouvé sa queue ?"
python bench/bearoff_distill.py --decisions 8000 --workers 30 --net "$NET" \
    --plies 0,1 --out docs/mesures/t80-controle-cubeless-decisions.json
say "banc cubeless : code $?"

say "── banc de videau, aux deux volumes"
python bench/cube_at_depth.py --positions 2000 --workers 30 --plies 0,1 \
    --net "$NET" --out docs/mesures/t80-controle-cube-2000.json
python bench/cube_at_depth.py --positions 20000 --workers 30 --plies 0,1 \
    --net "$NET" --out docs/mesures/t80-controle-cube-20000.json
say "bancs de videau : code $?"

say "═══ contrôle terminé le $(date -Is) ═══"
say "À lire ensemble : t80-controle-cubeless-decisions.json contre"
say "t80-colonne-cubeless-decisions.json (pire cas 0,0094) et contre le repère"
say "de T78 (0,0014). C'est ce qui tranche entre « interférence entre têtes » et"
say "« il manquait un étage » — et aucun des deux ne s'affirme sans ce chiffre."
