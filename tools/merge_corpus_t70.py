#!/usr/bin/env python3
"""T70 — fusionner des tranches de corpus en un corpus unique et pondéré.

## Pourquoi des tranches, et pourquoi une fusion et non un `cat`

Construire un corpus de 30 000 décisions demande une vingtaine d'heures, et le
générateur n'est pas reprenable : il accumule en mémoire et n'écrit qu'à la fin.
Un incident à la dix-neuvième heure coûterait les dix-neuf. On construit donc par
tranches indépendantes — chacune quelques heures, chacune perdable sans
conséquence — et on les fusionne.

Un `cat` produirait un fichier lisible et **faux**, pour trois raisons dont
aucune ne se voit :

1. **Les poids seraient ceux des tranches.** Le poids d'une décision vaut
   `fréquence naturelle de sa classe ÷ sa part dans le corpus`. Cette part
   change quand on réunit six tranches : un poids calculé sur 5 000 décisions
   appliqué à un corpus de 30 000 déplace la moyenne d'équité sans rien casser
   d'apparent.
2. **Les index se recouvriraient.** Chaque tranche numérote à partir de zéro. Or
   l'arbitrage journalise PAR INDEX et l'étape 0 de T71 apparie PAR INDEX : six
   décisions différentes portant le numéro 0 se confondraient silencieusement.
3. **Les doublons compteraient double.** Deux tranches de graines différentes
   peuvent tomber sur la même décision. Concaténées, elles la pondéreraient deux
   fois — et c'est justement sur les classes rares, où chaque décision pèse
   lourd, que la collision est la plus probable.

## La distribution naturelle

Chaque tranche mesure la sienne sur 20 000 décisions tirées de sa propre graine.
La fusion en prend la moyenne : six estimations indépendantes du même objet
valent mieux qu'une, et les tranches ayant toutes le même effectif
d'échantillon, la moyenne simple est la bonne.

## Ce qui doit concorder, sinon on refuse

Version du format, profondeur, largeur, filtres, réseau. Deux tranches produites
par des moteurs différents ne forment pas un corpus : elles forment deux corpus
dans un fichier. Le refus nomme ce qui diffère.

Usage :
    python tools/merge_corpus_t70.py --out docs/corpus/t70 \\
        docs/corpus/t70/tranches/tranche-*
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Ce qui définit « le même moteur ». Le reste (graine, cible, facteur
#: d'examen, quotas) a le droit de varier d'une tranche à l'autre : ce sont des
#: réglages de récolte, pas de mesure.
MUST_MATCH = ("version", "ply", "width", "model", "filters")


def load_slice(path: Path, context: str):
    """Une tranche : son manifeste et ses lignes. Refuse ce qui est incomplet."""
    manifest_path = path / "manifeste.json"
    corpus_path = path / f"corpus-{context}.jsonl"
    if not manifest_path.exists():
        raise SystemExit(f"REFUS — manifeste absent : {manifest_path}")
    if not corpus_path.exists():
        raise SystemExit(f"REFUS — corpus absent : {corpus_path}")
    manifest = json.loads(manifest_path.read_text())
    rows = [json.loads(line) for line in corpus_path.read_text().splitlines()
            if line.strip()]
    if not rows:
        raise SystemExit(f"REFUS — tranche vide : {corpus_path}")
    return manifest, rows


def check_compatible(manifests: list[tuple[Path, dict]]) -> None:
    reference_path, reference = manifests[0]
    for path, manifest in manifests[1:]:
        differences = [k for k in MUST_MATCH if manifest.get(k) != reference.get(k)]
        if differences:
            raise SystemExit(
                f"REFUS — {path.name} et {reference_path.name} ne décrivent pas le "
                f"même moteur ; désaccord sur : {', '.join(differences)}.\n"
                "Deux tranches produites par des moteurs différents ne forment pas "
                "un corpus, elles forment deux corpus dans un fichier.")


def merge_rows(slices: list[tuple[Path, list]]):
    """Concatène, dédoublonne sur l'identité de la DÉCISION, renumérote."""
    seen, rows, duplicates = {}, [], 0
    for path, part in slices:
        for row in part:
            key = (row["context"], row["turn"], row["position_id"],
                   tuple(row["dice"]))
            if key in seen:
                duplicates += 1
                continue
            seen[key] = path.name
            rows.append(dict(row, slice=path.name))
    for index, row in enumerate(rows):
        row["index"] = index
    return rows, duplicates


def reweight(rows: list, natural: dict) -> dict:
    """Le poids qui rétablit la fréquence naturelle, sur le corpus RÉUNI."""
    counts = collections.Counter(row["class"] for row in rows)
    total = len(rows)
    for row in rows:
        klass = row["class"]
        share = counts[klass] / total if total else 0.0
        row["weight"] = natural.get(klass, 0.0) / share if share else 0.0
    return dict(counts)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("slices", nargs="+", type=Path,
                        help="les répertoires de tranches à fusionner")
    parser.add_argument("--context", default="money")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    paths = sorted(set(args.slices))
    print(f"T70 — fusion de {len(paths)} tranches, contexte {args.context}")

    loaded = [(path,) + load_slice(path, args.context) for path in paths]
    check_compatible([(path, manifest) for path, manifest, _ in loaded])

    for path, manifest, part in loaded:
        print(f"  {path.name:22s} {len(part):6d} décisions   graine {manifest['seed']}")

    rows, duplicates = merge_rows([(path, part) for path, _, part in loaded])
    print(f"\n  {len(rows)} décisions après fusion "
          f"({duplicates} doublon(s) écarté(s))")

    # La distribution naturelle : la moyenne des estimations des tranches, qui
    # ont toutes le même effectif d'échantillon.
    naturals = [manifest["natural"] for _, manifest, _ in loaded]
    keys = sorted({k for n in naturals for k in n})
    natural = {k: sum(n.get(k, 0.0) for n in naturals) / len(naturals) for k in keys}

    counts = reweight(rows, natural)

    args.out.mkdir(parents=True, exist_ok=True)
    corpus_path = args.out / f"corpus-{args.context}.jsonl"
    with corpus_path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    digest = hashlib.sha256(corpus_path.read_bytes()).hexdigest()

    print("\n  remplissage par classe, corpus réuni :")
    for name in sorted(counts, key=lambda k: -counts[k]):
        print(f"    {name:22s} {counts[name]:6d}  "
              f"({100 * counts[name] / len(rows):5.2f} %)  "
              f"naturel {100 * natural.get(name, 0.0):5.2f} %  "
              f"poids {natural.get(name, 0.0) / (counts[name] / len(rows)):.3f}")

    reference = loaded[0][1]
    per_context = {}
    for _path, manifest, _part in loaded:
        stats = manifest["contexts"].get(args.context, {})
        for field in ("examined", "compared", "seconds"):
            per_context[field] = per_context.get(field, 0) + stats.get(field, 0)
    rate = (per_context.get("compared", 0)
            and len(rows) / per_context["compared"])

    manifest = {
        "version": reference["version"], "ply": reference["ply"],
        "width": reference["width"], "filters": reference["filters"],
        "model": reference["model"],
        "merged_from": [{"slice": path.name, "seed": m["seed"],
                         "decisions": len(part),
                         "sha256": m["contexts"].get(args.context, {}).get("sha256")}
                        for path, m, part in loaded],
        "natural": natural,
        "natural_sample": sum(m["natural_sample"] for _, m, _ in loaded),
        "duplicates_dropped": duplicates,
        "contexts": {args.context: {
            "decisions": len(rows),
            "examined": per_context.get("examined", 0),
            "compared": per_context.get("compared", 0),
            "disagreement_rate": rate,
            "seconds": per_context.get("seconds", 0.0),
            "sha256": digest,
            "by_class": counts,
        }},
    }
    (args.out / "manifeste.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(f"\n  → {corpus_path}  sha256 {digest[:16]}…")
    print(f"  → {args.out / 'manifeste.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
