"""T04 — the round-robin harness: the central instrument of this project.

> **On ne peut pas entraîner ce qu'on ne sait pas mesurer.**

A round-robin is preferred to a rating because backgammon has no absolute
yardstick, and because a full matrix reveals **non-transitivity** — A beats B,
B beats C, C beats A — which really does occur between engines of different
styles. A single number would hide it.

## Duplicate dice, and why the harness is built around them

Every pair plays each dice sequence **twice, with the seats swapped**. The same
rolls, the other way round. What that removes is the largest source of variance
in the measurement — the dice themselves — leaving the difference between the
two engines, which is the only thing being measured.

It also gives the harness its sharpest self-test. Run the same engine against
itself and the two games of a pair are *the same game*, so the total is **exactly
zero**, not zero within a confidence interval. A null control that comes back
non-zero means the harness is broken, and says so loudly.

## Parallelism by process, never by thread

`gnubg-nn` keeps the match score and the cube in process-wide globals and is not
thread-safe (see T03). Two threads would silently evaluate at each other's
score — plausible results, wrong measurement. Workers here are **processes**,
and every game's dice and engine randomness are derived from the seed and the
game index, so results do not depend on how work was scheduled.

## What this harness does not do

**Cubeless money games only.** When this module was written (T04) the cube was
T34 and match equity was T32, and neither existed; building a cubeful mode on
an unwritten cube model would have produced numbers that look like
measurements. Both exist now, and the cubeful loop lives in `cubeful.py`
(T35), on top of this module's seeding and duplicate machinery. This one stays
cubeless on purpose: it is the instrument T04 froze, and the measurements made
with it are only comparable to itself.
"""

from __future__ import annotations

import hashlib
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Protocol

from .rules import BLACK, NUM_POINTS, WHITE, Move, Play, Position

#: Points a single cubeless game can be worth.
NORMAL, GAMMON, BACKGAMMON = 1, 2, 3


def _f32(left: float, op: str, right: float) -> float:
    """One arithmetic step, rounded to float32 — the engine's precision.

    Used to reproduce `gn_money_equity` term for term in Python. See
    `NetworkEngine.choose_via_python` for why the width matters.
    """
    import struct

    value = left + right if op == "+" else (left - right if op == "-" else left * right)
    return struct.unpack("f", struct.pack("f", value))[0]


# ── Engines ──────────────────────────────────────────────────────────


class Engine(Protocol):
    """Anything that can choose a play. The harness knows nothing else about it."""

    name: str

    def choose(self, position: Position, d1: int, d2: int, rng: random.Random) -> Play | None:
        """Pick one of `position.legal_plays(d1, d2)`, or None when there are none."""


@dataclass
class RandomEngine:
    """Uniformly random among legal plays.

    Useless as a player and indispensable as a control: it is the only engine
    whose expected result against itself is obviously zero, and it costs nothing
    to run, so it makes the harness's self-tests cheap.
    """

    name: str = "random"

    def choose(self, position: Position, d1: int, d2: int, rng: random.Random) -> Play | None:
        plays = position.legal_plays(d1, d2)
        return rng.choice(plays) if plays else None


@dataclass
class FirstPlayEngine:
    """Always takes the first play the generator offers. Deterministic and bad.

    Its use is as a **different** opponent that costs nothing. Two `RandomEngine`
    instances with different names are not different players: duplicate dice and
    per-seat randomness make them cancel exactly, which is a property of the
    harness worth testing but useless for testing anything else.
    """

    name: str = "first-play"

    def choose(self, position: Position, d1: int, d2: int, rng: random.Random) -> Play | None:
        plays = position.legal_plays(d1, d2)
        return plays[0] if plays else None


@dataclass
class NetworkEngine:
    """gammonNet's own network, choosing at 0-ply.

    For each legal play, the resulting position is evaluated and the play that
    leaves the **opponent** worst off is taken.

    The sign is the whole subtlety. `play.result` has already handed the turn
    over, so the network's five probabilities describe the OPPONENT's chances,
    not ours. Our equity is the negative of theirs — which is why this minimises
    where a careless reading would maximise. Getting it backwards produces an
    engine that plays deliberately badly and never says so; the round-robin
    would just report a large negative number that looks like a weak model.

    The whole decision runs in C (`gn_best_play_0ply`). T05 measured the Python
    binding at a factor of about ten, because it builds an object per legal
    play — roughly eighteen per decision — and a round-robin at the volume
    `BRIEF.md` §5 asks for cannot pay that. `choose_via_python` keeps the
    readable path, and a test holds the two to the same choices: the fast one is
    only worth trusting while they agree.
    """

    model: str = "models/cubeless_prob5_512_512_256_128.bin"
    name: str = "gammonnet-0ply"
    _network: object = field(default=None, repr=False, compare=False)

    def _load(self):
        if self._network is None:
            from pathlib import Path

            from .infer import Network

            path = Path(self.model)
            if not path.is_absolute():
                path = Path(__file__).resolve().parent.parent.parent / self.model
            self._network = Network.load(path)
        return self._network

    def choose(self, position: Position, d1: int, d2: int, rng: random.Random) -> Play | None:
        import ctypes

        from .rules import _CPlay, _CPosition, _LIB

        network = self._load()

        if not getattr(_LIB.gn_best_play_0ply, "argtypes", None):
            _LIB.gn_best_play_0ply.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_CPosition),
                ctypes.c_int,
                ctypes.c_int,
                ctypes.POINTER(_CPlay),
            ]
            _LIB.gn_best_play_0ply.restype = ctypes.c_int

        chosen = _CPlay()
        status = _LIB.gn_best_play_0ply(
            ctypes.c_void_p(network._handle),
            ctypes.byref(position._to_c()),
            d1,
            d2,
            ctypes.byref(chosen),
        )
        if status < 0:
            raise ValueError(f"gn_best_play_0ply a refusé {position!r} avec {d1}-{d2}")
        if status == 0:
            return None

        moves = tuple(
            Move(chosen.moves[m].from_, chosen.moves[m].to) for m in range(chosen.num_moves)
        )
        return Play(moves=moves, result=Position._from_c(chosen.result))

    def choose_via_python(
        self, position: Position, d1: int, d2: int, rng: random.Random
    ) -> Play | None:
        """The same choice, spelled out. Slow, readable, and the fast path's check.

        The equity is accumulated in **float32, in the engine's order of
        operations**, and that is not pedantry. `Evaluation.money_equity`
        computes in float64, which separates plays the engine considers tied:
        in a settled gammon position four different plays came out at exactly
        `1.999999523163` in float32 while float64 spread them over 1.2e-07 —
        quantisation noise, not a preference. Ranking on the wider type makes
        the readable path disagree with the engine on which of several equally
        good moves to play, and the disagreement says nothing about either.

        A reference implementation should model the arithmetic the engine
        actually performs, not an idealised one.
        """
        plays = position.legal_plays(d1, d2)
        if not plays:
            return None

        network = self._load()
        best, best_equity = None, None
        for play in plays:
            if play.result.is_over():
                # A finished game has no continuation to estimate; score the
                # stake exactly. Seen from the opponent, hence the minus.
                equity = -float(game_value(play.result, position.turn))
            else:
                w, wg, wbg, lg, lbg = network.evaluate(play.result).as_tuple()
                # gn_money_equity, term for term: 2w + wg + wbg - lg - lbg - 1
                equity = _f32(2.0, "*", w)
                for value, op in ((wg, "+"), (wbg, "+"), (lg, "-"), (lbg, "-"), (1.0, "-")):
                    equity = _f32(equity, op, value)

            if best_equity is None or equity < best_equity:
                best, best_equity = play, equity

        return best


@dataclass
class Int8NetworkEngine:
    """T73's real int8 path (`gammonnet.infer_int8.Int8Network`), choosing at
    0-ply — the first engine that can actually PLAY with it, not just be
    measured against it (`tools/measure_qat_decision_loss.py` already did
    the measuring; this is what turns the same evaluator into a player this
    harness can run in a game, a duplicate pair, or a round-robin).

    There is no C-level `gn_best_play_0ply` equivalent for this path yet —
    `Int8Network` is a Python object calling `gn_gemm_int8_relu_pc` directly,
    not a `GnNetwork*` the search machinery knows about — so this IS the only
    path, not a slow readable cross-check of a fast one like `NetworkEngine`
    keeps. `SearchEngine` at ply ≥ 1 has no int8 counterpart either: this
    engine is 0-ply only, and stays that way until `gn_search.c` itself
    learns to dispatch to the int8 kernel.
    """

    model: str = "models/qat_int8.bin"
    name: str = "gammonnet-int8-0ply"
    _network: object = field(default=None, repr=False, compare=False)

    def _load(self):
        if self._network is None:
            from pathlib import Path

            from .infer_int8 import Int8Network

            path = Path(self.model)
            if not path.is_absolute():
                path = Path(__file__).resolve().parent.parent.parent / self.model
            self._network = Int8Network.load(path)
        return self._network

    def choose(self, position: Position, d1: int, d2: int, rng: random.Random) -> Play | None:
        from . import codec

        plays = position.legal_plays(d1, d2)
        if not plays:
            return None

        network = self._load()

        # All non-terminal candidates in ONE call to `Int8Network.forward_batch`,
        # not a loop over `forward` — the whole reason for its existence
        # (`docs/mesures/2026-08-31-T73-int8-debit-taille.md`): the kernel
        # LOSES to float32 at batch=1 (×0,22 measured), and a decision's
        # candidates are exactly the batch that gets it back.
        #
        # Deduplicated by RESULT, not one entry per play: many move orderings
        # land on the same final position (doubles especially), and the
        # kernel's accumulator caps a batch at 256 — evaluating the same
        # position twice would spend that budget on nothing.
        unique_results = list({play.result for play in plays
                               if not play.result.is_over()})
        probs_by_play = {}
        if unique_results:
            batch = network.forward_batch(
                [codec.encode(result) for result in unique_results])
            probs_by_play = dict(zip(unique_results, batch))

        best, best_equity = None, None
        for play in plays:
            if play.result.is_over():
                # Same convention as `NetworkEngine`: seen from the opponent,
                # hence the minus.
                equity = -float(game_value(play.result, position.turn))
            else:
                w, wg, wbg, lg, lbg = probs_by_play[play.result]
                equity = 2.0 * w + wg + wbg - lg - lbg - 1.0

            if best_equity is None or equity < best_equity:
                best, best_equity = play, equity

        return best


@dataclass
class SearchEngine:
    """gammonNet at an arbitrary depth, through `gn_search`.

    `NetworkEngine` above is the 0-ply special case, kept because it goes
    straight to `gn_best_play_0ply` and skips the search machinery entirely.
    This one is what T36 needs: the **same** model, decided at 1-ply and 2-ply,
    so that the only thing changing between the three measurements is the depth.

    WHY THE FILTER IS PART OF THE ENGINE'S IDENTITY. `name` carries it, and that
    is deliberate. A 2-ply search that keeps five candidates and one that keeps
    every legal play are not the same player, and T31 measured how much they can
    differ. A round-robin whose rows do not say which one ran would be a matrix
    of unnamed engines.

    NOT LOADED AT CONSTRUCTION. The harness pickles engines out to worker
    processes, and a loaded network is a ctypes handle into this process's
    address space — it would either fail to pickle or, worse, travel as a
    meaningless integer. Every worker loads its own copy on first use, exactly
    as `NetworkEngine` does.
    """

    ply: int = 0
    #: `filter[d]` candidates survive at depth d; empty means no filtering.
    filter: tuple[int, ...] = ()
    model: str = "models/cubeless_prob5_512_512_256_128.bin"
    name: str = field(default="")
    _network: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if not self.name:
            suffix = "-f" + "/".join(str(k) for k in self.filter) if self.filter else ""
            self.name = f"gammonnet-{self.ply}ply{suffix}"

    def _load(self):
        if self._network is None:
            from pathlib import Path

            from .infer import Network

            path = Path(self.model)
            if not path.is_absolute():
                path = Path(__file__).resolve().parent.parent.parent / self.model
            self._network = Network.load(path)
        return self._network

    def choose(self, position: Position, d1: int, d2: int, rng: random.Random) -> Play | None:
        from .search import SearchConfig, best_play

        config = SearchConfig(ply=self.ply, filter=tuple(self.filter))
        candidate = best_play(self._load(), position, d1, d2, config)
        return candidate.play if candidate is not None else None


@dataclass
class OracleEngine:
    """GNU Backgammon at a chosen depth. An instrument, not a teacher."""

    ply: int = 0
    name: str = field(default="")
    _oracle: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if not self.name:
            self.name = f"gnubg-{self.ply}ply"

    def choose(self, position: Position, d1: int, d2: int, rng: random.Random) -> Play | None:
        if self._oracle is None:
            from .oracle import Oracle

            self._oracle = Oracle(ply=self.ply)
        return self._oracle.best_play(position, d1, d2)


# ── Deterministic randomness ─────────────────────────────────────────


def derive_seed(base: int, key: str, index: int) -> int:
    """A stable 64-bit seed from a base seed, a pair key and a game index.

    Deliberately not Python's `hash`, which is salted per process: a harness
    whose results depended on the process it ran in would fail the
    reproducibility criterion in a way that only showed up sometimes.
    """
    digest = hashlib.blake2b(f"{base}|{key}|{index}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def pair_key(a: str, b: str) -> str:
    """The same key for (A, B) and (B, A), so both orders draw the same dice.

    This is what makes antisymmetry a real property of the harness rather than
    an arithmetic identity we imposed by negating one cell of the matrix.
    """
    return "|".join(sorted((a, b)))


# ── One game ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GameResult:
    """The outcome of one game, from WHITE's point of view."""

    points: int  # positive if WHITE won, negative if BLACK did
    turns: int
    stalled: bool = False

    @property
    def winner(self) -> int:
        return WHITE if self.points > 0 else BLACK


def game_value(position: Position, winner: int) -> int:
    """1, 2 or 3 points, by the ordinary cubeless rules.

    A gammon is a win where the loser has borne off nothing; a backgammon is a
    gammon where the loser still has a checker on the bar or in the winner's
    home board.
    """
    loser = BLACK if winner == WHITE else WHITE

    if position.off[loser] > 0:
        return NORMAL

    if position.bar[loser] > 0:
        return BACKGAMMON

    home = range(0, 6) if winner == WHITE else range(18, NUM_POINTS)
    for i in home:
        n = position.points[i]
        if (n < 0) if loser == BLACK else (n > 0):
            return BACKGAMMON

    return GAMMON


def opening_roll(dice: random.Random) -> tuple[int, int, int]:
    """The real opening: one die each, higher plays first, doubles are re-rolled.

    Returns `(first_player, d1, d2)`.
    """
    while True:
        d1, d2 = dice.randint(1, 6), dice.randint(1, 6)
        if d1 != d2:
            return (WHITE if d1 > d2 else BLACK, d1, d2)


#: A game that has not ended by this many turns is abandoned. Two random engines
#: shuffling checkers can in principle wander for a very long time; a cap keeps a
#: measurement from hanging, and every abandoned game is reported rather than
#: quietly counted as a draw.
MAX_TURNS = 10_000


def play_game(
    white: Engine,
    black: Engine,
    dice: random.Random,
    white_rng: random.Random,
    black_rng: random.Random,
) -> GameResult:
    """One cubeless money game. All randomness arrives through the arguments."""
    first, d1, d2 = opening_roll(dice)

    position = Position.initial()
    if first == BLACK:
        position = position.swapped_turn()

    turns = 0
    while turns < MAX_TURNS:
        engine = white if position.turn == WHITE else black
        rng = white_rng if position.turn == WHITE else black_rng

        play = engine.choose(position, d1, d2, rng)
        position = play.result if play is not None else position.swapped_turn()
        turns += 1

        if position.is_over():
            winner = position.winner()
            points = game_value(position, winner)
            return GameResult(points if winner == WHITE else -points, turns)

        d1, d2 = dice.randint(1, 6), dice.randint(1, 6)

    return GameResult(0, turns, stalled=True)


# ── A duplicate pair of games ────────────────────────────────────────


def play_duplicate(
    a: Engine, b: Engine, base_seed: int, index: int, dice_key: str | None = None
) -> tuple[int, bool]:
    """Play one dice sequence twice, seats swapped. Returns A's net points.

    Both games draw from the same dice stream and the same per-SEAT randomness.
    Seat, not engine: that is what makes `A vs A` reproduce the identical game
    twice and total exactly zero.

    `dice_key` OVERRIDES the pairing key, and exists for one purpose: making
    **different matchups draw the same dice**. T36 measures the same model at
    three depths against GNU Backgammon at three depths, and the quantity it
    wants is the difference between the three — the slope, not the levels. Left
    to the default the three matchups would have different engine names, hence
    different keys, hence three independent dice draws, and the slope would
    carry the variance of all three. Sharing the key pairs them, and the
    difference is measured on the same games.

    It is deliberately explicit rather than automatic: two matchups that share
    dice are no longer independent, and any interval computed across them has to
    know it.
    """
    key = dice_key if dice_key is not None else pair_key(a.name, b.name)
    seed = derive_seed(base_seed, key, index)

    total = 0
    stalled = False
    for swapped in (False, True):
        dice = random.Random(seed)
        white_rng = random.Random(seed ^ 0x5741_4954)
        black_rng = random.Random(seed ^ 0x424C_4143)

        white, black = (b, a) if swapped else (a, b)
        result = play_game(white, black, dice, white_rng, black_rng)

        # `result.points` is WHITE's. A sits in the black seat on the swapped leg.
        total += -result.points if swapped else result.points
        stalled = stalled or result.stalled

    return total, stalled


# ── Bootstrap confidence interval ────────────────────────────────────


def bootstrap_ci(
    samples: list[float], resamples: int = 10_000, seed: int = 0, level: float = 0.95
) -> tuple[float, float]:
    """Percentile bootstrap interval. Deterministic, given the seed.

    Resampling is over the **duplicate pairs**, not over individual games: the
    two games of a pair share their dice and are not independent, so treating
    them separately would understate the interval — the classic way to make a
    measurement look sharper than it is.
    """
    if not samples:
        return (float("nan"), float("nan"))

    n = len(samples)

    # Resampling n values `resamples` times is O(resamples x n) — five billion
    # steps for a million-game run, and all of it single-threaded after the
    # workers have gone home. It was measured doing exactly that.
    #
    # A duplicate pair can only score a handful of distinct values (-6..+6 in
    # half-points), so group them and draw the COUNTS from a multinomial
    # instead. Drawing which sample lands in the resample n times and drawing
    # how many of each value land are the same distribution; this one costs
    # O(resamples x distinct), which is a few hundred thousand steps.
    counts: dict[float, int] = {}
    for value in samples:
        counts[value] = counts.get(value, 0) + 1

    values = sorted(counts)
    weights = [counts[v] / n for v in values]

    try:
        import numpy as np

        generator = np.random.default_rng(seed)
        drawn = generator.multinomial(n, weights, size=resamples)
        means = np.sort(drawn @ np.array(values) / n)
        tail = (1.0 - level) / 2.0
        return (float(means[int(tail * resamples)]),
                float(means[int((1.0 - tail) * resamples) - 1]))
    except ImportError:
        pass

    # Sans numpy : le tirage naïf, correct et lent. Il reste praticable sur les
    # petits volumes des tests, et un round-robin d'un million de parties a de
    # toute façon numpy sous la main.
    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        total = 0.0
        for _ in range(n):
            total += samples[rng.randrange(n)]
        means.append(total / n)

    means.sort()
    tail = (1.0 - level) / 2.0
    return (means[int(tail * resamples)], means[int((1.0 - tail) * resamples) - 1])


# ── A pair result ────────────────────────────────────────────────────


@dataclass(frozen=True)
class PairResult:
    a: str
    b: str
    pairs: int
    ppg: float
    ci: tuple[float, float]
    win_rate: float
    stalled: int

    @property
    def games(self) -> int:
        return self.pairs * 2

    def __str__(self) -> str:
        low, high = self.ci
        return (
            f"{self.a} vs {self.b}: {self.ppg:+.4f} ppg "
            f"[{low:+.4f} ; {high:+.4f}] · {self.win_rate * 100:.1f} % de victoires "
            f"· {self.games} parties"
        )


def _worker(payload):
    a, b, base_seed, indices = payload
    results = []
    for index in indices:
        results.append(play_duplicate(a, b, base_seed, index))
    return results


def play_pair(
    a: Engine,
    b: Engine,
    pairs: int,
    base_seed: int = 0,
    workers: int = 1,
    bootstrap: int = 10_000,
) -> PairResult:
    """Play `pairs` duplicate pairs (so `2 * pairs` games) and summarise.

    The result never carries a bare number: `BRIEF.md` §5 makes the confidence
    interval part of the figure, not an optional decoration.
    """
    indices = list(range(pairs))

    if workers <= 1:
        outcomes = _worker((a, b, base_seed, indices))
    else:
        chunks = [indices[i::workers] for i in range(workers)]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            gathered = list(pool.map(_worker, [(a, b, base_seed, c) for c in chunks]))
        # Reassemble in index order so the result cannot depend on scheduling.
        by_index = {}
        for chunk, results in zip(chunks, gathered):
            by_index.update(dict(zip(chunk, results)))
        outcomes = [by_index[i] for i in indices]

    points = [float(p) for p, _ in outcomes]
    stalled = sum(1 for _, s in outcomes if s)

    ppg = sum(points) / (2 * len(points)) if points else float("nan")
    low, high = bootstrap_ci([p / 2.0 for p in points], bootstrap, seed=base_seed)

    wins = sum(1 for p, _ in outcomes if p > 0) + 0.5 * sum(1 for p, _ in outcomes if p == 0)
    win_rate = wins / len(outcomes) if outcomes else float("nan")

    return PairResult(a.name, b.name, len(points), ppg, (low, high), win_rate, stalled)


# ── The matrix ───────────────────────────────────────────────────────


@dataclass
class RoundRobin:
    results: dict[tuple[str, str], PairResult]
    names: list[str]

    def ppg(self, a: str, b: str) -> float:
        if a == b:
            return 0.0
        return self.results[(a, b)].ppg

    def table(self) -> str:
        width = max(len(n) for n in self.names) + 2
        lines = [" " * width + "".join(f"{n:>12}" for n in self.names)]
        for a in self.names:
            row = f"{a:<{width}}"
            for b in self.names:
                row += "           —" if a == b else f"{self.ppg(a, b):>+12.4f}"
            lines.append(row)
        return "\n".join(lines)

    def report(self) -> str:
        lines = [self.table(), "", "Détail, avec intervalle de confiance à 95 % (bootstrap) :"]
        seen = set()
        for (a, b), result in self.results.items():
            if (b, a) in seen:
                continue
            seen.add((a, b))
            lines.append(f"  {result}")
            if result.stalled:
                lines.append(f"    ⚠ {result.stalled} paires abandonnées à {MAX_TURNS} coups")
        return "\n".join(lines)


def round_robin(
    engines: list[Engine],
    pairs: int,
    base_seed: int = 0,
    workers: int = 1,
    bootstrap: int = 10_000,
    include_self: bool = False,
) -> RoundRobin:
    """Every engine against every other, each ordered pair measured on its own.

    Both `(A, B)` and `(B, A)` are actually played rather than one being negated
    from the other. That costs twice as much and buys the antisymmetry check its
    meaning: it verifies that the pairing and seeding really are symmetric,
    instead of asserting an identity we imposed.
    """
    results: dict[tuple[str, str], PairResult] = {}

    for a in engines:
        for b in engines:
            if a.name == b.name and not include_self:
                continue
            results[(a.name, b.name)] = play_pair(a, b, pairs, base_seed, workers, bootstrap)

    return RoundRobin(results, [e.name for e in engines])
