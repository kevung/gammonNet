#!/usr/bin/env python3
"""Race zone corpus: contact-free positions outside the exact bearoff domain.

## What is extracted, and how it is labelled

Positions come from 0-ply self-play of the incumbent network, which is where a
race network will actually be asked. A position is kept when
`classify.in_race_zone` holds: no contact, and not covered by the two-sided
bearoff table. At most `--per-game` positions are taken per game, at random
plies, because consecutive positions of one game are nearly one sample.

Each kept position is labelled by an UNTRUNCATED rollout (`truncate = 0`), so
the five nested outcome frequencies are real game outcomes and not a network
reading. A label therefore carries sampling noise: its standard error is stored
beside it and is the floor under any error measured against it. Labels are the
rollouts of our own incumbent at 0-ply; nothing external is consulted.

The output is an `.npz` with `features`, `probs` (rollout frequencies),
`equity`, `se`, `ids`, `klass`, `pips`. It is deterministic in
(seed, workers) up to the rollout engine's own determinism.

Usage:
    python tools/build_race_corpus.py --model models/cubeless_prob5_512_512_256_256.bin \\
        --count 50000 --trials 1296 --workers 12 --seed 20261004 \\
        --out build/race_train.npz
    python tools/build_race_corpus.py --smoke
"""
from __future__ import annotations

import argparse
import random
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

DEFAULT_MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_256.bin"
DEFAULT_SEED = 20261004
MAX_PLIES = 300


def _shard(task):
    """One worker: walk games, keep race-zone positions, roll them out."""
    worker, seed, quota, model, trials, per_game = task
    from gammonnet import codec
    from gammonnet.arena import BLACK, opening_roll
    from gammonnet.classify import classify, in_race_zone
    from gammonnet.infer import Network
    from gammonnet.rollout import RolloutConfig, rollout
    from gammonnet.rules import Position
    from gammonnet.search import SearchConfig, search_plays

    rng = random.Random(seed)
    rows = {key: [] for key in
            ("features", "probs", "equity", "se", "ids", "klass", "pips")}
    seen = set()
    with Network.load(model) as network:
        while len(rows["ids"]) < quota:
            position = Position.initial()
            first, d1, d2 = opening_roll(rng)
            if first == BLACK:
                position = position.swapped_turn()
            candidates = []
            for _ in range(MAX_PLIES):
                if position.is_over():
                    break
                if in_race_zone(position):
                    candidates.append(position)
                plays = position.legal_plays(d1, d2)
                if plays:
                    position = search_plays(network, position, d1, d2,
                                            SearchConfig(ply=0))[0].play.result
                else:
                    position = position.swapped_turn()
                d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
            rng.shuffle(candidates)
            for position in candidates[:per_game]:
                identifier = codec.position_id(position)
                if identifier in seen or len(rows["ids"]) >= quota:
                    continue
                seen.add(identifier)
                result = rollout(network, position, RolloutConfig(
                    trials=trials, truncate=0, seed=rng.getrandbits(31),
                    policy=SearchConfig(ply=0)))
                if result.stalled:
                    continue
                rows["features"].append(codec.encode(position))
                rows["probs"].append(result.frequencies)
                rows["equity"].append(result.equity)
                rows["se"].append(result.standard_error)
                rows["ids"].append(f"{identifier}:{position.turn}")
                rows["klass"].append(classify(position))
                rows["pips"].append((position.pip_count(0), position.pip_count(1)))
    return rows


def build(model: Path, count: int, trials: int, workers: int, seed: int,
          per_game: int):
    quota = -(-count // workers)
    tasks = [(i, seed + i, quota, str(model), trials, per_game)
             for i in range(workers)]
    if workers == 1:
        shards = [_shard(tasks[0])]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            shards = list(pool.map(_shard, tasks))
    merged, seen = {}, set()
    keep = []
    offset = 0
    for shard in shards:
        for index, identifier in enumerate(shard["ids"]):
            if identifier not in seen:
                seen.add(identifier)
                keep.append(offset + index)
        offset += len(shard["ids"])
    for key in shards[0]:
        flat = [item for shard in shards for item in shard[key]]
        merged[key] = [flat[i] for i in keep][:count]
    return {
        "features": np.asarray(merged["features"], dtype=np.float32),
        "probs": np.asarray(merged["probs"], dtype=np.float32),
        "equity": np.asarray(merged["equity"], dtype=np.float32),
        "se": np.asarray(merged["se"], dtype=np.float32),
        "ids": np.asarray(merged["ids"]),
        "klass": np.asarray(merged["klass"]),
        "pips": np.asarray(merged["pips"], dtype=np.int32),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL,
                        help="incumbent network: plays the games and the rollouts")
    parser.add_argument("--count", type=int, default=50_000)
    parser.add_argument("--trials", type=int, default=1296)
    parser.add_argument("--per-game", type=int, default=3)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "race_train.npz")
    parser.add_argument("--smoke", action="store_true",
                        help="a few hundred rows, 36 trials, a random-init "
                             "incumbent: plumbing only")
    args = parser.parse_args(argv)

    if args.smoke:
        from smoke_support import write_random_network
        args.count, args.trials, args.workers = 120, 24, 1
        if args.out == ROOT / "build" / "race_train.npz":
            args.out = Path(tempfile.mkdtemp(prefix="race-smoke-")) / "race.npz"
        args.model = write_random_network(
            args.out.parent / "incumbent.bin", [32, 16], args.seed)
    if not args.model.exists():
        print(f"REFUS - réseau absent : {args.model}", file=sys.stderr)
        return 2

    started = time.perf_counter()
    arrays = build(args.model, args.count, args.trials, args.workers,
                   args.seed, args.per_game)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.out, **arrays)
    rows = arrays["ids"].shape[0]
    print(f"race corpus : {rows:,} rows, {args.trials} trials/row, "
          f"{(time.perf_counter() - started) / 60:.2f} min -> {args.out}")
    print(f"  mean rollout se {float(arrays['se'].mean()):.4f}  "
          f"classes {dict(zip(*np.unique(arrays['klass'], return_counts=True)))}")
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
