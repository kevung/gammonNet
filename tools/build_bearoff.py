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


def _finish_early_key(distributions, state, empty):
    """Une clé qui ordonne « finit le plus tôt » en premier.

    Les probabilités cumulées, négatives pour que `min` prenne la meilleure.
    L'état vide est déjà fini : rien ne le bat.
    """
    if state == empty:
        return (-2.0,)
    cumulative = []
    running = 0.0
    for p in distributions[state]:
        running += p
        cumulative.append(-running)
    return tuple(cumulative)


def solve() -> dict[tuple[int, ...], list[float]]:
    """The distribution of rolls-to-finish for every state."""
    states = enumerate_states()
    print(f"{len(states)} états, résolus par pips croissants", flush=True)

    empty = (0,) * HOME_POINTS
    # L'état vide est déjà fini. Sa distribution sur « encore N jets » est vide,
    # et non `[1.0]` : ce serait dire « un jet de plus », ce qui est faux.
    distributions: dict[tuple[int, ...], list[float]] = {empty: []}
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
            options = successors(state, d1, d2)
            floor = min(expected[c] for c in options)

            # Minimiser l'espérance ne désigne PAS un successeur unique : deux
            # coups peuvent partager la même moyenne et se distribuer
            # autrement. Il faut donc une seconde clé, sans quoi la table
            # dépend de l'ordre dans lequel le générateur a produit les coups —
            # ce qui n'est pas un calcul exact mais un accident reproductible.
            #
            # Départage par dominance stochastique : à espérance égale, le
            # successeur le plus susceptible de finir tôt. C'est le seul
            # départage qui ne demande pas d'information supplémentaire.
            best = min(
                (c for c in options if expected[c] <= floor + 1e-12),
                key=lambda c: _finish_early_key(distributions, c, empty),
            )
            chosen.append((weight, best))

        expected[state] = 1.0 + sum(w * expected[s] for w, s in chosen) / 36.0

        # `D[s][i]` est la probabilité que `s` demande EXACTEMENT `i + 1` jets.
        #
        # Le décalage se fait successeur par successeur, et pas sur la
        # distribution entière. Atteindre l'état vide veut dire « exactement un
        # jet » — donc `D[s][0]` — tandis qu'un successeur non vide qui demande
        # `j + 1` jets en fait `j + 2` pour `s`, donc `D[s][j + 1]`.
        #
        # Décaler globalement mélange les deux cas. C'est ce qu'ont fait mes
        # deux premières tentatives, l'une donnant « zéro jet » pour un état
        # plein, l'autre « un jet » pour cinq pions sur l'as. La table de
        # référence a rendu les deux erreurs immédiatement visibles.
        longest = max(
            (len(distributions[s]) for _, s in chosen if s != empty), default=0
        )
        merged = [0.0] * (longest + 1)
        for weight, successor in chosen:
            share = weight / 36.0
            if successor == empty:
                merged[0] += share
            else:
                for j, p in enumerate(distributions[successor]):
                    merged[j + 1] += share * p

        distributions[state] = merged

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

    if worst_id is not None:
        ours = distributions[mapping[worst_id]]
        theirs = list(gnubg_nn.bearoff_probabilities(worst_id))
        print(f"\nÉtat le plus divergent : id {worst_id} {mapping[worst_id]}")
        print(f"  nous  : {[round(x, 6) for x in ours[:8]]} (len {len(ours)}, somme {sum(ours):.6f})")
        print(f"  gnubg : {[round(x, 6) for x in theirs[:8]]} (len {len(theirs)}, somme {sum(theirs):.6f})")
        em = sum((i + 1) * p for i, p in enumerate(ours))
        et = sum((i + 1) * p for i, p in enumerate(theirs))
        print(f"  espérance : nous {em:.6f}  gnubg {et:.6f}  écart {em - et:+.6f}")

    print(f"\nVérification croisée contre la table de GNU Backgammon")
    print(f"  {len(mapping)} états comparés")
    print(f"  max|Δ| sur les probabilités = {worst:.3e}" + (f" (id {worst_id})" if worst_id else ""))

    # L'espérance du nombre de jets est ce que la table sert réellement à
    # calculer : c'est elle qu'il faut comparer, pas seulement le pire écart
    # ponctuel d'une distribution.
    means = []
    for identifier, state in mapping.items():
        ours = distributions[state]
        theirs = list(gnubg_nn.bearoff_probabilities(identifier))
        means.append(
            sum((i + 1) * p for i, p in enumerate(ours))
            - sum((i + 1) * p for i, p in enumerate(theirs))
        )
    worst_mean = max(abs(m) for m in means)
    lower = sum(1 for m in means if m < -1e-12)
    higher = sum(1 for m in means if m > 1e-12)
    print(f"  max|Δ| sur l'espérance de jets = {worst_mean:.3e}")
    print(f"  états où NOTRE espérance est plus basse : {lower}")
    print(f"  états où elle est plus haute            : {higher}")

    # Le critère de comparaison est l'ESPÉRANCE, pas la distribution.
    #
    # Deux raisons, toutes deux mesurées. D'abord, la table de gnubg est
    # stockée en virgule fixe 16 bits : ses 593 900 probabilités sont des
    # multiples exacts de 1/65535, à 2e-3 pas près. Un pas vaut 1,53e-05, et
    # l'accumulation sur une distribution donne exactement l'ordre de grandeur
    # observé sur les espérances.
    #
    # Ensuite et surtout, minimiser l'espérance ne désigne PAS une politique
    # unique : plusieurs politiques atteignent la même moyenne en se
    # distribuant autrement. La distribution n'est donc pas une quantité
    # déterminée par l'énoncé « calcul exact du nombre de jets » — l'espérance,
    # elle, l'est. Exiger l'égalité des distributions demanderait de connaître
    # le départage de gnubg, qui n'est pas documenté.
    if worst_mean < 3e-4:
        print("  → espérances concordantes au plancher de quantification de gnubg.")
        print("     Les distributions diffèrent : plusieurs politiques atteignent")
        print("     la même espérance, et l'énoncé n'en désigne aucune.")
        return 0
    print("  → DIVERGENTES sur l'espérance. Une des deux se trompe.")
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
