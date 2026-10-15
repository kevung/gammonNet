#!/usr/bin/env python3
"""T72 — the large 0-ply distillation corpus, written in resumable parts.

## Why another corpus tool

`tools/build_prune_corpus.py` (T3A) already walks the right distribution:
self-play at 0-ply, and EVERY candidate child of every decision recorded with
the teacher's five probabilities -- the positions a search actually asks the
network about, good plays and bad ones alike. T72prep measured that a student
distilled from 800 000 such rows loses 3.2x the teacher's decision quality at
the teacher's own size; the question this corpus answers is whether volume
closes that gap. A 0-ply label costs one forward pass, so tens of millions of
rows are hours, not weeks. Three things the T3A tool cannot do at that volume:

* **Parts, resumable, named by host.** Each worker writes
  `part-<host>-<NNN>-<chunk>.npz` every `--chunk` rows; a restart skips the
  chunks already on disk. The host is IN the name because two machines number
  their workers alike, and an `scp` of same-named parts once silently
  overwrote 224 000 labels (2026-09-02).
* **Exact, compact features.** The encoder emits 26 distinct values; each row
  is stored as 196 `uint8` codes into a per-part `values` table (float32,
  exactly what the C encoder produced). 196 bytes instead of 784, losslessly
  -- `decode_part` below rebuilds the float32 matrix bit for bit, and refuses
  a value outside the table rather than rounding it.
* **Decisions.** Every row carries `decisions`, the index of the decision
  it belongs to in its worker's walk: the rows of one decision are the
  teacher-labelled children of ONE position and roll -- siblings -- and they
  are written contiguously. A ranking objective needs that grouping; a
  decision cut by a chunk boundary simply continues in the next part, under
  the same index. Parts written before this field existed have none.
* **Exploration.** With probability `--explore`, the walk follows a uniformly
  drawn candidate instead of the best one, so the corpus does not stay on the
  teacher's own line of play. Every candidate is still labelled by the
  teacher; exploration only changes which game continues.

Labels are the teacher network's own output -- our network, never gnubg's or
any other engine's (CLAUDE.md, rule 1).

## Determinism

Worker `i` of a run seeds `random.Random(seed + i)` and plays its chunks in
order; chunk `c` is the `c`-th block of `--chunk` rows of that worker's walk.
A resumed worker replays its walk from the start and skips the chunks already
written, so a resumed corpus is identical to an uninterrupted one -- the walk
is cheap next to the labelling. Same (seed, workers, chunk, explore, model)
=> same corpus.

Usage:
    python tools/build_distill_corpus.py --rows 8000000 --workers 28 \\
        --seed 20261013 --out build/t72-distill
    python tools/build_distill_corpus.py --rows 4000 --workers 2 --chunk 1000 \\
        --out /tmp/t72-smoke   # fumée
"""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
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

DEFAULT_MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_256.bin"
MAX_PLIES_PER_GAME = 300


def part_name(host: str, worker: int, chunk: int) -> str:
    return f"part-{host}-{worker:03d}-{chunk:05d}.npz"


def encode_codes(rows: list[list[float]]) -> tuple[np.ndarray, np.ndarray]:
    """Rows of float features -> (uint8 codes, float32 value table), exact."""
    features = np.asarray(rows, dtype=np.float32)
    values, codes = np.unique(features, return_inverse=True)
    if len(values) > 255:
        raise ValueError(f"{len(values)} valeurs distinctes : uint8 ne suffit pas")
    return codes.reshape(features.shape).astype(np.uint8), values.astype(np.float32)


def decode_part(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """One part -> (float32 features, float32 labels)."""
    with np.load(path) as z:
        codes, values, labels = z["codes"], z["values"], z["labels"]
    if codes.size and int(codes.max()) >= len(values):
        raise ValueError(f"{path}: code hors de la table des valeurs")
    return values[codes], labels


def _worker(args: tuple) -> int:
    worker, seed, quota, chunk, explore, model_path, out, host = args
    out = Path(out)
    chunks = (quota + chunk - 1) // chunk
    todo = [c for c in range(chunks) if not (out / part_name(host, worker, c)).exists()]
    if not todo:
        return 0
    last = max(todo)

    network = Network.load(model_path)
    rng = random.Random(seed)
    feats: list[list[float]] = []
    labels: list[tuple[float, ...]] = []
    ids: list[str] = []
    decisions: list[int] = []
    decision = 0   # index of the decision in this worker's walk
    c = 0          # index of the chunk being filled
    produced = 0   # rows of this worker's walk so far

    def flush() -> None:
        nonlocal feats, labels, ids, decisions
        name = out / part_name(host, worker, c)
        if c in todo:
            codes, values = encode_codes(feats)
            tmp = name.with_suffix(".tmp.npz")
            np.savez(tmp, codes=codes, values=values,
                     labels=np.asarray(labels, dtype=np.float32),
                     ids=np.asarray(ids, dtype="<U15"),
                     decisions=np.asarray(decisions, dtype=np.int64))
            os.replace(tmp, name)
        feats, labels, ids, decisions = [], [], [], []

    # The walk is replayed even through chunks already on disk (determinism),
    # but those chunks are neither encoded nor labelled-and-kept.
    while c <= last:
        position = Position.initial()
        first, d1, d2 = opening_roll(rng)
        if first == BLACK:
            position = position.swapped_turn()
        for _ in range(MAX_PLIES_PER_GAME):
            if position.is_over() or c > last:
                break
            plays = position.legal_plays(d1, d2)
            if not plays:
                position = position.swapped_turn()
                d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
                continue
            if len(plays) >= 2:
                ranked = search_plays(network, position, d1, d2, SearchConfig(ply=0))
                for cand in ranked:
                    if cand.evaluation is None:
                        continue
                    if c in todo:
                        result = cand.play.result
                        feats.append(codec.encode(result))
                        labels.append(cand.evaluation.as_tuple())
                        ids.append(codec.position_id(result))
                        decisions.append(decision)
                    else:
                        feats.append(None)  # placeholder: keeps the count
                    produced += 1
                    if produced % chunk == 0 or produced == quota:
                        flush()
                        c += 1
                        if produced == quota or c > last:
                            break
                decision += 1
                if not ranked:
                    position = position.swapped_turn()
                elif rng.random() < explore:
                    position = ranked[rng.randrange(len(ranked))].play.result
                else:
                    position = ranked[0].play.result
            else:
                position = plays[0].result
            d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
    return len(todo)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--workers", type=int, default=28)
    parser.add_argument("--chunk", type=int, default=50_000)
    parser.add_argument("--explore", type=float, default=0.1)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--host", default=socket.gethostname().split(".")[0])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if not args.model.is_file():
        print(f"{args.model} absent", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "rows": args.rows, "workers": args.workers, "chunk": args.chunk,
        "explore": args.explore, "seed": args.seed, "host": args.host,
        "model": args.model.name,
    }
    mpath = args.out / f"manifest-{args.host}.json"
    if mpath.exists() and json.loads(mpath.read_text()) != manifest:
        print(f"{mpath} existe avec d'autres réglages : refus de mélanger", file=sys.stderr)
        return 1
    mpath.write_text(json.dumps(manifest, indent=1) + "\n")

    base, rem = divmod(args.rows, args.workers)
    payloads = [(i, args.seed + i, base + (1 if i < rem else 0), args.chunk,
                 args.explore, str(args.model), str(args.out), args.host)
                for i in range(args.workers)]
    print(f"T72 — corpus de distillation : {args.rows:,} lignes, {args.workers} processus, "
          f"graine {args.seed}, hôte {args.host}, ε={args.explore}, enseignant {args.model.name}",
          flush=True)
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        written = sum(pool.map(_worker, payloads))
    print(f"  {written} parts écrites en {time.perf_counter() - start:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
