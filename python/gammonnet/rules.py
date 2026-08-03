"""ctypes binding for `src/gn_rules.h` — positions and legal plays.

The C library is the authority. This module exists so that the measurement side
of the project (Python, per `CLAUDE.md`) can drive exactly the same code the
inference library will run, rather than a Python re-implementation that could
agree with the rules while disagreeing with the engine.

Conventions are the header's, repeated here because getting them wrong does not
crash — it produces plausible, wrong results:

    points[i]  signed checker count; > 0 is WHITE, < 0 is BLACK, 0 is empty.
               Index i is point (i + 1) for WHITE and point (24 - i) for BLACK.
               WHITE bears off towards index 0, BLACK towards index 23.
    turn       the player who acts NEXT.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LIBRARY = ROOT / "build" / "libgammonnet.so"

WHITE = 0
BLACK = 1

NUM_POINTS = 24
NUM_CHECKERS = 15
MAX_MOVES_PER_PLAY = 4
MAX_PLAYS = 2048

BAR = -1
OFF = -2


class _CPosition(ctypes.Structure):
    _fields_ = [
        ("points", ctypes.c_byte * NUM_POINTS),
        ("bar", ctypes.c_ubyte * 2),
        ("off", ctypes.c_ubyte * 2),
        ("turn", ctypes.c_ubyte),
    ]


class _CMove(ctypes.Structure):
    _fields_ = [("from_", ctypes.c_byte), ("to", ctypes.c_byte)]


class _CPlay(ctypes.Structure):
    _fields_ = [
        ("moves", _CMove * MAX_MOVES_PER_PLAY),
        ("num_moves", ctypes.c_int),
        ("result", _CPosition),
    ]


def _load() -> ctypes.CDLL:
    if not LIBRARY.is_file():
        raise ImportError(
            f"{LIBRARY} absent — lancer `make build`"
        )
    lib = ctypes.CDLL(str(LIBRARY))

    lib.gn_position_initial.argtypes = [ctypes.POINTER(_CPosition)]
    lib.gn_position_initial.restype = None

    for name in (
        "gn_position_pip_count",
        "gn_position_checker_count",
    ):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.POINTER(_CPosition), ctypes.c_int]
        fn.restype = ctypes.c_int

    for name in (
        "gn_position_is_valid",
        "gn_position_is_over",
        "gn_position_winner",
    ):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.POINTER(_CPosition)]
        fn.restype = ctypes.c_int

    lib.gn_position_swap_turn.argtypes = [ctypes.POINTER(_CPosition)]
    lib.gn_position_swap_turn.restype = None

    lib.gn_legal_plays.argtypes = [
        ctypes.POINTER(_CPosition),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(_CPlay),
        ctypes.c_int,
    ]
    lib.gn_legal_plays.restype = ctypes.c_int

    return lib


_LIB = _load()

# One reusable output buffer. Sized at MAX_PLAYS so that a refusal from the C
# side is always about generation capacity, never about this buffer.
_PLAY_BUFFER = (_CPlay * MAX_PLAYS)()


@dataclass(frozen=True)
class Move:
    """One sub-move. `from_` may be BAR, `to` may be OFF."""

    from_: int
    to: int

    def __repr__(self) -> str:
        src = "bar" if self.from_ == BAR else str(self.from_)
        dst = "off" if self.to == OFF else str(self.to)
        return f"{src}/{dst}"


@dataclass(frozen=True)
class Play:
    """A complete legal play and the position it reaches."""

    moves: tuple[Move, ...]
    result: "Position"

    def __repr__(self) -> str:
        return " ".join(repr(m) for m in self.moves) or "(no play)"


@dataclass(frozen=True)
class Position:
    points: tuple[int, ...] = field(default=(0,) * NUM_POINTS)
    bar: tuple[int, int] = (0, 0)
    off: tuple[int, int] = (0, 0)
    turn: int = WHITE

    # ── Construction ────────────────────────────────────────────────

    @classmethod
    def initial(cls) -> "Position":
        """The standard starting position, WHITE to act."""
        c = _CPosition()
        _LIB.gn_position_initial(ctypes.byref(c))
        return cls._from_c(c)

    @classmethod
    def _from_c(cls, c: _CPosition) -> "Position":
        return cls(
            points=tuple(c.points),
            bar=(c.bar[0], c.bar[1]),
            off=(c.off[0], c.off[1]),
            turn=c.turn,
        )

    def _to_c(self) -> _CPosition:
        c = _CPosition()
        for i, n in enumerate(self.points):
            c.points[i] = n
        c.bar[0], c.bar[1] = self.bar
        c.off[0], c.off[1] = self.off
        c.turn = self.turn
        return c

    # ── Queries ─────────────────────────────────────────────────────

    def pip_count(self, player: int) -> int:
        """Pips `player` must still travel. A checker on the bar counts 25.

        The project's cheapest sentinel: whenever a position crosses a format
        boundary, compare pip counts on both sides before trusting anything.
        """
        return _LIB.gn_position_pip_count(ctypes.byref(self._to_c()), player)

    def checker_count(self, player: int) -> int:
        return _LIB.gn_position_checker_count(ctypes.byref(self._to_c()), player)

    def is_valid(self) -> bool:
        return bool(_LIB.gn_position_is_valid(ctypes.byref(self._to_c())))

    def is_over(self) -> bool:
        return bool(_LIB.gn_position_is_over(ctypes.byref(self._to_c())))

    def winner(self) -> int | None:
        w = _LIB.gn_position_winner(ctypes.byref(self._to_c()))
        return None if w < 0 else w

    def swapped_turn(self) -> "Position":
        return Position(self.points, self.bar, self.off, BLACK if self.turn == WHITE else WHITE)

    # ── Legal plays ─────────────────────────────────────────────────

    def legal_plays(self, d1: int, d2: int) -> list[Play]:
        """Every distinct legal play for `turn`, with the position each reaches.

        An empty list means the player genuinely has no legal play — a real
        outcome, not an error. A refusal from the C side raises instead: a
        truncated list would be indistinguishable from a position with fewer
        options, and would make a search quietly blind.
        """
        count = _LIB.gn_legal_plays(
            ctypes.byref(self._to_c()), d1, d2, _PLAY_BUFFER, MAX_PLAYS
        )
        if count < 0:
            raise ValueError(
                f"gn_legal_plays a refusé la position {self!r} avec les dés "
                f"({d1}, {d2}) — position invalide, dés hors bornes, ou capacité "
                f"de génération atteinte. Refusé, jamais approximé."
            )

        plays = []
        for i in range(count):
            c_play = _PLAY_BUFFER[i]
            moves = tuple(
                Move(c_play.moves[m].from_, c_play.moves[m].to)
                for m in range(c_play.num_moves)
            )
            plays.append(Play(moves=moves, result=Position._from_c(c_play.result)))
        return plays

    def __repr__(self) -> str:
        side = "W" if self.turn == WHITE else "B"
        occupied = ",".join(f"{i}:{n}" for i, n in enumerate(self.points) if n)
        return f"Position({side} to act, bar={self.bar}, off={self.off}, [{occupied}])"
