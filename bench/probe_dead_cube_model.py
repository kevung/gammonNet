#!/usr/bin/env python3
"""Le videau mort, sans réseau : le modèle seul, sur une grille.

## Le théorème que la sonde teste

À `away_on_roll <= cube`, le verdict correct est « never redouble » **pour
toute position** :

- gagner la partie au videau courant gagne déjà le match ;
- redoubler ne change donc rien à la branche gagnante ;
- mais aggrave la branche perdante — l'adversaire encaisse deux fois plus ;
- et l'adversaire ne passera jamais : passer donnerait au doubleur le videau
  courant, qui gagne le match, donc une MWC de zéro. N'importe quelle prise
  vaut mieux que zéro.

Rien là-dedans ne dépend de la distribution. Une sonde par positions mesurerait
donc le réseau autant que le modèle ; celle-ci balaie des distributions
synthétiques et n'interroge que `gn_cube_decide`.

## Ce qu'elle a établi (2026-08-26)

**Le modèle ne double jamais en videau mort** — 0 sur 495 distributions, dans
six états. Le défaut observé dans la campagne T35 vient donc d'ailleurs :
des bearoffs à `P(gain) = 1,0` exactement, où `e_nd = e_dbl = +1,0` et où
`gn_cube_verdict` tranche l'égalité `e_dt >= e_dp` vers `DOUBLE_PASS`. Un gain
certain restant certain à n'importe quel videau, son coût en équité est nul —
voir `docs/mesures/2026-08-26-T35-verdict.md`.

Usage :
    python bench/probe_dead_cube_model.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.cube import CubeOwner, decide  # noqa: E402
from gammonnet.cubeful import measured_efficiency  # noqa: E402
from gammonnet.infer import Evaluation  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402

#: (away au trait, away adverse, videau). Les quatre premiers sont morts pour
#: le seul joueur au trait ; les deux derniers le sont à un videau plus haut.
CASES = ((1, 3, 2), (1, 5, 2), (1, 7, 2), (2, 5, 2), (2, 7, 4), (1, 5, 4))

#: Des structures de gammon variées, pas une seule : un modèle qui ne
#: déraillerait que sur les positions gammonneuses passerait une grille trop
#: polie.
GAMMON_SHAPES = ((0.0, 0.0), (0.15, 0.15), (0.30, 0.10), (0.10, 0.30),
                 (0.45, 0.05))


def main() -> int:
    efficiency = measured_efficiency()[int(CubeOwner.OWNED)]
    print(f"efficacité (videau possédé) : {efficiency:.4f}\n")
    failures = 0

    for away_mover, away_opponent, cube in CASES:
        state = MatchState(away_on_roll=away_mover, away_opponent=away_opponent,
                           cube=cube, crawford=False)
        doubles, total, worst = 0, 0, None
        for i in range(1, 100):
            win = i / 100.0
            for gammon_win, gammon_lose in GAMMON_SHAPES:
                evaluation = Evaluation(
                    win, win * gammon_win, win * gammon_win * 0.05,
                    (1 - win) * gammon_lose, (1 - win) * gammon_lose * 0.05)
                decision = decide(evaluation, CubeOwner.OWNED, efficiency,
                                  state=state, jacoby=False)
                total += 1
                if decision.action.name != "NO_DOUBLE":
                    doubles += 1
                    gap = decision.equity_double - decision.equity_no_double
                    if worst is None or gap > worst[0]:
                        worst = (gap, win, decision)

        dead = cube >= away_mover
        print(f"── {away_mover}-away vs {away_opponent}-away, videau {cube} "
              f"({'MORT pour le trait' if dead else 'vivant'})")
        print(f"   {doubles}/{total} distributions font doubler le modèle")
        if worst is not None:
            gap, win, decision = worst
            print(f"   pire cas : P(gain)={win:.2f} → {decision.action.name}, "
                  f"e_nd={decision.equity_no_double:+.6f} "
                  f"e_dbl={decision.equity_double:+.6f} écart={gap:+.6f}")
        if dead and doubles:
            failures += 1

    if failures:
        print(f"\nREFUSÉ : {failures} état(s) de videau mort où le modèle double.")
        return 1
    print("\nAucun doublement en videau mort : le modèle tient le théorème.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
