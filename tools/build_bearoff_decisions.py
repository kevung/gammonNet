#!/usr/bin/env python3
"""T78 — a corpus of bearoff decisions, each scored exactly.

## Why a decision corpus and not just the table

Regressing the table teaches a network the *value* of a position. What the
engine actually needs is the *ordering* of the positions one roll can reach: an
error shared by every candidate move cancels out, and only the differences
decide. T38's number is a decision loss for exactly that reason, and the tail
it reports -- 0.0919 on the worst decision -- lives in the ordering, not in the
mean absolute error.

So the second stage of `tools/train_bearoff_net.py` trains on decisions, and
this is what it trains on: positions with dice, every legal move, and the
**exact** equity of each, from the mover's point of view.

## What one row is

One decision is a run of candidates in a flat array, delimited by `offsets` --
the compressed-row shape, not a padded rectangle. A single doubles roll with
eleven checkers can produce eighty distinct moves where the median decision has
six, and padding to the worst case would multiply the corpus by twelve for
nothing.

Each candidate is stored as the index pair `(side on roll after the move, side
that just moved)` -- the game has changed hands, and the exact equity of that
pair, negated, is what the move is worth to the mover. A move that bears off
the last checker is stored with `-1` as its first index: it ends the game, and
its value is **computed**, never looked up.

## The check that makes the indices trustworthy

Values come from the dense matrix (`tools/build_bearoff_matrix.py`), because
eight million random seeks would dominate the run. But the mapping from a
position to a pair of indices is written here, so a sample of every worker's
candidates is re-scored through `gammonnet.bearoff`, the T38 reader, and any
disagreement aborts the build. A corpus indexed one row off would train a
network on a different game and never say so.

Usage:
    python tools/build_bearoff_decisions.py --decisions 1000000 --workers 26
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.arena import game_value  # noqa: E402
from gammonnet.bearoff import TwoSidedBearoff, bearoff_index  # noqa: E402
from gammonnet.rules import BLACK, NUM_POINTS, WHITE, Position  # noqa: E402

DEFAULT_DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"
DEFAULT_MATRIX = ROOT / "build" / "ts6x11_cubeless.u16"
DEFAULT_OUT = ROOT / "build" / "bearoff_decisions.npz"

SCALE = 2.0 / 65535.0
POINTS = 6


def random_bearoff(rng: random.Random, chequers: int, table) -> Position:
    """The same draw as `bench/exact_gap.py` -- uniform on the checker count.

    Copied in shape rather than imported so that this tool does not depend on
    a bench; the comment there explains the choice, and changing one without
    the other would silently train on a different domain than the one measured.
    """
    while True:
        points = [0] * NUM_POINTS
        for player in (WHITE, BLACK):
            count = rng.randint(1, chequers)
            for _ in range(count):
                point = rng.randrange(POINTS)
                if player == WHITE:
                    points[point] += 1
                else:
                    points[NUM_POINTS - 1 - point] -= 1

        white = sum(n for n in points if n > 0)
        black = -sum(n for n in points if n < 0)
        position = Position(points=tuple(points), bar=(0, 0),
                            off=(15 - white, 15 - black), turn=WHITE)
        if table.contains(position):
            return position


def sides_of(position) -> tuple[list[int], list[int]]:
    white = [0] * POINTS
    black = [0] * POINTS
    for i in range(NUM_POINTS):
        n = position.points[i]
        if n > 0:
            white[i] += n
        elif n < 0:
            black[NUM_POINTS - 1 - i] += -n
    return white, black


def indices_of(position) -> tuple[int, int]:
    """`(index of the side on roll, index of the other)` for an in-domain position."""
    white, black = sides_of(position)
    mine, theirs = (white, black) if position.turn == WHITE else (black, white)
    return bearoff_index(mine, POINTS), bearoff_index(theirs, POINTS)


def build(payload):
    (database, matrix_path, positions, chequers, seed, count, checks,
     progress) = payload

    rng = random.Random(seed)
    table = TwoSidedBearoff(database)
    matrix = np.memmap(matrix_path, dtype="<u2", mode="r",
                       shape=(positions, positions))

    rows_pairs: list[list[tuple[int, int]]] = []
    rows_values: list[list[float]] = []
    verified = 0
    produced = 0

    while produced < count:
        position = random_bearoff(rng, chequers, table)
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = position.legal_plays(d1, d2)
        if len(plays) < 2:
            continue

        seen = set()
        pairs: list[tuple[int, int]] = []
        values: list[float] = []
        for play in plays:
            result = play.result
            key = (result.points, result.bar, result.off, result.turn)
            if key in seen:
                continue
            seen.add(key)
            if result.is_over():
                pairs.append((-1, -1))
                values.append(float(game_value(result, position.turn)))
                continue
            rolled, other = indices_of(result)
            value = -(float(matrix[rolled, other]) * SCALE - 1.0)
            pairs.append((rolled, other))
            values.append(value)

            if verified < checks:
                # The reader of T38, asked the same question by a different
                # route. One disagreement means the indexing is wrong and the
                # whole corpus is worthless.
                reference = -table.equity(result).cubeless
                if abs(reference - value) > 1e-12:
                    raise AssertionError(
                        f"index ({rolled}, {other}) : matrice {value!r}, "
                        f"table {reference!r}")
                verified += 1

        if len(pairs) < 2:
            continue
        rows_pairs.append(pairs)
        rows_values.append(values)
        produced += 1

        if progress and produced % 1000 == 0:
            with open(progress, "a") as handle:
                handle.write("x\n")

    table.close()

    lengths = np.array([len(row) for row in rows_pairs], dtype=np.int64)
    offsets = np.zeros(len(rows_pairs) + 1, dtype=np.int64)
    np.cumsum(lengths, out=offsets[1:])
    pairs_out = np.array([pair for row in rows_pairs for pair in row], dtype=np.int32)
    values_out = np.array([value for row in rows_values for value in row],
                          dtype=np.float32)
    best_out = np.array([int(np.argmax(row)) for row in rows_values], dtype=np.int32)
    return offsets, pairs_out, values_out, best_out, verified


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--decisions", type=int, default=1000000)
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--checks", type=int, default=2000,
                        help="candidats re-notés par le lecteur T38, par processus")
    parser.add_argument("--progress", default="/tmp/t78-corpus-progress.log")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    with TwoSidedBearoff(args.database) as probe:
        positions, chequers = probe.positions, probe.chequers

    workers = max(1, min(args.workers, args.decisions))
    share = [args.decisions // workers + (1 if i < args.decisions % workers else 0)
             for i in range(workers)]
    payloads = [(args.database, args.matrix, positions, chequers,
                 args.seed + 7919 * i, n, args.checks, args.progress)
                for i, n in enumerate(share) if n]

    print(f"T78 — corpus de décisions de bearoff : {args.decisions} décisions, "
          f"{len(payloads)} processus, graine {args.seed}")
    print(f"  suivi : {args.progress} (une ligne par millier)", flush=True)

    start = time.perf_counter()
    if len(payloads) == 1:
        gathered = [build(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            gathered = list(pool.map(build, payloads))
    elapsed = time.perf_counter() - start

    offsets_parts = [part[0] for part in gathered]
    pairs = np.concatenate([part[1] for part in gathered])
    values = np.concatenate([part[2] for part in gathered])
    best = np.concatenate([part[3] for part in gathered])
    verified = sum(part[4] for part in gathered)

    # Each worker numbered its candidates from zero; the offsets are shifted by
    # what came before, and the last entry of each part is the same total as the
    # first entry of the next -- hence the drop.
    offsets = [offsets_parts[0]]
    running = int(offsets_parts[0][-1])
    for part in offsets_parts[1:]:
        offsets.append(part[1:] + running)
        running += int(part[-1])
    offsets = np.concatenate(offsets)
    if offsets[-1] != pairs.shape[0]:
        raise AssertionError("les offsets ne recouvrent pas les candidats")

    decisions = offsets.shape[0] - 1
    np.savez_compressed(args.out, offsets=offsets, pairs=pairs, values=values,
                        best_slot=best, seed=args.seed)

    lengths = np.diff(offsets)
    best_value = values[offsets[:-1] + best]
    worst_value = np.minimum.reduceat(values, offsets[:-1])
    spread = best_value - worst_value

    print(f"\n{decisions} décisions, {pairs.shape[0]} candidats "
          f"({lengths.mean():.1f} par décision, jusqu'à {lengths.max()}), "
          f"en {elapsed / 60:.1f} min")
    print(f"  {verified} candidats re-notés par le lecteur T38 : tous identiques")
    print(f"  étendue meilleur-pire par décision : moyenne {spread.mean():.4f}, "
          f"maximum {spread.max():.4f}")
    print(f"  écrit dans {args.out} "
          f"({Path(args.out).stat().st_size / 1e6:.0f} Mo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
