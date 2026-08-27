#!/usr/bin/env bash
# T70 — la chaîne complète : corpus figé → arbitrage escaladé → étalon.
#
# À lancer DÉTACHÉ, la campagne durant des heures :
#
#     setsid nohup tools/campagne_t70.sh > /tmp/t70-campagne.log 2>&1 < /dev/null &
#
# Le script REFUSE de démarrer si une autre campagne tient déjà la machine :
# deux campagnes à 26 processus sur 32 cœurs ne vont pas deux fois plus vite,
# elles se volent leurs mesures et faussent les deux. `--force` passe outre,
# délibérément et par écrit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-/home/kunger/venv-gammonnet/bin/python}"
WORKERS="${WORKERS:-26}"
TARGET="${TARGET:-10000}"
CONTEXTS="${CONTEXTS:-money}"
WIDTH="${WIDTH:-6}"
OUT="${OUT:-docs/corpus/t70}"
FORCE="${1:-}"

busy() { pgrep -f 'run_t35.py|arbitrate_t70.py|build_corpus_t70.py' | grep -v "^$$\$" | head -1; }

if [ "$FORCE" != "--force" ] && [ -n "$(busy)" ]; then
    echo "REFUS — une campagne tient déjà la machine :"
    pgrep -af 'run_t35.py|arbitrate_t70.py|build_corpus_t70.py' | head -3
    echo "Attendre sa fin, ou relancer avec --force en sachant ce que cela coûte."
    exit 1
fi

echo "═══ T70 — campagne du $(date -Is) ═══"
echo "  $WORKERS processus, $TARGET décisions visées, contextes : $CONTEXTS"
echo "  charge au départ : $(uptime | sed 's/.*load average/load/')"
echo

echo "── 1/3  corpus figé ───────────────────────────────────────────"
"$PYTHON" -u tools/build_corpus_t70.py \
    --target "$TARGET" --contexts "$CONTEXTS" --width "$WIDTH" \
    --workers "$WORKERS" --out "$OUT"

for context in ${CONTEXTS//,/ }; do
    echo
    echo "── 2/3  arbitrage escaladé — $context ─────────────────────────"
    "$PYTHON" -u bench/arbitrate_t70.py \
        --corpus "$OUT/corpus-$context.jsonl" --workers "$WORKERS"

    echo
    echo "── 3/3  étalon : l'incumbent sur son propre registre — $context ─"
    # L'incumbent d'abord, toujours. Un registre où le moteur en place ne serait
    # PAS noté serait une échelle sans zéro : chaque candidat futur se lit comme
    # un écart à ce chiffre, jamais dans l'absolu.
    "$PYTHON" -u bench/measure_t70.py \
        --registry "$OUT/registre-$context.jsonl" --workers "$WORKERS" \
        --label "incumbent 2-ply" \
        --out "docs/mesures/t70-etalon-$context.json"
done

echo
echo "═══ terminé le $(date -Is) ═══"
