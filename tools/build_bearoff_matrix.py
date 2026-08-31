#!/usr/bin/env python3
"""T78 — extract the cubeless column of the two-sided table, once.

## Why extract anything at all

The two-sided base `gnubg-TS-06-11` is 1.2 GiB of four 16-bit columns per pair
of positions: cubeless equity, then the three cubeful ones. Distillation needs
exactly one of them -- the cubeless equity -- for all `12 376 x 12 376`
pairs. Taken alone it is `153 165 376 x 2` bytes, **306 MiB**, which fits in
memory and can be indexed as a matrix rather than seeked into eight bytes at a
time. A training run that seeked would spend all its time in the kernel.

Nothing here reinterprets the format: the layout, the scale and the indexing
were established in T38 and live in `python/gammonnet/bearoff.py`. This tool
streams the same bytes into a denser shape, and then **proves** it did so by
reading random pairs back through that reference reader.

## What it writes, into `build/`

* `ts6x11_cubeless.u16` -- the raw 16-bit cubeless column, C order, one entry
  per `(player, opponent)` pair. `equity = value / 65535 * 2 - 1`, the scale
  T38 established against `bearoffdump`.
* `ts6x11_sides.npy` -- `(12 376, 6)` int8, the checker layout of every index.
  `sides[k][i]` is the number of checkers `i + 1` pips from off. Built by
  enumeration and checked to be a bijection against `bearoff_index`.

Usage:
    python tools/build_bearoff_matrix.py
    python tools/build_bearoff_matrix.py --checks 5000
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.bearoff import HEADER_BYTES, TwoSidedBearoff, bearoff_index  # noqa: E402

DEFAULT_DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"
OUT_MATRIX = ROOT / "build" / "ts6x11_cubeless.u16"
OUT_SIDES = ROOT / "build" / "ts6x11_sides.npy"

CHUNK_ENTRIES = 1 << 23  # 8 M pairs -- 64 MiB read, 16 MiB written


def enumerate_sides(points: int, chequers: int) -> np.ndarray:
    """Every checker layout of the domain, at the index gnubg gives it.

    The enumeration order does not matter: each layout is placed at the index
    `bearoff_index` computes for it, and the result is checked to be a
    permutation. That check is the point -- a layout table silently off by one
    would make every training label describe a different position, and the
    trained network would be perfectly plausible and wrong.
    """
    from math import comb
    total_positions = comb(points + chequers, points)

    sides = np.full((total_positions, points), -1, dtype=np.int8)
    seen = np.zeros(total_positions, dtype=bool)

    def walk(prefix: list[int], remaining: int) -> None:
        if len(prefix) == points:
            index = bearoff_index(prefix, points)
            if seen[index]:
                raise AssertionError(f"index {index} produced twice")
            seen[index] = True
            sides[index] = prefix
            return
        for count in range(remaining + 1):
            walk(prefix + [count], remaining - count)

    walk([], chequers)
    if not seen.all():
        raise AssertionError("bearoff_index is not onto the index range")
    return sides


def extract(database: Path, out: Path, positions: int) -> str:
    """Stream the first of four columns into a dense matrix, hashing as we go."""
    pairs = positions * positions
    digest = hashlib.sha256()
    written = 0
    start = time.perf_counter()

    with database.open("rb") as source, out.open("wb") as sink:
        source.seek(HEADER_BYTES)
        while written < pairs:
            want = min(CHUNK_ENTRIES, pairs - written)
            raw = source.read(want * 8)
            if len(raw) != want * 8:
                raise AssertionError(f"short read at pair {written}")
            block = np.frombuffer(raw, dtype="<u2").reshape(-1, 4)[:, 0].copy()
            digest.update(block.tobytes())
            sink.write(block.tobytes())
            written += want
            if written % (CHUNK_ENTRIES * 8) == 0 or written == pairs:
                done = written / pairs
                print(f"  {done * 100:5.1f} %  {time.perf_counter() - start:6.1f} s",
                      flush=True)
    return digest.hexdigest()


def verify(database: Path, matrix: np.ndarray, positions: int, checks: int,
           seed: int) -> None:
    """Read random pairs back through the T38 reference reader.

    The extraction and the reference reader compute the same offset by two
    different routes; if they disagree anywhere, this is where it shows.
    """
    rng = random.Random(seed)
    with TwoSidedBearoff(database) as table:
        for _ in range(checks):
            i = rng.randrange(positions)
            j = rng.randrange(positions)
            expected = table.raw(i, j)[0]
            got = int(matrix[i, j])
            if got != expected:
                raise AssertionError(
                    f"pair ({i}, {j}) : extracted {got}, reference {expected}")
    print(f"  {checks} pairs re-read through gammonnet.bearoff : identical")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    parser.add_argument("--out", default=str(OUT_MATRIX))
    parser.add_argument("--sides", default=str(OUT_SIDES))
    parser.add_argument("--checks", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260828)
    args = parser.parse_args()

    database = Path(args.database)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with TwoSidedBearoff(database) as probe:
        points, chequers, positions = probe.points, probe.chequers, probe.positions

    print(f"T78 — colonne cubeless de {database.name} "
          f"({points} points, {chequers} pions, {positions} positions)")

    sides = enumerate_sides(points, chequers)
    np.save(args.sides, sides)
    print(f"  {sides.shape[0]} dispositions écrites dans {args.sides}")

    digest = extract(database, out, positions)
    size = out.stat().st_size
    print(f"  {size} octets écrits dans {out}  sha256={digest[:16]}…")
    if size != positions * positions * 2:
        raise AssertionError("taille inattendue")

    matrix = np.memmap(out, dtype="<u2", mode="r", shape=(positions, positions))
    verify(database, matrix, positions, args.checks, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
