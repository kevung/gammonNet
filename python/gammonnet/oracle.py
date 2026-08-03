"""GNU Backgammon as an instrument of measurement.

`CLAUDE.md` is explicit about what this is and is not. GNU Backgammon is run
here to **measure**, never to learn from and never to copy. Its output is not
covered by its licence — the FSF says so plainly — but its code and its weights
are, and neither enters this repository.

Nothing here is a source of truth about gammonNet's own strength. It is the
ruler, not the thing being measured.

## Two hazards, both established by probe rather than assumed

**The evaluation cache.** `gnubg_nn` caches evaluations. Timing a loop over one
repeated position measures the cache and not the engine — by a factor of about
3 000 at 1-ply and 60 000 at 2-ply, measured. Any throughput figure taken from
this module must come from **distinct** positions. See `docs/mesures/`.

**Global state.** The library keeps the match score and the cube in process-wide
globals, and it is not thread-safe. Parallel measurement must use **processes**,
never threads, or two workers will silently evaluate at each other's score.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from .rules import BLACK, WHITE, Play, Position
from . import gnubg_board as gb

import gnubg_nn

#: Position classes, as GNU Backgammon labels them.
CLASSES = {
    gnubg_nn.c_over: "over",
    gnubg_nn.c_bearoff: "bearoff",
    gnubg_nn.c_race: "race",
    gnubg_nn.c_crashed: "crashed",
    gnubg_nn.c_contact: "contact",
}


@dataclass(frozen=True)
class Evaluation:
    """The five probabilities, seen by the player on roll.

    The order was established by probe, not assumed: a position won outright
    returns `(1, 0, 0, 0, 0)`, the same position seen by the loser returns
    `(0, 0, 0, 0, 0)`, and a position about to win a gammon lights the second
    slot. This is the same five-way distribution `BRIEF.md` §6 requires for match
    play — the point being that a scalar equity cannot be converted to match
    equity, only a distribution can.
    """

    win: float
    win_gammon: float
    win_backgammon: float
    lose_gammon: float
    lose_backgammon: float

    @property
    def equity(self) -> float:
        """Cubeless money equity, in points per game.

        `(P(win) - P(lose)) + (gammons) + (backgammons)`, which is the usual
        reduction. It is offered for convenience and is **not** what match play
        should consume: use the distribution.
        """
        return (
            2.0 * self.win
            - 1.0
            + self.win_gammon
            + self.win_backgammon
            - self.lose_gammon
            - self.lose_backgammon
        )

    def nested_events_hold(self, tolerance: float = 1e-6) -> bool:
        """P(win) >= P(win gammon) >= P(win backgammon), and likewise for losses.

        A gammon is a win, and a backgammon is a gammon. A distribution that
        breaks this is not a distribution, and any equity computed from it is
        meaningless — plausible, but meaningless.
        """
        return (
            self.win + tolerance >= self.win_gammon >= self.win_backgammon - tolerance
            and (1.0 - self.win) + tolerance >= self.lose_gammon
            and self.lose_gammon + tolerance >= self.lose_backgammon
        )

    def as_tuple(self) -> tuple[float, float, float, float, float]:
        return (
            self.win,
            self.win_gammon,
            self.win_backgammon,
            self.lose_gammon,
            self.lose_backgammon,
        )


@dataclass(frozen=True)
class RankedPlay:
    """A candidate play with the oracle's opinion of it."""

    play: Play
    evaluation: Evaluation  # seen by the OPPONENT, who is on roll afterwards
    equity: float           # seen by the player who made the move


@contextlib.contextmanager
def match_score(us_away: int, them_away: int, crawford: bool = False):
    """Temporarily set the match score the oracle evaluates at.

    The score lives in a process-wide global inside the library. This context
    manager restores the money game afterwards so that a forgotten score cannot
    silently colour every later measurement.
    """
    gnubg_nn.set.score(us_away, them_away, 1 if crawford else 0)
    try:
        yield
    finally:
        gnubg_nn.set.score(0, 0, 0)


class Oracle:
    """GNU Backgammon, at a chosen search depth."""

    def __init__(self, ply: int = 0):
        if ply < 0:
            raise ValueError("la profondeur doit être positive ou nulle")
        self.ply = ply

    def __repr__(self) -> str:
        return f"Oracle(gnubg, {self.ply}-ply)"

    # ── Evaluation ──────────────────────────────────────────────────

    def evaluate(self, position: Position) -> Evaluation:
        """The five probabilities for `position`, seen by the player on roll.

        The translation to GNU Backgammon's board convention checks the pip
        count on the way through and raises rather than evaluate a position
        that is not the one intended.
        """
        return Evaluation(*gnubg_nn.probabilities(gb.to_gnubg(position), self.ply))

    def classify(self, position: Position) -> str:
        """`contact`, `crashed`, `race`, `bearoff` or `over`.

        Useful for reporting honestly: `BRIEF.md` §9 warns that a corpus heavy
        in bearoffs flatters an engine with exact tables and punishes one
        without, so a strength figure should say what it was measured on.
        """
        return CLASSES.get(gnubg_nn.classify(gb.to_gnubg(position)), "unknown")

    # ── Move choice ─────────────────────────────────────────────────

    def ranked_plays(self, position: Position, d1: int, d2: int) -> list[RankedPlay]:
        """Every legal play, ordered best first by the oracle's equity.

        The oracle's candidates are matched to **our** plays by resulting
        position key, rather than by re-applying its move notation. That reuses
        the generator T01 already checked against it and avoids a second,
        unverified way of applying a move.

        The candidate keys are in the **post-move** orientation — the mover has
        already handed over the turn — which is not the orientation
        `gnubg_nn.moves` uses. Established by probe over 8 621 positions.
        """
        ours = position.legal_plays(d1, d2)
        if not ours:
            return []

        by_key = {gb.key(play.result): play for play in ours}
        if len(by_key) != len(ours):
            raise AssertionError("deux coups légaux partagent une clé de position")

        _, candidates = gnubg_nn.best_move(
            gb.to_gnubg(position), d1, d2, self.ply, b"X", 0, 0, 1
        )

        ranked = []
        for key, _moves, probabilities, equity in candidates:
            play = by_key.get(key)
            if play is None:
                raise AssertionError(
                    f"GNU Backgammon propose un coup que nous ne générons pas ({key}) "
                    f"depuis {position!r} avec les dés {d1}-{d2}"
                )
            ranked.append(RankedPlay(play, Evaluation(*probabilities), equity))

        if len(ranked) != len(ours):
            raise AssertionError(
                f"{len(ranked)} candidats pour {len(ours)} coups légaux — "
                "l'oracle et nous ne voyons pas le même ensemble"
            )
        return ranked

    def best_play(self, position: Position, d1: int, d2: int) -> Play | None:
        """The oracle's choice, or None when there is no legal play."""
        ranked = self.ranked_plays(position, d1, d2)
        return ranked[0].play if ranked else None

    # ── Cube ────────────────────────────────────────────────────────

    def raw_cube_decision(self, position: Position) -> tuple:
        """The library's cube verdict, **uninterpreted**.

        Returned as it comes. Its six values were probed but their meaning was
        **not** established, and the library refuses the call outright in a
        money game — it needs a match score. Nothing in this repository reads
        this yet, and nothing should until T34 pins the semantics down against a
        corpus of known decisions.

        Exposed now only so that T34 inherits the plumbing rather than the
        temptation to guess.
        """
        key = gnubg_nn.key_of_board(gb.to_gnubg(position))
        return gnubg_nn.evaluate_cube_decision(key, self.ply, -1, b"X", 1)

    # ── Match equity ────────────────────────────────────────────────

    @staticmethod
    def match_equity(us_away: int, them_away: int) -> float:
        """The library's match equity for a score, in points.

        Antisymmetric by construction: `value(i, j) == -value(j, i)`, and zero on
        the diagonal. **Which table this is has not been established here** —
        recent GNU Backgammon ships Kazaross-XG2, but that is a claim to verify
        in T32, where attribution to Neil Kazaross becomes a delivery condition.
        """
        return gnubg_nn.equities.value(us_away, them_away)
