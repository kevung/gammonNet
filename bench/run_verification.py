#!/usr/bin/env python3
"""T11 — the verification round-robin: do we find the published strength ourselves?

The blocking task of phase 1. Its object is **certainty, not strength**: nothing
here wins a point of equity, it earns the right to believe the numbers read
afterwards.

The comparison points, both from `BRIEF.md`:

* **+57.8 mEq/game** — the model author's own figure at 0-ply, 10 M games. This is
  the only external reference this repository sets out to reproduce.

If the measured gap exceeds the confidence intervals it must be **explained
before phase 2 opens**. An unexplained gap invalidates everything after it.

Usage:
    python bench/run_verification.py --games 1000000 --workers 32
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.arena import NetworkEngine, OracleEngine, play_pair  # noqa: E402

PUBLISHED_AUTHOR_PPG = 0.0578       # the author's +57.8 mEq/game at 0-ply


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=1_000_000)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--seed", type=int, default=20260803)
    parser.add_argument("--ply", type=int, default=0)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    pairs = args.games // 2

    model = NetworkEngine()
    oracle = OracleEngine(ply=args.ply)

    print(f"T11 — round-robin de vérification")
    print(f"  {model.name} contre {oracle.name}, money sans videau")
    print(f"  {pairs} paires de dés dupliqués = {pairs * 2} parties")
    print(f"  graine {args.seed}, {args.workers} processus")
    print(f"  démarré à {time.strftime('%H:%M:%S')}\n", flush=True)

    start = time.perf_counter()
    result = play_pair(model, oracle, pairs=pairs, base_seed=args.seed,
                       workers=args.workers, bootstrap=args.bootstrap)
    elapsed = time.perf_counter() - start

    print(result)
    print(f"\n{result.games} parties en {elapsed / 60:.1f} min "
          f"({result.games / elapsed:.0f} parties/s)")
    if result.stalled:
        print(f"⚠ {result.stalled} paires abandonnées")

    low, high = result.ci
    print("\nComparaison aux chiffres publiés :")
    for label, published in (
        ("auteur du modèle, 0-ply", PUBLISHED_AUTHOR_PPG),
    ):
        inside = low <= published <= high
        verdict = "DANS l'intervalle" if inside else "HORS de l'intervalle"
        print(f"  {published:+.4f} ppg — {label}")
        print(f"      {verdict} [{low:+.4f} ; {high:+.4f}]")

    payload = {
        "measured_ppg": result.ppg,
        "ci95": [low, high],
        "win_rate": result.win_rate,
        "games": result.games,
        "pairs": result.pairs,
        "seed": args.seed,
        "ply": args.ply,
        "mode": "cubeless-money",
        "stalled_pairs": result.stalled,
        "elapsed_seconds": elapsed,
        "published_cubeful_ppg": PUBLISHED_CUBEFUL_PPG,
        "published_author_ppg": PUBLISHED_AUTHOR_PPG,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=2) + "\n")
        print(f"\nécrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
