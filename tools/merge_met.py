#!/usr/bin/env python3
"""T97 — réunir des campagnes indépendantes en une table, et les confronter.

## Pourquoi trois campagnes courtes plutôt qu'une longue

Elles se **moyennent** — l'erreur-type tombe d'un facteur racine du nombre de
campagnes — et elles se **contredisent** si quelque chose ne va pas. Une
campagne unique, si longue soit-elle, ne peut pas se répliquer elle-même : un
biais systématique y passerait pour de la précision.

Le χ² réduit imprimé en fin de course est ce contrôle. Il vaut 1 quand les
campagnes ne diffèrent que par l'échantillonnage. Nettement plus, et les
erreurs-types sont sous-estimées ou les campagnes ne mesurent pas la même
chose ; nettement moins, et elles ne sont pas indépendantes.

## Le garde qui refuse, plutôt que le commentaire qui prévient

Deux campagnes à la **même graine** ne sont pas deux échantillons : ce sont
deux fois le même. Les moyenner diviserait l'erreur-type affichée par racine de
deux sans rien apporter — un chiffre faux qui a l'air meilleur. Ce dépôt a
déjà perdu 224 000 étiquettes à un écrasement silencieux ; ici le programme
refuse et s'arrête.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import met  # noqa: E402

MAX_AWAY = met.MAX_AWAY

#: Ce qui doit être identique d'une campagne à l'autre pour qu'elles mesurent
#: la même grandeur. La graine, elle, doit être DIFFÉRENTE.
SHARED = ("ply", "cube_ply", "prune_k", "model", "max_away",
          "games_per_cell", "games_per_cell_far", "near")


def combine(values, errors):
    """Moyenne pondérée par l'inverse de la variance, et son erreur-type."""
    weights = [1.0 / (error * error) if error > 0 else 0.0 for error in errors]
    total = sum(weights)
    if total == 0.0:
        return sum(values) / len(values), 0.0, 0.0
    mean = sum(w * v for w, v in zip(weights, values)) / total
    error = math.sqrt(1.0 / total)
    chi2 = sum(w * (v - mean) ** 2 for w, v in zip(weights, values))
    return mean, error, chi2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--name", default="gammonnet-t97")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--table-out", type=Path, default=None)
    args = parser.parse_args()

    reports = [json.loads(path.read_text()) for path in args.reports]

    seeds = [report["seed"] for report in reports]
    if len(set(seeds)) != len(seeds):
        print(f"REFUS : graines répétées {seeds} — deux campagnes à la même "
              f"graine sont deux fois la même campagne, pas deux échantillons",
              file=sys.stderr)
        return 2

    for key in SHARED:
        values = {report.get(key) for report in reports}
        if len(values) != 1:
            print(f"REFUS : les campagnes diffèrent sur « {key} » : {values}",
                  file=sys.stderr)
            return 2

    mirrored = {report.get("mirror", False) for report in reports}
    if len(mirrored) != 1:
        print("REFUS : une passe miroir ne se moyenne pas avec une passe "
              "directe — elles mesurent des orientations différentes, et "
              "c'est leur écart qui est le résultat", file=sys.stderr)
        return 2

    print(f"T97 — {len(reports)} campagnes, graines {sorted(seeds)}")
    for report, path in zip(reports, args.reports):
        print(f"  {report['name']:26s} {report['games']:>9} parties  "
              f"{report['seconds'] / 3600:.1f} h  ({path})")

    pre = [[None] * MAX_AWAY for _ in range(MAX_AWAY)]
    post = [None] * MAX_AWAY
    stderr = {}
    chi2_total = 0.0
    chi2_cells = 0
    missing = 0

    for n in range(1, MAX_AWAY + 1):
        values, errors = [], []
        for report in reports:
            value = report["post"][n - 1]
            if value is None:
                continue
            values.append(value)
            errors.append(report["stderr"].get(f"post-{n}", 0.0))
        if not values:
            missing += 1
            continue
        mean, error, chi2 = combine(values, errors)
        post[n - 1] = mean
        stderr[f"post-{n}"] = error
        if len(values) > 1:
            chi2_total += chi2
            chi2_cells += len(values) - 1

    for a in range(1, MAX_AWAY + 1):
        for b in range(a, MAX_AWAY + 1):
            values, errors = [], []
            for report in reports:
                value = report["pre"][a - 1][b - 1]
                if value is None:
                    continue
                values.append(value)
                errors.append(report["stderr"].get(f"pre-{a}-{b}", 0.0))
            if not values:
                missing += 1
                continue
            mean, error, chi2 = combine(values, errors)
            pre[a - 1][b - 1] = mean
            pre[b - 1][a - 1] = 1.0 - mean
            stderr[f"pre-{a}-{b}"] = error
            if len(values) > 1:
                chi2_total += chi2
                chi2_cells += len(values) - 1

    reduced = chi2_total / chi2_cells if chi2_cells else float("nan")
    spread = math.sqrt(2.0 / chi2_cells) if chi2_cells else float("nan")
    print(f"\n  χ² réduit entre campagnes : {reduced:.3f} ± {spread:.3f} "
          f"sur {chi2_cells} degrés de liberté")

    # Le facteur d'échelle. La propagation implémentée dans `compute_met.py`
    # somme les variances des cellules consultées comme si elles étaient
    # indépendantes ; elles ne le sont pas — deux dépendances partagent leurs
    # propres dépendances, et la covariance positive qu'on néglige manque au
    # total. Plutôt que de propager une matrice de covariance à travers
    # cinquante étages, on mesure ce qui manque : la dispersion entre campagnes
    # indépendantes EST l'incertitude, et le rapport à ce qu'on avait annoncé
    # est le facteur qui manque. C'est la pratique des facteurs d'échelle, et
    # elle est dite plutôt que cachée.
    scale = math.sqrt(reduced) if reduced > 1.0 else 1.0
    if scale > 1.0:
        print(f"  facteur d'échelle appliqué aux erreurs-types : "
              f"×{scale:.3f}")
        print("    la propagation néglige la covariance entre dépendances ; "
              "la dispersion entre campagnes la mesure")
        for key in stderr:
            stderr[key] *= scale
    if missing:
        print(f"  {missing} cellules manquent partout")

    errors_near = [e for key, e in stderr.items()
                   if not key.startswith("post")
                   and sum(int(part) for part in key.split("-")[1:]) <= 10]
    if errors_near:
        print(f"  erreur-type des cellules a+b ≤ 10 : "
              f"médiane {sorted(errors_near)[len(errors_near) // 2]:.5f}")

    report = {
        "name": args.name,
        "sources": [str(path) for path in args.reports],
        "seeds": seeds,
        "games": sum(r["games"] for r in reports),
        "reduced_chi2": reduced,
        "chi2_dof": chi2_cells,
        "stderr_scale": scale,
        "max_away": MAX_AWAY,
        **{key: reports[0].get(key) for key in SHARED},
        "mirror": reports[0].get("mirror", False),
        "pre": pre,
        "post": post,
        "stderr": stderr,
    }

    if args.out:
        args.out.write_text(json.dumps(report, indent=1) + "\n")
        print(f"\n→ {args.out}")
    if args.table_out and not missing:
        met.write_table(args.table_out, pre, post, args.name)
        print(f"→ {args.table_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
