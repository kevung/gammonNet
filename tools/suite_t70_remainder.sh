#!/usr/bin/env bash
# T70 — la suite après les deux derniers lots (mochy, melbaa) : fusionner,
# puis rejouer la fin de campagne_t70_v2.sh pour le contexte money.
#
#     setsid nohup tools/suite_t70_remainder.sh \
#         > /home/kunger/dev/gammonNet-logs/t70-suite-remainder.log 2>&1 < /dev/null &
#
# ## Pourquoi ce script, plutôt que relancer campagne_t70_v2.sh
#
# Le corpus money-10000 a été arbitré en QUATRE morceaux disjoints, pas un
# seul run de `bench/arbitrate_t70.py` : le journal principal (3162, arrêté
# le 2026-08-28), le lot déjà fait sur mochy avant que smith soit rendue
# (1812, sur un fichier corpus SÉPARÉ `corpus-money-split-mochy.jsonl`), et
# les deux moitiés du reliquat (2513 + 2513, lancées le 2026-09-01 sur mochy
# et melbaa) une fois melbaa recompilé sur le MÊME tarball source que mochy
# (gnubg 1.08.003, build 20250313 des deux côtés — le désaccord ±0,005 PR
# mesuré en T3E venait de la source, pas du CPU : les deux se compilent avec
# les mêmes drapeaux SIMD -mavx malgré l'AVX2 disponible sur melbaa).
#
# `campagne_t70_v2.sh` ne sait fusionner que des corpus, pas des registres
# venus de runs séparés. Ce script fait cette fusion, PUIS rejoue exactement
# la fin de la phase B de `campagne_t70_v2.sh` (biais passe 1, étalon,
# carte T77, étape 0 de T71) sur le résultat.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-/home/kunger/venv-gammonnet/bin/python}"
T71="${T71:-/home/kunger/dev/gammonNet-t71}"
LOG="${LOG:-/home/kunger/dev/gammonNet-logs/t70-suite-remainder.log}"
WORKERS="${WORKERS:-30}"
MELBAA="${MELBAA:-kunger@melbaa}"
MELBAA_DIR="${MELBAA_DIR:-~/gammonNet-t70-arb}"

OUT="docs/corpus/t70/money-10000"
CORPUS="$OUT/corpus-money.jsonl"
REGISTRY="$OUT/registre-money.jsonl"

say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

mkdir -p docs/mesures "$(dirname "$LOG")"
say "═══ suite T70 — reliquat money : attente de la fin des deux campagnes ═══"

while pgrep -f 'arbitrate_t70[.]py.*remainder-mochy' > /dev/null; do
    sleep 300
done
say "mochy : arbitrage terminé"

while ssh "$MELBAA" 'pgrep -f "arbitrate_t70.py.*remainder-melbaa"' > /dev/null 2>&1; do
    sleep 300
done
say "melbaa : arbitrage terminé (ou injoignable — à vérifier si la suite échoue)"

say "── rapatriement du registre melbaa"
if ! scp -q "$MELBAA:$MELBAA_DIR/$OUT/registre-t70-remainder-melbaa.jsonl" \
        "$OUT/registre-t70-remainder-melbaa.jsonl"; then
    say "✗ rapatriement échoué — arrêt, rien d'automatique après"
    exit 1
fi
say "  $(wc -l < "$OUT/registre-t70-remainder-melbaa.jsonl") lignes rapatriées"

say "── fusion des quatre sources, dédoublonnée par index"
"$PYTHON" - "$OUT" <<'PYEOF' || { say "✗ fusion refusée — arrêt"; exit 1; }
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
sources = [
    out / "registre-money.jsonl.journal",
    out / "registre-money-split-mochy.jsonl",
    out / "registre-t70-remainder-mochy.jsonl",
    out / "registre-t70-remainder-melbaa.jsonl",
]
records = {}
for src in sources:
    if not src.exists():
        print(f"  absent, ignoré : {src.name}")
        continue
    n = 0
    for line in src.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if "index" not in row:
            continue  # la ligne d'en-tête d'un .journal
        records[row["index"]] = row
        n += 1
    print(f"  {src.name} : {n} lignes")

corpus_idx = {
    json.loads(line)["index"]
    for line in (out / "corpus-money.jsonl").read_text().splitlines()
    if line.strip()
}
missing = corpus_idx - records.keys()
extra = records.keys() - corpus_idx
print(f"fusion : {len(records)} décisions, {len(missing)} manquantes, {len(extra)} en trop")
if missing:
    print(f"REFUS — {len(missing)} décisions manquantes : {sorted(missing)[:10]}...",
          file=sys.stderr)
    sys.exit(1)

dest = out / "registre-money.jsonl"
with dest.open("w") as fh:
    for idx in sorted(records):
        fh.write(json.dumps(records[idx], sort_keys=True) + "\n")
print(f"→ {dest} : {len(records)} décisions")
PYEOF
say "fusion : registre-money.jsonl complet ($(wc -l < "$REGISTRY") lignes)"

say "── biais de la passe 1"
"$PYTHON" -u bench/audit_pass1_t70.py --registry "$REGISTRY" \
    --out docs/mesures/t70-biais-passe1-money.json

say "── étalon : l'incumbent sur son propre registre"
"$PYTHON" -u bench/measure_t70.py \
    --registry "$REGISTRY" --workers "$WORKERS" --label "incumbent 2-ply" \
    --out docs/mesures/t70-etalon-money.json

say "── carte d'erreur T77"
"$PYTHON" -u bench/error_map_t77.py \
    --scores docs/mesures/t70-etalon-money.json \
    --manifest "$OUT/manifeste.json" \
    --out docs/mesures/t77-carte-money.json

say "── T71 étape 0 : le professeur bat-il l'élève ?"
( cd "$T71" && "$PYTHON" -u bench/etape0_t71.py \
    --registry "$ROOT/$REGISTRY" --workers "$WORKERS" \
    --out docs/mesures/t71-etape0-money.json )
code=$?
say "T71 étape 0 : code $code (0 = professeur confirmé)"
say "═══ suite terminée le $(date -Is) ═══"
say "Aucun entraînement n'est lancé. La QAT de T73 et l'étape 1 de T71"
say "attendent la lecture d'un verdict par un humain."
