#!/usr/bin/env bash
# T70 — lancer la campagne quand la machine se libère VRAIMENT.
#
#     setsid nohup tools/lanceur_t70_v2.sh > /home/kunger/dev/gammonNet-logs/t70-lanceur.log 2>&1 < /dev/null &
#
# ## Pourquoi ce script remplace `campagne_t70_differee.sh`
#
# Le guetteur différé compte les campagnes tierces par `pgrep -cf 'run_t35\.py'`.
# Le compte ne retombe jamais à zéro, et pas à cause d'un calcul : un shell de
# surveillance laissé par une autre session porte `run_t35.py` DANS SON PROPRE
# argv (il attendait la fin d'une campagne, en se matchant lui-même — il
# s'attend donc indéfiniment). Il ne calcule rien, il occupe un nom.
#
# Le même piège frappe le `busy()` de `campagne_t70.sh`. Les deux verrous de la
# chaîne sont donc tenus fermés par un processus inerte, et la campagne T70 —
# le chemin critique de la phase 7 — n'aurait jamais démarré.
#
# ## Ce que ce script fait à la place
#
# Il compte les campagnes sur leur FORME RÉELLE : un interpréteur Python qui
# exécute le banc. Et il écarte explicitement tout ce qui porte
# `shell-snapshots` — la signature d'un shell d'agent, jamais celle d'un calcul.
#
# Il appelle ensuite `campagne_t70.sh --force`, non pour passer outre un
# contrôle, mais parce que le contrôle qu'il remplace est inutilisable ici. Le
# `--force` de ce script est prévu pour être employé « délibérément et par
# écrit » : ceci en est l'écrit.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

THRESHOLD="${THRESHOLD:-6}"
CALM_READINGS="${CALM_READINGS:-4}"
INTERVAL="${INTERVAL:-180}"
DEADLINE="${DEADLINE:-172800}"

#: Un calcul, c'est un Python qui exécute un banc. Un shell qui cite le nom du
#: banc dans sa ligne de commande n'est pas un calcul.
real_campaigns() {
    pgrep -af 'python.*(run_t35|arbitrate_t70|build_corpus_t70|measure_t70|etape0_t71|arbiter_bias_t70|error_map_t77)[.]py' \
        | grep -v 'shell-snapshots' | grep -cv "^$$ " || true
}

started=$(date +%s)
calm=0
echo "═══ T70 v2 — en attente de la machine, depuis $(date -Is) ═══"
echo "  seuil de charge : $THRESHOLD   relevés calmes requis : $CALM_READINGS"
echo "  campagnes réelles en cours : $(real_campaigns)"

while true; do
    now=$(date +%s)
    if [ $((now - started)) -gt "$DEADLINE" ]; then
        echo "ABANDON — la machine ne s'est pas libérée dans le délai imparti."
        exit 1
    fi

    # Si l'ancien guetteur a fini par lancer la campagne, ce script s'efface :
    # deux campagnes sur 32 cœurs ne vont pas deux fois plus vite, elles se
    # volent leurs mesures.
    if pgrep -af 'bash .*campagne_t70[.]sh' | grep -qv 'shell-snapshots'; then
        echo "  $(date +%H:%M)  la campagne T70 tourne déjà — ce lanceur s'efface."
        exit 0
    fi

    load=$(awk '{print int($1)}' /proc/loadavg)
    running=$(real_campaigns)

    if [ "$load" -lt "$THRESHOLD" ] && [ "$running" -eq 0 ]; then
        calm=$((calm + 1))
        echo "  $(date +%H:%M)  charge $load, aucune campagne réelle — calme $calm/$CALM_READINGS"
    else
        [ "$calm" -gt 0 ] && echo "  $(date +%H:%M)  charge $load, $running campagne(s) — compteur remis à zéro"
        calm=0
    fi

    if [ "$calm" -ge "$CALM_READINGS" ]; then
        echo
        echo "═══ machine libre, lancement à $(date -Is) ═══"
        exec ./tools/campagne_t70.sh --force
    fi
    sleep "$INTERVAL"
done
