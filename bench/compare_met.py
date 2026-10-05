#!/usr/bin/env python3
"""T97 — confronter la table calculée à Kazaross-XG2, et aux identités.

## Le seuil, annoncé avant les données

**Écrit et versionné pendant que la campagne tourne encore, précisément pour
qu'il ne puisse pas être choisi après coup.** Une cellule est *signalée* quand
les deux conditions tiennent ensemble :

  * l'écart dépasse **3 erreurs-types** de la cellule calculée — sans quoi c'est
    du bruit d'échantillonnage, et le signaler serait signaler notre volume ;
  * l'écart dépasse **0,005 en valeur absolue** — sans quoi c'est vrai mais sans
    conséquence : une demi-centième de MWC ne renverse aucune décision de
    videau, et une table de 350 cellules produirait de toute façon quelques
    écarts significatifs et minuscules.

Une cellule signalée **n'est pas une erreur** : la table de Kazaross est
elle-même une mesure, produite par d'autres moteurs. Ce que la fiche exige,
c'est qu'elle soit **arbitrée par un rollout plus long**, jamais expliquée.

## Les identités, vérifiées et non imposées

`compute_met.py` remplit la moitié basse par antisymétrie : la vérifier sur sa
sortie ne prouverait donc rien. Ce banc vérifie ce qui n'est pas imposé —
`MET(1,1) = 0,5`, les monotonies, et la cohérence entre la partie de Crawford
et l'après-Crawford. L'antisymétrie proprement dite se vérifie en recalculant
quelques cellules `(b, a)` avec une graine disjointe : c'est `--antisymmetry`,
qui demande une seconde campagne et non ce fichier.
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

#: Le seuil, en deux morceaux. Voir le docstring — il est versionné avec la
#: campagne en cours, pas après elle.
SIGMA_THRESHOLD = 3.0
ABSOLUTE_THRESHOLD = 0.005


def Table_key(away_a: int, away_b: int) -> str:
    """La clé d'erreur d'une cellule : les deux orientations la partagent."""
    low, high = min(away_a, away_b), max(away_a, away_b)
    return f"pre-{low}-{high}"


def load_computed(path: Path):
    report = json.loads(path.read_text())
    return report, report["pre"], report["post"], report.get("stderr", {})


def identities(pre, post, stderr, sigmas: float = 3.0) -> list[str]:
    """Ce qui doit tenir sur toute table d'équité de match digne du nom.

    **La tolérance est statistique, pas fixe.** Une table mesurée ne vérifie
    aucune identité exactement ; elle la vérifie à son erreur-type près. Une
    tolérance en dur signalerait les cellules les mieux mesurées — l'inverse de
    ce qu'on veut — et laisserait passer les autres.
    """
    problems = []

    def error(key: str) -> float:
        return stderr.get(key, 0.0)

    def combined(key_a: str, key_b: str) -> float:
        return math.sqrt(error(key_a) ** 2 + error(key_b) ** 2)

    e11 = error("pre-1-1")
    if abs(pre[0][0] - 0.5) > sigmas * e11:
        problems.append(f"MET(1,1) = {pre[0][0]:.5f} ± {e11:.5f}, 0,5 attendu "
                        f"({abs(pre[0][0] - 0.5) / e11:.1f} σ)")

    # Plus on est loin du but, moins on vaut — à adversaire fixé.
    for b in range(len(pre)):
        for a in range(len(pre) - 1):
            if pre[a][b] is None or pre[a + 1][b] is None:
                continue
            tolerance = sigmas * combined(Table_key(a + 1, b + 1),
                                          Table_key(a + 2, b + 1))
            if pre[a + 1][b] > pre[a][b] + tolerance:
                problems.append(
                    f"monotonie en a : MET({a + 2},{b + 1}) = {pre[a + 1][b]:.5f} "
                    f"> MET({a + 1},{b + 1}) = {pre[a][b]:.5f}")

    # Symétriquement : plus l'adversaire est loin, plus on vaut.
    for a in range(len(pre)):
        for b in range(len(pre) - 1):
            if pre[a][b] is None or pre[a][b + 1] is None:
                continue
            tolerance = sigmas * combined(Table_key(a + 1, b + 1),
                                          Table_key(a + 1, b + 2))
            if pre[a][b + 1] < pre[a][b] - tolerance:
                problems.append(
                    f"monotonie en b : MET({a + 1},{b + 2}) = {pre[a][b + 1]:.5f} "
                    f"< MET({a + 1},{b + 1}) = {pre[a][b]:.5f}")

    for n in range(len(post) - 1):
        if post[n] is None or post[n + 1] is None:
            continue
        tolerance = sigmas * combined(f"post-{n + 1}", f"post-{n + 2}")
        if post[n + 1] > post[n] + tolerance:
            problems.append(
                f"monotonie après-Crawford : POST({n + 2}) = {post[n + 1]:.5f} "
                f"> POST({n + 1}) = {post[n]:.5f}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--computed", type=Path, required=True,
                        help="le JSON rendu par tools/compute_met.py")
    parser.add_argument("--max-away", type=int, default=0,
                        help="ne comparer que jusqu'à ce away (0 = tout)")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    report, pre, post, stderr = load_computed(args.computed)
    limit = args.max_away or report["max_away"]

    print(f"T97 — « {report['name']} » contre Kazaross-XG2")
    print(f"  {report['games']} parties, profondeur {report['ply']} "
          f"(videau {report['cube_ply']})")
    if report.get("stderr_scale", 1.0) > 1.0:
        print(f"  erreurs-types portant le facteur d'échelle "
              f"×{report['stderr_scale']:.3f} de la réunion des campagnes")
    print(f"  seuil : écart > {SIGMA_THRESHOLD}σ ET > {ABSOLUTE_THRESHOLD} "
          f"en valeur absolue\n")

    flagged = []
    deltas = []

    for n in range(1, limit + 1):
        if post[n - 1] is None:
            continue
        delta = post[n - 1] - met.post_crawford(n)
        error = stderr.get(f"post-{n}", 0.0)
        deltas.append(abs(delta))
        if abs(delta) > SIGMA_THRESHOLD * error and abs(delta) > ABSOLUTE_THRESHOLD:
            flagged.append(("post", n, 1, post[n - 1], met.post_crawford(n),
                            delta, error))

    for a in range(1, limit + 1):
        for b in range(a, limit + 1):
            if pre[a - 1][b - 1] is None:
                continue
            delta = pre[a - 1][b - 1] - met.pre_crawford(a, b)
            error = stderr.get(f"pre-{a}-{b}", 0.0)
            deltas.append(abs(delta))
            if abs(delta) > SIGMA_THRESHOLD * error and \
                    abs(delta) > ABSOLUTE_THRESHOLD:
                flagged.append(("pre", a, b, pre[a - 1][b - 1],
                                met.pre_crawford(a, b), delta, error))

    deltas.sort()
    if deltas:
        median = deltas[len(deltas) // 2]
        print(f"  écart absolu : médiane {median:.5f}, "
              f"maximum {deltas[-1]:.5f}, sur {len(deltas)} cellules")

    print(f"\n  cellules signalées : {len(flagged)}")
    for kind, a, b, ours, theirs, delta, error in flagged[:40]:
        label = f"{kind}[{a}]" if kind == "post" else f"{kind}[{a}][{b}]"
        print(f"    {label:14s} nous {ours:.5f} ± {error:.5f}   "
              f"Kazaross {theirs:.5f}   écart {delta:+.5f} "
              f"({abs(delta) / error:.1f}σ)" if error else
              f"    {label:14s} nous {ours:.5f}   Kazaross {theirs:.5f}")

    problems = identities(pre, post, stderr)
    print(f"\n  identités violées : {len(problems)}")
    for problem in problems[:20]:
        print(f"    {problem}")

    if args.out:
        args.out.write_text(json.dumps({
            "computed": str(args.computed),
            "sigma_threshold": SIGMA_THRESHOLD,
            "absolute_threshold": ABSOLUTE_THRESHOLD,
            "cells": len(deltas),
            "median_abs_delta": deltas[len(deltas) // 2] if deltas else None,
            "max_abs_delta": deltas[-1] if deltas else None,
            "flagged": [{"kind": k, "a": a, "b": b, "ours": o, "kazaross": t,
                         "delta": d, "stderr": e}
                        for k, a, b, o, t, d, e in flagged],
            "identity_problems": problems,
        }, indent=1) + "\n")
        print(f"\n→ {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
