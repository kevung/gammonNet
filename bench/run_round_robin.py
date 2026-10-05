#!/usr/bin/env python3
"""Run a round-robin and print the matrix.

The instrument of T04, driven from the command line. It is not a strength
measurement of gammonNet — gammonNet does not evaluate anything yet (T10). What
it produces is a matrix between the engines available today, and the evidence
that the matrix has the properties an instrument must have.

Usage:
    python bench/run_round_robin.py --pairs 500 --workers 16
    python bench/run_round_robin.py --engines random,first-play --pairs 2000
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.arena import (  # noqa: E402
    FirstPlayEngine,
    OracleEngine,
    RandomEngine,
    SageEngine,
    SearchEngine,
    round_robin,
)

#: Les moteurs que ce banc sait aligner. **Les noms portent la profondeur
#: RÉELLE**, jamais l'étiquette d'origine : le moteur tiers de la phase 9
#: numérote ses niveaux depuis l'évaluation statique (son `1ply` est notre
#: 0-ply, T92), et une ligne de matrice qui reprendrait son étiquette
#: laisserait croire à un affrontement apparié qui n'en serait pas un.
#: Les poids candidats de T96. **Un réseau est ses poids** (`BRIEF.md` §8), d'où
#: le nom de ligne : dans six mois, une ligne qui dirait « le nouveau » ne dirait
#: plus rien. Les deux lignes ci-dessous ne diffèrent que par ce fichier — c'est
#: la condition pour que le tête-à-tête mesure le réseau et rien d'autre.
CANDIDATE = "models/cubeless_prob5_512_512_256_256.bin"

AVAILABLE = {
    "random": lambda: RandomEngine(name="random"),
    "first-play": lambda: FirstPlayEngine(name="first-play"),
    "gnubg-0ply": lambda: OracleEngine(ply=0),
    "gnubg-1ply": lambda: OracleEngine(ply=1),
    "gnubg-2ply": lambda: OracleEngine(ply=2),
    "gammonnet-0ply": lambda: SearchEngine(ply=0),
    "gammonnet-2ply": lambda: SearchEngine(ply=2, filter=(0, 1, 3), prune_k=12),
    "prob5-256-0ply": lambda: SearchEngine(
        ply=0, model=CANDIDATE, name="prob5-512-512-256-256-0ply"),
    "prob5-256-2ply": lambda: SearchEngine(
        ply=2, filter=(0, 1, 3), prune_k=12, model=CANDIDATE,
        name="prob5-512-512-256-256-2ply-f0/1/3-k12"),
    "sage-0ply": lambda: SageEngine(level="1ply"),
    "sage-1ply": lambda: SageEngine(level="2ply"),
    "sage-2ply": lambda: SageEngine(level="3ply"),
    "sage-3ply": lambda: SageEngine(level="4ply"),
    "sage-trunc1": lambda: SageEngine(level="truncated1"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engines", default="random,first-play,gnubg-0ply",
                        help=f"comma-separated; available: {','.join(AVAILABLE)}")
    parser.add_argument("--pairs", type=int, default=200,
                        help="duplicate pairs per ordered matchup (2 games each)")
    parser.add_argument("--seed", type=int, default=20260803)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--out", type=Path, default=None,
                        help="écrire la matrice en JSON — une campagne détachée "
                             "ne doit pas laisser son résultat dans un journal texte")
    args = parser.parse_args()

    names = [n.strip() for n in args.engines.split(",") if n.strip()]
    for name in names:
        if name not in AVAILABLE:
            parser.error(f"moteur inconnu : {name}. Disponibles : {', '.join(AVAILABLE)}")

    engines = [AVAILABLE[name]() for name in names]

    print(f"Round-robin : {len(engines)} moteurs, {args.pairs} paires par affrontement "
          f"ordonné ({2 * args.pairs} parties), graine {args.seed}, "
          f"{args.workers} processus")
    print("Dés dupliqués : chaque séquence est rejouée sièges échangés.\n")

    start = time.perf_counter()
    matrix = round_robin(
        engines,
        pairs=args.pairs,
        base_seed=args.seed,
        workers=args.workers,
        bootstrap=args.bootstrap,
    )
    elapsed = time.perf_counter() - start

    print(matrix.report())

    ordered_pairs = len(engines) * (len(engines) - 1)
    games = ordered_pairs * args.pairs * 2
    print(f"\n{games} parties en {elapsed:.1f} s ({games / elapsed:.0f} parties/s)")

    # Les propriétés que l'instrument doit avoir, vérifiées sur CE résultat.
    worst = 0.0
    for a in matrix.names:
        for b in matrix.names:
            worst = max(worst, abs(matrix.ppg(a, b) + matrix.ppg(b, a)))
    print(f"Résidu d'antisymétrie maximal : {worst:.3e}")

    if args.out:
        import json

        args.out.write_text(json.dumps({
            "engines": list(matrix.names),
            "pairs": args.pairs,
            "seed": args.seed,
            "bootstrap": args.bootstrap,
            "seconds": elapsed,
            "games": games,
            "antisymmetry_residual": worst,
            "results": [
                {"a": r.a, "b": r.b, "pairs": r.pairs, "games": r.games,
                 "ppg": r.ppg, "ci": list(r.ci), "win_rate": r.win_rate,
                 "stalled": r.stalled}
                for r in matrix.results.values()
            ],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n\u2192 {args.out}")

    print("\nCe tableau se lit avec son volume et son IC, jamais seul. En dessous")
    print("d'environ 1 M de parties par paire, deux bons moteurs ne se séparent pas")
    print("du bruit (BRIEF.md §9) — un écart non significatif est un résultat, pas")
    print("un échec de la mesure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
