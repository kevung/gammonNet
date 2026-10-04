#!/usr/bin/env python3
"""Chronométrer deux filtres de coups sur les mêmes décisions, entrelacés.

Deux passes de `measure_t70.py` lancées l'une après l'autre ne se partagent
pas la machine : une charge voisine qui change entre elles devient un « gain ».
Ici chaque processus joue chaque décision avec les DEUX réglages, l'ordre
alterné d'une décision à l'autre, si bien qu'une charge extérieure frappe les
deux côtés à parts égales. Pas de cache d'évaluation (désactivé par défaut) :
le second passage ne profite pas du premier.

Rend le temps total de chaque côté, le rapport, et son IC 95 % bootstrap sur
les décisions — une mesure, au sens de `CLAUDE.md` règle 3.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
PRUNE = ROOT / "models" / "prune_32.bin"


def parse(text: str, kind):
    return tuple(kind(x) for x in text.split(",")) if text else ()


def config_of(spec: dict, prune_net):
    from gammonnet.search import SearchConfig  # noqa: PLC0415
    return SearchConfig(ply=spec["ply"], filter=spec["filter"],
                        filter_extra=spec["extra"],
                        filter_threshold=spec["threshold"],
                        prune_net=prune_net, prune_k=spec["prune_k"])


def batch(payload):
    rows, spec_a, spec_b, offset = payload
    from gammonnet import codec  # noqa: PLC0415
    from gammonnet.infer import Network  # noqa: PLC0415
    from gammonnet.search import search_plays  # noqa: PLC0415

    net = Network.load(str(MODEL))
    prune = Network.load(str(PRUNE))
    configs = {"a": config_of(spec_a, prune), "b": config_of(spec_b, prune)}
    out = []
    for k, row in enumerate(rows):
        position = codec.position_from_id(row["position_id"], row["turn"])
        d1, d2 = row["dice"]
        order = ("a", "b") if (k + offset) % 2 == 0 else ("b", "a")
        seconds = {}
        for side in order:
            began = time.perf_counter()
            search_plays(net, position, d1, d2, configs[side])
            seconds[side] = time.perf_counter() - began
        out.append((seconds["a"], seconds["b"]))
    return out


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    import numpy as np

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--decisions", type=int, default=600)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--ply", type=int, default=2)
    parser.add_argument("--prune-k", type=int, default=12)
    for side in ("a", "b"):
        parser.add_argument(f"--{side}-filter", required=True)
        parser.add_argument(f"--{side}-extra", default="")
        parser.add_argument(f"--{side}-threshold", default="")
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20261004)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    rows = [json.loads(line) for line in Path(args.registry).read_text().splitlines()
            if line.strip()]
    step = max(1, len(rows) // args.decisions)
    rows = rows[::step][: args.decisions]
    specs = {side: {"ply": args.ply, "prune_k": args.prune_k,
                    "filter": parse(getattr(args, f"{side}_filter"), int),
                    "extra": parse(getattr(args, f"{side}_extra"), int),
                    "threshold": parse(getattr(args, f"{side}_threshold"), float)}
             for side in ("a", "b")}

    chunks = [rows[i::args.workers] for i in range(args.workers)]
    with ProcessPoolExecutor(args.workers) as pool:
        parts = list(pool.map(batch, [(c, specs["a"], specs["b"], i)
                                      for i, c in enumerate(chunks) if c]))
    pairs = np.asarray([p for part in parts for p in part])
    a, b = pairs[:, 0], pairs[:, 1]
    ratio = a.sum() / b.sum()
    rng = np.random.default_rng(args.seed)
    picks = rng.integers(0, len(a), size=(args.bootstrap, len(a)))
    ratios = np.sort(a[picks].sum(axis=1) / b[picks].sum(axis=1))
    low = float(ratios[int(0.025 * args.bootstrap)])
    high = float(ratios[int(0.975 * args.bootstrap) - 1])
    print(f"{len(a)} décisions, {args.workers} processus, ordre alterné")
    print(f"  A {a.sum():9.1f} s   ({1000 * a.mean():.1f} ms par décision)")
    print(f"  B {b.sum():9.1f} s   ({1000 * b.mean():.1f} ms par décision)")
    print(f"  A / B = ×{ratio:.3f}  [×{low:.3f} ; ×{high:.3f}]  (IC 95 %, bootstrap)")
    if args.out:
        Path(args.out).write_text(json.dumps({
            "decisions": len(a), "workers": args.workers, "specs": specs,
            "seconds_a": float(a.sum()), "seconds_b": float(b.sum()),
            "ratio": float(ratio), "ci95": [low, high]}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
