#!/usr/bin/env python3
"""T33 — the one-sided bearoff database, computed exactly.

`BRIEF.md` §3.3 is the licence argument for doing this at all: a bearoff table
is **not** a trained network, it is exact dynamic programming, and two correct
implementations produce identical files. That is a mathematical fact rather than
a work of authorship — which is why the result carries no copyright question,
and also why its acceptance criterion can be equality rather than similarity.

## What is computed

For every arrangement of up to fifteen checkers on the six home-board points —
54 263 of them — the **distribution of the number of rolls** needed to bear all
of them off, under the policy that minimises the expected number of rolls.

`D[s][k]` is the probability that state `s` takes exactly `k + 1` more rolls.

## What is not reimplemented

The legal moves. They come from `gn_legal_plays`, the generator T01 already
cross-checked against GNU Backgammon over 4 284 comparisons. Writing a second
move generator specialised to the home board would be a second thing capable of
being wrong, and it would buy nothing: the general one is fast enough here.

The opponent is parked on its own one-point, out of contact. A one-sided bearoff
has no opponent by definition; the position only needs to be structurally valid
for the generator to accept it.

Usage:
    python tools/build_bearoff.py                 # compute and write
    python tools/build_bearoff.py --check         # verify against gnubg's table
"""

from __future__ import annotations

import argparse
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import BLACK, WHITE, Position  # noqa: E402

OUT = ROOT / "models" / "bearoff_one_sided.bin"

HOME_POINTS = 6
MAX_CHECKERS = 15

#: Every distinct roll, with its weight out of 36.
ROLLS = [
    (d1, d2, 1 if d1 == d2 else 2)
    for d1 in range(1, 7)
    for d2 in range(d1, 7)
]


def state_position(state: tuple[int, ...]) -> Position:
    """A valid Position holding `state` on WHITE's home board.

    WHITE bears off towards index 0, so its home board is indices 0-5 and
    `state[i]` sits on index i. BLACK's fifteen checkers are parked on index 23,
    which is BLACK's own one-point and therefore nowhere near WHITE's home.
    """
    points = [0] * 24
    for i, n in enumerate(state):
        points[i] = n
    points[23] = -MAX_CHECKERS
    return Position(tuple(points), (0, 0), (MAX_CHECKERS - sum(state), 0), WHITE)


def successors(state: tuple[int, ...], d1: int, d2: int) -> list[tuple[int, ...]]:
    """The states reachable from `state` with this roll."""
    plays = state_position(state).legal_plays(d1, d2)
    if not plays:
        return [state]  # no legal play: the roll is wasted, the state stands
    return [tuple(play.result.points[:HOME_POINTS]) for play in plays]


def enumerate_states() -> list[tuple[int, ...]]:
    """All arrangements of 0..15 checkers on six points, ordered by pip count.

    The order matters: every bearoff move strictly reduces the pip count, so
    processing in increasing pip order guarantees a state's successors are
    already solved when it is reached. No recursion, no memo table to invalidate.
    """
    states: list[tuple[int, ...]] = []

    def walk(prefix: tuple[int, ...], remaining: int) -> None:
        if len(prefix) == HOME_POINTS:
            states.append(prefix)
            return
        for n in range(remaining + 1):
            walk(prefix + (n,), remaining - n)

    walk((), MAX_CHECKERS)
    states.sort(key=lambda s: sum(n * (i + 1) for i, n in enumerate(s)))
    return states


def solve() -> dict[tuple[int, ...], list[float]]:
    """The distribution of rolls-to-finish for every state."""
    states = enumerate_states()
    print(f"{len(states)} états, résolus par pips croissants", flush=True)

    empty = (0,) * HOME_POINTS
    # L'état vide est déjà fini : il n'a pas de distribution sur « encore N
    # jets ». La liste vide dit cela, et le décalage plus bas s'en accommode.
    distributions: dict[tuple[int, ...], list[float]] = {empty: [1.0]}
    expected: dict[tuple[int, ...], float] = {empty: 0.0}

    started = time.perf_counter()
    for done, state in enumerate(states):
        if state == empty:
            continue

        # Pour chaque jet, le successeur qui minimise l'espérance du nombre de
        # jets restants. C'est la politique que la table décrit ; une autre
        # politique donnerait une autre table, également « exacte » et non
        # comparable à la référence.
        chosen: list[tuple[int, tuple[int, ...]]] = []
        for d1, d2, weight in ROLLS:
            best = None
            best_expected = None
            for candidate in successors(state, d1, d2):
                value = expected[candidate]
                if best_expected is None or value < best_expected:
                    best, best_expected = candidate, value
            chosen.append((weight, best))

        expected[state] = 1.0 + sum(w * expected[s] for w, s in chosen) / 36.0

        longest = max(len(distributions[s]) for _, s in chosen)
        merged = [0.0] * (longest + 1)
        for weight, successor in chosen:
            share = weight / 36.0
            for k, p in enumerate(distributions[successor]):
                merged[k + 1] += share * p

        # `merged[0]` est la probabilité de finir en zéro jet, structurellement
        # nulle pour un état non vide. On la retire pour que l'indice 0 désigne
        # « exactement un jet », qui est la convention de la table de référence.
        # Sans cela les deux tables décrivent la même chose et ne se comparent
        # pas — c'est exactement ce qui s'est produit à la première tentative,
        # avec un max|Δ| de 1,0 sur l'état le plus simple qui soit.
        distributions[state] = merged[1:]

        if done % 5000 == 0 and done:
            rate = done / (time.perf_counter() - started)
            print(f"  {done}/{len(states)} — {rate:.0f} états/s", flush=True)

    return distributions


def id_map() -> dict[int, tuple[int, ...]]:
    """gnubg's own state numbering, used only to line the two tables up.

    Borrowing the index is not borrowing the answer: what gets compared is the
    distribution, which is computed here from scratch.
    """
    import gnubg_nn

    return {i: tuple(gnubg_nn.bearoff_id_2_pos(i)) for i in range(1, 54264)}


def write(distributions: dict[tuple[int, ...], list[float]], path: Path) -> None:
    """A flat binary: for each id, the length then the float64 distribution."""
    mapping = id_map()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(b"GNBO")
        handle.write(struct.pack("<i", len(mapping)))
        for identifier in sorted(mapping):
            distribution = distributions[mapping[identifier]]
            handle.write(struct.pack("<i", len(distribution)))
            handle.write(struct.pack(f"<{len(distribution)}d", *distribution))


def check(distributions: dict[tuple[int, ...], list[float]]) -> int:
    """Cross-check every entry against GNU Backgammon's table."""
    import gnubg_nn

    mapping = id_map()
    worst = 0.0
    worst_id = None
    mismatched_length = 0

    for identifier, state in mapping.items():
        ours = distributions[state]
        theirs = list(gnubg_nn.bearoff_probabilities(identifier))

        # Les queues nulles ne sont pas une différence : une distribution qui
        # s'arrête plus tôt dit la même chose qu'une qui traîne des zéros.
        length = max(len(ours), len(theirs))
        padded_ours = ours + [0.0] * (length - len(ours))
        padded_theirs = theirs + [0.0] * (length - len(theirs))
        if len(ours) != len(theirs):
            trimmed_ours = [p for p in ours if p != 0.0]
            trimmed_theirs = [p for p in theirs if p != 0.0]
            if len(trimmed_ours) != len(trimmed_theirs):
                mismatched_length += 1

        for a, b in zip(padded_ours, padded_theirs):
            delta = abs(a - b)
            if delta > worst:
                worst, worst_id = delta, identifier

    print(f"\nVérification croisée contre la table de GNU Backgammon")
    print(f"  {len(mapping)} états comparés")
    print(f"  max|Δ| = {worst:.3e}" + (f" (id {worst_id}, {mapping[worst_id]})" if worst_id else ""))
    print(f"  longueurs utiles divergentes : {mismatched_length}")

    if worst < 1e-9:
        print("  → identiques. Deux implémentations correctes d'un calcul exact.")
        return 0
    print("  → DIVERGENTES. Une des deux se trompe, ou la politique diffère.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    started = time.perf_counter()
    distributions = solve()
    print(f"résolu en {time.perf_counter() - started:.1f} s")

    status = check(distributions)

    if not args.check:
        write(distributions, Path(args.out))
        print(f"\nécrit dans {args.out} "
              f"({Path(args.out).stat().st_size / 1024:.0f} Kio)")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
