#!/usr/bin/env python3
"""T31, moitié coûteuse — la référence 2-ply **non filtrée**.

Le filtre de coups est ce qui rend le 2-ply praticable, et `PLAN.md` est
catégorique : *un filtre qui « ne change rien » n'a pas été mesuré*. Le mesurer
demande une référence — ce que le 2-ply choisit **sans aucun filtrage** — et
c'est le calcul le plus coûteux de la phase 3.

Ce script produit cette référence et rien d'autre. La comparaison des variantes
filtrées se fait ensuite, à partir du fichier écrit ici, sans refaire le calcul.

Ce qui est enregistré par décision :

* la position et les dés, pour que la comparaison soit rejouable ;
* le **classement complet** des coups, avec leur équité — pas seulement le
  meilleur. Un filtre se juge autant sur l'équité qu'il perd quand il se trompe
  que sur la fréquence de ses erreurs, et cela demande de savoir ce que valait
  le coup qu'il a écarté ;
* le nombre d'évaluations réseau consommées, qui rend le coût mesurable au lieu
  de supposé.

Usage :
    python bench/run_filter_reference.py --probe                # coût par décision
    python bench/run_filter_reference.py --decisions 2000 --workers 20
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import BLACK, WHITE, Position  # noqa: E402
from gammonnet import codec  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
SEED = 20260804

_NETWORK = None


def network():
    """Chargé paresseusement, une fois par processus."""
    global _NETWORK
    if _NETWORK is None:
        from gammonnet.infer import Network

        _NETWORK = Network.load(MODEL)
    return _NETWORK


def decision_points(count: int, seed: int = SEED) -> list[tuple[Position, int, int]]:
    """Des points de décision tirés de parties aléatoires, à graine fixe.

    Une décision par partie et non des plis consécutifs : des positions voisines
    partagent leurs sous-arbres, et une référence bâtie sur elles décrirait une
    charge que personne n'exécute — la même erreur que T03 a trouvée sur le banc
    de l'oracle.

    Les positions sans choix réel sont écartées : un filtre n'a rien à filtrer
    quand il n'y a qu'un seul coup légal.
    """
    rng = random.Random(seed)
    out: list[tuple[Position, int, int]] = []

    while len(out) < count:
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()

        for _ in range(rng.randint(2, 70)):
            if position.is_over():
                break
            plays = position.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
            position = rng.choice(plays).result if plays else position.swapped_turn()

        if position.is_over():
            continue

        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        if len(position.legal_plays(d1, d2)) < 2:
            continue
        out.append((position, d1, d2))

    return out


def evaluate_one(payload):
    """Une décision, en 2-ply non filtré. Renvoie le classement complet."""
    from gammonnet import search

    index, position_id, turn, d1, d2 = payload
    position = codec.position_from_id(position_id, turn)

    config = search.SearchConfig(ply=2, filter=())

    search.reset_evaluations()
    start = time.perf_counter()
    candidates = search.search_plays(network(), position, d1, d2, config)
    elapsed = time.perf_counter() - start
    used = search.evaluations()

    return {
        "index": index,
        "position_id": position_id,
        "turn": turn,
        "dice": [d1, d2],
        "ranking": [
            {"key": codec.position_id(c.play.result), "equity": c.equity}
            for c in candidates
        ],
        "evaluations": used,
        "seconds": elapsed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--probe", action="store_true",
                        help="chronométrer quelques décisions et s'arrêter")
    parser.add_argument("--start", type=int, default=0,
                        help="reprendre à cette décision (le fichier est complété, pas écrasé)")
    parser.add_argument("--out", default="docs/mesures/t31-reference-2ply.jsonl")
    args = parser.parse_args()

    if not MODEL.is_file():
        raise SystemExit(f"{MODEL} absent — lancer `python tools/export_model.py`")

    count = 6 if args.probe else args.decisions
    points = decision_points(count, args.seed)
    payloads = [
        (i, codec.position_id(p), p.turn, d1, d2)
        for i, (p, d1, d2) in enumerate(points)
    ]
    # Reprendre plutôt que refaire. Les points de décision dérivent de la
    # graine et de l'indice, donc la décision numéro `i` est la même à toutes
    # les exécutions : couper le calcul ne perd rien, il suffit de repartir de
    # là. C'est ce qui rend une coupure décidable sur des données plutôt que
    # redoutée comme un gaspillage.
    payloads = payloads[args.start:]

    if args.probe:
        print("Sonde : coût d'une décision 2-ply NON FILTRÉE, un processus")
        total_evals = total_time = 0
        for payload in payloads:
            result = evaluate_one(payload)
            total_evals += result["evaluations"]
            total_time += result["seconds"]
            print(f"  décision {result['index']}: {len(result['ranking']):3d} coups, "
                  f"{result['evaluations']:9,d} évaluations, {result['seconds']:7.2f} s")
        mean_time = total_time / len(payloads)
        print(f"\nmoyenne : {total_evals / len(payloads):,.0f} évaluations, "
              f"{mean_time:.2f} s par décision (1 fil)")
        for workers in (16, 20, 32):
            hours = args.decisions * mean_time / workers / 3600
            print(f"  {args.decisions} décisions sur {workers} processus : "
                  f"{hours:.2f} h" if hours >= 1
                  else f"  {args.decisions} décisions sur {workers} processus : "
                       f"{hours * 60:.0f} min")
        return 0

    print(f"T31 — référence 2-ply NON FILTRÉE")
    print(f"  {count} décisions, graine {args.seed}, {args.workers} processus")
    print(f"  démarré à {time.strftime('%H:%M:%S')}", flush=True)

    started = time.perf_counter()
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    done = args.start
    with out_path.open("a" if args.start else "w") as handle, ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(evaluate_one, payloads, chunksize=1):
            handle.write(json.dumps(result, sort_keys=True) + "\n")
            handle.flush()
            done += 1
            if done % 25 == 0:
                rate = done / (time.perf_counter() - started)
                remaining = (count - done) / rate / 60
                print(f"  {done}/{count} — {rate * 60:.1f} décisions/min, "
                      f"reste ~{remaining:.0f} min", flush=True)

    elapsed = time.perf_counter() - started
    print(f"\n{count} décisions en {elapsed / 60:.1f} min")
    print(f"écrit dans {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
