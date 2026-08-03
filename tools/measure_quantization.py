#!/usr/bin/env python3
"""Ce que la quantification coûte **en jeu**, et non en erreur quadratique.

## La métrique, et pourquoi ce n'est pas celle qu'on cite d'habitude

On mesure d'ordinaire l'erreur sur les sorties du réseau. C'est la mauvaise
grandeur. Une erreur qui décale **tous** les coups candidats de la même quantité
ne change aucun classement et ne coûte rien ; une erreur qui n'en décale qu'un
coûte exactement la différence d'équité entre les deux. Deux réseaux peuvent
avoir la même erreur quadratique et des taux d'erreur très différents.

Ce qui compte pour une analyse est donc :

1. **le taux de désaccord** — à quelle fréquence le modèle quantifié choisit un
   autre coup ;
2. **l'équité perdue quand il y a désaccord**, jugée par le modèle **de
   référence**, qui fait ici office de vérité.

Le produit des deux est l'équité perdue par décision, dans l'unité même où se
comptent les écarts entre moteurs — ce qui permet de la comparer au bruit plutôt
que de la déclarer « faible ».

C'est le protocole que `PLAN.md` définit déjà pour T31, appliqué à un autre
arbitrage : *« le taux de désaccord avec le 2-ply non filtré, et l'équité
moyenne perdue quand il y a désaccord »*.

    python tools/measure_quantization.py [--positions 300]
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import Position  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.search import ROLLS, SearchConfig, search_plays  # noqa: E402

SEED = 20260803
REFERENCE = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
QUANTIZED = ROOT / "models" / "cubeless_prob5_512_512_256_128-q8.bin"


def _tested(name: str | None) -> Path:
    """Le modèle mis à l'épreuve. Par défaut celui d'int8."""
    return Path(name) if name else QUANTIZED


def build_corpus(size: int) -> list[Position]:
    rng = random.Random(SEED)
    positions: list[Position] = []
    while len(positions) < size:
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()
        for _ in range(80):
            if position.is_over() or len(positions) >= size:
                break
            positions.append(position)
            plays = position.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
            position = rng.choice(plays).result if plays else position.swapped_turn()
    return positions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=300)
    parser.add_argument("--model", default=None, help="modèle à éprouver")
    args = parser.parse_args()

    tested_path = _tested(args.model)
    if not tested_path.is_file():
        print(f"{tested_path} absent — lancer `python tools/quantize_model.py`",
              file=sys.stderr)
        return 1

    corpus = build_corpus(args.positions)
    config = SearchConfig(ply=0)

    print(f"éprouvé : {tested_path.name}")
    with Network.load(REFERENCE) as truth, Network.load(tested_path) as tested:
        equity_gaps: list[float] = []   # écart d'équité sur la MEME position
        losses: list[float] = []        # équité perdue quand les coups diffèrent
        decisions = 0
        disagreements = 0

        for position in corpus:
            # 1. L'écart d'évaluation, position par position.
            a = truth.evaluate(position)
            b = tested.evaluate(position)
            equity_gaps.append(abs(a.money_equity - b.money_equity))

            # 2. Le désaccord de coup, et ce qu'il coûte.
            for d1, d2, _ in ROLLS:
                ranked = search_plays(truth, position, d1, d2, config)
                if len(ranked) < 2:
                    continue  # un seul coup : rien à décider
                decisions += 1

                chosen = search_plays(tested, position, d1, d2, config)[0]
                if chosen.result == ranked[0].result:
                    continue

                disagreements += 1
                # Jugé par la vérité : ce que vaut le coup choisi, contre ce que
                # valait le meilleur. Toujours <= 0 pour le coup choisi.
                by_result = {c.result: c.equity for c in ranked}
                losses.append(ranked[0].equity - by_result[chosen.result])

    print(f"corpus                          {len(corpus)} positions, "
          f"{decisions:,} décisions")
    print()
    print("── L'écart d'évaluation (la mauvaise métrique, pour mémoire) ──")
    print(f"  écart d'équité moyen          {statistics.fmean(equity_gaps):.6f}")
    print(f"  écart d'équité médian         {statistics.median(equity_gaps):.6f}")
    print(f"  écart d'équité maximal        {max(equity_gaps):.6f}")
    print()
    print("── Ce qui compte : le jeu ──")
    rate = disagreements / decisions if decisions else 0.0
    print(f"  taux de désaccord de coup     {rate * 100:.3f} %  "
          f"({disagreements:,} / {decisions:,})")
    if losses:
        print(f"  équité perdue, moyenne        {statistics.fmean(losses):.6f}")
        print(f"  équité perdue, médiane        {statistics.median(losses):.6f}")
        print(f"  équité perdue, maximale       {max(losses):.6f}")
        print()
        print(f"  ➜ équité perdue par décision  {rate * statistics.fmean(losses):.6f}")
    else:
        print("  aucun désaccord")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
