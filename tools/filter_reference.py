#!/usr/bin/env python3
"""T31 — produit la référence **2-ply non filtrée**, la moitié coûteuse.

## Pourquoi ce fichier existe, et ce qu'il permet de ne pas refaire

Chiffrer ce qu'un filtre coûte suppose de savoir ce qu'aurait choisi une
recherche **sans filtre**, et ce qu'aurait valu chaque autre coup. C'est
l'opération chère du projet : environ **1 812 000 évaluations par décision**,
soit ~5,1 s sur les 32 fils de `mochy` et ~2 min sur la machine de bureau.

La ruse est de ne pas stocker seulement le meilleur coup, mais **le classement
complet avec les équités**. Une fois ce fichier produit, **n'importe quelle
configuration de filtre se mesure sans jamais relancer la référence** : on fait
tourner la recherche filtrée, on regarde quel coup elle choisit, et on lit dans
le fichier ce que ce coup valait vraiment. Une génération, autant d'arbitrages
qu'on veut.

## Reprise

Le fichier est écrit **ligne par ligne, vidé à chaque décision**. Un travail de
plusieurs heures interrompu ne recommence pas de zéro : relancer avec le même
`--out` reprend là où il s'était arrêté. Sur une tâche qui se compte en heures,
la reprise n'est pas un confort — c'est ce qui distingue une mesure d'un pari.

## Le corpus

Marche aléatoire à graine fixe, **les deux couleurs au trait**, positions
terminales exclues. Délibérément **pas** la position d'ouverture : le rapport de
T30 note qu'un filtre y paraît toujours gratuit, parce qu'aucun coup n'y est
disputé. C'est la même leçon que T02 tire pour l'orientation.

Les décisions à **un seul coup légal** sont écartées : il n'y a rien à filtrer,
et les compter diluerait le taux de désaccord vers zéro sans rien mesurer.

    python tools/filter_reference.py --decisions 2000
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import Position, codec  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.search import (  # noqa: E402
    ROLLS, SearchConfig, evaluations, reset_evaluations, search_plays,
)

SEED = 20260803
MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
DEFAULT_OUT = ROOT / "build" / "filter_reference.jsonl"


def decisions(count: int):
    """Suite déterministe de décisions `(position, d1, d2)`.

    Déterministe au sens fort : la n-ième décision est la même quel que soit le
    nombre demandé. C'est ce qui rend la reprise possible — on saute les
    premières sans avoir à les recalculer.
    """
    rng = random.Random(SEED)
    produced = 0

    while produced < count:
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()

        for _ in range(80):
            if position.is_over() or produced >= count:
                break

            d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
            plays = position.legal_plays(d1, d2)
            if len(plays) > 1:
                yield position, d1, d2
                produced += 1
            position = rng.choice(plays).result if plays else position.swapped_turn()


def already_done(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open() as handle:
        return sum(1 for _ in handle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=int, default=2000)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--ply", type=int, default=2,
        help="profondeur de la référence (2 par défaut ; 1 pour une mise au "
             "point rapide, en sachant que ce n'est alors plus la référence)",
    )
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    done = already_done(args.out)
    if done >= args.decisions:
        print(f"{args.out} contient déjà {done} décisions — rien à faire")
        return 0
    if done:
        print(f"reprise : {done} décisions déjà écrites")

    config = SearchConfig(ply=args.ply)   # aucun filtre : c'est la référence
    started = time.perf_counter()

    with Network.load(MODEL) as net, args.out.open("a") as handle:
        for index, (position, d1, d2) in enumerate(decisions(args.decisions)):
            if index < done:
                continue

            reset_evaluations()
            began = time.perf_counter()
            ranked = search_plays(net, position, d1, d2, config)
            elapsed = time.perf_counter() - began

            handle.write(json.dumps({
                "position_id": codec.position_id(position),
                "turn": position.turn,
                "dice": [d1, d2],
                "ply": args.ply,
                "candidates": [
                    {"result_id": codec.position_id(c.result),
                     "result_turn": c.result.turn,
                     "equity": c.equity}
                    for c in ranked
                ],
                "evaluations": evaluations(),
                "seconds": round(elapsed, 3),
            }) + "\n")
            handle.flush()   # la reprise vaut ce que vaut ce flush

            elapsed_total = time.perf_counter() - started
            written = index + 1 - done
            remaining = (args.decisions - index - 1) * elapsed_total / max(written, 1)
            print(f"\r{index + 1}/{args.decisions}  "
                  f"{elapsed:.1f} s/décision  "
                  f"reste ~{remaining / 60:.0f} min", end="", flush=True)

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
