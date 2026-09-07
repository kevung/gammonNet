#!/usr/bin/env python3
"""T93 — l'écart entre les deux moteurs, apparié position par position.

## Pourquoi ce banc ne fait tourner aucun moteur

Le corpus de T93 a acheté d'avance **les deux coups** : celui de chacun est un
candidat du registre, à un indice écrit dans la ligne. Une fois l'arbitrage
payé, l'écart se lit — il ne se recalcule pas. C'est aussi ce qui rend le taux
hors registre nul par construction, et ce banc le **vérifie** au lieu de le
supposer.

## Ce qui est publié, et dans quel ordre

1. La perte de chacun par décision disputée, avec son intervalle.
2. **L'écart apparié** — la différence des deux pertes sur la même décision,
   avec un intervalle bootstrap tiré sur les positions. C'est le chiffre de la
   fiche : l'appariement retire presque toute la variance avant de compter, et
   les deux pertes séparées ne suffiraient pas à conclure.
3. La décomposition : par classe de position (notre taxonomie), par plan de jeu
   (la leur), et selon **qui menait la partie** d'où vient la position — ce
   dernier découpage est le contrôle du générateur, et si l'écart y change de
   signe, le corpus parle plus fort que les moteurs.

## Ce que ce chiffre n'est pas

**Pas un PR.** Le dénominateur est la décision *disputée* : les décisions où les
deux jouent le même coup sont absentes, et elles ne portent pas une perte nulle
— seulement une perte commune, invisible ici par construction. Multiplier par
500 rendrait un nombre à l'échelle d'un PR, calculé sur un dixième des
décisions. C'est l'avertissement de `bench/measure_t70.py`, et il vaut ici mot
pour mot.

Usage :
    python bench/compare_t93.py --registry docs/corpus/t93/depth-0/registre-money.jsonl
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT))

from bench.measure_t70 import weighted_bootstrap  # noqa: E402


def losses(row: dict) -> tuple[float, float, str, str]:
    """La perte de chaque camp sur une décision, et l'état de son coup.

    La perte est l'écart au **meilleur candidat du registre**, jamais une valeur
    absolue : c'est ce qui la rend comparable d'une décision à l'autre.
    """
    equities = row["equities"]
    best = max(equities)
    states = row.get("resolution") or ["resolved"] * len(equities)
    ours, theirs = row["ours"], row["theirs"]
    return (best - equities[ours], best - equities[theirs],
            states[ours], states[theirs])


def paired_bootstrap(deltas, weights, draws: int, seed: int):
    """L'IC de l'écart, tiré sur les **positions**, pas sur les coups.

    Deux coups de la même décision ne sont pas indépendants : rééchantillonner
    les coups sous-estimerait l'intervalle.
    """
    return weighted_bootstrap(deltas, weights, draws, seed)


def summarise(rows, draws, seed) -> dict:
    ours, theirs, deltas, weights = [], [], [], []
    states = collections.Counter()
    for row in rows:
        lo, lt, so, st = losses(row)
        ours.append(lo)
        theirs.append(lt)
        deltas.append(lo - lt)
        weights.append(row["weight"])
        states[f"ours:{so}"] += 1
        states[f"theirs:{st}"] += 1

    mean_o, lo_o, hi_o = weighted_bootstrap(ours, weights, draws, seed)
    mean_t, lo_t, hi_t = weighted_bootstrap(theirs, weights, draws, seed + 1)
    mean_d, lo_d, hi_d = paired_bootstrap(deltas, weights, draws, seed + 2)
    return {
        "decisions": len(rows),
        "ours": {"mean": mean_o, "ci": [lo_o, hi_o]},
        "theirs": {"mean": mean_t, "ci": [lo_t, hi_t]},
        "delta": {"mean": mean_d, "ci": [lo_d, hi_d]},
        "resolution": dict(states),
    }


def verdict(delta: dict) -> str:
    low, high = delta["ci"]
    if low > 0:
        return "ILS SONT DEVANT — l'intervalle de l'écart est entièrement positif"
    if high < 0:
        return "NOUS SOMMES DEVANT — l'intervalle de l'écart est entièrement négatif"
    return "INDISCERNABLE — l'intervalle de l'écart contient zéro"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260907)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    registry = Path(args.registry)
    rows = [json.loads(line) for line in registry.read_text().splitlines() if line.strip()]
    if not rows:
        print("registre vide", file=sys.stderr)
        return 2

    # Le contrôle que la fiche exige : hors registre nul, **vérifié**.
    missing = [r for r in rows if "theirs" not in r or "ours" not in r]
    if missing:
        print(f"REFUS — {len(missing)} ligne(s) sans indice de coup joué. "
              "Ce registre n'a pas été produit par tools/build_corpus_t93.py.",
              file=sys.stderr)
        return 2

    depth = rows[0].get("depth")
    overall = summarise(rows, args.bootstrap, args.seed)

    print(f"T93 — écart apparié, profondeur réelle {depth}, {registry.name}")
    print(f"  {overall['decisions']} décisions disputées, hors registre : 0 (par construction, vérifié)")
    print()
    print(f"  perte par décision disputée")
    print(f"    nous  {overall['ours']['mean']:.5f}  "
          f"[{overall['ours']['ci'][0]:.5f} ; {overall['ours']['ci'][1]:.5f}]")
    print(f"    eux   {overall['theirs']['mean']:.5f}  "
          f"[{overall['theirs']['ci'][0]:.5f} ; {overall['theirs']['ci'][1]:.5f}]")
    print(f"    écart {overall['delta']['mean']:+.5f}  "
          f"[{overall['delta']['ci'][0]:+.5f} ; {overall['delta']['ci'][1]:+.5f}]   "
          "(positif = nous perdons plus)")
    print(f"  → {verdict(overall['delta'])}")

    report = {"registry": str(registry), "depth": depth, "overall": overall,
              "by_class": {}, "by_game_plan": {}, "by_driver": {}}

    for field, target in (("class", "by_class"), ("game_plan", "by_game_plan")):
        if field not in rows[0]:
            continue
        print(f"\n  par {field}")
        groups = collections.defaultdict(list)
        for row in rows:
            groups[row[field]].append(row)
        for name in sorted(groups, key=lambda k: -len(groups[k])):
            if len(groups[name]) < 30:
                continue
            part = summarise(groups[name], max(2000, args.bootstrap // 5), args.seed)
            report[target][name] = part
            print(f"    {name:16s} n={part['decisions']:5d}  "
                  f"écart {part['delta']['mean']:+.5f} "
                  f"[{part['delta']['ci'][0]:+.5f} ; {part['delta']['ci'][1]:+.5f}]")

    if "driven_by_us" in rows[0]:
        print("\n  contrôle du générateur — qui menait la partie d'où vient la position")
        for flag, name in ((True, "nous"), (False, "eux")):
            group = [r for r in rows if r["driven_by_us"] is flag]
            if len(group) < 30:
                continue
            part = summarise(group, max(2000, args.bootstrap // 5), args.seed)
            report["by_driver"][name] = part
            print(f"    menée par {name:5s} n={part['decisions']:5d}  "
                  f"écart {part['delta']['mean']:+.5f} "
                  f"[{part['delta']['ci'][0]:+.5f} ; {part['delta']['ci'][1]:+.5f}]")
        both = report["by_driver"]
        if len(both) == 2:
            a, b = both["nous"]["delta"], both["eux"]["delta"]
            if (a["ci"][1] < b["ci"][0]) or (b["ci"][1] < a["ci"][0]):
                print("    ⚠ les deux moitiés ne se recouvrent pas : le corpus parle "
                      "autant que les moteurs, et le verdict global est à lire avec cette réserve.")

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
