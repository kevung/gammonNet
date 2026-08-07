#!/usr/bin/env python3
"""Ce que coûte la garde INTÉRIEURE du filtre — la mesure qui manquait.

## Pourquoi elle manque, et pourquoi elle pèse

T31 a mesuré la qualité du filtre à la **racine** : sa référence était un 2-ply
dont l'intérieur n'était pas filtré, et sa conclusion — « la garde 5 ne coûte
aucun désaccord » — ne porte que sur la racine.

Mais un 2-ply jouable en volume a besoin d'une garde **intérieure**, et c'est
elle qui fait tout le travail de compression : d'après `bench/cost_by_depth.py`,
passer de la garde intérieure 5 à la garde 1 fait tomber le coût d'une décision
de 41,5 s à 3,3 s. **Cette garde n'a jamais été mesurée en qualité.**

T36 s'en est trouvé bloqué : son 2-ply utilise la garde intérieure 1, et une part
inconnue de l'érosion mesurée peut lui revenir plutôt qu'au réseau. Tant que
cette part n'est pas connue, la ligne 2-ply de T36 est une **borne inférieure**
de notre force et non notre force.

## Le principe

Le même corpus, le même arbitre, et une seule chose qui change :

    serré  = 2-ply, garde intérieure 1   (ce que T36 a employé)
    large  = 2-ply, garde intérieure k   (k > 1)

Quand les deux choisissent le même coup, le filtre n'a rien coûté sur cette
décision — zéro, et c'est vrai. Sinon on arbitre par rollout à dés communs, et
la différence est ce que le resserrement a coûté.

**La comparaison est entre nous et nous.** Aucun biais d'arbitre ne s'y glisse :
notre rollout favorise notre réseau, mais il favorise les deux variantes de la
même façon, puisque c'est le même réseau des deux côtés. C'est la mesure la plus
propre de toute cette série.

Usage :
    python bench/filter_cost_inner.py --decisions 800 --wide 5 --workers 26
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.infer import Network  # noqa: E402
from gammonnet.rollout import RolloutConfig, rollout_difference  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

sys.path.insert(0, str(ROOT / "bench"))
from decision_loss import corpus  # noqa: E402

PROGRESS = Path(os.environ.get("T36_PROGRESS", "/tmp/filter-inner-progress.log"))


def measure(payload):
    model, tight, wide, trials, truncate, seed, cases = payload

    network = Network.load(model)
    tight_config = SearchConfig(ply=2, filter=(0, tight, 5))
    wide_config = SearchConfig(ply=2, filter=(0, wide, 5))

    losses, disagreements = [], 0
    for index, (position, d1, d2) in enumerate(cases):
        ranked_tight = search_plays(network, position, d1, d2, tight_config)
        ranked_wide = search_plays(network, position, d1, d2, wide_config)
        if not ranked_tight or not ranked_wide:
            continue

        a, b = ranked_tight[0].play, ranked_wide[0].play
        if a.result == b.result:
            losses.append(0.0)
        else:
            disagreements += 1
            config = RolloutConfig(trials=trials, truncate=truncate,
                                   seed=seed + index, policy=SearchConfig(ply=0))
            # `serré - large`, du point de vue de celui qui joue. Négatif veut
            # dire que le resserrement a coûté de l'équité.
            difference, _ = rollout_difference(network, a.result, b.result, config)
            losses.append(difference)

        with open(PROGRESS, "a") as fh:
            fh.write("x\n")

    return losses, disagreements


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    import numpy as np

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--decisions", type=int, default=800)
    parser.add_argument("--tight", type=int, default=1, help="garde intérieure serrée")
    parser.add_argument("--wide", type=int, default=5, help="garde intérieure large")
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--trials", type=int, default=648)
    parser.add_argument("--truncate", type=int, default=11)
    parser.add_argument("--seed", type=int, default=20260807)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    model = str(ROOT / "models" / "cubeless_prob5_512_512_256_128.bin")
    network = Network.load(model)

    print("Coût de la garde intérieure du filtre — nous contre nous")
    print(f"  serré = 2-ply garde {args.tight}   contre   "
          f"large = 2-ply garde {args.wide}")
    print(f"  {args.decisions} décisions de contact, graine {args.seed}, "
          f"{args.workers} processus")
    print(f"  suivi : {PROGRESS}", flush=True)

    cases = corpus(args.decisions, args.seed, network)
    print(f"  corpus : {len(cases)} positions\n", flush=True)

    workers = max(1, min(args.workers, len(cases)))
    chunks = [cases[i::workers] for i in range(workers)]
    payloads = [(model, args.tight, args.wide, args.trials, args.truncate,
                 args.seed + 7919 * i, chunk)
                for i, chunk in enumerate(chunks) if chunk]

    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
        gathered = list(pool.map(measure, payloads))
    elapsed = time.perf_counter() - start

    losses, disagreements = [], 0
    for part, count in gathered:
        losses.extend(part)
        disagreements += count

    array = np.asarray(losses, dtype=float)
    n = len(array)
    generator = np.random.default_rng(args.seed)
    draws = generator.integers(0, n, size=(args.bootstrap, n))
    means = np.sort(array[draws].mean(axis=1))
    low = float(means[int(0.025 * args.bootstrap)])
    high = float(means[int(0.975 * args.bootstrap) - 1])

    wrong = array[array != 0.0]
    print(f"décisions              : {n}")
    print(f"le resserrement change : {disagreements / n * 100:.1f} % des coups")
    print(f"équité par décision    : {array.mean():+.5f} "
          f"[{low:+.5f} ; {high:+.5f}]")
    if len(wrong):
        print(f"quand il change        : {wrong.mean():+.5f} "
              f"(pire {wrong.min():+.4f})")
    print(f"\n{n} décisions en {elapsed / 60:.1f} min sur {args.workers} processus")

    print("\nLecture. NÉGATIF veut dire que la garde serrée coûte de l'équité —")
    print("c'est-à-dire que la ligne 2-ply de T36 sous-estime notre force, et de")
    print("combien. La comparaison est entre nous et nous : le biais de l'arbitre")
    print("s'applique identiquement aux deux variantes et ne peut pas la fausser.")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "tight": args.tight, "wide": args.wide, "decisions": n,
            "disagreement_rate": disagreements / n,
            "mean": float(array.mean()), "ci95": [low, high],
            "mean_when_changed": float(wrong.mean()) if len(wrong) else 0.0,
            "trials": args.trials, "truncate": args.truncate,
            "seed": args.seed, "elapsed_seconds": elapsed,
        }, indent=2) + "\n")
        print(f"\nécrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
