#!/usr/bin/env python3
"""T39 — le contrôle de non-biais de l'arbitre, mesuré en volume.

« Un arbitre qu'on n'a pas vérifié n'arbitre rien. » Le test de la suite le
vérifie sur huit positions ; ce banc le mesure en volume, cubeless ET
cubeful, sur des positions du domaine de la table bilatérale — le seul
endroit où la bonne réponse est connue sans estimation.

Pour chaque position et chaque colonne (cubeless, puis videau centré /
possédé / adverse avec `cube_defer_first` — la convention de la table,
établie par sonde, voir `gn_rollout.h`), le rollout non tronqué joue ses
parties jusqu'au bout, décisions de videau EXACTES dans le domaine, et l'on
rapporte le z-score `(rollout − exact) / erreur-type`. Un arbitre non biaisé
donne des z ~ N(0, 1) : ~95 % dans ±1,96, moyenne nulle. C'est ce qu'on
regarde, pas une impression.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import codec  # noqa: E402
from gammonnet.bearoff import (  # noqa: E402
    NativeBearoff,
    TwoSidedBearoff,
    disable_shared,
    use_shared,
)
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rollout import RolloutConfig, rollout  # noqa: E402
from gammonnet.rules import BLACK, NUM_POINTS, WHITE, Position  # noqa: E402
from gammonnet.search import SearchConfig  # noqa: E402

DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"
MODEL_BIN = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
EFFICIENCY_FILE = ROOT / "docs" / "mesures" / "t34-efficacite.json"

SEED = 20260810
ROLLOUT_SEED = 424242

COLUMNS = ("cubeless", "centred", "owned", "opponent")
OWNER_OF = {"centred": 0, "owned": 1, "opponent": 2}


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


def measure(payload):
    """Graine de rollout PAR POSITION : les dés communs sont l'outil de la
    comparaison de variantes, pas de la mesure de biais — une graine unique
    partagée par toutes les positions ferait de leur chance commune un faux
    biais global (constaté : mean_z ≈ +0,4 sur la colonne cubeless pourtant
    non biaisée). Les quatre colonnes d'une MÊME position gardent la même
    graine : ça, c'est de la comparaison."""
    positions, trials, x3 = payload
    use_shared(DATABASE)
    native = NativeBearoff(DATABASE)
    network = Network.load(MODEL_BIN)

    rows = []
    for index, position in positions:
        exact = native.equities(position)
        target = {"cubeless": exact.cubeless, "centred": exact.centered,
                  "owned": exact.owned, "opponent": exact.opponent_owns}
        row = {"id": codec.position_id(position)}
        # Par indice, pas par hash() : celui de Python est randomisé par
        # processus, et une graine non reproductible ferait de chaque run un
        # protocole différent.
        seed = ROLLOUT_SEED + index
        for column in COLUMNS:
            if column == "cubeless":
                config = RolloutConfig(trials=trials, truncate=0,
                                       seed=seed,
                                       policy=SearchConfig(ply=0))
            else:
                owner = OWNER_OF[column]
                policy = SearchConfig(ply=0, use_cube=True,
                                      cube_owner=owner, cube_x=0.6)
                config = RolloutConfig(trials=trials, truncate=0,
                                       seed=seed, policy=policy,
                                       use_cube=True, cube_owner=owner,
                                       cube_x=x3, cube_defer_first=True)
            result = rollout(network, position, config)
            error = max(result.standard_error, 1e-12)
            row[column] = {
                "exact": target[column],
                "rollout": result.equity,
                "se": result.standard_error,
                "z": (result.equity - target[column]) / error,
                "cashed": result.cashed,
                "average_cube": result.average_cube,
                "stalled": result.stalled,
            }
        rows.append(row)

    native.close()
    disable_shared()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=120)
    parser.add_argument("--trials", type=int, default=2592)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    payload = json.loads(EFFICIENCY_FILE.read_text())["results"]
    x3 = (payload["centered"]["x"], payload["owned"]["x"],
          payload["opponent"]["x"])

    rng = random.Random(SEED)
    table = TwoSidedBearoff(DATABASE)
    positions = list(enumerate(
        random_bearoff(rng, table) for _ in range(args.positions)))
    table.close()

    chunk = (len(positions) + args.workers - 1) // args.workers
    payloads = [(positions[i:i + chunk], args.trials, x3)
                for i in range(0, len(positions), chunk)]
    with Pool(args.workers) as pool:
        rows = [r for batch in pool.map(measure, payloads) for r in batch]

    report = {"task": "T39-non-biais", "seed": SEED,
              "rollout_seed": ROLLOUT_SEED, "positions": args.positions,
              "trials": args.trials, "efficiency": list(x3),
              "columns": {}}
    for column in COLUMNS:
        # Deux régimes, agrégés séparément. Une position quasi certaine dont
        # la séquence perdante (probabilité ~1/2000) n'apparaît pas dans le
        # tirage rend une erreur-type NULLE et un écart minuscule : ce n'est
        # pas un biais, c'est la granularité d'un estimateur à N essais, qui
        # ne résout rien de plus fin que ~1/N. Le z n'a de sens que sur les
        # positions résolues (se > 0) ; les dégénérées sont jugées sur leur
        # écart absolu, borné par 3/N.
        resolved = [r[column] for r in rows if r[column]["se"] > 0.0]
        degenerate = [r[column] for r in rows if r[column]["se"] == 0.0]
        zs = [v["z"] for v in resolved]
        inside = sum(1 for z in zs if abs(z) <= 1.96)
        stalled = sum(r[column]["stalled"] for r in rows)
        gaps = [abs(v["rollout"] - v["exact"]) for v in degenerate]
        report["columns"][column] = {
            "n_resolved": len(zs),
            "inside_196": inside,
            "inside_rate": inside / len(zs) if zs else None,
            "mean_z": sum(zs) / len(zs) if zs else None,
            "max_abs_z": max(abs(z) for z in zs) if zs else None,
            "n_degenerate": len(degenerate),
            "max_degenerate_gap": max(gaps) if gaps else 0.0,
            # 6/N : un évènement de probabilité 6/N absent d'un tirage de N
            # essais est à e^-6 ≈ 0,25 % — un écart au-delà dénoncerait un
            # vrai biais, en deçà c'est la granularité de l'estimateur.
            "degenerate_within_6_over_n": (
                all(g <= 6.0 / args.trials for g in gaps)),
            "stalled": stalled,
        }
        if column != "cubeless":
            report["columns"][column]["cashed_fraction"] = (
                sum(r[column]["cashed"] for r in rows)
                / (len(rows) * args.trials))
            report["columns"][column]["average_cube"] = (
                sum(r[column]["average_cube"] for r in rows) / len(rows))

    worst = sorted(
        rows,
        key=lambda r: -max(
            (abs(r[c]["z"]) for c in COLUMNS if r[c]["se"] > 0.0),
            default=0.0))
    report["worst"] = [
        {"id": r["id"]} | {c: {k: r[c][k] for k in ("exact", "rollout", "se", "z")}
                           for c in COLUMNS}
        for r in worst[:10]
    ]

    print(json.dumps({k: v for k, v in report.items() if k != "worst"},
                     indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"écrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
