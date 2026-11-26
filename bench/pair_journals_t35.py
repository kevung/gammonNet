#!/usr/bin/env python3
"""#40 — deux journaux T35 de la même confrontation, rejoués aux mêmes dés, comparés paire par paire.

Une paire est une fonction pure de (graine, clé de dés, index) : rejouée dans un autre build, la
paire i reçoit les mêmes jets. Comparer deux journaux index par index mesure donc ce que le
changement de build déplace, avec la variance des dés en grande partie annulée — ici, ce que le
cache mêlé de #40 faisait aux tête-à-tête.

Imprime, sur les index communs : le nombre de paires dont l'issue diffère, la moyenne de chaque
journal, et l'écart apparié `avant − après` avec son IC 95 % (bootstrap sur les paires).

Usage : python bench/pair_journals_t35.py --before ancien.jsonl[.gz] --after nouveau.jsonl
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.arena import bootstrap_ci  # noqa: E402

#: Les champs qui décrivent la confrontation et ses dés : ils doivent coïncider.
SAME = ("task", "mode", "seed", "jacoby", "cube_cap", "match_length", "score_sampling",
        "dice_key")
OUTCOME = ("net", "turns", "doubles", "biggest_cube")


def read(path: Path) -> tuple[dict, dict[int, dict]]:
    opener = gzip.open if path.suffix == ".gz" else open
    header, rows = None, {}
    with opener(path, "rt") as lines:
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue          # a last line cut by a power loss
            if row.get("header"):
                header = row
            else:
                rows[row["i"]] = row
    if header is None:
        raise SystemExit(f"{path} : pas d'en-tête")
    return header, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    args = parser.parse_args()

    hb, rb = read(args.before)
    ha, ra = read(args.after)
    for key in SAME:
        if hb.get(key) != ha.get(key):
            raise SystemExit(f"{key} diffère ({hb.get(key)!r} / {ha.get(key)!r}) : "
                             f"pas les mêmes dés — refus")
    for side in ("ours", "theirs"):
        if hb[side]["name"] != ha[side]["name"]:
            raise SystemExit(f"{side} : {hb[side]['name']} / {ha[side]['name']} — refus")
    if hb["mode"] == "match":
        for i in set(rb) & set(ra):
            if (rb[i]["away_a"], rb[i]["away_b"]) != (ra[i]["away_a"], ra[i]["away_b"]):
                raise SystemExit(f"paire {i} : scores de départ différents — refus")

    common = sorted(set(rb) & set(ra))
    if not common:
        raise SystemExit("aucun index commun")
    differ = sum(1 for i in common
                 if any(rb[i].get(k) != ra[i].get(k) for k in OUTCOME))
    unit = "ppg" if hb["mode"] == "money" else "victoires nettes / match"
    before = [rb[i]["net"] / 2.0 for i in common]
    after = [ra[i]["net"] / 2.0 for i in common]
    diff = [b - a for b, a in zip(before, after)]
    n = len(common)
    lo, hi = bootstrap_ci(diff, args.bootstrap, seed=hb["seed"])
    print(f"avant : {args.before}  (empreinte {hb.get('eval_fingerprint')})")
    print(f"après : {args.after}  (empreinte {ha.get('eval_fingerprint')}, "
          f"cache {ha.get('evalcache_key', 'position seule')})")
    print(f"index communs : {n}, issue différente sur {differ} "
          f"({differ / n * 100:.1f} %)")
    print(f"moyenne avant : {sum(before) / n:+.4f} {unit}")
    print(f"moyenne après : {sum(after) / n:+.4f} {unit}")
    print(f"écart apparié avant − après : {sum(diff) / n:+.4f} [{lo:+.4f} ; {hi:+.4f}] "
          f"(IC 95 %, bootstrap sur les paires)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
