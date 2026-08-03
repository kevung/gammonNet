#!/usr/bin/env python3
"""T12 — freeze a corpus of positions and the five outputs they produce.

The point is not to check that the network is right. It is to make a **drift
visible**: if the encoding, the loader, or the weights ever move, this corpus
says so, loudly, instead of letting a thousand later measurements shift by a
little.

Two things are frozen per position:

* a **digest of the 196 features**, so that a change in the codec is caught on
  its own, before it can be confused with a change in the weights. A digest
  rather than the vector: 2 050 vectors of 196 float32 would be three and a
  half megabytes of versioned file, and for detecting drift a digest says
  exactly as much;
* the **five raw probabilities**, bit for bit, as the hexadecimal of their
  float32 representation. Decimal text would round, and a corpus that cannot
  distinguish `0.5214856` from `0.5214855` cannot detect the drift it exists to
  detect.

Coverage is not left to chance. `PLAN.md` requires contact, race, bearoff, bar
**and backgame**, and a random walk produces the first three in abundance and
the last one almost never — so backgames are constructed.

Usage:
    python tools/build_corpus_t12.py            # write tests/data/corpus_t12.jsonl
    python tools/build_corpus_t12.py --check    # verify the committed file
"""

from __future__ import annotations

import argparse
import json
import hashlib
import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import BLACK, NUM_POINTS, WHITE, Position  # noqa: E402
from gammonnet import codec  # noqa: E402
from gammonnet.infer import Network  # noqa: E402

CORPUS = ROOT / "tests" / "data" / "corpus_t12.jsonl"
MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
SEED = 20260804

QUOTAS = {
    "contact": 700,
    "race": 400,
    "bearoff": 400,
    "bar": 400,
    "backgame": 150,
}


def f32_hex(value: float) -> str:
    """The exact bits of a float32, as hex. No rounding, no locale."""
    return struct.pack(">f", value).hex()


def hex_f32(text: str) -> float:
    return struct.unpack(">f", bytes.fromhex(text))[0]


def features_digest(features) -> str:
    """A digest over the exact float32 bits of the whole vector.

    Big-endian and explicit: a native-order digest would differ between
    architectures and turn a portability question into a false regression.
    """
    payload = b"".join(struct.pack(">f", v) for v in features)
    return hashlib.blake2b(payload, digest_size=16).hexdigest()


# ── Classification ───────────────────────────────────────────────────


def _owned(position: Position, player: int) -> list[int]:
    return [
        i
        for i, n in enumerate(position.points)
        if (n > 0 if player == WHITE else n < 0) and n != 0
    ]


def _furthest(position: Position, player: int) -> int | None:
    owned = _owned(position, player)
    if not owned:
        return None
    return max(owned) if player == WHITE else min(owned)


def is_race(position: Position) -> bool:
    if position.bar[WHITE] or position.bar[BLACK]:
        return False
    white, black = _furthest(position, WHITE), _furthest(position, BLACK)
    if white is None or black is None:
        return True
    return white < black


def in_bearoff(position: Position, player: int) -> bool:
    if position.bar[player]:
        return False
    home = range(0, 6) if player == WHITE else range(18, NUM_POINTS)
    return all(i in home for i in _owned(position, player))


def anchors_in_opponent_home(position: Position, player: int) -> int:
    """Points held with 2+ checkers inside the OPPONENT's home board."""
    home = range(18, NUM_POINTS) if player == WHITE else range(0, 6)
    return sum(
        1
        for i in home
        if (position.points[i] >= 2 if player == WHITE else position.points[i] <= -2)
    )


def is_backgame(position: Position) -> bool:
    """Two or more anchors in the opponent's home board, while well behind.

    The defining shape of a backgame, and the one a random walk essentially
    never reaches: holding two deep points is a deliberate strategy, not an
    accident of dice.
    """
    for player in (WHITE, BLACK):
        if anchors_in_opponent_home(position, player) >= 2:
            other = BLACK if player == WHITE else WHITE
            if position.pip_count(player) > position.pip_count(other) + 20:
                return True
    return False


def classify(position: Position) -> str:
    if is_backgame(position):
        return "backgame"
    if position.bar[WHITE] or position.bar[BLACK]:
        return "bar"
    if in_bearoff(position, WHITE) or in_bearoff(position, BLACK):
        return "bearoff"
    if is_race(position):
        return "race"
    return "contact"


# ── Constructed backgames ────────────────────────────────────────────


def backgames(rng: random.Random, count: int) -> list[Position]:
    """Build backgame shapes directly. A random walk does not reach them.

    WHITE holds two deep anchors in BLACK's home board (indices 18-23) and is
    far behind on pips; the remaining checkers are scattered plausibly.
    """
    out: list[Position] = []
    guard = 0

    while len(out) < count and guard < count * 200:
        guard += 1
        points = [0] * NUM_POINTS

        anchors = rng.sample([18, 19, 20, 21, 22], 2)
        for index in anchors:
            points[index] = 2

        white_left = 15 - 4
        # Le reste de Blanc, réparti vers l'arrière : c'est ce qui rend la
        # position réellement en retard, et donc réellement un backgame.
        for _ in range(white_left):
            index = rng.randint(6, 23)
            if points[index] < 0:
                continue
            points[index] += 1

        black_left = 15
        for _ in range(black_left):
            index = rng.randint(0, 17)
            if points[index] > 0:
                continue
            points[index] -= 1

        position = Position(
            tuple(points), (0, 0), (0, 0), WHITE if rng.random() < 0.5 else BLACK
        )
        if not position.is_valid():
            continue
        if any(abs(n) > 15 for n in position.points):
            continue
        if classify(position) != "backgame":
            continue
        out.append(position)

    return out


# ── The walk ─────────────────────────────────────────────────────────


def collect(rng: random.Random) -> dict[str, list[Position]]:
    found: dict[str, list[Position]] = {k: [] for k in QUOTAS}
    found["backgame"] = backgames(rng, QUOTAS["backgame"])

    seen: set[tuple] = set()
    games = 0

    while any(len(found[k]) < QUOTAS[k] for k in QUOTAS) and games < 60_000:
        games += 1
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()

        for _ in range(400):
            if position.is_over():
                break

            category = classify(position)
            fingerprint = (position.points, position.bar, position.off, position.turn)
            if (
                len(found[category]) < QUOTAS[category]
                and fingerprint not in seen
                and rng.random() < 0.3
            ):
                found[category].append(position)
                seen.add(fingerprint)

            plays = position.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
            position = rng.choice(plays).result if plays else position.swapped_turn()

    return found


# ── Build ────────────────────────────────────────────────────────────


def build() -> list[dict]:
    if not MODEL.is_file():
        raise SystemExit(f"{MODEL} absent — lancer `python tools/export_model.py`")

    rng = random.Random(SEED)
    found = collect(rng)

    records = []
    with Network.load(MODEL) as network:
        for category in sorted(found):
            for n, position in enumerate(found[category]):
                features = codec.encode(position)
                evaluation = network.evaluate(position)
                records.append({
                    "id": f"{category}-{n:04d}",
                    "category": category,
                    "position_id": codec.position_id(position),
                    "turn": position.turn,
                    "pips": [position.pip_count(WHITE), position.pip_count(BLACK)],
                    "features_digest": features_digest(features),
                    "outputs_hex": [f32_hex(v) for v in evaluation.as_tuple()],
                })
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    records = build()
    text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)

    if args.check:
        if not CORPUS.is_file():
            print(f"{CORPUS} absent", file=sys.stderr)
            return 1
        if CORPUS.read_text() != text:
            print(f"{CORPUS} diffère de ce que la graine {SEED} produit", file=sys.stderr)
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
