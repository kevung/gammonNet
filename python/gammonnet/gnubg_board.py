"""Translate a gammonNet position into GNU Backgammon's board convention.

GNU Backgammon is an **instrument of measurement** here, never a source of code
or of weights (`CLAUDE.md`). This module is the bridge that lets us ask it
questions about a position we hold — used by T01 to cross-check legal play
generation against a genuinely independent implementation, and by T03 for the
oracle proper.

## The convention, established by probe rather than assumed

`gnubg` boards are `[[int] * 25, [int] * 25]`:

    board[1][j]   checkers of the player ON ROLL
    board[0][j]   checkers of the opponent
    index j       the point (j + 1) pips from bearing off, **for that player**
    index 24      that player's bar

Both halves are self-relative and both hold non-negative counts. So `board[1][0]`
is the on-roll player's ace point and `board[0][0]` is the opponent's ace point —
they are opposite ends of the physical board.

Verified against `gnubg_nn.position_id` and `gnubg_nn.key_of_board` on the
starting position and on plays returned by `gnubg_nn.moves`, which reports keys
in the **mover's** orientation (the mover stays at `board[1]` after the play).

## The pip count sentinel

Every conversion here is checked by pip count. `BRIEF.md` §6 keeps this rule for
a reason: an orientation error does not raise, it produces a plausible position
that is not the one you meant, and every measurement taken downstream is then
meaningless without ever looking wrong.
"""

from __future__ import annotations

from .rules import BLACK, NUM_POINTS, WHITE, Position

GnubgBoard = list[list[int]]


def to_gnubg(position: Position, on_roll: int | None = None) -> GnubgBoard:
    """Convert to a gnubg board seen from `on_roll` (default: `position.turn`).

    Raises ValueError if the pip counts do not survive the conversion.
    """
    if on_roll is None:
        on_roll = position.turn
    opponent = BLACK if on_roll == WHITE else WHITE

    board: GnubgBoard = [[0] * 25, [0] * 25]

    for i, n in enumerate(position.points):
        if n > 0:
            # Index i is WHITE's point (i + 1), so WHITE's own index is i.
            board[1 if on_roll == WHITE else 0][i] = n
        elif n < 0:
            # Index i is BLACK's point (24 - i), so BLACK's own index is 23 - i.
            board[1 if on_roll == BLACK else 0][NUM_POINTS - 1 - i] = -n

    board[1][24] = position.bar[on_roll]
    board[0][24] = position.bar[opponent]

    _assert_pips_survived(position, board, on_roll, opponent)
    return board


def from_gnubg(board: GnubgBoard, on_roll: int, turn: int | None = None) -> Position:
    """Convert back, given which of our players `board[1]` represents.

    `turn` defaults to `on_roll`; pass it explicitly to build a position whose
    checkers are seen from `on_roll` but where the other player is to act.
    """
    opponent = BLACK if on_roll == WHITE else WHITE
    points = [0] * NUM_POINTS

    # `board[1][j]` and `board[0][j]` are DIFFERENT physical points: both halves
    # are self-relative, so index j is the on-roll player's point (j + 1) and the
    # opponent's point (j + 1) counted from the other end. Both being occupied is
    # ordinary. The real conflict is two checkers of opposite colour landing on
    # the same absolute index, which is caught below.
    for half, player in ((board[1], on_roll), (board[0], opponent)):
        for j in range(NUM_POINTS):
            count = half[j]
            if not count:
                continue
            index = j if player == WHITE else NUM_POINTS - 1 - j
            if points[index]:
                raise ValueError(
                    f"les deux couleurs occupent le point d'index {index} — "
                    "le plateau gnubg fourni n'est pas une position légale"
                )
            points[index] = count if player == WHITE else -count

    bar = [0, 0]
    bar[on_roll] = board[1][24]
    bar[opponent] = board[0][24]

    # gnubg boards carry no borne-off count: it is implied by the 15 checkers
    # that are not on the board.
    off = [0, 0]
    off[on_roll] = 15 - sum(board[1])
    off[opponent] = 15 - sum(board[0])

    position = Position(
        points=tuple(points),
        bar=(bar[0], bar[1]),
        off=(off[0], off[1]),
        turn=on_roll if turn is None else turn,
    )
    _assert_pips_survived(position, board, on_roll, opponent)
    return position


def _gnubg_pip_count(half: list[int]) -> int:
    """Pips left for one half of a gnubg board. The bar counts 25."""
    return sum(n * (j + 1) for j, n in enumerate(half[:24])) + half[24] * 25


def _assert_pips_survived(
    position: Position, board: GnubgBoard, on_roll: int, opponent: int
) -> None:
    ours_on_roll = position.pip_count(on_roll)
    ours_opponent = position.pip_count(opponent)
    theirs_on_roll = _gnubg_pip_count(board[1])
    theirs_opponent = _gnubg_pip_count(board[0])

    if (ours_on_roll, ours_opponent) != (theirs_on_roll, theirs_opponent):
        raise ValueError(
            "la traduction vers gnubg ne conserve pas le compte de pips : "
            f"gammonNet ({ours_on_roll}, {ours_opponent}) vs "
            f"gnubg ({theirs_on_roll}, {theirs_opponent}). "
            "Tout ce qui suivrait serait dépourvu de sens."
        )


def key(position: Position, on_roll: int | None = None) -> str:
    """The gnubg 20-character position key, for set comparison of positions."""
    import gnubg_nn

    return gnubg_nn.key_of_board(to_gnubg(position, on_roll))


def legal_play_keys(position: Position, d1: int, d2: int) -> set[str]:
    """The set of positions GNU Backgammon considers reachable, as gnubg keys.

    `gnubg_nn.moves` returns keys in the mover's orientation, so these compare
    directly against `key(play.result, on_roll=position.turn)`.
    """
    import gnubg_nn

    return set(gnubg_nn.moves(to_gnubg(position), d1, d2, 0))
