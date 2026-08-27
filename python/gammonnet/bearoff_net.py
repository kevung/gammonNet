"""T78 — the distilled bearoff evaluator: features, weights, and forward pass.

## What this is for

The exact two-sided table `gnubg-TS-06-11` plays the endgame perfectly, and
T38 measured what it is worth: 0.00028 equity per bearoff decision on average,
0.0919 on the worst decision seen. But it is 1.2 GiB, so it stays native: a
browser gets the network, and pays that tail. This module is the other route --
**regress the table into a few tens of kilobytes** and carry it everywhere.

Nothing here reads the table. Inference needs the weights and nothing else,
which is the entire point; the table is a training oracle and a measuring
stick, not a runtime dependency.

## The domain, and the refusal outside it

`contains()` is the same predicate as `bearoff.TwoSidedBearoff.contains` --
both sides borne in, at most eleven checkers each, nobody on the bar. Outside
it, `equity()` raises rather than extrapolating; `tests/test_bearoff_net.py`
cross-checks the predicate and the side decomposition against the table reader
on random positions, because two implementations of the same domain are two
things that can disagree, and a disagreement here would be silent.

## The weight file

A deliberately plain format (`GNBONET1`), not BGNN. The BGNN writer in
`vendor/` describes 196-in / 5-out prob5 networks with nested sigmoids; this
network is 96-in / 1-out with a tanh, and pretending it is the same shape would
buy nothing and cost a reader that lies.

    magic   8 bytes  b"GNBONET1"
    int32   feature version
    int32   number of layers L
    L x (int32 in, int32 out)
    then, per layer, `in * out` float32 weights (row-major, out-major) and
    `out` float32 biases -- little-endian throughout.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from .rules import BLACK, NUM_POINTS, WHITE

#: The domain of `gnubg-TS-06-11`, restated here so that inference never needs
#: the 1.2 GiB file to know whether it is allowed to answer.
POINTS = 6
CHEQUERS = 11

#: Bumped whenever `side_features` changes shape or meaning. A weight file
#: carries the version it was trained with; loading a mismatch raises.
FEATURE_VERSION = 1

#: Per side: six points x (six thermometer bits + the raw count), then six
#: summary features. The pair input is twice this, mine first.
SIDE_FEATURES = POINTS * 7 + 6
INPUT_SIZE = 2 * SIDE_FEATURES

MAGIC = b"GNBONET1"
_PIPS = np.arange(1, POINTS + 1, dtype=np.float32)


def side_features(counts: np.ndarray) -> np.ndarray:
    """Features of one side's checker layout, `(N, 6)` counts in.

    `counts[k][i]` is the number of checkers `i + 1` pips from off. The
    thermometer bits are the standard trick for a small ordinal input: a
    network learns `n >= 3` far more readily from a bit than from a scalar,
    and the raw count is kept alongside so that stacks beyond six survive.
    """
    counts = np.asarray(counts, dtype=np.float32).reshape(-1, POINTS)
    n = counts.shape[0]

    thermometer = (counts[:, :, None] >= np.arange(1, POINTS + 1,
                                                   dtype=np.float32)).astype(np.float32)
    per_point = np.concatenate(
        [thermometer, (counts / CHEQUERS)[:, :, None]], axis=2
    ).reshape(n, POINTS * 7)

    total = counts.sum(axis=1)
    pip = counts @ _PIPS
    occupied = (counts > 0).sum(axis=1).astype(np.float32)
    highest = np.where(counts > 0, np.arange(1, POINTS + 1, dtype=np.float32), 0.0)
    highest = highest.max(axis=1)

    summary = np.stack([
        total / CHEQUERS,
        pip / (POINTS * CHEQUERS),
        np.mod(total, 2.0),
        highest / POINTS,
        occupied / POINTS,
        (total == 0).astype(np.float32),
    ], axis=1)

    return np.concatenate([per_point, summary], axis=1).astype(np.float32)


def position_sides(position) -> tuple[list[int], list[int]] | None:
    """`(white, black)` checker layouts, each seen from its own side.

    The same decomposition as `bearoff.TwoSidedBearoff._sides`, restated
    without the table so that inference stands alone. `white[i]` counts white
    checkers `i + 1` pips from off; `black[i]` does the same for black, whose
    points are the physical mirror. Confusing the two would turn the board
    around without breaking anything or signalling anything, which is why the
    test cross-checks it against the reader.
    """
    white = [0] * POINTS
    black = [0] * POINTS
    for i in range(NUM_POINTS):
        n = position.points[i]
        if n > 0:
            if i >= POINTS:
                return None
            white[i] += n
        elif n < 0:
            j = NUM_POINTS - 1 - i
            if j >= POINTS:
                return None
            black[j] += -n
    return white, black


def contains(position) -> bool:
    """Is this position one the distilled network is allowed to answer for?"""
    if position.is_over():
        return False
    if position.bar[WHITE] or position.bar[BLACK]:
        return False
    sides = position_sides(position)
    if sides is None:
        return False
    white, black = sides
    return sum(white) <= CHEQUERS and sum(black) <= CHEQUERS


class BearoffNet:
    """A small dense network, `tanh` out, evaluated with numpy.

    The forward pass is a handful of matrix multiplies: batching matters far
    more than any per-call cleverness, so the public entry points take arrays.
    """

    def __init__(self, layers: list[tuple[np.ndarray, np.ndarray]],
                 feature_version: int = FEATURE_VERSION):
        if feature_version != FEATURE_VERSION:
            raise ValueError(
                f"weights encode features v{feature_version}, this module is "
                f"v{FEATURE_VERSION} -- retrain rather than reinterpret")
        if layers[0][0].shape[0] != INPUT_SIZE:
            raise ValueError(f"first layer takes {layers[0][0].shape[0]} inputs, "
                             f"features give {INPUT_SIZE}")
        if layers[-1][0].shape[1] != 1:
            raise ValueError("the last layer must produce a single equity")
        self.layers = [(np.ascontiguousarray(w, dtype=np.float32),
                        np.ascontiguousarray(b, dtype=np.float32))
                       for w, b in layers]
        self.feature_version = feature_version

    # ── shape and cost ──────────────────────────────────────────────

    @property
    def sizes(self) -> list[int]:
        return [self.layers[0][0].shape[0]] + [w.shape[1] for w, _ in self.layers]

    @property
    def parameters(self) -> int:
        return sum(w.size + b.size for w, b in self.layers)

    @property
    def macs(self) -> int:
        return sum(w.size for w, _ in self.layers)

    # ── forward ─────────────────────────────────────────────────────

    def forward(self, features: np.ndarray) -> np.ndarray:
        x = np.asarray(features, dtype=np.float32)
        for index, (w, b) in enumerate(self.layers):
            x = x @ w + b
            if index + 1 < len(self.layers):
                np.maximum(x, 0.0, out=x)
        return np.tanh(x[:, 0])

    def equities_from_counts(self, mine: np.ndarray, theirs: np.ndarray) -> np.ndarray:
        """Equity for the side on roll, from both layouts, `(N, 6)` each."""
        features = np.concatenate([side_features(mine), side_features(theirs)], axis=1)
        return self.forward(features)

    def equity(self, position) -> float:
        """Equity of `position`, seen by `position.turn`. Raises off-domain."""
        if not contains(position):
            raise KeyError(f"outside the {POINTS}x{CHEQUERS} bearoff domain: {position!r}")
        white, black = position_sides(position)
        mine, theirs = (white, black) if position.turn == WHITE else (black, white)
        return float(self.equities_from_counts(np.array([mine]), np.array([theirs]))[0])

    # ── storage ─────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        path = Path(path)
        with path.open("wb") as handle:
            handle.write(MAGIC)
            handle.write(struct.pack("<ii", self.feature_version, len(self.layers)))
            for w, _ in self.layers:
                handle.write(struct.pack("<ii", w.shape[0], w.shape[1]))
            for w, b in self.layers:
                handle.write(np.ascontiguousarray(w.T, dtype="<f4").tobytes())
                handle.write(np.ascontiguousarray(b, dtype="<f4").tobytes())

    @classmethod
    def load(cls, path: str | Path) -> "BearoffNet":
        raw = Path(path).read_bytes()
        if raw[:8] != MAGIC:
            raise ValueError(f"{path} is not a {MAGIC.decode()} file")
        version, count = struct.unpack_from("<ii", raw, 8)
        offset = 16
        shapes = []
        for _ in range(count):
            shapes.append(struct.unpack_from("<ii", raw, offset))
            offset += 8
        layers = []
        for rows, cols in shapes:
            weights = np.frombuffer(raw, dtype="<f4", count=rows * cols,
                                    offset=offset).reshape(cols, rows).T.copy()
            offset += 4 * rows * cols
            bias = np.frombuffer(raw, dtype="<f4", count=cols, offset=offset).copy()
            offset += 4 * cols
            layers.append((weights, bias))
        if offset != len(raw):
            raise ValueError(f"{path}: {len(raw) - offset} trailing bytes")
        return cls(layers, feature_version=version)
