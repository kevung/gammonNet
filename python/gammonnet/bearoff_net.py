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

## The two families, and why the second exists

**Hand features alone** ask the network to rediscover, from six counts, what a
bearoff race is. That is the small artefact -- tens of kilobytes -- and it is
the first thing to try.

**Hand features plus a learned code per layout** is the second family. There
are only 12 376 layouts per side, so a table of `d` numbers each is a legitimate
part of the artefact: at `d = 12` it is 297 Kio in float32, 149 Kio in float16,
against the 1,2 Gio it replaces. Mathematically this is the same network fed a
one-hot identity of the layout; practically it is a lookup, and it lets the
network hold what a race *is* rather than deduce it from counts every time.

Which family wins is a measurement, and both are measured. The layout code
needs the combinatorial rank of a layout at inference -- `side_index` -- which
is the same rank `bearoff.bearoff_index` computes, tabulated once here so that
a batch is a `searchsorted` rather than twelve thousand python loops.

## The weight file

A deliberately plain format (`GNBONET1`), not BGNN. The BGNN writer in
`vendor/` describes 196-in / 5-out prob5 networks with nested sigmoids; this
network is 96-in / 1-out with a tanh, and pretending it is the same shape would
buy nothing and cost a reader that lies.

    magic   8 bytes  b"GNBONET1"
    int32   feature version
    int32   output activation: 0 = tanh, 1 = identity
    int32   layout-code width d (0 when there is none)
    int32   number of layers L
    L x (int32 in, int32 out)
    then, when d > 0, the 12 376 x d float32 layout codes
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

#: Every layout of the domain, at the combinatorial rank gnubg gives it, and
#: the sorted keys that turn a batch of layouts into one `searchsorted`.
def _layout_table():
    from .bearoff import bearoff_index
    layouts = []

    def walk(prefix, remaining):
        if len(prefix) == POINTS:
            layouts.append(tuple(prefix))
            return
        for count in range(remaining + 1):
            walk(prefix + [count], remaining - count)

    walk([], CHEQUERS)
    counts = np.array(layouts, dtype=np.int16)
    ranks = np.array([bearoff_index(layout, POINTS) for layout in layouts],
                     dtype=np.int32)
    keys = counts.astype(np.int64) @ ((CHEQUERS + 1) **
                                      np.arange(POINTS, dtype=np.int64))
    order = np.argsort(keys)
    return keys[order], ranks[order], counts.shape[0]


_KEYS, _RANKS, LAYOUTS = _layout_table()


def side_index(counts: np.ndarray) -> np.ndarray:
    """The combinatorial rank of each layout, `(N, 6)` counts in.

    The same rank as `bearoff.bearoff_index`, which the tests check pairwise --
    two ways of computing an index are two ways of being off by one.
    """
    counts = np.asarray(counts, dtype=np.int64).reshape(-1, POINTS)
    keys = counts @ ((CHEQUERS + 1) ** np.arange(POINTS, dtype=np.int64))
    found = np.searchsorted(_KEYS, keys)
    if np.any(found >= _KEYS.size) or np.any(_KEYS[np.minimum(found, _KEYS.size - 1)] != keys):
        raise KeyError("layout outside the domain")
    return _RANKS[found]

#: How the last layer is finished. `tanh` keeps the output inside the range an
#: equity can take; `identity` does not, and trains better where it matters --
#: most of the domain is lopsided, `tanh` saturates there, and a saturated unit
#: has no gradient to give exactly on the positions whose ordering is hardest.
#: Which of the two wins is a measurement, not a preference: see T78's fiche.
TANH, IDENTITY = 0, 1
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
                 feature_version: int = FEATURE_VERSION,
                 activation: int = TANH,
                 embedding: np.ndarray | None = None):
        if feature_version != FEATURE_VERSION:
            raise ValueError(
                f"weights encode features v{feature_version}, this module is "
                f"v{FEATURE_VERSION} -- retrain rather than reinterpret")
        self.embedding = (None if embedding is None
                          else np.ascontiguousarray(embedding, dtype=np.float32))
        width = SIDE_FEATURES + (0 if self.embedding is None
                                 else self.embedding.shape[1])
        if layers[0][0].shape[0] != 2 * width:
            raise ValueError(f"first layer takes {layers[0][0].shape[0]} inputs, "
                             f"the encoding gives {2 * width}")
        self.side_width = width
        # Une sortie : l'équité cubeless seule (T78). Quatre : les colonnes de
        # la table -- cubeless, puis les trois cubeful par possession du videau
        # (T80). Le nombre vit dans le fichier, il n'est pas supposé ici.
        self.outputs = layers[-1][0].shape[1]
        if self.outputs not in (1, 4):
            raise ValueError(f"{self.outputs} sorties : la table en a une ou quatre")
        self.layers = [(np.ascontiguousarray(w, dtype=np.float32),
                        np.ascontiguousarray(b, dtype=np.float32))
                       for w, b in layers]
        self.feature_version = feature_version
        if activation not in (TANH, IDENTITY):
            raise ValueError(f"unknown output activation {activation}")
        self.activation = activation

    # ── shape and cost ──────────────────────────────────────────────

    @property
    def sizes(self) -> list[int]:
        return [self.layers[0][0].shape[0]] + [w.shape[1] for w, _ in self.layers]

    @property
    def parameters(self) -> int:
        table = 0 if self.embedding is None else self.embedding.size
        return sum(w.size + b.size for w, b in self.layers) + table

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
        out = np.tanh(x) if self.activation == TANH else x
        return out[:, 0] if self.outputs == 1 else out

    def encode(self, counts: np.ndarray) -> np.ndarray:
        """One side's input block: its features, and its layout code if there is one."""
        features = side_features(counts)
        if self.embedding is None:
            return features
        return np.concatenate([features, self.embedding[side_index(counts)]], axis=1)

    def equities_from_counts(self, mine: np.ndarray, theirs: np.ndarray) -> np.ndarray:
        """Equity for the side on roll, from both layouts, `(N, 6)` each."""
        return self.forward(np.concatenate([self.encode(mine), self.encode(theirs)],
                                           axis=1))

    def equity(self, position):
        """Equity of `position`, seen by `position.turn`. Raises off-domain.

        A single float for a cubeless network; an `ExactEquity` -- the same
        four fields the table reader returns, in the same order -- for a
        four-output one, so that a caller can swap the table for the network
        without noticing.
        """
        if not contains(position):
            raise KeyError(f"outside the {POINTS}x{CHEQUERS} bearoff domain: {position!r}")
        white, black = position_sides(position)
        mine, theirs = (white, black) if position.turn == WHITE else (black, white)
        answer = self.equities_from_counts(np.array([mine]), np.array([theirs]))[0]
        if self.outputs == 1:
            return float(answer)
        from .bearoff import ExactEquity
        return ExactEquity(*(float(v) for v in answer))

    # ── storage ─────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        path = Path(path)
        with path.open("wb") as handle:
            handle.write(MAGIC)
            width = 0 if self.embedding is None else self.embedding.shape[1]
            handle.write(struct.pack("<iiii", self.feature_version, self.activation,
                                     width, len(self.layers)))
            for w, _ in self.layers:
                handle.write(struct.pack("<ii", w.shape[0], w.shape[1]))
            if self.embedding is not None:
                handle.write(np.ascontiguousarray(self.embedding, dtype="<f4").tobytes())
            for w, b in self.layers:
                handle.write(np.ascontiguousarray(w.T, dtype="<f4").tobytes())
                handle.write(np.ascontiguousarray(b, dtype="<f4").tobytes())

    @classmethod
    def load(cls, path: str | Path) -> "BearoffNet":
        raw = Path(path).read_bytes()
        if raw[:8] != MAGIC:
            raise ValueError(f"{path} is not a {MAGIC.decode()} file")
        version, activation, width, count = struct.unpack_from("<iiii", raw, 8)
        offset = 24
        shapes = []
        for _ in range(count):
            shapes.append(struct.unpack_from("<ii", raw, offset))
            offset += 8
        embedding = None
        if width:
            embedding = np.frombuffer(raw, dtype="<f4", count=LAYOUTS * width,
                                      offset=offset).reshape(LAYOUTS, width).copy()
            offset += 4 * LAYOUTS * width
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
        return cls(layers, feature_version=version, activation=activation,
                   embedding=embedding)
