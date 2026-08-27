#!/usr/bin/env python3
"""T70 — ce que chaque passe coûte, et jusqu'où elle résout.

## Pourquoi cette fiche a besoin de ce banc

T70 exige que « le coût machine d'un point de comparaison » soit chiffré, et que
l'instrument soit revu si ce coût se compte en jours. Les réglages de l'escalade
— profondeur de troncature, essais minimaux, résolution visée, seuil de la
passe 1 — décident de ce coût sur un ou deux ordres de grandeur, et aucun ne se
choisit par raisonnement.

Le premier jet de l'arbitrage l'a appris à ses dépens : une passe 3 en rollout
**complet** avec réduction de variance. T39 avait pourtant le chiffre — la VR
coûte ×19 en temps pour ×159 en variance sur un rollout tronqué à 11 plis — et
un rollout non tronqué joue cinq fois plus de plis. L'estimation qui en découle
est de l'ordre de six heures **par décision**. Deux décisions arbitrées en vingt
minutes l'ont confirmé avant que la campagne complète ne parte pour un mois.

Ce banc mesure donc, sur un petit nombre de décisions réelles, ce que chaque
réglage coûte et ce qu'il résout. Il ne recommande rien : il rend un tableau, et
le choix se fait sur le tableau.

## Ce qu'il rapporte

Par réglage : le temps par décision, la part de candidats `resolved`,
`dominated`, `open`, et le nombre d'essais réellement consommés. Un réglage qui
serait rapide en laissant tout `open` n'a rien résolu — les deux colonnes se
lisent ensemble ou pas du tout.

**Sur machine chargée, les temps ne valent rien** (règle 3). Les RAPPORTS entre
réglages restent lisibles, et c'est déjà ce qui sert à choisir ; le coût absolu
se remesure au calme.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench"))

from arbitrate_t70 import resolution_of  # noqa: E402
from gammonnet import codec  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rollout import RolloutConfig, rollout_candidates_paired  # noqa: E402
from gammonnet.rules import BLACK, WHITE  # noqa: E402
from gammonnet.search import SearchConfig  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"

#: Les réglages mis en concurrence. Écrits ici plutôt que passés en ligne de
#: commande : ce sont les candidats du choix, et le tableau doit rester le même
#: d'une exécution à l'autre pour être comparable.
SETTINGS = [
    {"name": "tronqué-7 VR",     "truncate": 7,  "vr": True,  "trials": 1296,
     "target_se": 0.006,  "min_trials": 72},
    {"name": "tronqué-11 VR",    "truncate": 11, "vr": True,  "trials": 1296,
     "target_se": 0.006,  "min_trials": 72},
    {"name": "tronqué-25 VR",    "truncate": 25, "vr": True,  "trials": 1296,
     "target_se": 0.00255, "min_trials": 108},
    {"name": "tronqué-11 sans VR", "truncate": 11, "vr": False, "trials": 5184,
     "target_se": 0.006,  "min_trials": 216},
    {"name": "complet sans VR",  "truncate": 0,  "vr": False, "trials": 5184,
     "target_se": 0.00255, "min_trials": 216},
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--decisions", type=int, default=4)
    parser.add_argument("--resolution", type=float, default=0.005)
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--only", default="", help="un seul réglage, par nom")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    rows = [json.loads(line) for line in
            Path(args.corpus).read_text().splitlines() if line.strip()][:args.decisions]
    if not rows:
        print("corpus vide", file=sys.stderr)
        return 2

    network = Network.load(str(MODEL))
    settings = [s for s in SETTINGS if not args.only or s["name"] == args.only]

    print("T70 — calibration de l'escalade")
    print(f"  {len(rows)} décisions du corpus, résolution visée {args.resolution}")
    print("  ⚠ machine chargée : lire les RAPPORTS, pas les temps absolus\n")
    print(f"  {'réglage':22s} {'s/décision':>11s} {'essais':>8s} "
          f"{'résolus':>9s} {'dominés':>9s} {'ouverts':>9s}")

    results = []
    for setting in settings:
        total_seconds = 0.0
        counts = {"resolved": 0, "dominated": 0, "open": 0}
        trials_total = 0
        for row in rows:
            opponent = BLACK if row["turn"] == WHITE else WHITE
            candidates = [codec.position_from_id(pid, opponent)
                          for pid in row["candidates"]]
            config = RolloutConfig(
                trials=setting["trials"], truncate=setting["truncate"],
                seed=args.seed + row["index"], policy=SearchConfig(ply=0),
                variance_reduction=setting["vr"],
                target_se=setting["target_se"], min_trials=setting["min_trials"])
            started = time.perf_counter()
            _eq, differences, errors, trials = rollout_candidates_paired(
                network, candidates, config, pivot=0)
            total_seconds += time.perf_counter() - started
            trials_total += trials
            for state in resolution_of(differences, errors, 0, args.resolution):
                counts[state] += 1

        per_decision = total_seconds / len(rows)
        total = sum(counts.values()) or 1
        print(f"  {setting['name']:22s} {per_decision:11.1f} "
              f"{trials_total // len(rows):8d} "
              f"{100 * counts['resolved'] / total:8.1f}% "
              f"{100 * counts['dominated'] / total:8.1f}% "
              f"{100 * counts['open'] / total:8.1f}%", flush=True)
        results.append({**setting, "seconds_per_decision": per_decision,
                        "trials_per_decision": trials_total / len(rows),
                        "counts": counts})

    print("\n  Lecture : un réglage rapide qui laisse tout « ouvert » n'a rien")
    print("  résolu. Les deux colonnes se lisent ensemble ou pas du tout.")
    if args.out:
        Path(args.out).write_text(json.dumps(
            {"decisions": len(rows), "resolution": args.resolution,
             "settings": results}, indent=2) + "\n")
        print(f"\n  → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
