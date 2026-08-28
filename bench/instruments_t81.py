#!/usr/bin/env python3
"""T81/T82 — les instruments de falsification, passés sur la pile classique.

**Aucun poids n'est entraîné ici.** Ce banc fait la seule chose qui doive être
faite avant d'entraîner quoi que ce soit : vérifier que les instruments
retrouvent ce qu'on sait déjà. La fiche T82 est explicite — « un extracteur qui
ne rend pas la réponse connue n'instrumente rien ».

Il produit deux sortes de lignes, et les confondre serait une faute :

- **Des contrôles**, dont la réponse est connue d'avance : le balayage des
  points de prise doit retrouver la forme fermée de Janowski, et les valeurs de
  manuel (0,25 à videau mort, 0,20 à videau vivant) ; la table lue doit porter
  le pivot -2/-1 Crawford, l'antisymétrie, les monotonies, l'identité DMP et la
  signature de parité du free drop. Un échec ici est un défaut d'instrument.

- **Une mesure neuve** : le **résidu de point fixe** de la pile classique —
  l'écart entre la MWC que le moteur assigne au début d'une partie et la
  cellule de table sur laquelle il est bâti. Ce chiffre n'existait pas dans ce
  dépôt. C'est le repère que le modèle appris de T82 devra battre, et sans lui
  son propre écart à la table ne voudrait rien dire.

Kazaross-XG2 est employée en **instrument**, jamais en entrée.

Usage :
    python bench/instruments_t81.py --max-away 25 --threshold 0.005
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "python"))

from gammonnet import instruments as I  # noqa: E402
from gammonnet.cube import CubeOwner  # noqa: E402
from gammonnet.cubeful import MODEL, measured_efficiency  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from gammonnet.rules import Position  # noqa: E402

#: Les deux valeurs de manuel de Janowski (1993), sans gammon : le point de
#: prise vaut 0,25 à videau mort et 0,20 à videau parfaitement vivant.
JANOWSKI_TEXTBOOK = {0.0: 0.25, 1.0: 0.20}


def sweep_controls(efficiency: tuple[float, float, float]) -> list[dict]:
    """Le balayage retrouve-t-il la forme fermée, et les valeurs de manuel ?"""
    rows = []
    for x in (0.0, efficiency[0], efficiency[1], efficiency[2], 1.0):
        swept_cash = I.swept_cash_point(x)
        swept_take = I.swept_take_point(x)
        rows.append(
            {
                "x": x,
                "cash_point_swept": swept_cash,
                "cash_point_closed_form": I.analytic_cash_point(x),
                "take_point_swept": swept_take,
                "take_point_closed_form": I.analytic_take_point(x),
                "double_point_swept": I.swept_double_point(x),
                "textbook_take_point": JANOWSKI_TEXTBOOK.get(x),
            }
        )
    for row in rows:
        row["gap_closed_form"] = abs(
            row["cash_point_swept"] - row["cash_point_closed_form"]
        )
        textbook = row["textbook_take_point"]
        row["gap_textbook"] = (
            None if textbook is None else abs(row["take_point_swept"] - textbook)
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-away", type=int, default=25)
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.005,
        help="le seuil ANNONCÉ D'AVANCE au-delà duquel une cellule est à arbitrer",
    )
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--out", default="docs/mesures/t81-instruments.json")
    args = parser.parse_args()

    efficiency = measured_efficiency()

    # ── 1. Les contrôles de balayage ──────────────────────────────────
    sweeps = sweep_controls(efficiency)
    worst_form = max(r["gap_closed_form"] for r in sweeps)
    worst_book = max(r["gap_textbook"] for r in sweeps if r["gap_textbook"] is not None)

    print("── Contrôle 1 : le balayage retrouve-t-il la formule ? ──")
    print(f"  efficacités mesurées (T34) : {tuple(round(v, 3) for v in efficiency)}")
    for row in sweeps:
        book = "" if row["gap_textbook"] is None else f"  manuel {row['gap_textbook']:.1e}"
        print(
            f"  x={row['x']:.3f}  CP balayé {row['cash_point_swept']:.6f}"
            f"  formule {row['cash_point_closed_form']:.6f}"
            f"  écart {row['gap_closed_form']:.1e}{book}"
        )
    print(f"  → pire écart à la forme fermée : {worst_form:.2e}")
    print(f"  → pire écart aux valeurs de manuel (0,25 / 0,20) : {worst_book:.2e}")

    # ── 2. Les propriétés de la table lue ─────────────────────────────
    read = I.read_met(args.max_away)
    post_row = I.post_crawford_row(args.max_away)
    properties = I.all_properties(read, lambda s, e: s.winning_chance(e), post_row)

    print("\n── Contrôle 2 : les propriétés de la table lue ──")
    for check in properties:
        mark = "OK   " if check.passed else "ÉCHEC"
        print(
            f"  {mark} {check.name:34s} pire : {check.worst_case or '—':38s}"
            f" écart {check.worst_error:.2e}"
        )

    # ── 3. La mesure neuve : le résidu de point fixe ───────────────────
    with Network.load(_ROOT / args.model) as network:
        opening = network.evaluate(Position.initial())
    implicit = I.implicit_met(I.classic_mwc_at_start(opening), args.max_away)
    residual = I.met_residual(implicit, read)
    worst_cell, worst_value = residual.worst
    above = residual.above(args.threshold)

    cubeful = I.implicit_met(
        I.classic_cubeful_mwc_at_start(opening, efficiency), args.max_away
    )
    cubeful_residual = I.met_residual(cubeful, read)
    cubeful_worst_cell, cubeful_worst_value = cubeful_residual.worst
    cubeful_above = cubeful_residual.above(args.threshold)

    print("\n── Mesure : le résidu de point fixe de la pile classique ──")
    print(
        "  évaluation de la position initiale : "
        f"P(gain) {opening.win:.4f}, P(gammon) {opening.win_gammon:.4f}, "
        f"P(gammon subi) {opening.lose_gammon:.4f}"
    )
    print(f"  écart absolu moyen à la table : {residual.mean_abs:.5f}")
    print(
        f"  pire cellule : {worst_cell[0]}-away/{worst_cell[1]}-away, "
        f"écart {worst_value:+.5f}"
    )
    print(
        f"  cellules au-delà du seuil annoncé ({args.threshold}) : "
        f"{len(above)} sur {len(residual.cells)}"
    )
    for cell, value in above[:5]:
        print(f"    {cell[0]}-away/{cell[1]}-away  {value:+.5f}")

    print("\n  la même extraction, mais cubeful (videau centré, Janowski aux x mesurés) :")
    print(f"  écart absolu moyen à la table : {cubeful_residual.mean_abs:.5f}")
    print(
        f"  pire cellule : {cubeful_worst_cell[0]}-away/{cubeful_worst_cell[1]}-away, "
        f"écart {cubeful_worst_value:+.5f}"
    )
    print(
        f"  cellules au-delà du seuil : {len(cubeful_above)} sur "
        f"{len(cubeful_residual.cells)}"
    )
    shrink = (
        residual.mean_abs / cubeful_residual.mean_abs
        if cubeful_residual.mean_abs > 0
        else float("inf")
    )
    print(
        f"  → le résidu moyen ne bouge presque pas ({shrink:.2f}×), mais les "
        f"cellules au-delà du seuil tombent de {len(above)} à {len(cubeful_above)} : "
        "le videau explique le désaccord LARGE, pas le désaccord MOYEN."
    )
    if abs(cubeful_worst_value) > abs(worst_value):
        print(
            "  → ATTENTION, la queue empire : "
            f"{cubeful_worst_cell[0]}-away/{cubeful_worst_cell[1]}-away passe à "
            f"{cubeful_worst_value:+.5f}. C'est un désaccord à ARBITRER par "
            "rollout de match, pas à expliquer (règle T82)."
        )

    payload = {
        "task": "T81/T82 — instruments de falsification",
        "generated": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "max_away": args.max_away,
        "threshold": args.threshold,
        "efficiency_t34": list(efficiency),
        "sweep_controls": sweeps,
        "sweep_worst_gap_closed_form": worst_form,
        "sweep_worst_gap_textbook": worst_book,
        "properties": [c.as_dict() for c in properties],
        "opening_evaluation": list(opening.as_tuple()),
        "fixed_point_residual": {
            "mean_abs": residual.mean_abs,
            "worst_cell": list(worst_cell),
            "worst_value": worst_value,
            "cells_above_threshold": len(above),
            "cells_total": len(residual.cells),
            "above": [
                {"away_on_roll": c[0], "away_opponent": c[1], "residual": v}
                for c, v in above
            ],
        },
        "fixed_point_residual_cubeful": {
            "mean_abs": cubeful_residual.mean_abs,
            "worst_cell": list(cubeful_worst_cell),
            "worst_value": cubeful_worst_value,
            "cells_above_threshold": len(cubeful_above),
            "cells_total": len(cubeful_residual.cells),
            "shrink_factor": shrink,
            "above": [
                {"away_on_roll": c[0], "away_opponent": c[1], "residual": v}
                for c, v in cubeful_above
            ],
        },
    }
    out = Path(args.out)
    if not out.is_absolute():
        out = _ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\n→ {out.relative_to(_ROOT)}")

    ok = all(c.passed for c in properties) and worst_form < 1e-6 and worst_book < 1e-6
    print("\nInstruments : " + ("verts." if ok else "UN CONTRÔLE A ÉCHOUÉ."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
