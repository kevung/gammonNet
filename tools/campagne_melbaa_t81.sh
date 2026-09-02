#!/usr/bin/env bash
# melbaa, la nuit du 2026-09-02 : le corpus T80, puis les étiquettes T81.
#
# melbaa est libre et sans couvre-feu. Elle enchaîne deux travaux qui ne se
# gênent pas :
#
# 1. le corpus d'un million de décisions de bearoff que le contrôle de T80
#    attend (en cours à l'appel de ce script) ;
# 2. les étiquettes cubeful par rollout de T81 — la marche basse de l'axe
#    « videau appris », celle qui RÉFUTE en heures au lieu de confirmer en
#    semaines (ADR 0002).
#
# Le coût d'une étiquette T81 a été MESURÉ, pas extrapolé : 98 s·cœur sur une
# machine par ailleurs saturée, donc une borne haute. 5 000 étiquettes tiennent
# dans la nuit ; c'est le volume retenu, et le manifeste portera le coût réel.
set -u

ROOT="$HOME/gammonNet-t71-labels"
LOG="$HOME/melbaa-nuit.log"
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

cd "$ROOT" || exit 1

say "═══ melbaa — corpus T80 puis étiquettes T81 ═══"

# ── 1. attendre le corpus de décisions de bearoff ───────────────────────
while [ "$(pgrep -cf 'build_bearoff_decision[s]\.py')" -gt 0 ]; do sleep 120; done
if [ -f build/bearoff_decisions.npz ]; then
    say "corpus T80 prêt : $(du -h build/bearoff_decisions.npz | cut -f1)"
else
    say "⚠ corpus T80 absent — voir ~/t80-corpus.log. On enchaîne quand même."
fi

# ── 2. les étiquettes cubeful de T81 ────────────────────────────────────
say "── T81 : étiquettes cubeful par rollout, 5 000 positions, 24 processus"
~/venv-gn/bin/python tools/build_labels_t81.py \
    --count 5000 --workers 24 --out build/t81-cubeful \
    >> "$LOG" 2>&1
say "T81 : code $?"

produced=$(cat build/t81-cubeful/labels.part-*.jsonl 2>/dev/null | wc -l)
say "  $produced étiquettes cubeful produites"
say "═══ nuit terminée le $(date -Is) ═══"
say "Rien n'est entraîné ici. B0 contre B est une décision qui se prend sur le"
say "coût mesuré, pas sur l'enthousiasme d'avoir des étiquettes."
