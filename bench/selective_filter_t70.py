#!/usr/bin/env python3
"""T70 — apparier deux filtres de coups en n'arbitrant que là où ils divergent.

`bench/paired_dumps_t70.py` apparie deux notations sur un registre ENTIÈREMENT
arbitré. Or quand deux réglages de recherche jouent le même coup, leur
différence de perte vaut zéro exactement, quelle que soit la valeur du coup :
l'arbitrage de cette décision n'entre pas dans Δ. Ne payer les rollouts que sur
les décisions où les deux réglages divergent rend le même Δ, décision par
décision, pour une fraction du coût — c'est ce qui rend la jauge abordable aux
contextes de score, dont aucun registre complet n'existe.

Deux temps, un même corpus figé de `tools/build_corpus_t70.py` :

1. `screen` joue chaque décision avec les deux réglages (contexte de score du
   corpus, élagage `k` et réseau d'élagage de la jauge money) et écrit :
   - l'écran : par décision, le coup de chaque réglage et son coût ;
   - le sous-corpus des décisions où les coups diffèrent, à confier tel quel à
     `bench/arbitrate_t70.py`. La graine d'arbitrage d'une décision dépend de
     son index absolu : le sous-corpus est arbitré comme il l'aurait été dans
     le corpus entier.
2. `pair` relit l'écran et le registre du sous-corpus, et rend Δ = perte(B) −
   perte(A) sur TOUTES les décisions de l'écran : zéro là où les coups sont
   égaux, la différence d'équités arbitrées ailleurs. Moyenne pondérée, IC 95 %
   bootstrap sur les positions, verdict de non-infériorité (borne haute ≤
   `--margin`) — la statistique de `paired_dumps_t70.py`, mêmes entrées.
   Une décision où l'un des deux coups sort des candidats du corpus est écartée
   et comptée à part, jamais comptée zéro — la règle de `paired_dumps_t70.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench"))

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_256.bin"
PRUNE = ROOT / "models" / "prune_32.bin"


def parse(text: str, kind):
    return tuple(kind(x) for x in text.split(",")) if text else ()


def screen_batch(payload):
    rows, context, specs = payload
    from gammonnet import codec  # noqa: PLC0415
    from gammonnet.infer import Network  # noqa: PLC0415
    from gammonnet.search import (  # noqa: PLC0415
        SearchConfig, evaluations, prune_evaluations, reset_evaluations, search_plays)
    from tools.build_corpus_t70 import CONTEXTS  # noqa: PLC0415

    net = Network.load(str(MODEL))
    prune = Network.load(str(PRUNE))
    state = CONTEXTS[context]
    configs = {side: SearchConfig(ply=spec["ply"], filter=spec["filter"],
                                  filter_extra=spec["extra"],
                                  filter_threshold=spec["threshold"],
                                  use_match=state is not None, match=state,
                                  prune_net=prune, prune_k=spec["prune_k"])
               for side, spec in specs.items()}
    out = []
    for row in rows:
        position = codec.position_from_id(row["position_id"], row["turn"])
        d1, d2 = row["dice"]
        record = {"index": row["index"], "class": row["class"], "weight": row["weight"]}
        for side, config in configs.items():
            reset_evaluations()
            began = time.perf_counter()
            ranked = search_plays(net, position, d1, d2, config)
            played = codec.position_id(ranked[0].play.result) if ranked else None
            record[side] = {
                "played": played, "inside": played in row["candidates"],
                "evals": evaluations(), "prune_evals": prune_evaluations(),
                "seconds": time.perf_counter() - began}
        out.append(record)
    return out


def screen(args) -> int:
    corpus = Path(args.corpus)
    rows = [json.loads(line) for line in corpus.read_text().splitlines() if line.strip()]
    context = rows[0]["context"]
    specs = {side: {"ply": args.ply, "prune_k": args.prune_k,
                    "filter": parse(getattr(args, f"{side}_filter"), int),
                    "extra": parse(getattr(args, f"{side}_extra"), int),
                    "threshold": parse(getattr(args, f"{side}_threshold"), float)}
             for side in ("a", "b")}
    chunks = [rows[i::args.workers] for i in range(args.workers)]
    with ProcessPoolExecutor(args.workers) as pool:
        parts = list(pool.map(screen_batch, [(c, context, specs) for c in chunks if c]))
    records = sorted((r for part in parts for r in part), key=lambda r: r["index"])
    differing = {r["index"] for r in records if r["a"]["played"] != r["b"]["played"]}

    with open(args.screen, "w") as fh:
        fh.write(json.dumps({"header": True, "corpus": corpus.name, "context": context,
                             "specs": specs}, sort_keys=True) + "\n")
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    with open(args.differing, "w") as fh:
        for row in rows:
            if row["index"] in differing:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
    print(f"{len(records)} décisions, contexte {context} : "
          f"{len(differing)} où les deux réglages divergent → {args.differing}")
    return 0


def pair(args) -> int:
    from compare_t70 import paired_statistics  # noqa: PLC0415

    lines = [json.loads(line) for line in Path(args.screen).read_text().splitlines()
             if line.strip()]
    header = lines[0]
    records = lines[1:]
    registry = {}
    for line in Path(args.registry).read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            registry[row["index"]] = row

    differences, weights = [], []
    outside = missing = bounded = 0
    for record in records:
        a, b = record["a"]["played"], record["b"]["played"]
        if not (record["a"]["inside"] and record["b"]["inside"]):
            # La règle de `paired_dumps_t70.py` : hors des candidats d'un côté,
            # la décision sort de l'appariement, même quand les coups sont égaux.
            outside += 1
            continue
        if a == b:
            differences.append(0.0)
            weights.append(record["weight"])
            continue
        row = registry.get(record["index"])
        if row is None:
            missing += 1
            continue
        candidates, equities = row["candidates"], row["equities"]
        ia, ib = candidates.index(a), candidates.index(b)
        states = row.get("resolution") or []
        if states and "dominated" in (states[ia], states[ib]):
            bounded += 1
        # Δ = perte(B) − perte(A) = équité(A) − équité(B) : le meilleur s'annule.
        differences.append(equities[ia] - equities[ib])
        weights.append(record["weight"])
    if missing:
        print(f"{missing} décisions divergentes absentes du registre : "
              "arbitrer le sous-corpus en entier", file=sys.stderr)
        return 2

    mean, low, high, z = paired_statistics(differences, weights, args.bootstrap, args.seed)
    changed = sum(1 for d in differences if d != 0.0)
    cost = {key: (sum(r["a"][key] for r in records), sum(r["b"][key] for r in records))
            for key in ("evals", "prune_evals", "seconds")}
    passed = high <= args.margin
    print(f"contexte {header['context']} — Δ perte par décision (B − A) : {mean:+.5f}  "
          f"[{low:+.5f} ; {high:+.5f}]  (IC 95 %, bootstrap {args.bootstrap}), z = {z:+.2f}")
    print(f"  décisions appariées : {len(differences)}   dont coup différent : {changed}"
          f"   hors registre : {outside}   coup borné (dominé) : {bounded}")
    for key, (ca, cb) in cost.items():
        print(f"  {key:12s} A {ca:14.1f}   B {cb:14.1f}   ×{ca / cb if cb else float('inf'):.3f}")
    print(f"  non-infériorité (borne haute ≤ {args.margin}) : "
          f"{'TENUE' if passed else 'NON TENUE'}")
    if args.out:
        Path(args.out).write_text(json.dumps({
            "context": header["context"], "corpus": header["corpus"],
            "specs": header["specs"], "registry": Path(args.registry).name,
            "decisions": len(records), "paired": len(differences), "changed": changed,
            "outside": outside, "bounded": bounded,
            "delta": mean, "ci95": [low, high], "z": z, "margin": args.margin,
            "non_inferior": passed,
            "cost": {k: {"a": ca, "b": cb} for k, (ca, cb) in cost.items()},
        }, indent=2, sort_keys=True) + "\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("screen", help="jouer les deux réglages, extraire les divergences")
    s.add_argument("--corpus", required=True)
    s.add_argument("--screen", required=True, help="écran de sortie (.jsonl)")
    s.add_argument("--differing", required=True, help="sous-corpus à arbitrer (.jsonl)")
    s.add_argument("--workers", type=int, default=14)
    s.add_argument("--ply", type=int, default=2)
    s.add_argument("--prune-k", type=int, default=12)
    for side in ("a", "b"):
        s.add_argument(f"--{side}-filter", required=True)
        s.add_argument(f"--{side}-extra", default="")
        s.add_argument(f"--{side}-threshold", default="")
    s.set_defaults(run=screen)

    p = sub.add_parser("pair", help="Δ apparié sur l'écran, registre du sous-corpus")
    p.add_argument("--screen", required=True)
    p.add_argument("--registry", required=True)
    p.add_argument("--margin", type=float, default=0.001)
    p.add_argument("--bootstrap", type=int, default=10_000)
    p.add_argument("--seed", type=int, default=20260827)
    p.add_argument("--out", default="")
    p.set_defaults(run=pair)

    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
