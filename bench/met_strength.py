#!/usr/bin/env python3
"""T97 — deux tables d'équité de match s'affrontent, tout le reste identique.

## Pourquoi ce banc existe, et pourquoi il est le seul qui autorise à changer

`bench/compare_met.py` dit de combien notre table s'écarte de Kazaross-XG2.
Il ne dit **pas** laquelle est la meilleure : une table plus proche d'une autre
table n'est pas une table meilleure, et la table de Kazaross est elle-même une
mesure, faite par d'autres moteurs. Seul un affrontement tranche.

## Ce qui est tenu identique, et ce qui ne l'est pas

Les deux joueurs sont **le même moteur** — mêmes poids, même profondeur, même
filtre, même réseau d'élagage, même table de fin de partie. Ils ne diffèrent
que par le fichier de table qu'ils consultent. Les matchs sont joués à **dés
dupliqués** : la même séquence est rejouée sièges échangés, de sorte qu'un
moteur contre lui-même totalise **exactement** zéro.

C'est ce que `GammonNetCubePlayer.met_table` rend possible : la table active
est un état global du processus, et les dés communs veulent les deux joueurs
dans le même processus. Chacun installe la sienne avant chacune de ses
décisions — 5 200 octets de `memcpy` contre une recherche.

## Le volume, et ce qu'il peut établir

Une table ne pèse que sur les décisions de videau, et seulement là où les deux
tables divergent assez pour renverser un verdict. L'effet attendu est donc
**petit**, et le volume doit être dit avec le résultat plutôt que choisi après
lui. `BRIEF.md` §9 : en dessous d'environ un million de parties par paire, deux
bons moteurs ne se séparent pas du bruit — et deux tables séparées de 0,002 de
MWC sur quelques cellules sont deux moteurs très proches.

Un écart non significatif est donc un **résultat attendu**, pas un échec : il
borne ce que le choix de table peut coûter, ce qui est déjà une information que
personne ne publie.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import met  # noqa: E402
from gammonnet.arena import bootstrap_ci  # noqa: E402
from gammonnet.cubeful import GammonNetCubePlayer, play_match_duplicate  # noqa: E402

_A = _B = None


def _install(a, b):
    global _A, _B
    _A, _B = a, b


def _play(payload):
    seed, index, away_a, away_b = payload
    won, stats = play_match_duplicate(_A, _B, away_a, away_b, seed, index,
                                      dice_key="met")
    return won, stats["games"], stats["stalled"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table-a", default="",
                        help="table du joueur A (vide = la compilée)")
    parser.add_argument("--table-b", default="",
                        help="table du joueur B (vide = la compilée)")
    parser.add_argument("--pairs", type=int, default=2000)
    parser.add_argument("--length", type=int, default=7)
    parser.add_argument("--ply", type=int, default=0)
    parser.add_argument("--cube-ply", type=int, default=0)
    parser.add_argument("--workers", type=int, default=28)
    parser.add_argument("--seed", type=int, default=20260917)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if args.table_a == args.table_b:
        print("REFUS : les deux joueurs consulteraient la même table — le "
              "résultat serait zéro par construction, ce qui ne mesure rien",
              file=sys.stderr)
        return 2

    def named(path):
        if not path:
            return "kazaross-xg2"
        met.use_table(path)
        name = met.table_name()
        met.reset_table()
        return name

    name_a, name_b = named(args.table_a), named(args.table_b)

    a = GammonNetCubePlayer(ply=args.ply, cube_ply=args.cube_ply,
                            met_table=args.table_a, name=f"met:{name_a}")
    b = GammonNetCubePlayer(ply=args.ply, cube_ply=args.cube_ply,
                            met_table=args.table_b, name=f"met:{name_b}")

    print(f"T97 — « {name_a} » contre « {name_b} »")
    print(f"  matchs en {args.length} points, {args.pairs} paires "
          f"({2 * args.pairs} matchs), dés dupliqués, profondeur {args.ply} "
          f"(videau {args.cube_ply}), graine {args.seed}")

    payloads = [(args.seed, index, args.length, args.length)
                for index in range(args.pairs)]
    started = time.time()
    results, games, stalled = [], 0, 0
    with mp.Pool(args.workers, initializer=_install, initargs=(a, b)) as pool:
        for index, (won, played, was_stalled) in enumerate(
                pool.imap_unordered(_play, payloads, chunksize=4)):
            results.append(won / 2.0)  # la paire rend -2, 0 ou +2
            games += played
            stalled += int(was_stalled)
            if (index + 1) % 500 == 0:
                print(f"  {index + 1}/{args.pairs} paires", flush=True)

    elapsed = time.time() - started
    mean = sum(results) / len(results)
    low, high = bootstrap_ci(results, args.bootstrap, args.seed)

    print(f"\n  {name_a} contre {name_b} : {mean:+.5f} match par paire "
          f"[{low:+.5f} ; {high:+.5f}]")
    print(f"  {2 * args.pairs} matchs, {games} parties, {stalled} bloquées, "
          f"{elapsed:.0f} s")
    if low <= 0.0 <= high:
        print("  zéro est dans l'intervalle : à ce volume, le choix de table "
              "ne se distingue pas du bruit. C'est un résultat — il borne ce "
              "que ce choix peut coûter.")

    if args.out:
        args.out.write_text(json.dumps({
            "a": name_a, "b": name_b,
            "table_a": args.table_a, "table_b": args.table_b,
            "pairs": args.pairs, "matches": 2 * args.pairs, "games": games,
            "length": args.length, "ply": args.ply, "cube_ply": args.cube_ply,
            "seed": args.seed, "seconds": elapsed, "stalled": stalled,
            "mean": mean, "ci": [low, high],
        }, indent=1) + "\n")
        print(f"\n→ {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
