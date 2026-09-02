#!/usr/bin/env python3
"""T70 — tirer un sous-échantillon stratifié à arbitrer, sans toucher au corpus.

    python tools/subsample_corpus_t70.py --corpus docs/corpus/t70/money/corpus-money.jsonl \\
        --target 10000 --out docs/corpus/t70/money-10k

## Pourquoi un sous-échantillon plutôt qu'un corpus plus petit

L'arbitrage coûte **16,7 minutes·cœur par décision** (mesuré le 2026-08-28,
machine libre, 30 processus) : 262 heures pour les 28 374 décisions de money.
Récolter, en comparaison, ne coûte presque rien.

On garde donc le corpus entier — il est récolté, versé, et son empreinte est
figée — et l'on n'arbitre qu'une partie. Ce qui reste n'est pas perdu : il
attend, et pourra être arbitré plus tard **en prolongeant le même registre**.

## Les deux propriétés qui rendent ce prolongement possible

1. **Les index d'origine sont conservés.** Le sous-échantillon est un vrai
   sous-ensemble du corpus, pas une renumérotation. Le journal d'arbitrage
   classe par index ; deux campagnes successives s'y ajoutent sans se marcher
   dessus, et `measure_t70` comme l'étape 0 de T71 apparient toujours par index.

2. **Les poids d'origine sont conservés.** Le poids vaut « fréquence naturelle
   de la classe ÷ sa part dans le corpus ». Le tirage étant **proportionnel par
   classe**, les parts sont préservées à l'arrondi près : le poids du corpus
   entier reste le bon, et la moyenne pondérée du sous-échantillon estime sans
   biais celle du corpus complet. Les recalculer sur le sous-échantillon aurait
   l'effet inverse — deux campagnes successives vivraient sous deux
   pondérations, et leur réunion ne voudrait plus rien dire.

## Le tirage

Proportionnel par classe, sans remise, déterministe pour une graine donnée. Les
classes trop petites pour leur quota sont prises en entier, et le reliquat est
redistribué aux autres — sinon une strate rare, déjà la moins bien mesurée,
serait la première à rétrécir.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import sys
from pathlib import Path


def stratified(rows: list, target: int, seed: int):
    """Un tirage proportionnel par classe, les petites classes prises entières."""
    by_class = collections.defaultdict(list)
    for row in rows:
        by_class[row["class"]].append(row)

    total = len(rows)
    quota = {name: target * len(part) / total for name, part in by_class.items()}

    # Les classes plus petites que leur quota sont prises en entier ; ce
    # qu'elles ne consomment pas retourne au pot commun. Sans cette passe, le
    # reliquat serait perdu et le tirage rendrait moins que la cible.
    taken, remaining, pool = {}, target, []
    for name, part in by_class.items():
        want = int(round(quota[name]))
        if want >= len(part):
            taken[name] = list(part)
            remaining -= len(part)
        else:
            pool.append(name)
    if pool:
        weight = sum(len(by_class[n]) for n in pool)
        for name in pool:
            share = len(by_class[name]) / weight if weight else 0.0
            want = min(len(by_class[name]), int(round(remaining * share)))
            rng = random.Random(seed + hash_name(name))
            taken[name] = rng.sample(by_class[name], want)

    chosen = [row for name in sorted(taken) for row in taken[name]]
    chosen.sort(key=lambda r: r["index"])
    return chosen, {name: len(part) for name, part in taken.items()}


def hash_name(name: str) -> int:
    """Un décalage de graine STABLE par classe.

    `hash()` d'une chaîne varie d'un processus Python à l'autre — même piège que
    celui déjà nommé dans `build_corpus_t70.py`. Un tirage irreproductible ne se
    verrait pas : il rendrait un sous-échantillon parfaitement valide, mais un
    autre à chaque exécution.
    """
    return int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--target", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    rows = [json.loads(l) for l in args.corpus.read_text().splitlines() if l.strip()]
    if not rows:
        print("corpus vide", file=sys.stderr)
        return 2
    context = rows[0]["context"]

    print(f"T70 — sous-échantillon à arbitrer, contexte {context}")
    print(f"  corpus : {len(rows)} décisions   cible : {args.target}")

    chosen, counts = stratified(rows, args.target, args.seed)
    before = collections.Counter(r["class"] for r in rows)

    print(f"\n  {len(chosen)} décisions retenues\n")
    print(f"  {'classe':22s}{'corpus':>9s}{'retenu':>9s}{'part corpus':>13s}{'part retenue':>14s}")
    for name in sorted(before, key=lambda k: -before[k]):
        got = counts.get(name, 0)
        print(f"  {name:22s}{before[name]:9d}{got:9d}"
              f"{100 * before[name] / len(rows):12.2f}%"
              f"{100 * got / len(chosen) if chosen else 0:13.2f}%")

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"corpus-{context}.jsonl"
    with path.open("w") as fh:
        for row in chosen:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    manifest_src = args.manifest or (args.corpus.parent / "manifeste.json")
    manifest = json.loads(manifest_src.read_text()) if manifest_src.exists() else {}
    manifest["subsample"] = {
        "from": str(args.corpus), "from_decisions": len(rows),
        "decisions": len(chosen), "seed": args.seed,
        "sha256": digest, "by_class": counts,
        "note": "Index et poids d'origine conservés : ce fichier est un vrai "
                "sous-ensemble du corpus, et arbitrer le reste plus tard "
                "prolonge le même registre au lieu de le refaire.",
    }
    (args.out / "manifeste.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(f"\n  → {path}  sha256 {digest[:16]}…")
    print(f"  → {args.out / 'manifeste.json'}")
    print(f"\n  coût d'arbitrage attendu : ~{len(chosen) * 16.7 / 60 / 30:.0f} h "
          f"à 30 processus (16,7 min·cœur par décision, mesuré le 2026-08-28)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
