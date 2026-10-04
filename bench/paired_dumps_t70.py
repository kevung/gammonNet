#!/usr/bin/env python3
"""T70 — deux dumps de `measure_t70.py --dump` sur le même registre, appariés.

`bench/compare_t70.py` fait jouer deux moteurs ; cet outil relit deux notations
déjà faites, décision par décision, ce qui suffit quand les deux moteurs ne
diffèrent que par un réglage de recherche (filtre de coups, élagage) : chaque
dump porte déjà la perte, et depuis le triplet de filtre, le coût de la
décision (évaluations du grand réseau, du réseau d'élagage, secondes de
recherche).

Ce qu'il rend : Δ = perte(candidat) − perte(référence), moyenne pondérée et IC
95 % bootstrap sur les positions (`compare_t70.paired_statistics`), le rapport
des coûts, et le verdict de non-infériorité : la borne HAUTE de l'IC doit être
≤ la marge (`--margin`). Une décision hors registre d'un côté ou de l'autre est
écartée de l'appariement et comptée à part, jamais comptée zéro.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

from compare_t70 import paired_statistics  # noqa: E402


def read(path: Path) -> tuple[dict, dict[int, dict]]:
    header, rows = {}, {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("header"):
            header = row
        else:
            rows[row["index"]] = row
    return header, rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("reference", help="dump de la référence")
    parser.add_argument("candidate", help="dump du candidat")
    parser.add_argument("--margin", type=float, default=0.001)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    ref_header, ref = read(Path(args.reference))
    cand_header, cand = read(Path(args.candidate))
    if ref_header.get("registry") != cand_header.get("registry"):
        print("registres différents : l'appariement n'a pas de sens", file=sys.stderr)
        return 2

    common = sorted(set(ref) & set(cand))
    paired = [i for i in common
              if ref[i]["loss"] is not None and cand[i]["loss"] is not None]
    outside = len(common) - len(paired)
    differences = [cand[i]["loss"] - ref[i]["loss"] for i in paired]
    weights = [ref[i]["weight"] for i in paired]
    mean, low, high, z = paired_statistics(differences, weights,
                                           args.bootstrap, args.seed)
    changed = sum(1 for d in differences if d != 0.0)

    def total(rows, key):
        return sum(rows[i].get(key, 0) for i in common)

    cost = {key: (total(ref, key), total(cand, key))
            for key in ("evals", "prune_evals", "seconds")}
    passed = high <= args.margin

    print(f"Δ perte par décision (candidat − référence) : {mean:+.5f}  "
          f"[{low:+.5f} ; {high:+.5f}]  (IC 95 %, bootstrap {args.bootstrap}), z = {z:+.2f}")
    print(f"  décisions appariées : {len(paired)}   dont coup différent : {changed}"
          f"   hors registre d'un côté : {outside}")
    for key, (a, b) in cost.items():
        ratio = a / b if b else float("inf")
        print(f"  {key:12s} référence {a:14.1f}   candidat {b:14.1f}   ×{ratio:.3f}")
    print(f"  non-infériorité (borne haute ≤ {args.margin}) : "
          f"{'TENUE' if passed else 'NON TENUE'}")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "reference": ref_header, "candidate": cand_header,
            "paired": len(paired), "changed": changed, "outside": outside,
            "delta": mean, "ci95": [low, high], "z": z, "margin": args.margin,
            "non_inferior": passed,
            "cost": {k: {"reference": a, "candidate": b} for k, (a, b) in cost.items()},
        }, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
