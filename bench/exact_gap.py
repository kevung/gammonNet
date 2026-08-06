#!/usr/bin/env python3
"""T38 — l'équité perdue par décision, mesurée contre un arbitre **parfait**.

## Pourquoi cette mesure vaut plus que son domaine

Partout ailleurs, dire qu'un moteur joue mieux qu'un autre demande un arbitre —
des rollouts, avec leur variance et leur biais, et la réserve que « un rollout
conduit par notre réseau nous favorise ». **Dans le domaine de la table
bilatérale, cette difficulté disparaît.** La table donne l'équité exacte de
n'importe quelle position de bearoff, donc de n'importe quel coup légal ; le
meilleur coup s'y lit sans estimer quoi que ce soit.

On obtient donc, sans le moindre arbitre discutable :

* le **taux d'accord** de chaque moteur avec le jeu parfait ;
* et surtout l'**équité qu'il perd par décision**, en points, exactement.

C'est la forme que doit prendre toute mesure de qualité dans ce projet — une
partie ne rend qu'un point de donnée, une décision en rend un aussi mais il y en
a cinquante-cinq par partie, et celui-ci n'a aucune variance.

## Ce que cette mesure ne dit pas

Elle porte sur les positions **de bearoff sans contact**, celles que la table
couvre : au plus onze pions par camp, tous dans les six premiers points. Elle ne
dit rien du contact, et `BRIEF.md` §9 avertit qu'un corpus riche en fins de
partie flatte un moteur qui a des tables et punit celui qui n'en a pas. Le
chiffre produit ici est donc **le trou que la table comblerait**, pas une force
globale.

Usage :
    python bench/exact_gap.py --decisions 2000 --plies 0,1,2
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.arena import game_value  # noqa: E402
from gammonnet.bearoff import TwoSidedBearoff  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import BLACK, NUM_POINTS, WHITE, Position  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

DEFAULT_DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"


def random_bearoff(rng: random.Random, table: TwoSidedBearoff) -> Position:
    """Une position de bearoff tirée au hasard dans le domaine de la table.

    Le tirage est délibérément **non uniforme sur les positions** mais uniforme
    sur le nombre de pions : tirer uniformément parmi les répartitions donnerait
    surtout des positions à onze pions, alors que les décisions intéressantes
    sont réparties sur tout le spectre.
    """
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


def exact_equity_of_play(table: TwoSidedBearoff, result: Position, mover: int) -> float:
    """L'équité exacte d'un coup, du point de vue de celui qui l'a joué.

    Deux cas, et le premier est un piège : une position terminale **se calcule**,
    elle ne se lit dans aucune table. Le résultat a rendu le trait, donc ce que
    la table dit de lui est vu par l'adversaire — d'où la négation.
    """
    if result.is_over():
        return float(game_value(result, mover))
    return -table.equity(result).cubeless


def score_all(table, position, plays) -> list[float]:
    """L'équité exacte de chaque coup, dans l'ordre où ils sont donnés.

    Une **liste parallèle**, et non un dictionnaire indexé par `id` : les objets
    de coup sont régénérés à chaque appel de `legal_plays`, donc leur identité
    ne survit pas d'un appel à l'autre. La première version de ce fichier a fait
    exactement cette erreur, et elle a levé — ce qui est la bonne façon d'échouer.
    """
    return [exact_equity_of_play(table, play.result, position.turn) for play in plays]


def measure(payload):
    """Un lot de décisions, dans un processus.

    Chaque processus tire ses propres positions à partir d'une graine qui lui est
    propre, ouvre sa propre vue sur la table et sa propre session GNU Backgammon.
    Rien n'est partagé, donc rien n'a à être verrouillé — et le résultat ne
    dépend pas de la répartition, puisque chaque lot est déterministe.
    """
    database, model, plies, with_gnubg, seed, count = payload

    rng = random.Random(seed)
    table = TwoSidedBearoff(database)
    network = Network.load(model)

    engines = {f"gammonnet-{p}ply": ("ours", p) for p in plies}
    if with_gnubg:
        from gammonnet.gnubg_engine import GnubgEngine
        for p in plies:
            engines[f"gnubg-{p}ply"] = ("gnubg", GnubgEngine(ply=p))

    losses = {name: [] for name in engines}
    agreed = {name: 0 for name in engines}
    considered = 0

    while considered < count:
        position = random_bearoff(rng, table)
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = position.legal_plays(d1, d2)
        if len(plays) < 2:
            continue

        scored = score_all(table, position, plays)
        top = max(scored)
        considered += 1

        for name, (kind, handle) in engines.items():
            if kind == "ours":
                ranked = search_plays(network, position, d1, d2,
                                      SearchConfig(ply=handle))
                chosen = ranked[0].play if ranked else None
            else:
                chosen = handle.choose(position, d1, d2, rng)
            if chosen is None:
                continue

            value = None
            for play, equity in zip(plays, scored):
                if play.result == chosen.result:
                    value = equity
                    break
            if value is None:
                raise AssertionError(f"{name} a joué un coup que nous ne générons pas")

            losses[name].append(top - value)
            if abs(top - value) < 1e-12:
                agreed[name] += 1

    table.close()
    return losses, agreed, considered


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--decisions", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260806)
    parser.add_argument("--plies", default="0,1,2")
    parser.add_argument("--workers", type=int, default=28)
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    parser.add_argument("--with-gnubg", action="store_true",
                        help="mesurer aussi GNU Backgammon, à la même profondeur")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    plies = [int(p) for p in args.plies.split(",") if p.strip()]
    model = str(ROOT / "models" / "cubeless_prob5_512_512_256_128.bin")

    with TwoSidedBearoff(args.database) as probe:
        points, chequers = probe.points, probe.chequers

    print(f"T38 — équité perdue par décision, contre la table exacte "
          f"{points}x{chequers}")
    print(f"  {args.decisions} décisions, graine {args.seed}, "
          f"{args.workers} processus\n", flush=True)

    workers = max(1, min(args.workers, args.decisions))
    share = [args.decisions // workers + (1 if i < args.decisions % workers else 0)
             for i in range(workers)]
    payloads = [
        (args.database, model, plies, args.with_gnubg, args.seed + 1000 * i, n)
        for i, n in enumerate(share) if n
    ]

    import time
    start = time.perf_counter()
    if len(payloads) == 1:
        gathered = [measure(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            gathered = list(pool.map(measure, payloads))
    elapsed = time.perf_counter() - start

    names = list(gathered[0][0])
    losses = {name: [] for name in names}
    agreed = {name: 0 for name in names}
    considered = 0
    for part_losses, part_agreed, part_count in gathered:
        for name in names:
            losses[name].extend(part_losses[name])
            agreed[name] += part_agreed[name]
        considered += part_count


    print(f"{considered} décisions en {elapsed / 60:.1f} min\n")

    print(f"\n{'moteur':<20}{'accord':>10}{'perte moyenne':>16}"
          f"{'si désaccord':>15}{'pire':>10}")
    rows = []
    for name in names:
        values = losses[name]
        if not values:
            continue
        n = len(values)
        mean = sum(values) / n
        wrong = [v for v in values if v > 1e-12]
        rows.append({
            "engine": name,
            "decisions": n,
            "agreement": agreed[name] / n,
            "mean_loss": mean,
            "mean_loss_when_wrong": (sum(wrong) / len(wrong)) if wrong else 0.0,
            "worst_loss": max(values),
        })
        print(f"{name:<20}{agreed[name] / n * 100:>9.1f} %{mean:>16.5f}"
              f"{(sum(wrong) / len(wrong) if wrong else 0.0):>15.5f}"
              f"{max(values):>10.4f}")

    print("\nLecture : la perte est en points d'équité money, exacte — la table")
    print("bilatérale note tout coup légal sans rien estimer. Le domaine est le")
    print("bearoff sans contact ; ce chiffre est le trou qu'une table comblerait,")
    print("pas une force globale.")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "task": "T38", "seed": args.seed, "decisions": considered,
            "database": str(args.database), "rows": rows,
        }, indent=2) + "\n")
        print(f"\nécrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
