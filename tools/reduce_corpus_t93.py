#!/usr/bin/env python3
"""T93 — réduire le corpus à ce que la mesure demande réellement.

## Le fait qui autorise cette réduction

La grandeur de T93 est **l'écart apparié** entre les deux moteurs sur la même
décision :

    écart = (meilleur − équité du coup à nous) − (meilleur − équité du leur)
          = équité du leur − équité du coup à nous

**Le « meilleur » disparaît.** L'écart ne dépend d'aucun autre candidat que les
deux coups joués — c'est une identité, pas une approximation. Arbitrer six
candidats par décision achète donc quatre valeurs dont la mesure de la fiche
n'a aucun usage, et l'arbitrage est le poste cher : **101 s·cœur par décision
en moyenne mesurée**, dont l'essentiel part en rollouts sur les candidats.

Ce banc produit donc un corpus réduit à **deux candidats** — le coup de chacun —
et à un tirage aléatoire de `--target` décisions. Les deux réductions sont
mesurées et publiées ; la seconde a un coût statistique (l'intervalle s'élargit
en 1/√n) que la fiche chiffre, la première n'en a aucun.

## Ce que la réduction coûte quand même, et qui est dit

Les **pertes individuelles** ne sont plus « l'écart au meilleur coup connu »
mais « l'écart au meilleur **des deux coups joués** ». Elles restent
comparables entre les deux moteurs sur une même décision — c'est tout ce que
l'écart demande — mais elles ne sont plus une note absolue et ne doivent pas
être lues comme telle. `bench/compare_t93.py` le rappelle dans sa sortie.

Le tirage préserve la stratification : il est uniforme sur les lignes, et le
banc **vérifie** que la distribution par classe survit plutôt que de le
supposer. Les poids de strate sont recalculés sur l'échantillon.

Usage :
    python tools/reduce_corpus_t93.py --depth 2 --target 2000
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--depth", type=int, required=True)
    parser.add_argument("--target", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260907)
    parser.add_argument("--root", default=str(ROOT / "docs" / "corpus" / "t93"))
    args = parser.parse_args()

    source = Path(args.root) / f"depth-{args.depth}"
    rows = [json.loads(line)
            for line in (source / "corpus-money.jsonl").read_text().splitlines()
            if line.strip()]
    manifest = json.loads((source / "manifeste.json").read_text())

    before = collections.Counter(r["class"] for r in rows)
    rng = random.Random(args.seed)
    kept = sorted(rng.sample(rows, min(args.target, len(rows))),
                  key=lambda r: r["index"])
    after = collections.Counter(r["class"] for r in kept)

    reduced = []
    for row in kept:
        ours, theirs = row["ours"], row["theirs"]
        if ours == theirs:
            raise ValueError(
                f"décision {row['index']} : les deux coups sont le même. "
                "Ce corpus ne devrait contenir que des désaccords ; refusé."
            )
        candidates = [row["candidates"][ours], row["candidates"][theirs]]
        reduced.append({**row, "candidates": candidates, "ours": 0, "theirs": 1,
                        "candidates_full": row["candidates"]})

    # Les poids sont recalculés sur l'échantillon : la fréquence naturelle de la
    # classe divisée par sa part ICI. Reprendre les poids du corpus entier
    # donnerait une moyenne pondérée par une stratification qui n'est plus celle
    # des lignes qu'on lit.
    natural = manifest["natural"]
    total = len(reduced)
    for row in reduced:
        share = after[row["class"]] / total
        row["weight"] = natural[row["class"]] / share if share else 0.0

    out = Path(args.root) / f"depth-{args.depth}-n{total}"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "corpus-money.jsonl"
    with open(path, "w") as fh:
        for row in reduced:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    drift = {name: (after[name] / total) - (before[name] / len(rows))
             for name in sorted(before)}
    worst = max(abs(v) for v in drift.values()) if drift else 0.0

    (out / "manifeste.json").write_text(json.dumps({
        **{k: v for k, v in manifest.items() if k not in ("sha256", "by_class")},
        "reduced_from": str(source),
        "reduced_seed": args.seed,
        "decisions": total,
        "candidates_per_decision": 2,
        "by_class": dict(after),
        "class_share_drift": drift,
        "worst_class_share_drift": worst,
        "sha256": digest,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"T93 — corpus réduit, profondeur {args.depth}")
    print(f"  {len(rows)} → {total} décisions, 6 candidats → 2 (les deux coups joués)")
    print(f"  dérive maximale de part de classe : {100 * worst:.2f} points")
    for name in sorted(before, key=lambda k: -before[k]):
        print(f"    {name:22s} {100 * before[name] / len(rows):5.2f} %  →  "
              f"{100 * after[name] / total:5.2f} %")
    print(f"  {path}  sha256 {digest[:16]}…")
    if worst > 0.02:
        print("  ⚠ dérive supérieure à 2 points : la stratification n'a pas survécu "
              "au tirage, et les poids ne la rattrapent qu'en moyenne.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
