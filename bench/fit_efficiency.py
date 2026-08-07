#!/usr/bin/env python3
"""T34 — l'efficacité du videau, ajustée contre la table bilatérale exacte.

`docs/specs/t34-videau-spec.md` §3 est explicite : `x` est **le seul paramètre
libre** du modèle, et il « est ajusté par moindres carrés contre les équités
cubeful exactes de la table bilatérale ... jamais repris d'un autre moteur ».
C'est ce que ce script fait, et rien de plus — un scan fin de `x`, pas un
optimiseur, comme le prescrit la fiche de tâche.

## Ce que le domaine permet, et ce qu'il ne permet pas

Le domaine de la table bilatérale est **sans gammon** (`W = L = 1`, démontré en
T38) : `P(gain) = (cubeless + 1) / 2` s'y lit directement dans la table, sans
réseau. L'ajustement ne contraint donc que le comportement gammonless du
modèle ; la composante gammon (`W`, `L` > 1) n'est validée nulle part par une
référence exacte — il n'en existe pas dans ce dépôt. `docs/specs/` le dit,
et le rapport le répète.

## Pourquoi ce script réimplémente le modèle en NumPy plutôt que d'appeler `libgammonnet.so`

`gn_cube_equity` reste **la** référence : `tests/test_cube.py` la vérifie
formule par formule contre les ancrages numériques de la spécification. Ce
script vise 5000+ positions × 1001 valeurs de `x` × 3 états — quinze millions
d'évaluations — et l'overhead ctypes par appel (mesuré en T05 : facteur dix
rien que pour construire les objets Python d'un coup) le rendrait
impraticable. La reformulation vectorisée ci-dessous n'est valide que dans le
domaine gammonless (`W = L = 1`), ce que ce script vérifie explicitement
plutôt que de le supposer, et se recale contre `gn_cube_equity` réel sur un
échantillon avant de faire tourner le scan complet — un désaccord y romprait
immédiatement, avant de produire 5000 chiffres qui se tromperaient tous de la
même façon.

Usage :
    python bench/fit_efficiency.py --samples 8000 --seed 20260807
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.bearoff import TwoSidedBearoff  # noqa: E402
from gammonnet.cube import CubeInputs, CubeOwner  # noqa: E402

from exact_gap import random_bearoff  # noqa: E402

DEFAULT_DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"

STATES = {
    "owned": CubeOwner.OWNED,
    "centered": CubeOwner.CENTRED,
    "opponent": CubeOwner.OPPONENT,
}


def collect(database: Path, samples: int, seed: int):
    """`samples` positions de bearoff, leur `p` déduit de la table, et les
    trois équités cubeful exactes qui servent de cible à l'ajustement."""
    import random

    rng = random.Random(seed)
    p = np.empty(samples)
    targets = {name: np.empty(samples) for name in STATES}

    with TwoSidedBearoff(database) as table:
        for i in range(samples):
            position = random_bearoff(rng, table)
            equity = table.equity(position)
            # P(gain) = (cubeless + 1) / 2 -- valable ici seulement : la table
            # ne distingue gains simples et gammons nulle part dans ce domaine
            # (T38), donc l'équité cubeless EST la moyenne pondérée par p, sans
            # terme de gammon à démêler.
            p[i] = (equity.cubeless + 1.0) / 2.0
            targets["owned"][i] = equity.owned
            targets["centered"][i] = equity.centered
            targets["opponent"][i] = equity.opponent_owns

    return p, targets


def live_curves(p: np.ndarray):
    """`E_live`, vectorisé, gammonless (`W = L = 1`) -- spec §2.

    Fixe pour de bon : ni `TP_live` (0,20) ni `CP_live` (0,80) ne dépendent de
    `x`, seul le mélange final (1-x)*mort + x*vivant en dépend. Ce sont les
    ancrages que `tests/test_cube.py::test_gammonless_take_and_cash_points`
    vérifie déjà contre `gn_cube_take_point`.
    """
    tp_live, cp_live = 0.2, 0.8
    e = 2.0 * p - 1.0  # e(p) = p*1 - (1-p)*1, gammonless

    owned = np.where(p <= cp_live, -1.0 + 2.5 * p, np.maximum(1.0, e))
    opponent = np.where(p <= tp_live, np.minimum(-1.0, e),
                        -1.0 + 2.5 * (p - tp_live))
    centered = np.where(
        p <= tp_live, np.minimum(-1.0, e),
        np.where(p <= cp_live, -1.0 + 2.0 * (p - tp_live) / 0.6, np.maximum(1.0, e)),
    )
    dead = e
    return dead, {"owned": owned, "centered": centered, "opponent": opponent}


def cross_check(p: np.ndarray, live: dict, dead: np.ndarray, checks: int = 25):
    """`gn_cube_equity` réel, sur un sous-échantillon, à `x = 0.5` -- le
    garde-fou qui empêche cette reformulation de diverger en silence."""
    rng = np.random.default_rng(0)
    idx = rng.choice(len(p), size=min(checks, len(p)), replace=False)
    worst = 0.0
    for i in idx:
        inputs = CubeInputs(win=float(p[i]), win_points=1.0, lose_points=1.0)
        for name, owner in STATES.items():
            reference = inputs.equity(owner, 1, 0.5)
            predicted = 0.5 * dead[i] + 0.5 * live[name][i]
            worst = max(worst, abs(reference - predicted))
    if worst > 1e-9:
        raise AssertionError(
            f"la reformulation NumPy diverge de gn_cube_equity de {worst:.3e} -- arrêt"
        )
    return worst


def fit(p: np.ndarray, targets: dict, step: float = 0.001):
    """Le scan fin de `x`, par état, minimisant l'erreur quadratique moyenne."""
    dead, live = live_curves(p)
    cross_check(p, live, dead)

    grid = np.arange(0.0, 1.0 + step / 2, step)
    results = {}
    for name in STATES:
        target = targets[name]
        best_x, best_rms = None, None
        for x in grid:
            predicted = (1.0 - x) * dead + x * live[name]
            residual = predicted - target
            rms = float(np.sqrt(np.mean(residual ** 2)))
            if best_rms is None or rms < best_rms:
                best_rms, best_x = rms, float(x)

        predicted = (1.0 - best_x) * dead + best_x * live[name]
        residual = predicted - target
        results[name] = {
            "x": best_x,
            "rms": best_rms,
            "max_abs_residual": float(np.max(np.abs(residual))),
            "mean_residual": float(np.mean(residual)),
        }
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=int, default=8000)
    parser.add_argument("--seed", type=int, default=20260807)
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    parser.add_argument("--step", type=float, default=0.001)
    parser.add_argument("--out", default=str(ROOT / "docs" / "mesures" / "t34-efficacite.json"))
    args = parser.parse_args()

    print(f"T34 — ajustement de l'efficacité du videau contre la table bilatérale")
    print(f"  {args.samples} positions, graine {args.seed}, pas de scan {args.step}\n")

    p, targets = collect(Path(args.database), args.samples, args.seed)
    print(f"  {len(p)} positions collectées, p dans [{p.min():.4f}, {p.max():.4f}]\n")

    results = fit(p, targets, step=args.step)

    print(f"{'état':<12}{'x ajusté':>10}{'RMS':>12}{'max|Δ|':>12}{'biais moyen':>14}")
    for name, r in results.items():
        print(f"{name:<12}{r['x']:>10.3f}{r['rms']:>12.5f}{r['max_abs_residual']:>12.5f}"
              f"{r['mean_residual']:>14.6f}")

    payload = {
        "task": "T34",
        "seed": args.seed,
        "samples": len(p),
        "step": args.step,
        "database": str(args.database),
        "results": results,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nécrit dans {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
