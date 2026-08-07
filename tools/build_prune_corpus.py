#!/usr/bin/env python3
"""T3A — build the distillation corpus for the pruning network.

## What this generates, and why this shape

A pruning network's real job, once wired into `gn_search`, is to score
**candidate children at a search node** well enough to rank them — the network
never has to be right in an absolute sense, only in relative order, because
only the top-k survivors go on to real evaluation. So the training
distribution this script builds is exactly that: candidate resulting
positions encountered while our own engine plays itself at 0-ply, each
labelled with the GRAND network's five raw probabilities on that position.

The self-play walk reuses the same idea as `bench/decision_loss.py`'s
`corpus()` — games advanced by the engine's own 0-ply choice — but records
more than the move actually taken. At every decision point (2+ legal plays),
`search_plays(..., ply=0)` already evaluates and ranks *every* legal child
with the grand network internally (one `gn_search_plays` call, one C-side
loop); every one of those children becomes a training row, at no extra
network-evaluation cost over just playing the game. Positions with a single
forced legal play are skipped: there is no ranking decision to learn there.

Labels are the grand network's own output, never gnubg's: distillation is
network-to-network. See `docs/etudes/README.md`, registry row 2026-08-03
("réseaux d'élagage... pas encore implémentée" — this script is that
implementation, and the note there already says the weights must be
distilled from *our* network, not gnubg's).

## Reproducibility

The corpus is deterministic in (seed, worker count): each worker `i` seeds
`random.Random(seed + i)` and stops once it has produced its share of the
target row count. Regenerating with the same `--seed` and `--workers`
reproduces it byte-for-byte modulo dict/set iteration order, which this
script does not rely on. Changing `--workers` changes how the target count is
split across seeds and therefore the exact rows collected — record the
worker count alongside the seed if the corpus must be reproduced exactly.

The output `.npz` is gitignored (`build/`); this docstring plus the seed
recorded in `models/prune_32.provenance.json` (by `train_prune.py`) are its
provenance.

Usage:
    python tools/build_prune_corpus.py --count 800000 --workers 26
    python tools/build_prune_corpus.py --count 2000 --workers 4   # dry run
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import codec  # noqa: E402
from gammonnet.arena import BLACK, opening_roll  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import Position  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

DEFAULT_MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
DEFAULT_OUT = ROOT / "build" / "prune_corpus.npz"
DEFAULT_COUNT = 800_000
DEFAULT_WORKERS = 26
#: T3A's base seed. Documented here, and echoed into the provenance of the
#: model this corpus trains — see `tools/train_prune.py`.
BASE_SEED = 20260807

#: A game abandoned past this many plies is restarted fresh rather than left
#: to wander — the same guard `bench/decision_loss.py.corpus()` uses.
MAX_PLIES_PER_GAME = 300

PROGRESS = Path(os.environ.get("T3A_CORPUS_PROGRESS", "/tmp/t3a-corpus-progress.log"))


def _generate_shard(args: tuple[int, int, int, str]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """One worker's share: self-play at 0-ply, recording every candidate child.

    Runs in a subprocess — loads its own `Network` handle (ctypes state is not
    fork-safe to share) and seeds its own RNG from `seed`.
    """
    worker_id, seed, quota, model_path = args
    network = Network.load(model_path)
    rng = random.Random(seed)

    features: list[list[float]] = []
    labels: list[tuple[float, ...]] = []
    ids: list[str] = []

    written = 0
    while len(features) < quota:
        position = Position.initial()
        first, d1, d2 = opening_roll(rng)
        if first == BLACK:
            position = position.swapped_turn()

        for _ in range(MAX_PLIES_PER_GAME):
            if position.is_over() or len(features) >= quota:
                break

            plays = position.legal_plays(d1, d2)
            if not plays:
                position = position.swapped_turn()
                d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
                continue

            if len(plays) >= 2:
                ranked = search_plays(network, position, d1, d2, SearchConfig(ply=0))
                for candidate in ranked:
                    if candidate.evaluation is None:
                        continue
                    result = candidate.play.result
                    features.append(codec.encode(result))
                    labels.append(candidate.evaluation.as_tuple())
                    ids.append(codec.position_id(result))
                    if len(features) >= quota:
                        break
                position = ranked[0].play.result if ranked else position.swapped_turn()
            else:
                position = plays[0].result

            d1, d2 = rng.randint(1, 6), rng.randint(1, 6)

            if len(features) - written >= 5000:
                written = len(features)
                with open(PROGRESS, "a") as fh:
                    fh.write(f"worker {worker_id}: {written}/{quota}\n")

    with open(PROGRESS, "a") as fh:
        fh.write(f"worker {worker_id}: done, {len(features)}/{quota}\n")

    return (
        np.asarray(features[:quota], dtype=np.float32),
        np.asarray(labels[:quota], dtype=np.float32),
        ids[:quota],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=BASE_SEED)
    args = parser.parse_args()

    if not args.model.is_file():
        print(f"{args.model} absent — lancer `make model`", file=sys.stderr)
        return 1

    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text("")

    workers = max(1, args.workers)
    base = args.count // workers
    remainder = args.count % workers
    quotas = [base + (1 if i < remainder else 0) for i in range(workers)]
    payloads = [
        (i, args.seed + i, quota, str(args.model))
        for i, quota in enumerate(quotas)
        if quota > 0
    ]

    print("T3A — corpus de distillation pour le réseau d'élagage")
    print(f"  cible : {args.count:,} positions, {len(payloads)} processus, graine de base {args.seed}")
    print(f"  modèle enseignant : {args.model.name}")
    print(f"  suivi : {PROGRESS}", flush=True)

    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
        shards = list(pool.map(_generate_shard, payloads))
    elapsed = time.perf_counter() - start

    features = np.concatenate([s[0] for s in shards], axis=0)
    labels = np.concatenate([s[1] for s in shards], axis=0)
    ids = np.array([i for s in shards for i in s[2]], dtype="<U15")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, features=features, labels=labels, ids=ids,
                        seed=args.seed, workers=len(payloads), model=str(args.model))

    rate = len(features) / elapsed if elapsed > 0 else float("inf")
    print(f"\n  {len(features):,} positions écrites dans {args.out}")
    print(f"  {elapsed:.1f} s, {rate:,.0f} positions/s")
    print(f"  taille : {args.out.stat().st_size / 1e6:.1f} Mo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
