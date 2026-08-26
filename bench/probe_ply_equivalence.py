#!/usr/bin/env python3
"""Les deux moteurs comptent-ils les plies pareil ? Mesuré, pas supposé.

## Pourquoi la question n'est pas rhétorique

T30 a déjà attrapé exactement cette erreur chez nous : *« Cette formule décrit
un 1-ply, pas un 2-ply : la profondeur était décalée d'un ply. »* Rien ne
garantit qu'un « 3-ply » de gnubg et un « 3-ply » de gammonNet nomment la même
chose, et une comparaison de force à profondeur mal appariée mesurerait le
décalage plutôt que les moteurs.

## L'identité qui tranche, et pourquoi elle ne suppose rien

`gn_search.h` définit la récursion :

    V(pos, k) = SOMME sur les 21 jets de  w(jet) × max sur les coups ( -V(résultat, k-1) )

Elle ne parle que d'un moteur à la fois. On peut donc la poser à **gnubg avec
ses propres évaluations** : si son équité « 1-ply » d'une position vaut la
moyenne pondérée du meilleur `-` son équité « 0-ply » des positions résultantes,
alors son 1-ply énumère un jet adverse — exactement notre définition. Aucune
comparaison entre réseaux n'intervient : chaque moteur est confronté à
lui-même.

Un décalage d'un ply se verrait immédiatement : l'identité tomberait à côté de
plusieurs centièmes d'équité, très au-dessus du bruit d'arrondi.

## La réserve, nommée

À 1 ply, les filtres de coups de gnubg ne peuvent pas changer le résultat : les
coups sont notés au 0-ply et le meilleur est pris, filtré ou non. À 2 plies ils
mordent, et l'identité n'est alors exacte que si l'on reproduit son filtre. La
vérification porte donc sur le pas 0→1, qui est celui où un décalage
d'indexation vivrait.

Usage :
    python bench/probe_ply_equivalence.py --positions 8
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from gammonnet.gnubg_board import to_gnubg  # noqa: E402
from gammonnet.gnubg_engine import GnubgSession  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import Position  # noqa: E402
from gammonnet.search import SearchConfig, position_equity  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
SEED = 20260826

#: `op_eval` rend six flottants par plateau : les cinq probabilités, puis
#: l'équité money cubeless. Sondé, pas supposé.
EQUITY = 5

#: Les 21 jets distincts et leur poids. (1,2) et (2,1) sont le même jet.
ROLLS = tuple((a, b, (1 if a == b else 2) / 36.0)
              for a in range(1, 7) for b in range(a, 7))


def corpus(count: int, seed: int = SEED) -> list[Position]:
    rng = random.Random(seed)
    out: list[Position] = []
    position = Position.initial()
    while len(out) < count:
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = position.legal_plays(d1, d2)
        if len(plays) >= 3:
            out.append(position)
        position = rng.choice(plays).result if plays else position.swapped_turn()
        if position.is_over():
            position = Position.initial()
    return out


def reconstruct_ours(net, position: Position) -> float:
    """V(pos,1) reconstruite depuis nos propres V(.,0)."""
    zero = SearchConfig(ply=0)
    total = 0.0
    for d1, d2, weight in ROLLS:
        plays = position.legal_plays(d1, d2)
        if plays:
            best = max(-position_equity(net, play.result, zero) for play in plays)
        else:
            passed = position.swapped_turn()
            best = -position_equity(net, passed, zero)
        total += weight * best
    return total


def reconstruct_theirs(engine: GnubgSession, position: Position) -> float:
    """V(pos,1) reconstruite depuis les V(.,0) de GNUBG lui-même."""
    total = 0.0
    for d1, d2, weight in ROLLS:
        plays = position.legal_plays(d1, d2)
        if plays:
            boards = [to_gnubg(play.result) for play in plays]
            values = engine.evaluate(boards, plies=0, prune=0)
            best = max(-v[EQUITY] for v in values)
        else:
            passed = position.swapped_turn()
            values = engine.evaluate([to_gnubg(passed)], plies=0, prune=0)
            best = -values[0][EQUITY]
        total += weight * best
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=8)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "docs" / "mesures" / "t3b-ply-equivalence.json")
    args = parser.parse_args()

    net = Network.load(MODEL)
    cases = corpus(args.positions)
    rows = []

    with GnubgSession() as engine:
        print(f"{'':>4} {'nous V(1)':>12} {'reconstruite':>13} {'écart':>11}"
              f"   {'gnubg V(1)':>12} {'reconstruite':>13} {'écart':>11}")
        for index, position in enumerate(cases):
            ours_direct = position_equity(net, position, SearchConfig(ply=1))
            ours_rebuilt = reconstruct_ours(net, position)

            board = to_gnubg(position)
            theirs_direct = engine.evaluate([board], plies=1,
                                             prune=0)[0][EQUITY]
            theirs_rebuilt = reconstruct_theirs(engine, position)

            rows.append({
                "ours_direct": ours_direct, "ours_rebuilt": ours_rebuilt,
                "theirs_direct": theirs_direct, "theirs_rebuilt": theirs_rebuilt,
            })
            print(f"{index:>4} {ours_direct:>12.6f} {ours_rebuilt:>13.6f} "
                  f"{ours_direct - ours_rebuilt:>+11.2e}   "
                  f"{theirs_direct:>12.6f} {theirs_rebuilt:>13.6f} "
                  f"{theirs_direct - theirs_rebuilt:>+11.2e}")

    ours_max = max(abs(r["ours_direct"] - r["ours_rebuilt"]) for r in rows)
    theirs_max = max(abs(r["theirs_direct"] - r["theirs_rebuilt"]) for r in rows)
    print(f"\n  écart maximal, nous  : {ours_max:.3e}")
    print(f"  écart maximal, gnubg : {theirs_max:.3e}")
    verdict = ("Les deux moteurs comptent les plies de la même façon."
               if max(ours_max, theirs_max) < 1e-3
               else "DÉCALAGE : l'identité ne tient pas — voir les écarts.")
    print(f"\n  {verdict}")

    args.out.write_text(json.dumps(
        {"task": "T3B", "probe": "ply numbering equivalence",
         "identity": "V(pos,1) = sum_rolls w * max_plays(-V(result,0))",
         "positions": len(cases), "seed": SEED,
         "max_gap": {"ours": ours_max, "gnubg": theirs_max},
         "rows": rows}, indent=1, ensure_ascii=False))
    print(f"  → {args.out}")
    return 0 if max(ours_max, theirs_max) < 1e-3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
