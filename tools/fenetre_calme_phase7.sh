#!/usr/bin/env bash
# Phase 7 — l'ordre du travail dans la fenêtre où la machine se libère.
#
#     setsid nohup tools/fenetre_calme_phase7.sh > /home/kunger/dev/gammonNet-logs/phase7.log 2>&1 < /dev/null &
#
# ## Pourquoi un seul script pour trois fiches
#
# Une seule ressource, la machine, et trois travaux qui la veulent. Les lancer
# séparément, chacun avec son guetteur, produit ce qu'on a déjà vu : deux
# campagnes à 26 processus qui se volent leurs mesures. L'ordre est donc décidé
# ici, une fois, et il tient à ce que chaque travail EXIGE de la machine :
#
#   1. T73, le micro-banc GEMM int8 vs f32 — QUELQUES MINUTES, un seul cœur,
#      mais il mesure un DÉBIT : il lui faut le silence, pas des cœurs. C'est la
#      seule chose qu'il ne pourra plus avoir une fois la campagne partie, et il
#      commande le verdict DS-09 sans lequel `train_qat_int8.py` refuse de
#      démarrer. Il passe donc en premier, et il coûte presque rien à T70.
#   2. T70, la campagne — des heures, 26 processus. Le chemin critique.
#   3. T71 étape 0 — le professeur bat-il l'élève ? Se note sur le registre que
#      (2) vient de figer, donc ne peut pas passer avant.
#
# ## Ce que ce script ne fait pas
#
# Il ne lance AUCUN entraînement. Ni la QAT de T73, ni l'étape 1 de T71 : les
# deux sont derrière un verdict que ce script produit mais n'interprète pas.
# Engager des jours de machine sur un verdict lu par un script serait
# exactement ce que la règle 2 du dépôt interdit.
set -uo pipefail

LOGS="${LOGS:-/home/kunger/dev/gammonNet-logs}"
T70="${T70:-/home/kunger/dev/gammonNet-t70}"
T71="${T71:-/home/kunger/dev/gammonNet-t71}"
T73="${T73:-/home/kunger/dev/gammonNet-t73}"
PYTHON="${PYTHON:-/home/kunger/venv-gammonnet/bin/python}"
CONTEXT="${CONTEXT:-money}"
WORKERS="${WORKERS:-26}"

#: Deux seuils, parce que les deux travaux ne demandent pas la même chose. La
#: campagne veut des cœurs libres ; le micro-banc veut le SILENCE — un cœur
#: voisin qui tourne suffit à décaler un débit, et un débit décalé est
#: exactement le genre de chiffre que la règle 3 refuse.
THRESHOLD="${THRESHOLD:-6}"
QUIET_THRESHOLD="${QUIET_THRESHOLD:-2}"
CALM_READINGS="${CALM_READINGS:-4}"
INTERVAL="${INTERVAL:-180}"
DEADLINE="${DEADLINE:-172800}"

mkdir -p "$LOGS"

real_campaigns() {
    pgrep -af 'python.*(run_t35|arbitrate_t70|build_corpus_t70|measure_t70|etape0_t71|arbiter_bias_t70|error_map_t77)[.]py' \
        | grep -v 'shell-snapshots' | grep -cv "^$$ " || true
}

load1() { awk '{print $1}' /proc/loadavg; }

say() { echo "[$(date +%H:%M:%S)] $*"; }

say "═══ phase 7 — orchestration de la fenêtre calme ═══"
say "campagnes réelles en cours : $(real_campaigns), charge $(load1)"

# ── Ce qui peut se faire SOUS charge se fait maintenant ────────────────────
# Compiler n'est pas mesurer : la construction du micro-banc n'a aucune raison
# d'attendre le silence, et l'y faire attendre gaspillerait la fenêtre.
say "── préparation : construction du micro-banc T73 (sous charge, sans effet sur la mesure)"
nice -n 15 make -C "$T73" build/bench_gemm_int8 build/bench_gemm_int8_sse2 2>&1 \
    | tail -3 | sed 's/^/  /' \
    || say "  (la construction se refera au moment du banc)"

# ── Attendre le silence ────────────────────────────────────────────────────
started=$(date +%s)
calm=0
while true; do
    if [ $(( $(date +%s) - started )) -gt "$DEADLINE" ]; then
        say "ABANDON — la machine ne s'est pas libérée dans le délai imparti."
        exit 1
    fi
    load=$(awk '{print int($1)}' /proc/loadavg)
    running=$(real_campaigns)
    if [ "$load" -lt "$THRESHOLD" ] && [ "$running" -eq 0 ]; then
        calm=$((calm + 1))
        say "  charge $load, aucune campagne réelle — calme $calm/$CALM_READINGS"
    else
        [ "$calm" -gt 0 ] && say "  charge $load, $running campagne(s) — compteur remis à zéro"
        calm=0
    fi
    [ "$calm" -ge "$CALM_READINGS" ] && break
    sleep "$INTERVAL"
done

say ""
say "═══ machine libre ═══"

# ── 1/3  T73 — le micro-banc, tant que le silence dure ─────────────────────
say ""
say "── 1/3  T73 : micro-banc GEMM int8 vs f32, au repos ──────────"
before=$(load1)
say "  charge avant : $before  (seuil de silence exigé : < $QUIET_THRESHOLD)"

if awk -v l="$before" -v t="$QUIET_THRESHOLD" 'BEGIN{exit !(l < t)}'; then
    (
        cd "$T73" || exit 1
        for old in docs/mesures/t73-gemm-int8.json docs/mesures/t73-gemm-int8-sse2.json; do
            [ -f "$old" ] && mv -f "$old" "${old%.json}-sous-charge.json" \
                && echo "  ancien chiffre sous charge conservé : ${old%.json}-sous-charge.json"
        done
        echo "  ── chemin natif complet"
        make bench-gemm 2>&1 | tail -30
        echo "  ── chemin dégradé SSE2, sans FMA ni AVX2 (le test décisif de l'anomalie du lot)"
        make bench-gemm-sse2 2>&1 | tail -30
    )
    after=$(load1)
    say "  charge après : $after"
    # La preuve que la mesure vaut quelque chose est écrite À CÔTÉ d'elle, et
    # pas dans un commentaire de commit : un chiffre de débit sans ses
    # conditions n'est pas relisible.
    cat > "$T73/docs/mesures/t73-gemm-conditions.json" <<JSON
{
  "quand": "$(date -Is)",
  "charge_avant": $before,
  "charge_apres": $after,
  "seuil_de_silence": $QUIET_THRESHOLD,
  "campagnes_reelles_concurrentes": $(real_campaigns),
  "note": "Micro-banc exécuté dans la fenêtre calme ouverte par la fin de la campagne T3D, AVANT la campagne T70. Les chiffres mesurés machine chargée du 2026-08-27 sont conservés sous *-sous-charge.json et ne comptent pas."
}
JSON
    say "  → $T73/docs/mesures/t73-gemm-conditions.json"
else
    say "  ⚠ REFUS — la charge ($before) dépasse le seuil de silence."
    say "    Le micro-banc mesure un débit : le lancer ici rendrait un chiffre"
    say "    aussi invalide que celui de cette nuit. On passe à T70, et le banc"
    say "    reste à refaire."
fi

# ── 2/3  T70 — la campagne ─────────────────────────────────────────────────
say ""
say "── 2/3  T70 : la campagne (des heures, $WORKERS processus) ────"
( cd "$T70" && ./tools/campagne_t70.sh --force )
campagne=$?
say "  campagne T70 terminée, code $campagne"

if [ "$campagne" -ne 0 ]; then
    say ""
    say "  ✗ la campagne T70 a échoué. L'étape 0 de T71 se note sur le registre"
    say "    qu'elle devait figer : sans lui il n'y a rien à noter, et un"
    say "    registre tronqué produirait un z parfaitement présentable et faux."
    say "    On s'arrête ici."
    exit "$campagne"
fi

# ── 3/3  T71 étape 0 ───────────────────────────────────────────────────────
REGISTRY="$T70/docs/corpus/t70/registre-$CONTEXT.jsonl"
say ""
say "── 3/3  T71 étape 0 : le professeur bat-il l'élève ? ──────────"
if [ ! -s "$REGISTRY" ]; then
    say "  ✗ registre absent ou vide : $REGISTRY"
    exit 1
fi
say "  registre : $(wc -l < "$REGISTRY") décisions"
( cd "$T71" && mkdir -p docs/mesures && "$PYTHON" -u bench/etape0_t71.py \
    --registry "$REGISTRY" --workers "$WORKERS" \
    --out "docs/mesures/t71-etape0-$CONTEXT.json" )
etape0=$?

say ""
say "═══ fenêtre calme épuisée le $(date -Is) ═══"
say "  T73 micro-banc : voir $T73/docs/mesures/t73-gemm-int8.json"
say "  T70 campagne   : code $campagne"
say "  T71 étape 0    : code $etape0 (0 = professeur confirmé)"
say ""
say "  Rien d'autre n'est lancé. La QAT de T73 et l'étape 1 de T71 attendent"
say "  chacune la lecture d'un verdict — par un humain, pas par ce script."
exit 0
