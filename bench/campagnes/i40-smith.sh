#!/bin/bash
# #40 — les tête-à-tête à deux réseaux, rejoués sur le cache corrigé (clé position+réseau),
# avec la colonne corrigée de la chance de #41 (juge : 768×768 c373141, celui de v1.9.0).
#
# Mêmes graines, mêmes clés de dés et mêmes politiques que les campagnes d'origine : la paire i
# rejoue les dés de la paire i, ce qui apparie l'ancien journal (cache mêlé) et le nouveau.
#
#   1. #39 money  : candidat ea604e7 contre c373141, graine 20261113 (origine : 150 000 paires)
#   2. #38 money  : 768×768 contre 4 couches c373141, graine 20261107 (origine : 100 000 + 50 000)
#   3. #39 match  : graine 20261112, 7 points (origine : 35 000 paires)
#   4. #38 match  : graine 20261106, 7 points (origine : 35 000 paires)
#
# Volumes, déclarés le 2026-11-26 AVANT lecture d'après le pilote i40-pilote.sh (1 000 paires
# money de #39) : variance par paire divisée par 33,9, juge +7 % de temps, 1 000/1 000 paires
# identiques avec et sans juge. Money : 30 000 paires (IC corrigé attendu ≈ ±0,0017 ppg, contre
# ±0,0045 brut à 150 000). Match : 10 000 paires (le gain en match n'est pas encore mesuré).
# Les 1 000 paires du pilote avec juge ouvrent le journal i39-money (même en-tête, mêmes dés).
# Seuils inchangés (T98) : money borne basse ≥ −0,010 ppg ; match borne basse ≥ 49,5 %.
# Lecture : la colonne corrigée fait foi si ses garde-fous tiennent (|z| de la chance < 3,
# identité comptable) ; la colonne brute est imprimée à côté.
#
# Arbre : ~/gn40 (git archive de fix/cache-par-reseau, vendor relié, poids copiés et vérifiés).
# À lancer détaché : WORKERS=40 setsid nohup bench/campagnes/i40-smith.sh > i40-smith.out 2>&1 &
# Relancer reprend : les journaux sautent les paires déjà jouées.
set -u
cd "$(dirname "$0")/../.." || exit 1
P=${PY:-/usr/bin/python3.12}
W=${WORKERS:-40}
J=${OUT:-build/i40}
MONEY_PAIRS=${MONEY_PAIRS:-30000}
MATCH_PAIRS=${MATCH_PAIRS:-10000}
OLD768=models/cubeless_prob5_768_768_256_256_256.bin
OLD512=models/cubeless_prob5_512_512_256_256.bin
NEW768=models/candidate_ea604e7_768_768_256_256_256.bin
JUDGE=$OLD768
mkdir -p "$J"

h2h() {  # mode, ours, theirs, graine, paires, journal [, --match-length 7]
  "$P" bench/run_t35.py --mode "$1" --theirs self --ours-policy normal \
    --ours-model "$2" --theirs-model "$3" --seed "$4" --pairs "$5" \
    --luck-model "$JUDGE" --workers "$W" --journal "$J/$6.jsonl" "${@:7}" \
    >> "$J/$6.log" 2>&1
  "$P" bench/report_t35.py --journal "$J/$6.jsonl" > "$J/$6-rapport.txt" 2>&1
}

h2h money "$NEW768" "$OLD768" 20261113 "$MONEY_PAIRS" i39-money
echo "i39-money" > "$J/etape"
h2h money "$OLD768" "$OLD512" 20261107 "$MONEY_PAIRS" i38-money
echo "i38-money" > "$J/etape"
h2h match "$NEW768" "$OLD768" 20261112 "$MATCH_PAIRS" i39-match --match-length 7
echo "i39-match" > "$J/etape"
h2h match "$OLD768" "$OLD512" 20261106 "$MATCH_PAIRS" i38-match --match-length 7
echo FINI > "$J/fini"
