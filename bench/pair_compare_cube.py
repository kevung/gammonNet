#!/usr/bin/env python3
"""Deux dumps de `compare_cube.py --dump` sur le même corpus, appariés ligne à ligne.

Pour chaque tranche (tout, money, match, contact, bearoff) : l'accord avec gnubg
de chaque réseau, l'écart apparié et son IC 95 % (bootstrap sur les POSITIONS —
une position porte plusieurs décisions, contextes et possesseurs, qui ne sont
pas indépendantes), et l'équité abandonnée par notre verdict **valorisée par
gnubg** (`max(sans double, min(pris, passé))` moins la branche choisie). Cette
perte n'est pas arbitrée : gnubg est la règle, pas la vérité.

    python bench/pair_compare_cube.py A.jsonl B.jsonl      # Δ = B − A
"""
import json
import random
import sys
from collections import defaultdict


def load(path):
    rows = {}
    for line in open(path):
        r = json.loads(line)
        rows[(r["position_id"], r["turn"], r["context"], r["owner"])] = r
    return rows


def gnubg_loss(r):
    """Equity given up, valued by gnubg, by our verdict."""
    double = min(r["gnubg_take"], r["gnubg_drop"])
    best = max(r["gnubg_nodouble"], double)
    doubles = r["our_action"] in ("DOUBLE_TAKE", "DOUBLE_PASS")
    return best - (double if doubles else r["gnubg_nodouble"])


def boot(keys_by_pos, values, n=10000, seed=20260827):
    rng = random.Random(seed)
    pos = list(keys_by_pos)
    stats = []
    for _ in range(n):
        tot = cnt = 0.0
        for _ in pos:
            p = pos[rng.randrange(len(pos))]
            for k in keys_by_pos[p]:
                tot += values[k]
                cnt += 1
        stats.append(tot / cnt)
    stats.sort()
    return stats[int(0.025 * n)], stats[int(0.975 * n)]


a, b = load(sys.argv[1]), load(sys.argv[2])
assert a.keys() == b.keys(), "corpus différents"
for label, filt in [("tout", lambda k, r: True),
                    ("money", lambda k, r: k[2] == "money"),
                    ("match", lambda k, r: k[2] != "money"),
                    ("contact", lambda k, r: r["origin"] == "contact"),
                    ("bearoff", lambda k, r: r["origin"] == "bearoff")]:
    keys = [k for k in a if filt(k, a[k])]
    by_pos = defaultdict(list)
    for k in keys:
        by_pos[k[0]].append(k)
    agree_a = sum(a[k]["agree"] for k in keys) / len(keys)
    agree_b = sum(b[k]["agree"] for k in keys) / len(keys)
    d_agree = {k: b[k]["agree"] - a[k]["agree"] for k in keys}
    only_a = sum(1 for k in keys if a[k]["agree"] and not b[k]["agree"])
    only_b = sum(1 for k in keys if b[k]["agree"] and not a[k]["agree"])
    la = {k: gnubg_loss(a[k]) for k in keys}
    lb = {k: gnubg_loss(b[k]) for k in keys}
    d_loss = {k: lb[k] - la[k] for k in keys}
    same = sum(1 for k in keys if a[k]["our_action"] == b[k]["our_action"])
    lo, hi = boot(by_pos, d_agree, n=2000)
    llo, lhi = boot(by_pos, d_loss, n=2000)
    print(f"{label:8} n={len(keys):5}  accord A {agree_a*100:.2f} %  B {agree_b*100:.2f} %  "
          f"Δ {(agree_b-agree_a)*100:+.2f} pts [{lo*100:+.2f} ; {hi*100:+.2f}]  "
          f"(A seul {only_a}, B seul {only_b}, même verdict {same})  "
          f"perte-gnubg A {sum(la.values())/len(keys):.5f} B {sum(lb.values())/len(keys):.5f} "
          f"Δ {sum(d_loss.values())/len(keys):+.5f} [{llo:+.5f} ; {lhi:+.5f}]")
