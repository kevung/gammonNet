#!/usr/bin/env python3
"""Gauge a race-zone network against the incumbent evaluator.

Instrument: on a gauge corpus (`build_race_corpus.py`, a seed disjoint from the
training corpora, positions shared with them removed and counted), compare each
network's cubeless money equity to the rollout equity of the same position.

Reported, per network and per stratum (`classify` class): mean absolute error,
RMSE, bias. Reported once: the PAIRED difference of absolute errors
(candidate - incumbent), its standard error and 95 % interval, and the mean
rollout standard error, which is the noise floor of every figure above. A
difference whose interval contains zero is not a difference. Negative favours
the candidate.

What this is not: a decision loss, and not a game strength. It says how well
each network estimates the equity of a race-zone position. Whether that moves
play is a separate measurement, made once the network is wired into the search.

Usage:
    python tools/gauge_race_net.py --corpus build/race_gauge.npz \\
        --candidate models/race_net.bin --incumbent models/cubeless_prob5_512_512_256_256.bin \\
        --exclude build/race_train.npz --out docs/mesures/race-gauge.json
    python tools/gauge_race_net.py --smoke
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))


def equities(model: Path, features: np.ndarray) -> np.ndarray:
    from gammonnet.infer import Network

    with Network.load(model) as network:
        return np.asarray([network.evaluate_features(row.tolist()).money_equity
                           for row in features], dtype=np.float64)


def summarise(error: np.ndarray) -> dict:
    return {"n": int(error.size), "mae": float(np.abs(error).mean()),
            "rmse": float(math.sqrt((error ** 2).mean())),
            "bias": float(error.mean())}


def gauge(corpus: Path, candidate: Path, incumbent: Path,
          exclude: list[Path]) -> dict:
    data = np.load(corpus)
    banned = set()
    for path in exclude:
        banned.update(np.load(path)["ids"].tolist())
    keep = np.asarray([i not in banned for i in data["ids"].tolist()])
    features, truth = data["features"][keep], data["equity"][keep].astype(np.float64)
    klass, se = data["klass"][keep], data["se"][keep]
    if truth.size < 2:
        raise SystemExit("REFUS - moins de deux positions de jauge utilisables.")

    errors = {name: equities(path, features) - truth
              for name, path in (("candidate", candidate), ("incumbent", incumbent))}
    paired = np.abs(errors["candidate"]) - np.abs(errors["incumbent"])
    half = 1.96 * float(paired.std(ddof=1)) / math.sqrt(paired.size)
    return {
        "corpus": str(corpus), "rows": int(truth.size),
        "excluded_as_training": int((~keep).sum()),
        "rollout_mean_se": float(se.mean()),
        "overall": {name: summarise(e) for name, e in errors.items()},
        "by_class": {str(k): {name: summarise(e[klass == k])
                              for name, e in errors.items()}
                     for k in np.unique(klass)},
        "paired_abs_error_candidate_minus_incumbent": {
            "mean": float(paired.mean()), "ci95": [float(paired.mean() - half),
                                                   float(paired.mean() + half)]},
        "reading": "negative favours the candidate; an interval containing 0 "
                   "is no difference; every error is bounded below by the "
                   "rollout noise (rollout_mean_se).",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, default=ROOT / "build" / "race_gauge.npz")
    parser.add_argument("--candidate", type=Path, default=ROOT / "models" / "race_net.bin")
    parser.add_argument("--incumbent", type=Path,
                        default=ROOT / "models" / "cubeless_prob5_512_512_256_256.bin")
    parser.add_argument("--exclude", type=Path, nargs="*", default=[],
                        help="training corpora whose positions are dropped")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)

    if args.smoke:
        import build_race_corpus
        from smoke_support import write_random_network
        workdir = (args.out.parent / "smoke-inputs" if args.out
                   else Path(tempfile.mkdtemp(prefix="race-smoke-")))
        build_race_corpus.main(["--smoke", "--out", str(workdir / "gauge.npz"),
                                "--seed", "7"])
        args.corpus = workdir / "gauge.npz"
        args.incumbent = workdir / "incumbent.bin"
        args.candidate = write_random_network(workdir / "candidate.bin", [16, 8], 3)
        args.out = args.out or workdir / "gauge.json"
    for needed in (args.corpus, args.candidate, args.incumbent):
        if not needed.exists():
            print(f"REFUS - absent : {needed}", file=sys.stderr)
            return 2

    report = gauge(args.corpus, args.candidate, args.incumbent, args.exclude)
    report["smoke"] = args.smoke
    text = json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True)
    if args.out:
        args.out.write_text(text)
        print(f"-> {args.out}")
    paired = report["paired_abs_error_candidate_minus_incumbent"]
    print(f"{report['rows']} positions ({report['excluded_as_training']} "
          f"exclues), bruit de rollout {report['rollout_mean_se']:.4f}")
    for name, row in report["overall"].items():
        print(f"  {name:<10} mae {row['mae']:.5f} rmse {row['rmse']:.5f} "
              f"bias {row['bias']:+.5f}")
    print(f"  écart apparié (candidat - titulaire) {paired['mean']:+.5f} "
          f"IC95 [{paired['ci95'][0]:+.5f} ; {paired['ci95'][1]:+.5f}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
