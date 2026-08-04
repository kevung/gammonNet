#!/usr/bin/env python3
"""T31 — le filtre se comporte-t-il autrement **en match** qu'en money ?

## La réserve à laquelle ce script répond

Le rapport de T31 chiffre le coût du filtre en **money**, et pose sa propre
limite : *« tout ceci est mesuré en money — un filtre devra être revérifié en
match après T32 »*. T32 est faite, la table est branchée dans la recherche
(`SearchConfig.use_match`), et cette vérification devient possible.

**Pourquoi elle n'est pas une formalité.** Un filtre garde les `k` meilleurs
coups d'un pré-tri peu profond. En money, ce pré-tri classe par équité cubeless ;
en match, par équité de match. **Les deux ne classent pas pareil** — à
2-away/2-away un gammon emporte le match, et un coup gammonnant que le pré-tri
money reléguait au sixième rang peut être le bon. Un filtre serré risque donc
d'écarter en match des coups qu'il gardait à raison en money.

## La méthode, et ce qu'elle emprunte

Les **positions et les dés** viennent de la référence de T31 — les mêmes 121
décisions, pour que les deux mesures parlent des mêmes situations. Ce qui ne
peut pas être réutilisé, ce sont ses **équités** : elles sont en money, et c'est
tout le sujet.

La profondeur retenue est **1-ply**, pas 2. Un 2-ply non filtré coûte ~3,8 M
évaluations par décision — 121 d'entre elles représentent des heures sur cette
machine, et c'est un travail pour `mochy`. Le 1-ply en coûte 7 475, soit une
minute pour tout le corpus, et il répond déjà à la question posée : **le
pré-tri classe-t-il autrement quand le score entre en jeu ?** Le mécanisme du
filtre est le même aux deux profondeurs.

**C'est donc un indicateur, pas la mesure finale.** Le dire est le sujet même de
ce fichier.

    python bench/filter_in_match.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import codec  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
REFERENCE = ROOT / "docs" / "mesures" / "t31-reference-2ply.jsonl"

# Les scores où le filtre a le plus de raisons de se comporter autrement.
# 2-away/2-away est celui où les gammons pèsent le plus ; 25/25 est le témoin,
# censé retrouver le money. Sans ce témoin, un écart mesuré ne se distinguerait
# pas d'un bug.
SCORES = [
    ("money", None),
    ("2-away / 2-away", MatchState(away_on_roll=2, away_opponent=2)),
    ("4-away / 2-away", MatchState(away_on_roll=4, away_opponent=2)),
    ("2-away / 4-away", MatchState(away_on_roll=2, away_opponent=4)),
    ("25 / 25 (témoin)", MatchState(away_on_roll=25, away_opponent=25)),
]

KEEPS = (1, 3, 5)
PLY = 1


def configs(state, keep):
    """Non filtré et filtré, au même score et à la même profondeur."""
    if state is None:
        return (SearchConfig(ply=PLY),
                SearchConfig(ply=PLY, filter=(0, keep)))
    return (SearchConfig(ply=PLY, use_match=True, match=state),
            SearchConfig(ply=PLY, use_match=True, match=state, filter=(0, keep)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=REFERENCE)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if not args.reference.is_file():
        print(f"{args.reference} absent", file=sys.stderr)
        return 1

    decisions = [json.loads(line) for line in args.reference.open()]
    if args.limit:
        decisions = decisions[: args.limit]

    print(f"{len(decisions)} décisions, {PLY}-ply, positions et dés repris de "
          f"{args.reference.name}")
    print(f"\n{'score':>18s} {'garde':>6s} {'désaccord':>11s} "
          f"{'perte moyenne':>14s} {'perte/décision':>15s}")

    with Network.load(MODEL) as net:
        # Positions décodées une fois pour toutes.
        boards = [(codec.position_from_id(r["position_id"], r["turn"]), *r["dice"])
                  for r in decisions]

        for label, state in SCORES:
            unfiltered = configs(state, 1)[0]

            # LA VÉRITÉ NE DÉPEND PAS DE LA TAILLE DU FILTRE. La calculer dans
            # la boucle des gardes la referait trois fois pour le même
            # résultat — c'est ce que faisait la première version, et cela
            # triplait le coût de la partie la plus chère.
            truths = []
            for position, d1, d2 in boards:
                ranked = search_plays(net, position, d1, d2, unfiltered)
                truths.append(ranked if len(ranked) >= 2 else None)

            for keep in KEEPS:
                filtered = configs(state, keep)[1]

                disagreements = 0
                losses: list[float] = []
                counted = 0

                for (position, d1, d2), truth in zip(boards, truths):
                    if truth is None:
                        continue
                    counted += 1

                    chosen = search_plays(net, position, d1, d2, filtered)
                    if not chosen or chosen[0].result == truth[0].result:
                        continue

                    disagreements += 1
                    # Jugée par la recherche non filtrée, au MÊME score : c'est
                    # elle la vérité ici, pas la référence money.
                    by_result = {c.result: c.equity for c in truth}
                    if chosen[0].result in by_result:
                        losses.append(truth[0].equity - by_result[chosen[0].result])

                rate = disagreements / counted if counted else 0.0
                mean = statistics.fmean(losses) if losses else 0.0
                print(f"{label:>18s} {keep:>6d} "
                      f"{rate * 100:10.2f}% {mean:14.5f} {rate * mean:15.6f}",
                      flush=True)

    print("\nLa perte est en équité de match (2·MWC − 1) pour les lignes de score,")
    print("et en points pour la ligne money. Les deux échelles ne se comparent")
    print("qu'avec précaution — c'est le TAUX de désaccord qui se lit d'une")
    print("ligne à l'autre.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
