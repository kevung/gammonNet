#!/usr/bin/env bash
# T70 — la campagne conséquente : 30 000 décisions, construites par tranches.
#
#     setsid nohup tools/campagne_t70_tranches.sh > /home/kunger/dev/gammonNet-logs/t70-campagne.log 2>&1 < /dev/null &
#
# ## Pourquoi des tranches
#
# Le générateur de corpus n'est pas reprenable : il accumule en mémoire et
# n'écrit qu'à la fin. Une construction de vingt heures interrompue à la
# dix-neuvième coûte les dix-neuf. On construit donc SIX tranches indépendantes
# de 5 000 décisions — trois à quatre heures chacune, chacune perdable sans
# conséquence — puis on les fusionne. `merge_corpus_t70.py` recalcule les poids
# sur le corpus RÉUNI, renumérote les index et écarte les doublons : un `cat`
# rendrait un fichier lisible et faux sur les trois points.
#
# Ce script est lui-même reprenable **à la tranche près** : une tranche dont le
# corpus existe déjà est sautée. Le relancer après une coupure reprend où il en
# était, sans rien recalculer de ce qui est payé.
#
# ## L'ordre, et pourquoi le contrôle de non-biais n'est plus en tête
#
# `campagne_t70.sh` place le contrôle de l'arbitre en étape 0, avant tout. La
# raison est bonne — « un arbitre qu'on n'a pas vérifié n'arbitre rien » — mais
# ce qu'il protège, c'est l'ARBITRAGE, pas la récolte : construire le corpus
# n'appelle jamais l'arbitre. Il est donc placé ici juste avant l'arbitrage,
# où il garde exactement le même pouvoir d'arrêt, sans faire attendre vingt
# heures de récolte derrière lui.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-/home/kunger/venv-gammonnet/bin/python}"
T71="${T71:-/home/kunger/dev/gammonNet-t71}"
WORKERS="${WORKERS:-26}"
CONTEXT="${CONTEXT:-money}"
SLICES="${SLICES:-6}"
PER_SLICE="${PER_SLICE:-5000}"
EXAMINE="${EXAMINE:-22}"
WIDTH="${WIDTH:-6}"
#: Les graines des tranches sont espacées d'un million. Le générateur donne au
#: worker `i` la graine `seed + 7919*i` : à 26 processus, une tranche occupe
#: 198 000 valeurs. Un million laisse cinq fois la marge nécessaire pour que
#: deux tranches ne récoltent jamais les mêmes positions.
SEED_BASE="${SEED_BASE:-20260827}"
SEED_STEP="${SEED_STEP:-1000000}"

TRANCHES="docs/corpus/t70/tranches"
OUT="docs/corpus/t70"
LOGS="${LOGS:-/home/kunger/dev/gammonNet-logs}"
mkdir -p "$TRANCHES" "$OUT" "$LOGS" docs/mesures

say() { echo "[$(date +%m-%d\ %H:%M:%S)] $*"; }

say "═══ T70 — campagne conséquente : $SLICES × $PER_SLICE décisions ═══"
say "  $WORKERS processus, contexte $CONTEXT, facteur d'examen $EXAMINE"

# Une tranche peut déjà tourner (lancée à la main pour ne pas laisser la machine
# inoccupée pendant l'écriture de ce script). On l'attend plutôt que de lancer
# une seconde récolte par-dessus.
while pgrep -f 'python.*build_corpus_t70[.]py' | grep -qv "^$$\$"; do
    say "  une récolte est déjà en cours — on l'attend"
    sleep 300
done

# ── 1/6  les tranches ──────────────────────────────────────────────────────
for n in $(seq 1 "$SLICES"); do
    tag=$(printf "tranche-%02d" "$n")
    corpus="$TRANCHES/$tag/corpus-$CONTEXT.jsonl"
    if [ -s "$corpus" ]; then
        say "── $tag : déjà récoltée ($(wc -l < "$corpus") décisions), sautée"
        continue
    fi
    seed=$((SEED_BASE + n * SEED_STEP))
    say "── $tag : récolte de $PER_SLICE décisions, graine $seed"
    "$PYTHON" -u tools/build_corpus_t70.py \
        --target "$PER_SLICE" --contexts "$CONTEXT" --width "$WIDTH" \
        --workers "$WORKERS" --examine-factor "$EXAMINE" --seed "$seed" \
        --out "$TRANCHES/$tag" > "$LOGS/t70-$tag.log" 2>&1
    code=$?
    if [ "$code" -ne 0 ] || [ ! -s "$corpus" ]; then
        say "  ✗ $tag a échoué (code $code) — voir $LOGS/t70-$tag.log"
        say "    Les tranches déjà récoltées sont conservées : relancer ce"
        say "    script reprendra à celle-ci."
        exit 1
    fi
    say "  ✓ $tag : $(wc -l < "$corpus") décisions"
done

# ── 2/6  la fusion ─────────────────────────────────────────────────────────
say ""
say "── fusion des tranches ────────────────────────────────────────"
"$PYTHON" -u tools/merge_corpus_t70.py --context "$CONTEXT" --out "$OUT" \
    "$TRANCHES"/tranche-* || { say "✗ fusion échouée"; exit 1; }
CORPUS="$OUT/corpus-$CONTEXT.jsonl"
say "  corpus réuni : $(wc -l < "$CORPUS") décisions"

# ── 3/6  le contrôle de non-biais, juste avant l'arbitrage ─────────────────
say ""
say "── contrôle de non-biais de l'arbitre ─────────────────────────"
"$PYTHON" -u bench/arbiter_bias_t70.py \
    --decisions "${BIAS_DECISIONS:-60}" --truncate "${TRUNCATE:-9}" \
    --workers "$WORKERS" --out docs/mesures/t70-non-biais.json
bias=$?
if [ "$bias" -ne 0 ]; then
    say ""
    say "  ✗ L'ARBITRE NE PASSE PAS SON PROPRE CONTRÔLE. Aucun arbitrage ne"
    say "    tourne avec ces réglages (T39, règle reprise par T70). Le corpus"
    say "    récolté est conservé : il ne dépend pas de l'arbitre."
    exit "$bias"
fi

# ── 4/6  l'arbitrage, reprenable ───────────────────────────────────────────
say ""
say "── arbitrage escaladé ─────────────────────────────────────────"
"$PYTHON" -u bench/arbitrate_t70.py \
    --corpus "$CORPUS" --workers "$WORKERS" --chunk "${CHUNK:-64}" \
    --truncate "${TRUNCATE:-9}" --deep-truncate "${DEEP_TRUNCATE:-21}" \
    || { say "✗ arbitrage interrompu — le journal est conservé, relancer ce"
         say "  script reprendra les décisions manquantes."; exit 1; }
REGISTRY="$OUT/registre-$CONTEXT.jsonl"

# ── 5/6  l'étalon et la carte d'erreur ─────────────────────────────────────
say ""
say "── étalon : l'incumbent sur son propre registre ────────────────"
"$PYTHON" -u bench/measure_t70.py \
    --registry "$REGISTRY" --workers "$WORKERS" --label "incumbent 2-ply" \
    --out "docs/mesures/t70-etalon-$CONTEXT.json" || exit 1

say ""
say "── carte d'erreur par classe (T77) ─────────────────────────────"
"$PYTHON" -u bench/error_map_t77.py \
    --scores "docs/mesures/t70-etalon-$CONTEXT.json" \
    --manifest "$OUT/manifeste.json" \
    --out "docs/mesures/t77-carte-$CONTEXT.json" || exit 1

# ── 6/6  T71 étape 0 ───────────────────────────────────────────────────────
say ""
say "── T71 étape 0 : le professeur bat-il l'élève ? ────────────────"
( cd "$T71" && "$PYTHON" -u bench/etape0_t71.py \
    --registry "$ROOT/$REGISTRY" --workers "$WORKERS" \
    --out "docs/mesures/t71-etape0-$CONTEXT.json" )
etape0=$?

say ""
say "═══ campagne terminée ═══"
say "  registre    : $REGISTRY ($(wc -l < "$REGISTRY") décisions)"
say "  étalon      : docs/mesures/t70-etalon-$CONTEXT.json"
say "  carte T77   : docs/mesures/t77-carte-$CONTEXT.json"
say "  T71 étape 0 : code $etape0 (0 = professeur confirmé)"
say ""
say "  Aucun entraînement n'est lancé. La QAT de T73 et l'étape 1 de T71"
say "  attendent la lecture d'un verdict par un humain."
exit 0
