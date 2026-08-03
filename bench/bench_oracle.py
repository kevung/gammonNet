#!/usr/bin/env python3
"""Measure the throughput of the GNU Backgammon oracle.

> **Une conclusion de performance se mesure, elle ne se déduit pas.**

The one thing this bench exists to prevent is the obvious mistake: timing a loop
over a single repeated position. `gnubg_nn` caches evaluations, so that loop
measures the cache. It is reported here side by side with the honest figure,
because the gap is large enough that a naive measurement does not look wrong —
it looks great.

Usage:
    python bench/bench_oracle.py               # default sample sizes
    python bench/bench_oracle.py --positions 5000
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import Position  # noqa: E402
from gammonnet import gnubg_board as gb  # noqa: E402
from gammonnet.oracle import Oracle  # noqa: E402

import gnubg_nn  # noqa: E402

SEED = 20260803

#: How many evaluations to time at each depth. A 2-ply evaluation costs roughly
#: four orders of magnitude more than a 0-ply one, so the counts differ wildly.
SAMPLES = {0: 20_000, 1: 3_000, 2: 200}


def distinct_positions(count: int, seed: int = SEED) -> list[Position]:
    """`count` positions, **one per game**, each from a different random game.

    Taking consecutive positions from one game would be cheaper and wrong. They
    share most of their search sub-trees, so a deep search over the second one
    is largely answered by the cache the first one filled. The measurement would
    then describe a workload nobody runs.

    One position per game, at a random depth into it, keeps the shared sub-trees
    down to what chance provides.
    """
    rng = random.Random(seed)
    positions: list[Position] = []

    while len(positions) < count:
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()

        for _ in range(rng.randint(2, 60)):
            if position.is_over():
                break
            plays = position.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
            position = rng.choice(plays).result if plays else position.swapped_turn()

        if not position.is_over():
            positions.append(position)

    return positions


def time_evaluations(boards, ply: int) -> float:
    """Evaluations per second over the boards given, in order."""
    start = time.perf_counter()
    for board in boards:
        gnubg_nn.probabilities(board, ply)
    return len(boards) / (time.perf_counter() - start)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=20_000,
                        help="size of the distinct-position pool")
    args = parser.parse_args()

    print(f"génération de {args.positions} positions distinctes (graine {SEED})…")
    positions = distinct_positions(args.positions)
    boards = [gb.to_gnubg(p) for p in positions]
    print(f"{len(boards)} positions prêtes\n")

    print("Débit de l'oracle GNU Backgammon")
    print("=" * 74)
    print(f"{'profondeur':>12} {'distinctes':>16} {'répétée (cache)':>18} {'facteur':>12}")
    print("-" * 74)

    honest = {}
    cursor = 0

    for ply, count in SAMPLES.items():
        # Une TRANCHE DISJOINTE par profondeur. Réutiliser les mêmes positions
        # ferait mesurer au 2-ply un cache que le 0-ply vient de remplir avec
        # exactement les évaluations de feuilles dont il a besoin.
        sample = boards[cursor:cursor + count]
        cursor += count
        if len(sample) < count:
            print(f"  (pool trop petit pour {ply}-ply : {len(sample)} positions)")
        if not sample:
            continue

        distinct_rate = time_evaluations(sample, ply)

        # Le même volume, sur UNE position : ce que mesure une boucle naïve.
        cached_rate = time_evaluations([sample[0]] * len(sample), ply)

        honest[ply] = distinct_rate
        print(f"{ply:>10}-ply {distinct_rate:>14.1f}/s {cached_rate:>16.1f}/s "
              f"{cached_rate / distinct_rate:>11.0f}×")

    print("-" * 74)
    print("La colonne « répétée » est un piège de mesure, pas un résultat : elle")
    print("chronomètre le cache d'évaluation de gnubg. Seule la première compte.\n")

    print("Coût par décision, à partir de la colonne honnête")
    print("=" * 74)
    for ply, rate in honest.items():
        cost_ms = 1000.0 / rate
        match_s = cost_ms * 300 / 1000.0  # ~300 décisions dans un match de 7 points
        print(f"{ply:>10}-ply {cost_ms:>10.3f} ms/évaluation    "
              f"match de 7 points ≈ {match_s:>8.1f} s (1 fil)")

    print()
    print("Rappel : ce sont les débits de GNU BACKGAMMON, l'instrument de mesure.")
    print("Ils ne disent rien du débit de gammonNet, qui n'évalue encore rien (T10),")
    print("ni du navigateur, dont la pénalité reste une hypothèse jusqu'à T21.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
