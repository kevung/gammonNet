#!/usr/bin/env bash
# T70 — attendre que la machine se libère, puis lancer la campagne.
#
#     setsid nohup tools/campagne_t70_differee.sh > /tmp/t70-differee.log 2>&1 < /dev/null &
#
# Pourquoi ce script existe : la machine porte une campagne T3D qui tient 24
# processus, et aucune coordination n'est possible avec la session qui l'a
# lancée (les messages inter-sessions demandent une approbation humaine qui n'a
# pas eu lieu). On ne peut donc ni demander la machine, ni être prévenu qu'elle
# se libère. On l'observe.
#
# Le garde-fou de `campagne_t70.sh` reste en place : ce script n'appelle celui-ci
# QU'UNE FOIS la machine calme, et celui-là refuse encore de démarrer s'il se
# trompe. Deux verrous valent mieux qu'un quand personne ne surveille.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

#: La charge en dessous de laquelle on considère la machine disponible. La
#: machine a 32 fils ; 6 laisse la place à ce qui traîne sans attendre le
#: silence complet, qui pourrait ne jamais venir.
THRESHOLD="${THRESHOLD:-6}"
#: Combien de relevés calmes CONSÉCUTIFS avant de lancer. Un creux passager
#: entre deux campagnes ne doit pas déclencher trois heures d'arbitrage.
CALM_READINGS="${CALM_READINGS:-5}"
INTERVAL="${INTERVAL:-300}"
DEADLINE="${DEADLINE:-86400}"

started=$(date +%s)
calm=0

echo "═══ T70 — en attente de la machine, depuis $(date -Is) ═══"
echo "  seuil de charge : $THRESHOLD   relevés calmes requis : $CALM_READINGS"
echo "  relevé toutes les ${INTERVAL}s, abandon après ${DEADLINE}s"

while true; do
    now=$(date +%s)
    if [ $((now - started)) -gt "$DEADLINE" ]; then
        echo "ABANDON — la machine ne s'est pas libérée dans le délai imparti."
        echo "Lancer la campagne à la main quand elle le sera."
        exit 1
    fi

    load=$(awk '{print int($1)}' /proc/loadavg)
    others=$(pgrep -cf 'run_t35\.py' || true)

    if [ "$load" -lt "$THRESHOLD" ] && [ "${others:-0}" -eq 0 ]; then
        calm=$((calm + 1))
        echo "  $(date +%H:%M)  charge $load, aucune campagne tierce — calme $calm/$CALM_READINGS"
    else
        [ "$calm" -gt 0 ] && echo "  $(date +%H:%M)  charge $load, $others processus tiers — compteur remis à zéro"
        calm=0
    fi

    if [ "$calm" -ge "$CALM_READINGS" ]; then
        echo
        echo "═══ machine libre, lancement à $(date -Is) ═══"
        exec ./tools/campagne_t70.sh
    fi
    sleep "$INTERVAL"
done
