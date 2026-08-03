#!/usr/bin/env python3
"""T31 — ce que le filtre de coups coûte en qualité, mesuré.

> *Un filtre qui « ne change rien » n'a pas été mesuré.* — `PLAN.md`

La référence produite par `run_filter_reference.py` contient, pour chaque
décision, l'équité 2-ply de **tous** les coups légaux. Cela suffit à évaluer
**n'importe quelle taille de filtre hors ligne, et exactement** : un filtre de
taille `k` classe les coups à faible profondeur, garde les `k` premiers, puis
choisit parmi eux le meilleur au 2-ply. Comme l'équité 2-ply de chaque coup est
connue, le coup que le filtre aurait retenu se déduit sans relancer la moindre
recherche.

C'est ce qui rend la référence rentable : elle coûte cher une fois, et répond
ensuite à toutes les tailles de filtre sans nouveau calcul.

Deux nombres par taille de filtre, ceux que le critère réclame :

* le **taux de désaccord** avec le 2-ply non filtré ;
* l'**équité moyenne perdue**, à la fois par décision et conditionnellement à
  un désaccord. La seconde est la seule qui dise si les désaccords sont
  anodins ou coûteux.

Usage :
    python bench/analyse_filter.py
    python bench/analyse_filter.py --reference docs/mesures/t31-reference-2ply.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import codec  # noqa: E402
from gammonnet.infer import Network  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"

#: Tailles de filtre évaluées. 0 signifie « aucun filtrage », donc le témoin.
FILTER_SIZES = (1, 2, 3, 4, 5, 6, 8, 10, 12, 16)


def shallow_ranking(network, position, d1, d2) -> list[str]:
    """Les coups classés au 0-ply, meilleur d'abord — le pré-tri du filtre.

    Même convention de signe que partout ailleurs : `play.result` a déjà passé
    le trait, donc son évaluation décrit l'ADVERSAIRE et le meilleur coup est
    celui qui la minimise.
    """
    from gammonnet.arena import game_value

    scored = []
    for play in position.legal_plays(d1, d2):
        if play.result.is_over():
            equity = -float(game_value(play.result, position.turn))
        else:
            equity = network.evaluate(play.result).money_equity
        scored.append((equity, codec.position_id(play.result)))
    scored.sort()
    return [key for _, key in scored]


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalle de Wilson — honnête là où le normal ne l'est pas.

    Sur un taux proche de zéro et un échantillon modeste, l'intervalle normal
    déborde sous zéro et suggère une précision qu'on n'a pas.
    """
    if total == 0:
        return (float("nan"), float("nan"))
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default="docs/mesures/t31-reference-2ply.jsonl")
    args = parser.parse_args()

    path = ROOT / args.reference
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        raise SystemExit(f"{path} est vide")

    print(f"Référence : {len(rows)} décisions 2-ply non filtrées ({path.name})")

    evaluations = [r["evaluations"] for r in rows]
    seconds = [r["seconds"] for r in rows]
    moves = [len(r["ranking"]) for r in rows]
    print(f"  coups légaux par décision : médiane {statistics.median(moves):.0f}, "
          f"max {max(moves)}")
    print(f"  évaluations par décision  : médiane {statistics.median(evaluations):,.0f}, "
          f"moyenne {statistics.mean(evaluations):,.0f}, max {max(evaluations):,.0f}")
    print(f"  secondes par décision     : médiane {statistics.median(seconds):.1f}, "
          f"moyenne {statistics.mean(seconds):.1f}, max {max(seconds):.1f}")
    print()

    network = Network.load(MODEL)

    # Pour chaque décision : le classement peu profond, et l'équité 2-ply de
    # chaque coup. Tout le reste est de l'arithmétique.
    prepared = []
    for row in rows:
        position = codec.position_from_id(row["position_id"], row["turn"])
        d1, d2 = row["dice"]
        equity = {c["key"]: c["equity"] for c in row["ranking"]}
        best = max(equity.values())
        prepared.append((shallow_ranking(network, position, d1, d2), equity, best,
                         row["evaluations"]))

    print("Ce que coûte le filtre, par taille")
    print("=" * 82)
    print(f"{'garde':>6} {'désaccord':>12} {'IC 95 %':>18} {'éq. perdue':>13} "
          f"{'si désaccord':>14} {'débit':>8}")
    print("-" * 82)

    for keep in FILTER_SIZES:
        disagreements = 0
        applicable = 0
        losses = []

        saved = 0.0
        total = 0.0
        for shallow, equity, best, used in prepared:
            # Le coût d'une décision 2-ply est porté par les coups qu'elle
            # développe à la racine : garder `k` coups sur `n` en ramène la
            # part à k/n. C'est une estimation à partir des évaluations
            # réellement comptées, pas une mesure d'un build filtré.
            total += used
            saved += used * min(keep, len(shallow)) / len(shallow)

            if len(shallow) <= keep:
                continue  # le filtre ne retranche rien : la décision ne le teste pas
            applicable += 1
            kept = shallow[:keep]
            chosen = max(equity[k] for k in kept)
            loss = best - chosen
            if loss > 0:
                disagreements += 1
                losses.append(loss)

        if applicable == 0:
            continue

        rate = disagreements / applicable
        low, high = wilson(disagreements, applicable)
        mean_loss = sum(losses) / applicable if applicable else 0.0
        conditional = statistics.mean(losses) if losses else 0.0

        speedup = total / saved if saved else float("inf")
        print(f"{keep:>6} {rate * 100:>11.2f}% "
              f"[{low * 100:>6.2f} ; {high * 100:>6.2f}] "
              f"{mean_loss:>12.5f} {conditional:>14.5f} {speedup:>7.1f}×")

    print("-" * 82)
    print("« garde » : nombre de coups conservés après le pré-tri 0-ply.")
    print("« éq. perdue » : équité moyenne perdue PAR DÉCISION, en points.")
    print("« si désaccord » : la même, conditionnée aux décisions où le filtre se trompe.")
    print()
    print("Les décisions offrant moins de coups que la taille du filtre sont exclues :")
    print("le filtre n'y retranche rien et les compter diluerait le taux vers zéro.")
    print()
    print("« débit » : facteur ESTIMÉ, à partir des évaluations comptées et de la part de")
    print("coups conservés. Ce n'est pas le chronométrage d'un build filtré — ce serait")
    print("une mesure, et elle reste à faire.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
