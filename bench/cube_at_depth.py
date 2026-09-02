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

## Ce que T80 y ajoute — 2026-08-28

Deux choses, sans toucher au protocole ni à la graine, donc les colonnes
publiées par T34 restent lisibles telles quelles :

1. **L'équité perdue**, et pas seulement l'accord. Une décision de videau a
   deux branches, et la table les note toutes les deux exactement : la perte
   d'un verdict est donc `max(e_nd, min(e_dt, 1))` moins la branche choisie.
   Sans variance, comme le reste de ce domaine. Un désaccord à 0,001 et un
   désaccord à 0,3 ne sont pas la même erreur, et l'accord seul les confond.
2. **Le réseau distillé** (`--net`), qui rend les trois équités cubeful sans
   la table. Il est jugé par la même règle §4, alimentée par ses propres
   sorties — le modèle de Janowski n'intervient plus du tout dans sa colonne.
   C'est la comparaison qui décide si distiller les colonnes cubeful vaut la
   peine : notre modèle est à 97,5-98,3 % d'accord ici, avec un `x` ajusté.

Le tirage reste fait **en un seul endroit**, dans le processus parent, puis
distribué : à graine et à nombre de positions égaux, les positions sont les
mêmes qu'en séquentiel, quel que soit le nombre de processus.
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
from gammonnet.bearoff_net import BearoffNet  # noqa: E402
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


def branch_of(action: CubeAction, e_nd: float, e_double: float) -> float:
    """L'équité EXACTE de la branche qu'un verdict choisit.

    Doubler ou non : c'est la seule chose que le verdict décide, l'adversaire
    répondant au mieux. `TOO_GOOD` et `NO_DOUBLE` gardent donc le videau, tandis
    que `DOUBLE_TAKE` et `DOUBLE_PASS` le tournent — et ce que le double vaut
    est `min(e_dt, 1)`, l'adversaire prenant ou passant à son avantage.
    """
    return e_nd if action in (CubeAction.NO_DOUBLE, CubeAction.TOO_GOOD) else e_double


def cube_loss(action: CubeAction, e_nd: float, e_double: float) -> float:
    """Ce que ce verdict abandonne, exactement, contre le meilleur des deux."""
    return max(e_nd, e_double) - branch_of(action, e_nd, e_double)


def net_decision(net: BearoffNet, position: Position,
                 owner: CubeOwner) -> tuple[CubeAction, float, float]:
    """Le verdict du réseau distillé : la même règle, ses propres équités.

    Le modèle de videau n'intervient pas — pas de Janowski, pas de `x` ajusté.
    Le réseau rend les trois colonnes cubeful, et la table §4 les lit comme
    elle lit celles de la table exacte.
    """
    predicted = net.equity(position)
    e_nd = predicted.owned if owner == CubeOwner.OWNED else predicted.centered
    e_dt = 2.0 * predicted.opponent_owns
    return verdict(e_nd, e_dt, 1.0), e_nd, min(e_dt, 1.0)


def evaluate(payload):
    """Un lot de positions, dans un processus : rien n'est partagé."""
    (positions, x_of_raw, net_path, plies) = payload

    x_of = {CubeOwner(owner): x for owner, x in x_of_raw.items()}
    use_shared(str(DATABASE))
    native = NativeBearoff(str(DATABASE))
    network = Network.load(str(MODEL_BIN))
    net = BearoffNet.load(net_path) if net_path else None

    rows = []
    for encoded in positions:
        # Toutes les positions tirées ont le trait aux blancs (`random_bearoff`).
        position = codec.position_from_id(encoded, WHITE)
        for owner, x in x_of.items():
            exact_action, e_nd_exact, e_dbl_exact = exact_decision(
                native, position, owner)
            entry = {
                "id": encoded,
                "owner": owner.name,
                "exact": exact_action.name,
                "exact_margin": e_nd_exact - e_dbl_exact,
            }
            for ply in plies:
                config = SearchConfig(ply=ply, use_cube=True,
                                      cube_owner=int(owner), cube_x=x)
                probs = position_probs(network, position, config)
                ours = decide(probs, owner, x)
                entry[f"ply{ply}"] = ours.action.name
                entry[f"ply{ply}_margin"] = (ours.equity_no_double
                                             - ours.equity_double)
                entry[f"ply{ply}_loss"] = cube_loss(ours.action, e_nd_exact,
                                                    e_dbl_exact)
            if net is not None:
                action, e_nd_net, e_dbl_net = net_decision(net, position, owner)
                entry["net"] = action.name
                entry["net_margin"] = e_nd_net - e_dbl_net
                entry["net_loss"] = cube_loss(action, e_nd_exact, e_dbl_exact)
            rows.append(entry)

    disable_shared()
    native.close()
    return rows


def block_for(rows, key: str) -> dict:
    """Accord et équité perdue, pour une colonne de verdicts."""
    losses = [r[f"{key}_loss"] for r in rows]
    agreed = sum(1 for r in rows if r[key] == r["exact"])
    return {
        "n": len(rows), "agreed": agreed, "rate": agreed / len(rows) if rows else None,
        "mean_loss": sum(losses) / len(losses) if losses else None,
        "worst_loss": max(losses) if losses else None,
        "above_0.01": sum(1 for v in losses if v > 0.01),
    }


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--positions", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--plies", default="0,1")
    parser.add_argument("--net", default="",
                        help="réseau distillé à quatre sorties (T80)")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    plies = [int(p) for p in args.plies.split(",") if p.strip()]
    efficiency = json.loads(EFFICIENCY_FILE.read_text())["results"]
    x_of = {CubeOwner.OWNED: efficiency["owned"]["x"],
            CubeOwner.CENTRED: efficiency["centered"]["x"]}

    # LE TIRAGE RESTE CENTRAL. Les positions sont tirées ici, dans l'ordre, puis
    # distribuées : à graine et à compte égaux, ce sont celles de la version
    # séquentielle de T34, quel que soit le nombre de processus.
    rng = random.Random(SEED)
    table = TwoSidedBearoff(DATABASE)
    drawn = [codec.position_id(random_bearoff(rng, table))
             for _ in range(args.positions)]
    table.close()

    workers = max(1, min(args.workers, args.positions))
    chunks = [drawn[i::workers] for i in range(workers)]
    payloads = [(chunk, {int(k): v for k, v in x_of.items()}, args.net, plies)
                for chunk in chunks if chunk]

    print(f"T34/T80 — la décision de videau contre la décision exacte")
    print(f"  {args.positions} positions, graine {SEED}, {len(payloads)} processus")
    print(f"  x mesurés : possédé {x_of[CubeOwner.OWNED]:.3f}, "
          f"centré {x_of[CubeOwner.CENTRED]:.3f}")
    if args.net:
        print(f"  réseau distillé : {Path(args.net).name}")
    print(flush=True)

    if len(payloads) == 1:
        gathered = [evaluate(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            gathered = list(pool.map(evaluate, payloads))
    rows = [row for part in gathered for row in part]

    report = {"task": "T34-phase2-3a + T80", "seed": SEED,
              "positions": args.positions,
              "efficiency": {k.name: v for k, v in x_of.items()},
              "network": args.net, "per_owner": {}}
    columns = [f"ply{p}" for p in plies] + (["net"] if args.net else [])

    for owner in x_of:
        subset = [r for r in rows if r["owner"] == owner.name]
        block = {key: block_for(subset, key) for key in columns}
        contested = [r for r in subset
                     if r["exact"] != "NO_DOUBLE"
                     or any(r[key] != "NO_DOUBLE" for key in columns)]
        block["contested"] = {key: block_for(contested, key) for key in columns}
        report["per_owner"][owner.name] = block

    print(f"{'possesseur':<12}{'colonne':<10}{'accord':>9}{'perte moy.':>13}"
          f"{'pire':>10}{'> 0,01':>8}")
    for owner in x_of:
        for key in columns:
            row = report["per_owner"][owner.name][key]
            print(f"{owner.name:<12}{key:<10}{row['rate'] * 100:>8.1f} %"
                  f"{row['mean_loss']:>13.6f}{row['worst_loss']:>10.4f}"
                  f"{row['above_0.01']:>8}")

    print("\nLecture : la perte est l'équité exacte abandonnée par le verdict —")
    print("max(e_nd, e_double) moins la branche choisie. Sans variance : les deux")
    print("branches sont lues dans la table, elles ne sont pas estimées.")

    if len(plies) > 1:
        flips = [r for r in rows if r[f"ply{plies[0]}"] != r[f"ply{plies[-1]}"]]
        report["ply_flips"] = {
            "n": len(flips),
            "toward_exact": sum(1 for r in flips if r[f"ply{plies[-1]}"] == r["exact"]),
            "away_from_exact": sum(1 for r in flips if r[f"ply{plies[0]}"] == r["exact"]),
        }

    last = columns[-1]
    report["worst_disagreements"] = sorted(
        (r for r in rows if r[last] != r["exact"]),
        key=lambda r: -r[f"{last}_loss"])[:20]

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"\nécrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
