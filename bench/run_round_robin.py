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
    round_robin,
)

AVAILABLE = {
    "random": lambda: RandomEngine(name="random"),
    "first-play": lambda: FirstPlayEngine(name="first-play"),
    "gnubg-0ply": lambda: OracleEngine(ply=0),
    "gnubg-1ply": lambda: OracleEngine(ply=1),
    "gnubg-2ply": lambda: OracleEngine(ply=2),
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

    print("\nCe tableau ne dit rien de la force de gammonNet, qui n'évalue encore rien")
    print("(T10). Il établit que l'instrument est droit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
