#!/usr/bin/env python3
"""T34 phase 2, étape 3 (a) — la décision de videau à profondeur, contre la
décision exacte de la table bilatérale.

Le levier de validation que §8 revendique : dans le domaine de la table, les
trois équités cubeful sont EXACTES, donc la décision exacte se lit — pas
besoin d'oracle externe ni de rollout. La décision exacte au videau centré ou
possédé se dérive des équités stockées par la table même du §4 :

    e_nd     = équité cubeful du possesseur courant
    e_dt     = 2 × équité « l'adversaire possède »   (après double pris)
    e_dp     = +1                                     (après double passé)
    verdict  = table §4 (too good / double-pass / double-take / no double)

Notre côté : la même mécanique de verdict, mais alimentée par le MODÈLE — la
distribution (exacte au 0-ply dans le domaine, propagée par `gn_search_probs`
au 1-ply) passée à `cube.decide` avec le `x` mesuré. Ce que le banc mesure est
donc la fidélité du verdict du modèle §3 à la vérité exacte, et ce que la
profondeur y change.

Sortie : taux d'accord par possesseur et par profondeur, désaccords classés
par ampleur exacte (l'écart d'équité exacte entre le verdict choisi et le
bon), JSON complet à côté.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import Position  # noqa: E402
from gammonnet import codec  # noqa: E402
from gammonnet.bearoff import (  # noqa: E402
    NativeBearoff,
    TwoSidedBearoff,
    disable_shared,
    use_shared,
)
from gammonnet.cube import CubeAction, CubeOwner, decide  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import BLACK, NUM_POINTS, WHITE  # noqa: E402
from gammonnet.search import SearchConfig, position_probs  # noqa: E402

DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"
MODEL_BIN = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
EFFICIENCY_FILE = ROOT / "docs" / "mesures" / "t34-efficacite.json"

SEED = 20260808


def random_bearoff(rng: random.Random, table: TwoSidedBearoff) -> Position:
    """Le tirage de `bench/exact_gap.py` : uniforme sur le nombre de pions."""
    while True:
        points = [0] * NUM_POINTS
        for player in (WHITE, BLACK):
            count = rng.randint(1, table.chequers)
            for _ in range(count):
                point = rng.randrange(table.points)
                if player == WHITE:
                    points[point] += 1
                else:
                    points[NUM_POINTS - 1 - point] -= 1
        white = sum(n for n in points if n > 0)
        black = -sum(n for n in points if n < 0)
        position = Position(points=tuple(points), bar=(0, 0),
                            off=(15 - white, 15 - black), turn=WHITE)
        if table.contains(position):
            return position


def verdict(e_nd: float, e_dt: float, e_dp: float) -> CubeAction:
    """La table §4, à la lettre — les mêmes quatre lignes que `gn_cube.c`,
    citées à la spécification plutôt qu'au code."""
    e_double = min(e_dt, e_dp)
    if e_nd > e_dp and e_nd >= e_double:
        return CubeAction.TOO_GOOD
    if e_dt >= e_dp:
        return CubeAction.DOUBLE_PASS
    if e_double > e_nd:
        return CubeAction.DOUBLE_TAKE
    return CubeAction.NO_DOUBLE


def exact_decision(native: NativeBearoff, position: Position,
                   owner: CubeOwner) -> tuple[CubeAction, float, float]:
    """Le verdict exact, et les équités des deux branches qui le portent."""
    exact = native.equities(position)
    e_nd = exact.owned if owner == CubeOwner.OWNED else exact.centered
    e_dt = 2.0 * exact.opponent_owns
    action = verdict(e_nd, e_dt, 1.0)
    return action, e_nd, min(e_dt, 1.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=2000)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    efficiency = json.loads(EFFICIENCY_FILE.read_text())["results"]
    x_of = {CubeOwner.OWNED: efficiency["owned"]["x"],
            CubeOwner.CENTRED: efficiency["centered"]["x"]}

    rng = random.Random(SEED)
    table = TwoSidedBearoff(DATABASE)
    use_shared(DATABASE)
    native = NativeBearoff(DATABASE)
    network = Network.load(MODEL_BIN)

    positions = [random_bearoff(rng, table) for _ in range(args.positions)]

    rows = []
    for position in positions:
        for owner, x in x_of.items():
            exact_action, e_nd_exact, e_dbl_exact = exact_decision(
                native, position, owner)
            entry = {
                "id": codec.position_id(position),
                "owner": owner.name,
                "exact": exact_action.name,
                "exact_margin": e_nd_exact - e_dbl_exact,
            }
            for ply in (0, 1):
                config = SearchConfig(ply=ply, use_cube=True,
                                      cube_owner=int(owner), cube_x=x)
                probs = position_probs(network, position, config)
                ours = decide(probs, owner, x)
                entry[f"ply{ply}"] = ours.action.name
                entry[f"ply{ply}_margin"] = (ours.equity_no_double
                                             - ours.equity_double)
            rows.append(entry)

    # Agrégats.
    report = {"task": "T34-phase2-3a", "seed": SEED,
              "positions": args.positions, "efficiency":
              {k.name: v for k, v in x_of.items()}, "per_owner": {}}
    for owner in x_of:
        subset = [r for r in rows if r["owner"] == owner.name]
        block = {}
        for ply in (0, 1):
            agreed = sum(1 for r in subset if r[f"ply{ply}"] == r["exact"])
            block[f"ply{ply}"] = {"n": len(subset), "agreed": agreed,
                                  "rate": agreed / len(subset)}
        block["contested"] = {}
        contested = [r for r in subset
                     if r["exact"] != "NO_DOUBLE"
                     or r["ply0"] != "NO_DOUBLE" or r["ply1"] != "NO_DOUBLE"]
        for ply in (0, 1):
            agreed = sum(1 for r in contested if r[f"ply{ply}"] == r["exact"])
            block["contested"][f"ply{ply}"] = {
                "n": len(contested), "agreed": agreed,
                "rate": agreed / len(contested) if contested else None}
        report["per_owner"][owner.name] = block

    # La profondeur change-t-elle la décision ? Compté plutôt que supposé —
    # et quand elle la change, dans quel sens par rapport à l'exact.
    flips = [r for r in rows if r["ply0"] != r["ply1"]]
    report["ply_flips"] = {
        "n": len(flips),
        "toward_exact": sum(1 for r in flips if r["ply1"] == r["exact"]),
        "away_from_exact": sum(1 for r in flips if r["ply0"] == r["exact"]),
    }

    worst = sorted((r for r in rows if r["ply1"] != r["exact"]),
                   key=lambda r: -abs(r["exact_margin"]))[:20]
    report["worst_ply1_disagreements"] = worst

    print(json.dumps({k: v for k, v in report.items()
                      if k != "worst_ply1_disagreements"}, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"écrit dans {args.out}")

    disable_shared()
    table.close()
    native.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
