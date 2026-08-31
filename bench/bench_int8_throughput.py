#!/usr/bin/env python3
"""T73 — le débit RÉEL du chemin int8, pas celui du noyau seul.

## Pourquoi ce banc, et ce qu'il pourrait bien montrer de gênant

`bench_gemm_int8.c` a mesuré le noyau `gn_gemm_int8_relu` au lot du moteur
(32) : ×2,13 à ×2,23 sur float32, seuil DS-09 franchi. Mais il a aussi
mesuré, à la même occasion, le lot **1** : ×0,79 — **int8 PERD** à batch=1.
`Int8Network.forward` (`python/gammonnet/infer_int8.py`) et
`Int8NetworkEngine` (`python/gammonnet/arena.py`) évaluent une position à la
fois, en quatre appels `ctypes` séparés par décision — exactement le régime
où le micro-banc dit que le noyau perd, plus le coût `ctypes` lui-même.

Ce banc ne suppose donc rien : il CHRONOMÈTRE le chemin tel qu'il existe
réellement aujourd'hui, contre le chemin flottant existant, sur la même
machine, dans les mêmes conditions — `CLAUDE.md` règle 3.

    python bench/bench_int8_throughput.py [--positions 2000]
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import codec  # noqa: E402
from gammonnet.arena import Int8NetworkEngine, NetworkEngine, opening_roll  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.infer_int8 import Int8Network  # noqa: E402
from gammonnet.rules import BLACK, Position  # noqa: E402

FLOAT_MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
INT8_MODEL = ROOT / "models" / "qat_int8.bin"


def walk(count: int, seed: int) -> list[tuple[Position, int, int]]:
    rng = random.Random(seed)
    out: list[tuple[Position, int, int]] = []
    position = Position.initial()
    first, d1, d2 = opening_roll(rng)
    if first == BLACK:
        position = position.swapped_turn()
    while len(out) < count:
        if position.is_over():
            position = Position.initial()
            first, d1, d2 = opening_roll(rng)
            if first == BLACK:
                position = position.swapped_turn()
        plays = position.legal_plays(d1, d2)
        if plays:
            out.append((position, d1, d2))
            position = rng.choice(plays).result
        else:
            position = position.swapped_turn()
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--positions", type=int, default=2000)
    parser.add_argument("--decisions", type=int, default=500)
    args = parser.parse_args()

    print("T73 — débit réel : int8 (batch=1, tel que déployé) contre float32\n")

    # ── 1. Le forward seul, une position à la fois ──────────────────────
    positions = [p for p, _, _ in walk(args.positions, seed=20260831)]
    features = [codec.encode(p) for p in positions]

    with Network.load(FLOAT_MODEL) as net:
        start = time.perf_counter()
        for f in features:
            net.evaluate_features(f)
        float_elapsed = time.perf_counter() - start
    float_rate = len(features) / float_elapsed

    int8_net = Int8Network.load(INT8_MODEL)
    start = time.perf_counter()
    for f in features:
        int8_net.forward(f)
    int8_elapsed = time.perf_counter() - start
    int8_rate = len(features) / int8_elapsed

    print(f"forward seul, {len(features)} positions, une à la fois :")
    print(f"  float32   {float_rate:9.0f} éval/s   ({float_elapsed:.3f} s)")
    print(f"  int8      {int8_rate:9.0f} éval/s   ({int8_elapsed:.3f} s)")
    print(f"  rapport   ×{int8_rate / float_rate:.2f} (>1 = int8 plus rapide)\n")

    # ── 2. La décision complète : choisir un coup, tous ses candidats ───
    cases = walk(args.decisions, seed=20260832)
    float_engine = NetworkEngine()
    int8_engine = Int8NetworkEngine()
    rng = random.Random(0)

    start = time.perf_counter()
    for position, d1, d2 in cases:
        float_engine.choose(position, d1, d2, rng)
    float_decision_elapsed = time.perf_counter() - start

    start = time.perf_counter()
    for position, d1, d2 in cases:
        int8_engine.choose(position, d1, d2, rng)
    int8_decision_elapsed = time.perf_counter() - start

    print(f"décision complète (tous les coups candidats), {len(cases)} décisions :")
    print(f"  float32   {len(cases) / float_decision_elapsed:9.0f} décisions/s")
    print(f"  int8      {len(cases) / int8_decision_elapsed:9.0f} décisions/s")
    print(f"  rapport   ×{float_decision_elapsed / int8_decision_elapsed:.2f} "
          f"(>1 = int8 plus rapide)\n")

    # ── 3. La taille du fichier ──────────────────────────────────────────
    float_size = FLOAT_MODEL.stat().st_size
    int8_size = INT8_MODEL.stat().st_size
    print("taille des poids :")
    print(f"  float32   {float_size:9,} octets")
    print(f"  int8      {int8_size:9,} octets   (×{float_size / int8_size:.2f} plus petit)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
