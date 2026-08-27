#!/usr/bin/env python3
"""T70/T71 — deux moteurs sur le même registre, appariés décision par décision.

## Ce que cet outil règle

`bench/measure_t70.py` note un moteur. Comparer deux notes séparées perdrait
l'appariement : la variance entre décisions écrase de très loin l'écart entre
deux moteurs, et c'est le mode de défaillance que T36 a documenté — vingt-quatre
heures de machine pour rendre ±0,017 quand l'effet vaut 0,02.

Ici la comparaison est **appariée sur la position** : chaque décision rend un
seul nombre, `perte(A) − perte(B)`, et la plupart valent exactement zéro parce
que les deux moteurs ont joué le même coup. Zéro est la bonne valeur, pas une
commodité, et exclure ces décisions gonflerait la moyenne des désaccords.

## L'usage nommé par la fiche : l'étape 0 de T71

> *« Mesurer le professeur avant d'étiqueter en volume. »* — DS-14, la règle d'or

Un élève distillé converge à la force de son maître, quelle que soit la quantité
de données. Avant tout étiquetage massif, il faut donc vérifier que notre 2-ply
distributionnel bat le réseau seul **au ply de jeu** : `--a-ply 2 --b-ply 0`,
z > 3 sur ≥ 10 000 décisions appariées. Si le professeur ne bat pas l'élève, la
fiche T71 s'arrête là et le résultat se publie — c'est un déclencheur du plan de
recherche, pas un échec à cacher.

Le z rendu ici est celui du test apparié sur les différences, et il est lu avec
le bootstrap qui l'accompagne : sur des différences très majoritairement nulles,
le t de Student suppose une normalité que ces données n'ont pas.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT))

from gammonnet import codec  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
FILTERS = {0: (), 1: (0, 5), 2: (0, 1, 5), 3: (0, 1, 1, 5)}


def engine(model_path: str, ply: int, prune_model: str, prune_k: int, state):
    network = Network.load(model_path)
    prune_net = Network.load(prune_model) if prune_model else None
    config = SearchConfig(ply=ply, filter=FILTERS[ply],
                          use_match=state is not None, match=state,
                          prune_net=prune_net, prune_k=prune_k)
    return network, config


def compare_batch(payload):
    rows, context, a_spec, b_spec = payload
    from tools.build_corpus_t70 import CONTEXTS  # noqa: PLC0415

    state = CONTEXTS[context]
    a_net, a_config = engine(*a_spec, state)
    b_net, b_config = engine(*b_spec, state)

    out = []
    for row in rows:
        position = codec.position_from_id(row["position_id"], row["turn"])
        d1, d2 = row["dice"]
        a_ranked = search_plays(a_net, position, d1, d2, a_config)
        b_ranked = search_plays(b_net, position, d1, d2, b_config)
        if not a_ranked or not b_ranked:
            continue
        a_played = codec.position_id(a_ranked[0].play.result)
        b_played = codec.position_id(b_ranked[0].play.result)

        if a_played == b_played:
            # Même coup : la décision ne sépare pas les moteurs. Elle compte
            # pour zéro, et elle compte — la retirer ferait lire l'écart moyen
            # des désaccords comme s'il était l'écart moyen tout court.
            out.append({"index": row["index"], "class": row["class"],
                        "weight": row["weight"], "difference": 0.0,
                        "agreed": True, "outside": False})
            continue

        equities = row["equities"]
        best = max(equities)
        candidates = row["candidates"]
        if a_played not in candidates or b_played not in candidates:
            out.append({"index": row["index"], "class": row["class"],
                        "weight": row["weight"], "difference": None,
                        "agreed": False, "outside": True})
            continue

        loss_a = best - equities[candidates.index(a_played)]
        loss_b = best - equities[candidates.index(b_played)]
        out.append({"index": row["index"], "class": row["class"],
                    "weight": row["weight"], "difference": loss_a - loss_b,
                    "agreed": False, "outside": False})
    return out


def paired_statistics(differences, weights, draws: int, seed: int):
    """Moyenne pondérée, IC bootstrap, et le z apparié — les trois ensemble.

    Le z seul induirait en erreur ici : les différences sont nulles sur la
    grande majorité des décisions, une loi que le t de Student ne décrit pas.
    L'intervalle bootstrap ne suppose rien, et c'est lui qui tranche quand les
    deux se contredisent.
    """
    import numpy as np

    values = np.asarray(differences, dtype=float)
    w = np.asarray(weights, dtype=float)
    n = len(values)
    if n < 2:
        return 0.0, 0.0, 0.0, 0.0
    mean = float((values * w).sum() / w.sum())
    error = float(values.std(ddof=1) / math.sqrt(n))
    z = mean / error if error > 0 else 0.0

    generator = np.random.default_rng(seed)
    picks = generator.integers(0, n, size=(draws, n))
    sampled, sampled_w = values[picks], w[picks]
    means = np.sort((sampled * sampled_w).sum(axis=1) / sampled_w.sum(axis=1))
    return (mean, float(means[int(0.025 * draws)]),
            float(means[int(0.975 * draws) - 1]), z)


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--a-model", default=str(MODEL))
    parser.add_argument("--a-ply", type=int, default=2)
    parser.add_argument("--a-prune-model", default="")
    parser.add_argument("--a-prune-k", type=int, default=0)
    parser.add_argument("--a-label", default="")
    parser.add_argument("--b-model", default=str(MODEL))
    parser.add_argument("--b-ply", type=int, default=0)
    parser.add_argument("--b-prune-model", default="")
    parser.add_argument("--b-prune-k", type=int, default=0)
    parser.add_argument("--b-label", default="")
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    registry = Path(args.registry)
    rows = [json.loads(line) for line in registry.read_text().splitlines() if line.strip()]
    if not rows:
        print("registre vide", file=sys.stderr)
        return 2
    context = rows[0]["context"]

    a_label = args.a_label or f"{Path(args.a_model).stem} {args.a_ply}-ply"
    b_label = args.b_label or f"{Path(args.b_model).stem} {args.b_ply}-ply"
    a_spec = (args.a_model, args.a_ply, args.a_prune_model, args.a_prune_k)
    b_spec = (args.b_model, args.b_ply, args.b_prune_model, args.b_prune_k)

    print(f"T70 — {a_label}  contre  {b_label}")
    print(f"  {len(rows)} décisions appariées, contexte {context}", flush=True)

    workers = max(1, min(args.workers, len(rows)))
    payloads = [(rows[i::workers], context, a_spec, b_spec) for i in range(workers)]
    payloads = [p for p in payloads if p[0]]

    started = time.perf_counter()
    if len(payloads) == 1:
        gathered = [compare_batch(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            gathered = list(pool.map(compare_batch, payloads))
    elapsed = time.perf_counter() - started

    scored = [s for part in gathered for s in part]
    usable = [s for s in scored if s["difference"] is not None]
    outside = sum(1 for s in scored if s["outside"])
    agreed = sum(1 for s in usable if s["agreed"])

    mean, low, high, z = paired_statistics([s["difference"] for s in usable],
                                           [s["weight"] for s in usable],
                                           args.bootstrap, args.seed)

    # `difference` est perte(A) − perte(B) : négatif veut dire que A perd MOINS,
    # donc que A est meilleur. Le signe est retourné à l'affichage pour que
    # « avantage » se lise comme un avantage.
    print(f"\n  avantage de {a_label} : {-mean:+.6f} par décision")
    print(f"    IC 95 % : [{-high:+.6f} ; {-low:+.6f}]   z apparié = {-z:+.2f}")
    print(f"  désaccords : {len(usable) - agreed}/{len(usable)} "
          f"({100 * (len(usable) - agreed) / max(len(usable), 1):.1f} %)")
    print(f"  hors registre : {outside} "
          f"({100 * outside / max(len(scored), 1):.2f} %)")
    print(f"  {elapsed:.0f} s de mur sur {workers} processus")

    verdict = ("A bat B" if -z > 3 else
               "B bat A" if -z < -3 else
               "indiscernable au seuil z = 3")
    print(f"\n  verdict : {verdict}")
    if abs(-z) > 3 and (low < 0 < high):
        print("  ⚠ le z et l'intervalle bootstrap se contredisent — c'est "
              "l'intervalle qui tranche, le z suppose une normalité que des "
              "différences majoritairement nulles n'ont pas.")

    result = {"a": a_label, "b": b_label, "registry": registry.name,
              "context": context, "decisions": len(scored),
              "compared": len(usable), "agreed": agreed, "outside": outside,
              "advantage_a": -mean, "ci95": [-high, -low], "z": -z,
              "verdict": verdict, "seconds": elapsed, "workers": workers}
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"\n  → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
