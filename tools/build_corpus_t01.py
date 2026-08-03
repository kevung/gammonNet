#!/usr/bin/env python3
"""Build the frozen T01 corpus of positions for legal-play cross-checking.

The corpus is generated **deterministically** from a seed and then committed, so
that a future disagreement is a change in behaviour and never a change in the
sample. Regenerating it with the same seed must reproduce it byte for byte.

Two sources feed it:

* **Handcrafted** positions, one per degenerate case T01 requires to be covered
  explicitly — no legal play at all, a single playable die, the obligation to
  play the larger die, partially playable doubles, forced and over-bear-offs.
  These are the cases a random walk reaches rarely or never, and they are
  precisely the ones where a rules engine is most likely to be wrong.

* **Random self-play**, filtered into categories until each quota is met:
  contact, checkers on the bar, closed and nearly-closed boards, pure races,
  and bearoffs.

Usage:
    python tools/build_corpus_t01.py            # write tests/data/corpus_t01.jsonl
    python tools/build_corpus_t01.py --check    # verify the committed file matches
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import BLACK, NUM_POINTS, WHITE, Position  # noqa: E402

CORPUS = ROOT / "tests" / "data" / "corpus_t01.jsonl"
SEED = 20260803

# Every distinct unordered roll. Doubles included.
ALL_ROLLS = [(d1, d2) for d1 in range(1, 7) for d2 in range(d1, 7)]

QUOTAS = {
    "contact": 60,
    "bar": 40,
    "closure": 25,
    "race": 30,
    "bearoff": 40,
}


# ── Classification ───────────────────────────────────────────────────


def _checkers(position: Position, player: int) -> list[tuple[int, int]]:
    """(index, count) of `player`'s checkers on points, own-order irrelevant."""
    return [
        (i, n if player == WHITE else -n)
        for i, n in enumerate(position.points)
        if (n > 0) == (player == WHITE) and n != 0
    ]


def _furthest_index(position: Position, player: int) -> int | None:
    """Index of the checker with the most pips still to travel."""
    owned = [i for i, _ in _checkers(position, player)]
    if not owned:
        return None
    return max(owned) if player == WHITE else min(owned)


def is_race(position: Position) -> bool:
    """True when the two players can no longer hit each other."""
    if position.bar[WHITE] or position.bar[BLACK]:
        return False
    white = _furthest_index(position, WHITE)
    black = _furthest_index(position, BLACK)
    if white is None or black is None:
        return True
    # WHITE travels towards 0, BLACK towards 23. They have passed each other
    # once WHITE's furthest-back checker is beyond BLACK's.
    return white < black


def in_bearoff(position: Position, player: int) -> bool:
    """True when every one of `player`'s checkers is home (or already off)."""
    if position.bar[player]:
        return False
    home = range(0, 6) if player == WHITE else range(18, NUM_POINTS)
    return all(i in home for i, _ in _checkers(position, player))


def made_point_run(position: Position, player: int) -> int:
    """Longest run of consecutive points held by `player` with 2+ checkers."""
    best = run = 0
    for i in range(NUM_POINTS):
        n = position.points[i]
        held = (n >= 2) if player == WHITE else (n <= -2)
        run = run + 1 if held else 0
        best = max(best, run)
    return best


def classify(position: Position) -> str:
    if position.bar[WHITE] or position.bar[BLACK]:
        return "bar"
    if in_bearoff(position, WHITE) or in_bearoff(position, BLACK):
        return "bearoff"
    if is_race(position):
        return "race"
    if max(made_point_run(position, WHITE), made_point_run(position, BLACK)) >= 5:
        return "closure"
    return "contact"


# ── Handcrafted degenerate cases ─────────────────────────────────────


def _position(white: dict[int, int], black: dict[int, int], *,
              bar=(0, 0), off=(0, 0), turn=WHITE) -> Position:
    """Build a position from {index: count} maps. Indices are gn_rules indices."""
    points = [0] * NUM_POINTS
    for i, n in white.items():
        points[i] = n
    for i, n in black.items():
        points[i] = -n
    return Position(tuple(points), tuple(bar), tuple(off), turn)


def handcrafted() -> list[tuple[str, str, Position]]:
    """(label, category, position) for each case T01 must cover explicitly."""
    cases: list[tuple[str, str, Position]] = []

    # 1. No legal play at all: WHITE is on the bar and BLACK owns every point of
    #    WHITE's entry board (indices 18-23 are BLACK's home, where WHITE enters).
    cases.append((
        "aucun-coup-legal-plateau-ferme",
        "no_move",
        _position(
            white={12: 5, 11: 5, 10: 3},
            black={18: 2, 19: 2, 20: 2, 21: 2, 22: 2, 23: 2, 0: 3},
            bar=(2, 0),
            turn=WHITE,
        ),
    ))

    # 2. A single playable die: WHITE is on the bar and five of the six entry
    #    points are shut, leaving index 18 — a 6. Any roll without a 6 has no
    #    legal play at all, since nothing else may move while a checker waits on
    #    the bar. WHITE's other fourteen checkers sit on the ace point, where
    #    they are frozen anyway: their only move would be to bear off, which is
    #    illegal while a checker is outside the home board.
    cases.append((
        "un-seul-de-jouable-entree-unique",
        "no_move",
        _position(
            white={0: 14},
            black={19: 2, 20: 2, 21: 2, 22: 2, 23: 2, 11: 5},
            bar=(1, 0),
            turn=WHITE,
        ),
    ))

    # 3. Must play the larger die. WHITE is on the bar with exactly two entry
    #    points open — index 23 (a 1) and index 18 (a 6) — and index 17 shut, so
    #    neither entry allows a second sub-move. Both dice are playable alone,
    #    never together; the rules then force the larger. With (6, 1) only the
    #    entry on index 18 is legal. WHITE's other fourteen checkers sit on the
    #    ace point and cannot move at all while one checker is still outside.
    cases.append((
        "obligation-de-jouer-le-plus-grand-de",
        "bar",
        _position(
            white={0: 14},
            black={17: 2, 19: 2, 20: 2, 21: 2, 22: 2, 11: 5},
            bar=(1, 0),
            turn=WHITE,
        ),
    ))

    # 4. Doubles only partially playable. WHITE enters from the bar on index 23
    #    with a 1, and then stops: index 22 is shut, and the ace-point checkers
    #    cannot move. Three of the four sub-moves of a 1-1 are unplayable.
    cases.append((
        "doubles-partiellement-jouables",
        "bar",
        _position(
            white={0: 14},
            black={18: 2, 19: 2, 20: 2, 21: 2, 22: 2, 11: 5},
            bar=(1, 0),
            turn=WHITE,
        ),
    ))

    # 5. Forced bear-off with an over-bear: WHITE's furthest checker is on its
    #    3-point, so a 6 bears it off rather than moving it.
    cases.append((
        "sortie-forcee-sur-de-superieur",
        "bearoff",
        _position(
            white={0: 2, 1: 2, 2: 1},
            black={23: 2, 22: 2, 21: 2},
            off=(10, 9),
            turn=WHITE,
        ),
    ))

    # 6. Exact bear-off only: no over-bearing is legal because checkers remain
    #    further back than the die.
    cases.append((
        "sortie-exacte-uniquement",
        "bearoff",
        _position(
            white={0: 3, 3: 2, 5: 2},
            black={23: 3, 20: 2, 18: 2},
            off=(8, 8),
            turn=WHITE,
        ),
    ))

    # 7. The same three shapes with BLACK to act. An orientation bug that only
    #    shows up for one colour is exactly the failure this project fears, and
    #    a corpus of WHITE-to-act positions would never reveal it.
    cases.append((
        "noir-au-trait-sortie-forcee",
        "bearoff",
        _position(
            white={0: 2, 1: 2, 2: 2},
            black={23: 2, 22: 2, 21: 1},
            off=(9, 10),
            turn=BLACK,
        ),
    ))
    cases.append((
        "noir-au-trait-sur-la-barre",
        "bar",
        _position(
            white={5: 2, 4: 2, 3: 2, 2: 2, 1: 2, 17: 2, 16: 3},
            black={11: 5, 12: 5, 13: 3},
            bar=(0, 2),
            turn=BLACK,
        ),
    ))
    cases.append((
        "noir-au-trait-course-pure",
        "race",
        _position(
            white={0: 3, 1: 3, 2: 3, 3: 3, 4: 3},
            black={23: 3, 22: 3, 21: 3, 20: 3, 19: 3},
            turn=BLACK,
        ),
    ))

    return cases


# ── Random self-play ─────────────────────────────────────────────────


def sample_positions(rng: random.Random, quotas: dict[str, int]) -> list[tuple[str, str, Position]]:
    """Walk random games, keeping positions until every quota is filled."""
    collected: dict[str, list[Position]] = {k: [] for k in quotas}
    seen: set[tuple] = set()
    game = 0

    while any(len(collected[k]) < quotas[k] for k in quotas) and game < 20000:
        game += 1
        position = Position.initial()
        # Vary who starts, so neither colour is over-represented.
        if rng.random() < 0.5:
            position = position.swapped_turn()

        for _ in range(400):
            if position.is_over():
                break

            category = classify(position)
            fingerprint = (position.points, position.bar, position.off, position.turn)
            if (
                category in collected
                and len(collected[category]) < quotas[category]
                and fingerprint not in seen
                and rng.random() < 0.25
            ):
                collected[category].append(position)
                seen.add(fingerprint)

            d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
            plays = position.legal_plays(d1, d2)
            if not plays:
                position = position.swapped_turn()
                continue
            position = rng.choice(plays).result

    out = []
    for category in sorted(collected):
        for n, position in enumerate(collected[category]):
            out.append((f"{category}-{n:03d}", category, position))
    return out


# ── Serialisation ────────────────────────────────────────────────────


def to_record(identifier: str, category: str, position: Position) -> dict:
    return {
        "id": identifier,
        "category": category,
        "points": list(position.points),
        "bar": list(position.bar),
        "off": list(position.off),
        "turn": position.turn,
        "pips": [position.pip_count(WHITE), position.pip_count(BLACK)],
    }


def from_record(record: dict) -> Position:
    return Position(
        points=tuple(record["points"]),
        bar=tuple(record["bar"]),
        off=tuple(record["off"]),
        turn=record["turn"],
    )


def build() -> list[dict]:
    rng = random.Random(SEED)
    entries = handcrafted() + sample_positions(rng, QUOTAS)

    records = []
    for identifier, category, position in entries:
        if not position.is_valid():
            raise SystemExit(
                f"la position {identifier} est structurellement invalide — "
                "15 pions par joueur, aucun point à deux couleurs"
            )
        records.append(to_record(identifier, category, position))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed corpus is what this seed produces",
    )
    args = parser.parse_args()

    records = build()
    text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)

    if args.check:
        if not CORPUS.is_file():
            print(f"{CORPUS} absent", file=sys.stderr)
            return 1
        if CORPUS.read_text() != text:
            print(
                f"{CORPUS} diffère de ce que la graine {SEED} produit — "
                "le corpus n'est plus reproductible",
                file=sys.stderr,
            )
            return 1
        print(f"{CORPUS} : {len(records)} positions, reproductible")
        return 0

    CORPUS.parent.mkdir(parents=True, exist_ok=True)
    CORPUS.write_text(text)

    counts: dict[str, int] = {}
    for record in records:
        counts[record["category"]] = counts.get(record["category"], 0) + 1
    print(f"{CORPUS} : {len(records)} positions")
    for category in sorted(counts):
        print(f"    {category:10s} {counts[category]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
