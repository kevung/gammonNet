#!/usr/bin/env python3
"""Fige un repère natif : des positions, leurs caractéristiques, leurs sorties.

T20 demande que WebAssembly et natif coïncident à `max|Δ| < 1e-6`. Les comparer
suppose un point de comparaison, et ce point doit être **produit par le natif**
puis lu tel quel par le module WebAssembly — pas recalculé des deux côtés à
partir d'une graine, ce qui n'établirait rien si les deux générateurs
divergeaient.

Le fichier est binaire et plat, pour qu'un lecteur JavaScript n'ait rien à
interpréter :

    int32     magic 'GNRF'
    int32     nombre de positions
    int32     nombre de caractéristiques (196)
    int32     nombre de sorties (5)
    float32[] caractéristiques, count x 196, positions bout à bout
    float32[] sorties,          count x 5

    python tools/dump_reference.py [--count 2000] [--out build/reference.bin]
"""

from __future__ import annotations

import argparse
import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import Position, codec  # noqa: E402
from gammonnet.infer import Network  # noqa: E402

# La graine du projet. Le même corpus que `test_infer.py` et `test_codec.py` :
# les tâches parlent des mêmes positions, ce qui rend les rapports comparables.
SEED = 20260803
DEFAULT_COUNT = 2_000
DEFAULT_MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
DEFAULT_OUT = ROOT / "build" / "reference.bin"

MAGIC = b"GNRF"


def build_corpus(size: int) -> list[Position]:
    rng = random.Random(SEED)
    positions: list[Position] = []

    while len(positions) < size:
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()

        for _ in range(400):
            if position.is_over() or len(positions) >= size:
                break
            positions.append(position)

            plays = position.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
            position = rng.choice(plays).result if plays else position.swapped_turn()

    return positions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.model.is_file():
        print(f"{args.model} absent — lancer `make model`", file=sys.stderr)
        return 1

    positions = build_corpus(args.count)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    with Network.load(args.model) as network, args.out.open("wb") as handle:
        handle.write(MAGIC)
        handle.write(struct.pack("<3i", len(positions), codec.NUM_FEATURES, 5))

        features_blob = bytearray()
        outputs_blob = bytearray()

        for position in positions:
            features = codec.encode(position)
            probs = network.evaluate_features(features).as_tuple()
            features_blob += struct.pack(f"<{codec.NUM_FEATURES}f", *features)
            outputs_blob += struct.pack("<5f", *probs)

        handle.write(features_blob)
        handle.write(outputs_blob)

    print(f"→ {args.out} : {len(positions)} positions, {args.out.stat().st_size:,} octets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
