"""Translate a gammonNet position into the board convention of a third engine.

The engine on the other side of this bridge is an **instrument of measurement**,
exactly as GNU Backgammon is (`CLAUDE.md`): it is executed, never copied, and
nothing it produces enters an artefact this repository distributes. This module
is the only place that knows its board layout.

## The convention, established by reading its own source rather than assumed

The board is a flat list of 26 signed integers, held in the **mover's** frame:

    board[p]   for p in 1..24, point `p` counted from the mover's bearing-off
               end. Positive counts are the mover's checkers, negative the
               opponent's — one array for both players, unlike gnubg's two
               self-relative halves.
    board[0]   opponent checkers on the bar, a non-negative count
    board[25]  mover checkers on the bar, a non-negative count

Borne-off checkers are not stored: they are implied by the fifteen that are not
on the board, which is why `from_sage` reconstructs them by subtraction.

## The pip count sentinel

Every conversion here is checked by pip count, per `BRIEF.md` §6. An orientation
error does not raise: it produces a plausible position that is not the one you
meant, and every measurement taken downstream is then meaningless without ever
looking wrong. This is the cheapest guard the project owns, and the one whose
absence would be least visible.
"""

from __future__ import annotations

from .rules import BLACK, NUM_CHECKERS, NUM_POINTS, WHITE, Position

SageBoard = list[int]

#: Index of the mover's bar in a 26-element board.
MOVER_BAR = 25
#: Index of the opponent's bar.
OPPONENT_BAR = 0


def to_sage(position: Position, on_roll: int | None = None) -> SageBoard:
    """Convert to a 26-element board seen from `on_roll` (default: its turn).

    Raises ValueError if the pip counts do not survive the conversion.
    """
    if on_roll is None:
        on_roll = position.turn
    opponent = BLACK if on_roll == WHITE else WHITE

    board: SageBoard = [0] * 26

    for i, n in enumerate(position.points):
        if not n:
            continue
        # Index i is WHITE's point (i + 1) and BLACK's point (24 - i). The board
        # is numbered from the mover's end, and signed from the mover's side.
        if on_roll == WHITE:
            board[i + 1] = n
        else:
            board[NUM_POINTS - i] = -n

    board[MOVER_BAR] = position.bar[on_roll]
    board[OPPONENT_BAR] = position.bar[opponent]

    _assert_pips_survived(position, board, on_roll, opponent)
    return board


def from_sage(board: SageBoard, on_roll: int, turn: int | None = None) -> Position:
    """Convert back, given which of our players the positive counts represent.

    `turn` defaults to `on_roll`; pass it explicitly to build the position that
    follows a play, where the checkers are still seen from `on_roll` but the
    other player is to act.
    """
    opponent = BLACK if on_roll == WHITE else WHITE
    points = [0] * NUM_POINTS

    for p in range(1, NUM_POINTS + 1):
        n = board[p]
        if not n:
            continue
        index = p - 1 if on_roll == WHITE else NUM_POINTS - p
        points[index] = n if on_roll == WHITE else -n

    bar = [0, 0]
    bar[on_roll] = board[MOVER_BAR]
    bar[opponent] = board[OPPONENT_BAR]

    on_board_mover = sum(n for n in board[1:25] if n > 0) + board[MOVER_BAR]
    on_board_opponent = -sum(n for n in board[1:25] if n < 0) + board[OPPONENT_BAR]

    off = [0, 0]
    off[on_roll] = NUM_CHECKERS - on_board_mover
    off[opponent] = NUM_CHECKERS - on_board_opponent
    if off[0] < 0 or off[1] < 0:
        raise ValueError(
            f"plateau à plus de {NUM_CHECKERS} pions pour un camp : {board!r}. "
            "Refusé, jamais corrigé en silence."
        )

    position = Position(
        points=tuple(points),
        bar=(bar[0], bar[1]),
        off=(off[0], off[1]),
        turn=on_roll if turn is None else turn,
    )
    _assert_pips_survived(position, board, on_roll, opponent)
    return position


def _sage_pip_count(board: SageBoard, mover: bool) -> int:
    """Pips left for one side. The bar counts 25, as everywhere in this project."""
    if mover:
        return (
            sum(n * p for p, n in enumerate(board[:25]) if p >= 1 and n > 0)
            + board[MOVER_BAR] * 25
        )
    # The opponent travels the other way: its point `p` is 25 - p on this board.
    return (
        sum(-n * (25 - p) for p, n in enumerate(board[:25]) if p >= 1 and n < 0)
        + board[OPPONENT_BAR] * 25
    )


def _assert_pips_survived(
    position: Position, board: SageBoard, on_roll: int, opponent: int
) -> None:
    ours_on_roll = position.pip_count(on_roll)
    ours_opponent = position.pip_count(opponent)
    theirs_on_roll = _sage_pip_count(board, mover=True)
    theirs_opponent = _sage_pip_count(board, mover=False)

    if (ours_on_roll, ours_opponent) != (theirs_on_roll, theirs_opponent):
        raise ValueError(
            "la traduction ne conserve pas le compte de pips : "
            f"gammonNet ({ours_on_roll}, {ours_opponent}) vs "
            f"plateau ({theirs_on_roll}, {theirs_opponent}). "
            "Tout ce qui suivrait serait dépourvu de sens."
        )
