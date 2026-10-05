#!/usr/bin/env python3
"""T92 étape 2 — ce qu'une décision coûte, de chaque côté, sur la même machine.

Ce banc ne dit rien de la force. Il dit **combien de temps** chaque moteur met à
rendre une décision de coup, à chaque niveau qu'il expose, sur les mêmes
positions et la même machine. C'est le chiffre qui dimensionne tout le reste :
une campagne de 10 000 décisions est une affaire d'heures ou de semaines selon
ce qu'il rend.

## Les niveaux ne portent pas le même nom des deux côtés

Vérifié dans la source du moteur tiers (`gnubg.py`, `GnuBgAnalyzer.__init__` :
`eval_level_str = f"{n_plies + 1}-ply"`, avec le commentaire « Display label uses
our XG convention (1-ply = raw NN) ») :

| là-bas | ici, et chez GNU Backgammon |
|---|---|
| `1ply` | 0-ply — réseau brut sur chaque candidat |
| `2ply` | 1-ply |
| `3ply` | **2-ply** — le niveau publié de ce dépôt |
| `4ply` | 3-ply |

Comparer notre 2-ply à leur `2ply` comparerait deux profondeurs différentes et
rendrait un verdict faux dans le sens qui nous arrange. Les paires de ce banc
sont donc appariées sur la **profondeur réelle**, jamais sur l'étiquette.

## Une mesure de temps exige une machine au repos

`CLAUDE.md` règle 3, et la mémoire du projet : sous charge, tout chiffre de
temps est faux d'un facteur variable, sans en avoir l'air. Ce banc refuse de
rendre un temps si la charge dépasse `--max-load` au démarrage.

Usage :
    python bench/cost_per_decision_sage.py --positions 40 --out docs/mesures/t92-cout.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.rules import BLACK, WHITE, Position  # noqa: E402
from gammonnet.sage_board import to_sage  # noqa: E402

SEED = 20260907


@dataclass(frozen=True)
class _AdHocLevel:
    """Un niveau non canonique, pour la seule décomposition de T93."""

    name: str
    ply: int
    filter: tuple[int, ...]
    prune_k: int


#: Nos niveaux, par profondeur réelle. `prune_k` vient de la table canonique C.
OURS = ("instant", "normal", "thorough")

#: Les leurs, avec la profondeur réelle que porte chaque étiquette.
THEIRS = {"1ply": 0, "2ply": 1, "3ply": 2, "4ply": 3, "truncated1": None}


def sample_positions(seed: int, count: int) -> list[tuple[Position, int, int]]:
    """Positions atteintes par notre moteur 0-ply contre lui-même.

    Le tirage par coups au hasard du contrôle de pont ne convient pas ici : il
    produit des plateaux qu'aucune partie sérieuse n'atteint, et le coût d'une
    décision dépend du nombre de coups légaux, donc de la position. On veut le
    coût sur ce qu'un moteur rencontre vraiment.
    """
    from gammonnet.search import SearchConfig, best_play
    from gammonnet.infer import Network

    net = Network.load(ROOT / "models" / "cubeless_prob5_512_512_256_128.bin")
    rng = random.Random(seed)
    out: list[tuple[Position, int, int]] = []
    config = SearchConfig(ply=0)
    while len(out) < count:
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()
        for _ in range(120):
            d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
            if position.legal_plays(d1, d2):
                out.append((position, d1, d2))
                if len(out) >= count:
                    break
            candidate = best_play(net, position, d1, d2, config)
            position = candidate.play.result if candidate else position.swapped_turn()
            if position.is_over():
                break
    return out[:count]


def time_ours(items, level_name: str) -> dict:
    """Un niveau canonique nommé, ou `ply<N>` — la configuration de `bench/pr.py`.

    `ply1` n'a pas de forme canonique parce qu'il n'est servi à personne ; il
    existe ici parce que la décomposition de T93 en a besoin, et il reprend
    exactement la configuration dont T3E a publié le PR (1-ply **non filtré** :
    avec `filter[1] = 1` la passe profonde ne rescore qu'un candidat et le coup
    choisi reste celui du 0-ply).
    """
    from gammonnet.infer import Network
    from gammonnet.search import SearchConfig, best_play, search_level

    net = Network.load(ROOT / "models" / "cubeless_prob5_512_512_256_128.bin")

    if level_name.startswith("ply"):
        ply = int(level_name[3:])
        filters = {0: (), 1: (), 2: (0, 1, 3)}
        level = _AdHocLevel(name=level_name, ply=ply, filter=filters[ply],
                            prune_k=12 if ply >= 2 else 0)
    else:
        level = search_level(level_name)

    prune = None
    if level.prune_k:
        prune = Network.load(ROOT / "models" / "prune_32.bin")
    config = SearchConfig(
        ply=level.ply, filter=level.filter, prune_net=prune, prune_k=level.prune_k
    )

    times = []
    for position, d1, d2 in items:
        start = time.perf_counter()
        best_play(net, position, d1, d2, config)
        times.append(time.perf_counter() - start)
    return _summary(times, {"level": level_name, "ply": level.ply,
                            "filter": list(level.filter), "prune_k": level.prune_k})


def time_theirs(items, level: str, threads: int) -> dict:
    import bgsage

    analyzer = bgsage.BgBotAnalyzer(eval_level=level, parallel_threads=threads)
    times = []
    for position, d1, d2 in items:
        board = to_sage(position)
        start = time.perf_counter()
        analyzer.checker_play(board, d1, d2)
        times.append(time.perf_counter() - start)
    return _summary(times, {"level": level, "ply": THEIRS[level], "threads": threads})


def _summary(times: list[float], extra: dict) -> dict:
    ordered = sorted(times)
    return {
        **extra,
        "decisions": len(times),
        "mean_s": statistics.fmean(times),
        "median_s": statistics.median(times),
        "p90_s": ordered[int(0.9 * (len(ordered) - 1))],
        "total_s": sum(times),
    }


def load_average() -> float:
    return os.getloadavg()[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=40)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--max-load", type=float, default=2.0,
                        help="refuse de mesurer au-dessus de cette charge (règle 3)")
    parser.add_argument("--levels-theirs", default="1ply,2ply,3ply,truncated1")
    parser.add_argument("--levels-ours", default=",".join(OURS))
    parser.add_argument("--threads", type=int, default=1,
                        help="fils du moteur tiers ; 1 pour un coût par cœur comparable")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    load = load_average()
    if load > args.max_load:
        print(
            f"REFUS — charge {load:.2f} > {args.max_load}. Un temps mesuré sous charge "
            "est faux d'un facteur variable et n'en a pas l'air (CLAUDE.md règle 3)."
        )
        return 2

    items = sample_positions(args.seed, args.positions)
    legal = [len(p.legal_plays(d1, d2)) for p, d1, d2 in items]

    report = {
        "seed": args.seed,
        "positions": len(items),
        "load_at_start": load,
        "machine": platform.node(),
        "cpu_count": os.cpu_count(),
        "legal_plays_mean": statistics.fmean(legal),
        "ours": [],
        "theirs": [],
    }

    for name in args.levels_ours.split(","):
        row = time_ours(items, name)
        report["ours"].append(row)
        print(f"ours   {name:10s} ply={row['ply']} "
              f"médiane {row['median_s']*1000:9.2f} ms  moyenne {row['mean_s']*1000:9.2f} ms")

    for name in args.levels_theirs.split(","):
        row = time_theirs(items, name, args.threads)
        report["theirs"].append(row)
        ply = "rollout" if row["ply"] is None else row["ply"]
        print(f"theirs {name:10s} ply={ply} "
              f"médiane {row['median_s']*1000:9.2f} ms  moyenne {row['mean_s']*1000:9.2f} ms")

    report["load_at_end"] = load_average()
    if args.out:
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
