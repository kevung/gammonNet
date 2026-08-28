#!/usr/bin/env bash
# T70 — reprendre les quatre contextes de score, une fois money terminé.
#
#     setsid nohup tools/reprise_contextes_t70.sh > /home/kunger/dev/gammonNet-logs/t70-reprise.log 2>&1 < /dev/null &
#
# Les huit tranches des contextes de score ont échoué le 2026-08-28 à 04h58, en
# quelques secondes : `gnubg_state()` était appelé avec un paramètre `beavers`
# qui n'existe dans aucune signature. La branche ne s'exécute QUE pour un
# contexte de score — money passe `state = None` et la saute entière — donc
# elle n'avait jamais tourné, ni en récolte ni en arbitrage.
#
# Corrigé et éprouvé des deux côtés : 12 décisions récoltées en 2a-2a, puis six
# arbitrées avec leurs vrais intervalles et leurs champs d'audit.
#
# Ce script attend que la campagne de money rende la machine, puis relance
# `campagne_t70_v2.sh`. La phase B étant idempotente, money est reconnu comme
# fait et sauté ; seuls les quatre contextes sont récoltés puis traités.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
LOGS="${LOGS:-/home/kunger/dev/gammonNet-logs}"
INTERVAL="${INTERVAL:-300}"
DEADLINE="${DEADLINE:-259200}"

say() { echo "[$(date +%m-%d\ %H:%M:%S)] $*"; }

busy() {
    pgrep -af 'python.*(build_corpus_t70|arbitrate_t70|measure_t70|arbiter_bias_t70|error_map_t77|etape0_t71)[.]py|bash .*campagne_t70_v2[.]sh' \
        | grep -v 'shell-snapshots' | grep -cv "^$$ " || true
}

started=$(date +%s)
say "═══ reprise des quatre contextes — en attente de la fin de money ═══"
say "  processus de campagne en cours : $(busy)"

while [ "$(busy)" -gt 0 ]; do
    if [ $(( $(date +%s) - started )) -gt "$DEADLINE" ]; then
        say "ABANDON — money n'a pas rendu la machine dans le délai."
        exit 1
    fi
    sleep "$INTERVAL"
done

say ""
say "═══ money terminé, reprise des contextes à $(date -Is) ═══"
exec ./tools/campagne_t70_v2.sh
