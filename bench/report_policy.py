"""Dépouiller la mesure de la politique sans état contre T35 — spec §9.2.

Le journal de la politique est joué avec la clé de dés du journal de T35
(`run_t35.py --dice-key-from`) : sa paire i rejoue la situation de la paire i de
T35 — même score échantillonné, mêmes jets. D'où trois chiffres :

* la MWC de la politique, IC 95 % bootstrap sur les paires (comme `report_t35`) ;
* la MWC de T35 **sur les mêmes indices** — le même tirage de scores ;
* l'écart apparié (politique − T35) par paire, IC 95 % bootstrap : c'est lui
  qui dit si la politique « retrouve T35 dans son intervalle ».

    python bench/report_policy.py --journal docs/mesures/politique-t35-match.jsonl \\
        --reference docs/mesures/t35-match-v2.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

from run_t35 import read_journal  # noqa: E402

from gammonnet.arena import bootstrap_ci  # noqa: E402


def mwc(samples: list[float]) -> float:
    return (sum(samples) / len(samples) + 1.0) / 2.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    args = parser.parse_args()

    header, rows = read_journal(args.journal)
    ref_header, ref_rows = read_journal(args.reference)
    if header is None or ref_header is None:
        raise SystemExit("journal sans en-tête")
    common = sorted(i for i in rows if i in ref_rows and not rows[i].get("stalled"))
    if not common:
        raise SystemExit("aucune paire commune")
    for i in common:
        a, b = rows[i], ref_rows[i]
        if (a["away_a"], a["away_b"], a["post_crawford"]) != (
                b["away_a"], b["away_b"], b["post_crawford"]):
            raise SystemExit(f"paire {i} : pas la même situation de départ")

    ours = [rows[i]["net"] / 2.0 for i in common]
    ref = [ref_rows[i]["net"] / 2.0 for i in common]
    diff = [a - b for a, b in zip(ours, ref)]
    seed = header["seed"]
    lo, hi = bootstrap_ci(ours, args.bootstrap, seed=seed)
    rlo, rhi = bootstrap_ci(ref, args.bootstrap, seed=seed)
    dlo, dhi = bootstrap_ci(diff, args.bootstrap, seed=seed)
    all_ref = [r["net"] / 2.0 for r in ref_rows.values()]
    flo, fhi = bootstrap_ci(all_ref, min(args.bootstrap, 2000), seed=seed)

    same = sum(1 for a, b in zip(ours, ref) if a == b)
    print(f"paires communes : {len(common)} (indices {common[0]}..{common[-1]})")
    print(f"politique ({header['ours'].get('policy_level', '?')}) : MWC {mwc(ours) * 100:.2f} % "
          f"[{(lo + 1) / 2 * 100:.2f} ; {(hi + 1) / 2 * 100:.2f}]")
    print(f"T35, mêmes indices : MWC {mwc(ref) * 100:.2f} % "
          f"[{(rlo + 1) / 2 * 100:.2f} ; {(rhi + 1) / 2 * 100:.2f}]")
    print(f"T35, journal entier ({len(all_ref)} paires) : MWC {mwc(all_ref) * 100:.2f} % "
          f"[{(flo + 1) / 2 * 100:.2f} ; {(fhi + 1) / 2 * 100:.2f}]")
    mean = sum(diff) / len(diff)
    print(f"écart apparié politique − T35 : {mean / 2 * 100:+.2f} points de MWC "
          f"[{dlo / 2 * 100:+.2f} ; {dhi / 2 * 100:+.2f}]")
    print(f"paires au même résultat net : {same}/{len(common)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
