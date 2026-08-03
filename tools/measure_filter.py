#!/usr/bin/env python3
"""T31 — ce qu'un filtre de coups coûte en qualité, et ce qu'il fait gagner.

## Les deux nombres, et pourquoi un seul ne suffit pas

`PLAN.md` est explicite : *« le taux de désaccord avec le 2-ply non filtré, et
l'équité moyenne perdue quand il y a désaccord. Un filtre qui "ne change rien"
n'a pas été mesuré. »*

Les deux comptent, et séparément :

- un filtre peut **changer souvent** de coup pour des broutilles — deux coups
  équivalents, l'ordre importe peu ;
- un filtre peut **changer rarement** mais rater précisément les positions
  décisives.

Leur **produit** est l'équité perdue par décision, dans l'unité même où se
comptent les écarts entre moteurs — ce qui permet de la confronter à ce que T11
a mesuré (+0,0400 ppg contre GNU Backgammon) plutôt que de la déclarer « faible ».

## La référence sert de vérité

`tools/filter_reference.py` a stocké le **classement complet** de la recherche
non filtrée, équités comprises. On n'a donc rien à recalculer de coûteux ici :
on fait tourner la recherche filtrée, on regarde son coup, et on lit ce que ce
coup valait pour la référence.

    python tools/measure_filter.py --filters 1/1 2/1 2/2 4/4 8/2
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import codec  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.search import (  # noqa: E402
    SearchConfig, evaluations, reset_evaluations, search_plays,
)

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
DEFAULT_REFERENCE = ROOT / "build" / "filter_reference.jsonl"

# T11 : l'avantage mesuré du modèle sur GNU Backgammon, dans cet
# environnement. C'est l'échelle à laquelle une perte doit être rapportée.
MEASURED_EDGE_PPG = 0.0400
DECISIONS_PER_GAME = 25


def parse_filter(text: str) -> tuple[int, int]:
    """« top/inner » — le nombre de candidats gardés à chaque niveau."""
    top, inner = text.split("/")
    return int(top), int(inner)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--filters", nargs="+", default=["4/4", "2/2", "2/1", "1/1"])
    parser.add_argument("--limit", type=int, default=0, help="0 = tout le fichier")
    args = parser.parse_args()

    if not args.reference.is_file():
        print(f"{args.reference} absent — lancer d'abord "
              f"`python tools/filter_reference.py`", file=sys.stderr)
        return 1

    reference = [json.loads(line) for line in args.reference.open()]
    if args.limit:
        reference = reference[: args.limit]
    if not reference:
        print("référence vide", file=sys.stderr)
        return 1

    # La profondeur de la référence fait partie de la référence. Comparer une
    # recherche filtrée à 2-ply contre une référence produite à 1-ply ne
    # mesurerait pas un filtre : cela mesurerait un changement de profondeur, et
    # rien dans les chiffres ne le dirait. Refusé, jamais approximé.
    plies = {r.get("ply") for r in reference}
    if plies != {2} and len(plies) == 1 and None not in plies:
        depth = plies.pop()
        print(f"⚠️  référence produite à {depth}-ply : les filtres seront "
              f"évalués à {depth}-ply pour que la comparaison ait un sens")
    elif len(plies) > 1:
        print(f"référence incohérente : profondeurs mêlées {plies}", file=sys.stderr)
        return 1
    elif None in plies:
        print("référence sans profondeur déclarée — la régénérer avec la "
              "version actuelle de `filter_reference.py`", file=sys.stderr)
        return 1
    else:
        depth = 2

    unfiltered_cost = statistics.fmean(r["evaluations"] for r in reference)
    print(f"référence : {len(reference)} décisions à {depth}-ply, "
          f"{unfiltered_cost:,.0f} évaluations/décision en moyenne")
    print()
    print(f"{'filtre':>8s} {'éval/déc':>10s} {'gain':>7s} {'désaccord':>11s} "
          f"{'perte moy.':>11s} {'perte/déc':>11s} {'≈ ppg':>9s}")

    with Network.load(MODEL) as net:
        for text in args.filters:
            top, inner = parse_filter(text)
            config = SearchConfig(ply=depth, filter=(0, inner, top))

            disagreements = 0
            losses: list[float] = []
            total_evaluations = 0
            started = time.perf_counter()

            for record in reference:
                position = codec.position_from_id(record["position_id"], record["turn"])
                d1, d2 = record["dice"]

                reset_evaluations()
                ranked = search_plays(net, position, d1, d2, config)
                total_evaluations += evaluations()
                if not ranked:
                    continue

                chosen = codec.position_id(ranked[0].result)
                best = record["candidates"][0]
                if chosen == best["result_id"]:
                    continue

                disagreements += 1
                # Jugé par la référence : ce que vaut réellement le coup choisi.
                by_id = {c["result_id"]: c["equity"] for c in record["candidates"]}
                if chosen in by_id:
                    losses.append(best["equity"] - by_id[chosen])

            rate = disagreements / len(reference)
            mean_loss = statistics.fmean(losses) if losses else 0.0
            per_decision = rate * mean_loss
            cost = total_evaluations / len(reference)

            print(f"{text:>8s} {cost:10,.0f} "
                  f"{unfiltered_cost / cost:6.1f}× "
                  f"{rate * 100:10.2f}% "
                  f"{mean_loss:11.5f} {per_decision:11.6f} "
                  f"{per_decision * DECISIONS_PER_GAME:9.4f}"
                  f"   ({time.perf_counter() - started:.0f} s)")

    print()
    print(f"« ≈ ppg » = perte par décision × {DECISIONS_PER_GAME} décisions par partie.")
    print(f"À comparer à l'avantage mesuré en T11 : "
          f"+{MEASURED_EDGE_PPG:.4f} ppg contre GNU Backgammon.")
    print("Un filtre dont la perte approche cet ordre de grandeur mange ce que")
    print("la recherche est censée apporter.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
