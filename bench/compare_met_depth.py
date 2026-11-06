#!/usr/bin/env python3
"""T97 §7.4 — the plateau cells at three depths, against Kazaross-XG2.

Reads the merged table (pawns 0-ply, cube 0-ply), the cube arbitration
(pawns 0, cube 1) and the pawn arbitration (pawns 1, cube 1), all computed
from the same dependency table. Single-campaign errors carry the ×1.145
scale of the merged table (§5); the merged table already carries it.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import met  # noqa: E402

M = ROOT / "docs" / "mesures"
PLATEAU = [(14, 21), (16, 23), (16, 25), (14, 25), (12, 22), (13, 21)]
WITNESSES = [(2, 3), (3, 5), (4, 7), (5, 5)]


def main() -> int:
    merged = json.loads((M / "t97-table-reunie.json").read_text())
    scale = merged["stderr_scale"]
    runs = {
        "pions 0, videau 0": (merged, 1.0),
        "pions 0, videau 1": (json.loads((M / "t97-arbitrage-videau-1ply.json").read_text()), scale),
        "pions 1, videau 1": (json.loads((M / "t97-arbitrage-pions-1ply.json").read_text()), scale),
    }

    def cell(run, a, b):
        report, s = run
        return report["pre"][a - 1][b - 1], report["stderr"][f"pre-{a}-{b}"] * s

    print(f"{'cellule':8s} {'Kazaross':>9s} " + " ".join(f"{k:>22s}" for k in runs))
    for a, b in PLATEAU + WITNESSES:
        k = met.pre_crawford(a, b)
        cols = []
        for run in runs.values():
            v, e = cell(run, a, b)
            cols.append(f"{v - k:+.5f} ± {e:.5f}".rjust(22))
        print(f"{a:>3d}-{b:<4d} {k:9.5f} " + " ".join(cols))

    for label, cells in (("plateau", PLATEAU), ("témoins", WITNESSES)):
        n = len(cells)
        for name, run in runs.items():
            mean = sum(cell(run, a, b)[0] - met.pre_crawford(a, b) for a, b in cells) / n
            err = math.sqrt(sum(cell(run, a, b)[1] ** 2 for a, b in cells)) / n
            print(f"{label} — {name} : écart moyen à Kazaross {mean:+.5f} ± {err:.5f}")
        lo, hi = runs["pions 0, videau 1"], runs["pions 1, videau 1"]
        d = sum(cell(hi, a, b)[0] - cell(lo, a, b)[0] for a, b in cells) / n
        e = math.sqrt(sum(cell(hi, a, b)[1] ** 2 + cell(lo, a, b)[1] ** 2 for a, b in cells)) / n
        print(f"{label} — effet des pions 1-ply (à videau 1) : {d:+.5f} ± {e:.5f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
