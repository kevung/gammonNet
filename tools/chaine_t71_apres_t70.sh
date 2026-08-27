#!/usr/bin/env bash
# T71 — prendre la machine dès que la campagne T70 la rend, et pas avant.
#
#     setsid nohup tools/chaine_t71_apres_t70.sh > /tmp/t71-chaine.log 2>&1 < /dev/null &
#
# Pourquoi ce script existe : l'étape 0 de T71 se note sur le registre figé que
# la campagne T70 produit. Elle ne peut donc ni démarrer avant, ni attendre
# qu'un humain constate la fin — la campagne dure des heures et personne ne
# regarde. Le script observe deux choses, et exige les deux :
#
#   1. l'ARTEFACT : le registre existe, et la carte T77 — dernière étape de la
#      chaîne T70 — a été écrite. Un registre seul peut être celui d'une
#      campagne interrompue au milieu ;
#   2. le SILENCE : plus aucun processus de la campagne ne tourne.
#
# L'artefact sans le silence, c'est une campagne encore en cours. Le silence
# sans l'artefact, c'est une campagne qui a échoué — et le script le DIT au
# lieu d'enchaîner sur un registre absent ou tronqué.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-/home/kunger/venv-gammonnet/bin/python}"
T70="${T70:-/home/kunger/dev/gammonNet-t70}"
CONTEXT="${CONTEXT:-money}"
REGISTRY="${REGISTRY:-$T70/docs/corpus/t70/registre-$CONTEXT.jsonl}"
WITNESS="${WITNESS:-$T70/docs/mesures/t77-carte-$CONTEXT.json}"
WORKERS="${WORKERS:-26}"
INTERVAL="${INTERVAL:-180}"
DEADLINE="${DEADLINE:-172800}"

#: Les processus de la campagne T70. Tant que l'un d'eux vit, la machine est à
#: elle : deux campagnes à 26 processus sur 32 cœurs se volent leurs mesures.
#:
#: Un calcul, c'est un Python qui exécute un banc, ou le shell de la campagne.
#: PAS un shell qui cite le nom d'un banc dans son argv — une autre session en a
#: laissé un qui attend sa propre disparition, et compter ce genre de processus
#: ferait attendre ce script indéfiniment. D'où l'exclusion de
#: `shell-snapshots`, signature d'un shell d'agent et jamais d'un calcul.
BUSY_RE='python.*(run_t35|build_corpus_t70|arbitrate_t70|measure_t70|error_map_t77|arbiter_bias_t70)[.]py|bash .*campagne_t70[.]sh'

busy() {
    pgrep -af "$BUSY_RE" | grep -v 'shell-snapshots' | grep -v "^$$ " | head -1
}

started=$(date +%s)
echo "═══ T71 — en attente de la fin de la campagne T70, depuis $(date -Is) ═══"
echo "  registre attendu : $REGISTRY"
echo "  témoin de fin    : $WITNESS"

while true; do
    now=$(date +%s)
    if [ $((now - started)) -gt "$DEADLINE" ]; then
        echo "ABANDON — la campagne T70 n'a pas rendu la machine dans le délai."
        exit 1
    fi

    if [ -z "$(busy)" ]; then
        if [ -s "$REGISTRY" ] && [ -s "$WITNESS" ]; then
            echo
            echo "═══ campagne T70 terminée, T71 étape 0 démarre à $(date -Is) ═══"
            echo "  registre : $(wc -l < "$REGISTRY") décisions"
            break
        fi
        # Silence sans artefact. Deux cas : la campagne n'a pas encore démarré
        # (le guetteur différé attend encore son creux), ou elle a échoué. On
        # les sépare sur l'existence du guetteur, et on ne devine jamais.
        if pgrep -af 'campagne_t70_differee[.]sh|lanceur_t70_v2[.]sh' \
                | grep -q 'bash '; then
            : # le guetteur veille encore ; rien d'anormal, on attend
        else
            echo "  $(date +%H:%M)  ⚠ ni campagne en vie, ni artefact — "
            echo "    la chaîne T70 a probablement échoué. Registre : "
            echo "    $([ -e "$REGISTRY" ] && echo présent || echo absent) ; "
            echo "    témoin : $([ -e "$WITNESS" ] && echo présent || echo absent)."
            echo "    On continue d'attendre : une relance manuelle sera vue."
        fi
    fi
    sleep "$INTERVAL"
done

mkdir -p docs/mesures
OUT="docs/mesures/t71-etape0-$CONTEXT.json"

echo
echo "── étape 0 — le professeur bat-il l'élève ? ───────────────────"
"$PYTHON" -u bench/etape0_t71.py \
    --registry "$REGISTRY" --workers "$WORKERS" --out "$OUT"
code=$?

echo
echo "═══ étape 0 rendue le $(date -Is), code $code ═══"
echo "  → $OUT"
if [ "$code" -ne 0 ]; then
    echo
    echo "  Le verdict n'est PAS « professeur confirmé ». La fiche T71 s'arrête"
    echo "  ici et le résultat se publie : c'est un déclencheur §13 du plan de"
    echo "  recherche, pas un échec à cacher. AUCUNE étape 1 n'est lancée —"
    echo "  400 000 étiquettes tirées d'une recherche dont l'avantage n'est pas"
    echo "  établi coûteraient des jours de machine pour du bruit."
fi
exit "$code"
