#!/usr/bin/env python3
"""Ce que le transport en float16 (`BGN6`) déplace, position par position.

`tools/measure_quantization.py` a rendu le verdict du 2026-08-04 sur l'ancien
réseau, à 400 positions et sur un seul cœur. Ceci le refait sur le réseau servi,
à un volume où le **maximum** observé veut dire quelque chose — c'est lui que la
spec du format (`docs/specs/format-bgn6-spec.md`) inscrit comme borne mesurée.

Deux familles de grandeurs, et seule la seconde coûte quelque chose en jeu :

1. **l'écart d'évaluation** — sur chaque position du corpus ET sur chaque
   position résultante d'un coup légal (c'est elles que la recherche évalue) :
   écart absolu maximal sur les cinq sorties, écart d'équité money ;
2. **le désaccord de coup à 0-ply** — pour chacun des 21 lancers, le coup choisi
   par le modèle float16 est-il celui du float32, et sinon, ce qu'il perd jugé
   par le float32.

La perte à 2-ply au réglage servi se mesure ailleurs, contre les rollouts du
registre de T70 (`bench/measure_t70.py` + `bench/paired_dumps_t70.py`).

    python bench/measure_fp16.py --fp32 models/cubeless_prob5_768_768_256_256_256.bin \\
        --fp16 models/strehl-prob5-512-512-256-256_v1.8.0_2026-10-15.bin16 \\
        --positions 20000 --workers 30 --out docs/mesures/t32-fp16-positions.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

from gammonnet.infer import Network  # noqa: E402
from gammonnet.search import ROLLS, SearchConfig, search_plays  # noqa: E402
from measure_quantization import SEED, build_corpus  # noqa: E402

_NETS: tuple[Network, Network] | None = None


def _init(fp32: str, fp16: str) -> None:
    global _NETS
    _NETS = (Network.load(fp32), Network.load(fp16))


def _gaps(wide, half) -> tuple[float, float]:
    """(écart maximal sur les cinq sorties, écart d'équité money)."""
    a, b = wide.as_tuple(), half.as_tuple()
    return (max(abs(x - y) for x, y in zip(a, b)),
            abs(wide.money_equity - half.money_equity))


def _chunk(positions: list) -> dict:
    wide_net, half_net = _NETS
    config = SearchConfig(ply=0)
    out = {"root_out": [], "root_eq": [], "child_out": [], "child_eq": [],
           "decisions": 0, "losses": []}
    for position in positions:
        o, e = _gaps(wide_net.evaluate(position), half_net.evaluate(position))
        out["root_out"].append(o)
        out["root_eq"].append(e)
        for d1, d2, _ in ROLLS:
            ranked = search_plays(wide_net, position, d1, d2, config)
            if not ranked:
                continue
            seen = set()
            for play in ranked:
                if play.result in seen:
                    continue
                seen.add(play.result)
                o, e = _gaps(wide_net.evaluate(play.result),
                             half_net.evaluate(play.result))
                out["child_out"].append(o)
                out["child_eq"].append(e)
            if len(ranked) < 2:
                continue  # un seul coup : rien à décider
            out["decisions"] += 1
            chosen = search_plays(half_net, position, d1, d2, config)[0]
            if chosen.result != ranked[0].result:
                by_result = {c.result: c.equity for c in ranked}
                out["losses"].append(ranked[0].equity - by_result[chosen.result])
    return out


def _quantiles(values: list[float]) -> dict:
    ordered = sorted(values)

    def q(p: float) -> float:
        return ordered[min(len(ordered) - 1, int(p * len(ordered)))]

    return {"n": len(ordered), "mean": statistics.fmean(ordered),
            "p50": q(0.50), "p99": q(0.99), "p999": q(0.999),
            "max": ordered[-1]}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fp32", required=True, help="le modèle de référence (BGNN)")
    parser.add_argument("--fp16", required=True, help="le même, emballé (BGN6)")
    parser.add_argument("--positions", type=int, default=20_000)
    parser.add_argument("--workers", type=int, default=30)
    parser.add_argument("--chunk", type=int, default=100)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    corpus = build_corpus(args.positions)
    chunks = [corpus[i:i + args.chunk] for i in range(0, len(corpus), args.chunk)]
    merged = {"root_out": [], "root_eq": [], "child_out": [], "child_eq": [],
              "decisions": 0, "losses": []}
    with ProcessPoolExecutor(args.workers, initializer=_init,
                             initargs=(args.fp32, args.fp16)) as pool:
        for done, part in enumerate(pool.map(_chunk, chunks), 1):
            for key in ("root_out", "root_eq", "child_out", "child_eq", "losses"):
                merged[key] += part[key]
            merged["decisions"] += part["decisions"]
            print(f"\r  {done}/{len(chunks)} tranches", end="", flush=True)
    print()

    decisions, losses = merged["decisions"], merged["losses"]
    rate = len(losses) / decisions
    # Intervalle de Wilson à 95 % sur le taux de désaccord : avec quelques
    # dizaines de désaccords, l'approximation normale serait fausse aux bords.
    z = 1.96
    centre = (rate + z * z / (2 * decisions)) / (1 + z * z / decisions)
    half = (z / (1 + z * z / decisions)) * math.sqrt(
        rate * (1 - rate) / decisions + z * z / (4 * decisions ** 2))
    result = {
        "fp32": Path(args.fp32).name, "fp16": Path(args.fp16).name,
        "corpus": {"seed": SEED, "positions": len(corpus), "ply": 0},
        "positions": {"outputs": _quantiles(merged["root_out"]),
                      "equity": _quantiles(merged["root_eq"])},
        "children": {"outputs": _quantiles(merged["child_out"]),
                     "equity": _quantiles(merged["child_eq"])},
        "decisions": decisions,
        "disagreements": len(losses),
        "disagreement_rate": rate,
        "disagreement_rate_ci95": [centre - half, centre + half],
        "loss_when_disagree": _quantiles(losses) if losses else None,
        "loss_per_decision": sum(losses) / decisions,
    }
    for scope in ("positions", "children"):
        eq, outs = result[scope]["equity"], result[scope]["outputs"]
        print(f"{scope:10s} n={eq['n']:>10,}  équité moy {eq['mean']:.3e}  "
              f"p99,9 {eq['p999']:.3e}  max {eq['max']:.3e}  "
              f"| sorties max {outs['max']:.3e}")
    print(f"désaccord de coup  {len(losses):,} / {decisions:,} = {rate * 100:.4f} %  "
          f"[{result['disagreement_rate_ci95'][0] * 100:.4f} ; "
          f"{result['disagreement_rate_ci95'][1] * 100:.4f}]")
    if losses:
        print(f"perte si désaccord moy {statistics.fmean(losses):.3e}  "
              f"max {max(losses):.3e}")
    print(f"perte par décision {result['loss_per_decision']:.3e}")
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
