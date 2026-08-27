#!/usr/bin/env bash
# T70 — la campagne complète : money + les quatre contextes de score.
#
#     setsid nohup tools/campagne_t70_v2.sh > /home/kunger/dev/gammonNet-logs/t70-campagne.log 2>&1 < /dev/null &
#
# ## Ce qui change par rapport à la v1 : la traîne, mesurée
#
# Une récolte de 5 000 décisions à 26 processus finit avec la moitié de ses
# processus à l'arrêt. Mesuré le 2026-08-27 à 148 min d'une tranche : 15 des 26
# processus muets depuis 10 à 23 minutes, 224 cœur·minutes perdues sur 3 856
# — 6 % et en hausse. La cause est structurelle : chaque processus s'arrête
# quand SES quotas sont pleins, et les derniers chassent les classes rares
# pendant que les autres n'ont plus rien à faire. Le pool les garde en vie, d'où
# une apparence trompeuse : 26 processus dans `ps`, et une charge de 5.
#
# On lance donc DEUX récoltes de front, à 13 processus chacune. Elles ne
# finissent pas ensemble — c'est le but : la traîne de l'une est couverte par le
# plein régime de l'autre, et dès qu'une place se libère, la suivante démarre.
# Gain attendu : la moitié environ des 6-10 % perdus. Ce n'est pas spectaculaire,
# et c'est écrit ici pour que personne n'en attende davantage.
#
# ## L'ordre
#
#   A. toutes les récoltes, deux de front, prises dans une file ;
#   B. puis, contexte par contexte : fusion → contrôle de non-biais →
#      arbitrage → **audit du biais de passe 1** → étalon → carte T77.
#
# La phase B est séquentielle : l'arbitrage sature les 26 processus à lui seul.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-/home/kunger/venv-gammonnet/bin/python}"
T71="${T71:-/home/kunger/dev/gammonNet-t71}"
LOGS="${LOGS:-/home/kunger/dev/gammonNet-logs}"
WORKERS="${WORKERS:-26}"
PARALLEL="${PARALLEL:-2}"
JOB_WORKERS="${JOB_WORKERS:-13}"
EXAMINE="${EXAMINE:-22}"
WIDTH="${WIDTH:-6}"
PER_SLICE="${PER_SLICE:-5000}"
SEED_BASE="${SEED_BASE:-20260827}"

TRANCHES="docs/corpus/t70/tranches"
mkdir -p "$TRANCHES" "$LOGS" docs/mesures

say() { echo "[$(date +%m-%d\ %H:%M:%S)] $*"; }

#: money à 30 000 (six tranches), chaque contexte de score à 10 000 (deux).
#: Les contextes de score sont plus petits parce que la fiche les demande pour
#: la STRATIFICATION, pas pour la sensibilité : c'est money qui doit voir un
#: gain modeste par décision, et money seul porte l'étalon de T71.
CONTEXTS_MONEY="money:6"
CONTEXTS_MATCH="2a-2a:2 3a-3a:2 4a-2a:2 2a-4a:2"
ALL="$CONTEXTS_MONEY $CONTEXTS_MATCH"

#: Les graines : espacées d'un million entre tranches (le générateur donne au
#: processus `i` la graine `seed + 7919*i`, soit 103 000 valeurs à 13 processus)
#: et de cent millions entre contextes. Aucune collision possible.
seed_for() {
    local ctx="$1" slice="$2" rank=0
    for entry in $ALL; do
        [ "${entry%%:*}" = "$ctx" ] && break
        rank=$((rank + 1))
    done
    echo $((SEED_BASE + rank * 100000000 + slice * 1000000))
}

harvest() {
    local ctx="$1" slice="$2"
    local tag; tag=$(printf "%s-%02d" "$ctx" "$slice")
    local dir="$TRANCHES/$tag"
    local seed; seed=$(seed_for "$ctx" "$slice")
    say "  ▶ $tag démarre ($JOB_WORKERS processus, graine $seed)"
    T70_CORPUS_PROGRESS="/tmp/t70-progress-$tag.log" \
    "$PYTHON" -u tools/build_corpus_t70.py \
        --target "$PER_SLICE" --contexts "$ctx" --width "$WIDTH" \
        --workers "$JOB_WORKERS" --examine-factor "$EXAMINE" --seed "$seed" \
        --out "$dir" > "$LOGS/t70-$tag.log" 2>&1
    local code=$?
    if [ "$code" -eq 0 ] && [ -s "$dir/corpus-$ctx.jsonl" ]; then
        say "  ✓ $tag : $(wc -l < "$dir/corpus-$ctx.jsonl") décisions"
    else
        say "  ✗ $tag a échoué (code $code) — voir $LOGS/t70-$tag.log"
    fi
}

say "═══ T70 — campagne complète : money 30 000 + quatre contextes à 10 000 ═══"
say "  phase A : récoltes, $PARALLEL de front à $JOB_WORKERS processus"

# Une récolte de la v1 peut encore tourner à 26 processus : on l'attend, sinon
# on lancerait 26 + 26 sur 32 cœurs et les deux iraient moins vite que l'une.
while pgrep -f 'python.*build_corpus_t70[.]py' > /dev/null; do
    say "  une récolte de la campagne précédente tourne encore — on l'attend"
    sleep 300
done

# ── PHASE A : la file des récoltes ─────────────────────────────────────────
running=0
for entry in $ALL; do
    ctx="${entry%%:*}"; count="${entry##*:}"
    for slice in $(seq 1 "$count"); do
        tag=$(printf "%s-%02d" "$ctx" "$slice")
        if [ -s "$TRANCHES/$tag/corpus-$ctx.jsonl" ]; then
            say "  $tag : déjà récoltée, sautée"
            continue
        fi
        # v1 nommait les tranches money « tranche-NN ». On les reconnaît.
        legacy=$(printf "tranche-%02d" "$slice")
        if [ "$ctx" = "money" ] && [ -s "$TRANCHES/$legacy/corpus-money.jsonl" ]; then
            say "  $tag : déjà récoltée sous $legacy, sautée"
            continue
        fi
        while [ "$running" -ge "$PARALLEL" ]; do
            wait -n
            running=$((running - 1))
        done
        harvest "$ctx" "$slice" &
        running=$((running + 1))
    done
done
wait
say "── phase A terminée : toutes les récoltes sont faites"

# ── PHASE B : par contexte, la chaîne complète ─────────────────────────────
for entry in $ALL; do
    ctx="${entry%%:*}"
    OUT="docs/corpus/t70/$ctx"
    say ""
    say "═══ contexte $ctx ═══"

    say "── fusion des tranches"
    slices=$(ls -d "$TRANCHES"/${ctx}-* 2>/dev/null || true)
    [ "$ctx" = "money" ] && slices="$slices $(ls -d "$TRANCHES"/tranche-* 2>/dev/null || true)"
    if [ -z "$slices" ]; then say "  ✗ aucune tranche pour $ctx"; continue; fi
    "$PYTHON" -u tools/merge_corpus_t70.py --context "$ctx" --out "$OUT" $slices \
        || { say "  ✗ fusion échouée"; continue; }
    CORPUS="$OUT/corpus-$ctx.jsonl"

    say "── cohérence des tranches"
    "$PYTHON" -u tools/coherence_t70.py --context "$ctx" $slices || true

    if [ "$ctx" = "money" ]; then
        say "── contrôle de non-biais de l'arbitre"
        # Une fois pour toutes : l'arbitre est le même quel que soit le
        # contexte, et son contrôle s'appuie sur les tables exactes, qui sont
        # cubeless — donc money.
        "$PYTHON" -u bench/arbiter_bias_t70.py \
            --decisions "${BIAS_DECISIONS:-60}" --truncate "${TRUNCATE:-9}" \
            --workers "$WORKERS" --out docs/mesures/t70-non-biais.json
        if [ $? -ne 0 ]; then
            say "  ✗ L'ARBITRE NE PASSE PAS SON PROPRE CONTRÔLE — aucun arbitrage"
            say "    ne tourne avec ces réglages (T39, règle reprise par T70)."
            exit 1
        fi
    fi

    say "── arbitrage escaladé ($ctx)"
    "$PYTHON" -u bench/arbitrate_t70.py \
        --corpus "$CORPUS" --workers "$WORKERS" --chunk "${CHUNK:-64}" \
        --truncate "${TRUNCATE:-9}" --deep-truncate "${DEEP_TRUNCATE:-21}" \
        || { say "  ✗ arbitrage interrompu — le journal est conservé, relancer"
             say "    ce script reprendra les décisions manquantes."; continue; }
    REGISTRY="$OUT/registre-$ctx.jsonl"

    # Le critère d'acceptation de T70 demande que le biais de la passe 1 soit
    # « chiffré et publié AVEC CHAQUE USAGE de l'instrument ». Il est donc
    # produit ici, à côté du registre, et non sur demande.
    say "── biais de la passe 1 ($ctx)"
    "$PYTHON" -u bench/audit_pass1_t70.py --registry "$REGISTRY" \
        --out "docs/mesures/t70-biais-passe1-$ctx.json" || true

    say "── étalon : l'incumbent sur son propre registre ($ctx)"
    "$PYTHON" -u bench/measure_t70.py \
        --registry "$REGISTRY" --workers "$WORKERS" --label "incumbent 2-ply" \
        --out "docs/mesures/t70-etalon-$ctx.json" || continue

    say "── carte d'erreur par classe, T77 ($ctx)"
    "$PYTHON" -u bench/error_map_t77.py \
        --scores "docs/mesures/t70-etalon-$ctx.json" \
        --manifest "$OUT/manifeste.json" \
        --out "docs/mesures/t77-carte-$ctx.json" || true

    if [ "$ctx" = "money" ]; then
        say "── T71 étape 0 : le professeur bat-il l'élève ?"
        ( cd "$T71" && "$PYTHON" -u bench/etape0_t71.py \
            --registry "$ROOT/$REGISTRY" --workers "$WORKERS" \
            --out "docs/mesures/t71-etape0-money.json" )
        say "  T71 étape 0 : code $? (0 = professeur confirmé)"
    fi
done

say ""
say "═══ campagne complète terminée le $(date -Is) ═══"
say "  Aucun entraînement n'est lancé. La QAT de T73 et l'étape 1 de T71"
say "  attendent la lecture d'un verdict par un humain."
