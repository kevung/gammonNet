#!/usr/bin/env python3
"""T97 — calculer une table d'équité de match avec ce moteur, et rien d'autre.

## Pourquoi il n'y a pas de point fixe à chercher

Une partie se termine toujours par des points marqués : l'un des deux `away`
**décroît strictement**. La valeur d'une cellule ne dépend donc que de cellules
dont la somme `a + b` est plus petite, déjà calculées quand on y arrive. La
table se remplit par programmation dynamique, **aucune valeur initiale n'est
injectée**, et l'objection « votre table de départ était la leur » ne se pose
pas.

Trois familles de cellules, dans cet ordre :

  `POST[n]`   après-Crawford, le poursuivant à `n`-away contre 1-away.
              Ne dépend que de `POST[m]`, `m < n`.
  `PRE[a][1]` la partie de Crawford elle-même — sans videau, c'est une règle.
              Dépend de `POST`.
  `PRE[a][b]` `a, b >= 2`, videau vivant. Dépend de `PRE` à `a + b` moindre.

## Ce que le pilote mesure avant qu'on dimensionne quoi que ce soit

`--pilot` joue quelques cellules et imprime le débit réel. Le volume de la
campagne se lit dessus, jamais sur une extrapolation (`CLAUDE.md`, règle 3).

## Le contrôle qui vérifie la prémisse au lieu de la croire

`--check-dependencies` recalcule des cellules avec les cases **non encore
calculées** remplies de 0, puis de 1. Si la prémisse ci-dessus est vraie, les
deux passes rendent exactement le même nombre : aucune case non calculée n'a
été lue. Si elles diffèrent, la programmation dynamique est fausse et tout ce
qui suit l'est aussi.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import met  # noqa: E402
from gammonnet.arena import derive_seed  # noqa: E402
from gammonnet.cubeful import GammonNetCubePlayer, play_cubeful_game  # noqa: E402

MAX_AWAY = met.MAX_AWAY

#: L'état partagé d'un ouvrier : le joueur, et la table qu'il consulte.
_PLAYER = None


def _install(ply: int, cube_ply: int, model: str, prune_k: int,
             pre: list[list[float]], post: list[float], name: str) -> None:
    """Armer un ouvrier : la table d'abord, le joueur ensuite.

    La table est installée **avant** que le joueur charge quoi que ce soit, et
    elle est relue par les accesseurs du C pour que l'ouvrier refuse de
    travailler contre une table qu'il n'a pas vraiment reçue.
    """
    global _PLAYER
    met.set_table(pre, post, name)
    if met.table_name() != name:
        raise RuntimeError(f"table non installée : {met.table_name()!r}")
    _PLAYER = GammonNetCubePlayer(ply=ply, cube_ply=cube_ply, model=model,
                                  prune_k=prune_k,
                                  prune_model="models/prune_32.bin" if prune_k else "")


def _play_one(payload):
    """Une partie au score. Rend les points nets du siège WHITE."""
    away_white, away_black, crawford, seed = payload
    dice = random.Random(seed)
    white_rng = random.Random(seed ^ 0x5741_4954)
    black_rng = random.Random(seed ^ 0x424C_4143)
    result = play_cubeful_game(_PLAYER, _PLAYER, dice, white_rng, black_rng,
                               jacoby=False,
                               match=(away_white, away_black, crawford))
    return result.points, result.stalled


class Table:
    """La table en construction. `None` = pas encore calculée.

    Elle sert deux choses : garder les cellules produites, et **fabriquer la
    table que les ouvriers consultent** — où les cases non calculées portent une
    valeur de remplissage dont le contrôle de dépendance prouve qu'elle n'est
    jamais lue.
    """

    def __init__(self):
        self.pre = [[None] * MAX_AWAY for _ in range(MAX_AWAY)]
        self.post = [None] * MAX_AWAY
        self.error = {}

    def snapshot(self, filler: float) -> tuple[list[list[float]], list[float]]:
        pre = [[filler if cell is None else cell for cell in row]
               for row in self.pre]
        post = [filler if cell is None else cell for cell in self.post]
        return pre, post

    def pre_at(self, away_a: int, away_b: int) -> float:
        """`PRE[a][b]`, en se servant de l'antisymétrie pour la moitié basse."""
        value = self.pre[away_a - 1][away_b - 1]
        if value is None:
            mirror = self.pre[away_b - 1][away_a - 1]
            if mirror is None:
                raise KeyError(f"PRE[{away_a}][{away_b}] pas encore calculée")
            return 1.0 - mirror
        return value


def value_after(table: Table, away_white: int, away_black: int,
                points: int, post_crawford_now: bool) -> float:
    """Ce que vaut, pour WHITE, une partie qui rapporte `points` à un camp.

    `points` est signé : positif si WHITE marque. `post_crawford_now` dit si la
    partie qui vient de finir était la partie de Crawford — auquel cas la suite
    du match est d'après-Crawford.
    """
    if points > 0:
        if points >= away_white:
            return 1.0
        left = away_white - points
        if post_crawford_now or away_black == 1:
            # WHITE poursuit, le meneur est à 1-away, Crawford est derrière.
            return table.post[left - 1]
        return table.pre_at(left, away_black)

    if points < 0:
        gained = -points
        if gained >= away_black:
            return 0.0
        left = away_black - gained
        if post_crawford_now or away_white == 1:
            # BLACK poursuit : `post` donne SA chance, WHITE a le complément.
            return 1.0 - table.post[left - 1]
        return table.pre_at(away_white, left)

    raise ValueError("une partie ne rapporte jamais zéro point")


def measure_cell(pool, table: Table, away_white: int, away_black: int,
                 crawford: bool, games: int, seed: int, key: str):
    """Jouer une cellule et rendre (valeur, erreur-type, parties bloquées)."""
    payloads = [(away_white, away_black, crawford,
                 derive_seed(seed, key, index)) for index in range(games)]
    values = []
    stalled = 0
    for points, was_stalled in pool.imap_unordered(_play_one, payloads,
                                                   chunksize=64):
        stalled += int(was_stalled)
        values.append(value_after(table, away_white, away_black, points,
                                  post_crawford_now=crawford))

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / max(len(values) - 1, 1)
    return mean, math.sqrt(variance / len(values)), stalled


def cells_in_order(max_away: int, mirror: bool = False):
    """Les cellules, dans l'ordre où leurs dépendances sont prêtes.

    `mirror` mesure la **moitié basse** (`a >= b`) et déduit la haute, au lieu
    de l'inverse. Les deux passes remplissent la même table ; ce qui change est
    laquelle des deux orientations est mesurée et laquelle est déduite. Les
    confronter est la seule façon de vérifier l'antisymétrie sans l'imposer —
    une passe unique la retrouverait par construction.
    """
    for n in range(1, max_away + 1):
        yield ("post", n, 1)
    for total in range(2, 2 * max_away + 1):
        for a in range(1, max_away + 1):
            b = total - a
            if 1 <= b <= max_away and (a >= b if mirror else a <= b):
                yield ("pre", a, b)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=2000,
                        help="parties par cellule")
    parser.add_argument("--games-far", type=int, default=0,
                        help="parties par cellule au-delà de --near "
                             "(0 = même volume partout)")
    parser.add_argument("--near", type=int, default=10,
                        help="seuil sur a+b séparant les cellules consultées "
                             "souvent des autres")
    parser.add_argument("--max-away", type=int, default=MAX_AWAY)
    parser.add_argument("--ply", type=int, default=0)
    parser.add_argument("--cube-ply", type=int, default=0)
    parser.add_argument("--prune-k", type=int, default=0)
    parser.add_argument("--model", default="models/cubeless_prob5_512_512_256_128.bin")
    parser.add_argument("--workers", type=int, default=28)
    parser.add_argument("--seed", type=int, default=20260917)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--table-out", type=Path, default=None,
                        help="fichier GNMET1 à écrire")
    parser.add_argument("--name", default="gammonnet-t97")
    parser.add_argument("--mirror", action="store_true",
                        help="mesurer la moitié basse et déduire la haute — "
                             "le contrôle d'antisymétrie")
    parser.add_argument("--pilot", type=int, default=0,
                        help="ne calculer que les N premières cellules")
    parser.add_argument("--check-dependencies", type=int, default=0,
                        help="recalculer N cellules avec les cases non "
                             "calculées à 0 puis à 1")
    args = parser.parse_args()

    table = Table()
    todo = list(cells_in_order(args.max_away, mirror=args.mirror))
    if args.pilot:
        todo = todo[:args.pilot]

    started = time.time()
    games_played = 0
    stalled_total = 0

    print(f"T97 — {len(todo)} cellules, {args.games} parties par cellule "
          f"({args.games_far or args.games} au-delà de a+b={args.near}), "
          f"{args.workers} ouvriers, profondeur {args.ply} "
          f"(videau {args.cube_ply})", flush=True)

    for index, (kind, a, b) in enumerate(todo):
        games = args.games
        if args.games_far and a + b > args.near:
            games = args.games_far

        if kind == "post":
            away_white, away_black, crawford = a, 1, False
        else:
            away_white, away_black = a, b
            crawford = (min(a, b) == 1)

        fillers = [0.0]
        if args.check_dependencies and index < args.check_dependencies:
            fillers = [0.0, 1.0]

        results = []
        for filler in fillers:
            pre, post = table.snapshot(filler)
            with mp.Pool(args.workers, initializer=_install,
                         initargs=(args.ply, args.cube_ply, args.model,
                                   args.prune_k, pre, post,
                                   f"{args.name}-partielle")) as pool:
                results.append(measure_cell(pool, table, away_white,
                                            away_black, crawford, games,
                                            args.seed, f"{kind}-{a}-{b}"))

        if len(results) == 2 and results[0][0] != results[1][0]:
            print(f"  ✗ {kind}[{a}][{b}] : remplissage 0 → {results[0][0]}, "
                  f"remplissage 1 → {results[1][0]} — une case non calculée "
                  f"est lue, la programmation dynamique est fausse")
            return 2

        value, error, stalled = results[0]
        games_played += games * len(fillers)
        stalled_total += stalled

        if kind == "post":
            table.post[a - 1] = value
            table.error[f"post-{a}"] = error
        else:
            table.pre[a - 1][b - 1] = value
            table.pre[b - 1][a - 1] = 1.0 - value
            table.error[f"pre-{a}-{b}"] = error

        elapsed = time.time() - started
        rate = games_played / elapsed
        print(f"  [{index + 1}/{len(todo)}] {kind}[{a}][{b}] = {value:.5f} "
              f"± {error:.5f}   {rate:.0f} parties/s", flush=True)

    elapsed = time.time() - started
    print(f"\n{games_played} parties en {elapsed:.0f} s "
          f"({games_played / elapsed:.0f} parties/s), "
          f"{stalled_total} bloquées")

    report = {
        "name": args.name,
        "seed": args.seed,
        "games_per_cell": args.games,
        "games_per_cell_far": args.games_far or args.games,
        "near": args.near,
        "ply": args.ply,
        "cube_ply": args.cube_ply,
        "prune_k": args.prune_k,
        "model": args.model,
        "max_away": args.max_away,
        "mirror": args.mirror,
        "cells": len(todo),
        "games": games_played,
        "seconds": elapsed,
        "stalled": stalled_total,
        "pre": table.pre,
        "post": table.post,
        "stderr": table.error,
    }

    if args.out:
        args.out.write_text(json.dumps(report, indent=1) + "\n")
        print(f"→ {args.out}")

    if args.table_out and all(cell is not None for cell in table.post) and \
            all(cell is not None for row in table.pre for cell in row):
        met.write_table(args.table_out, table.pre, table.post, args.name)
        print(f"→ {args.table_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
