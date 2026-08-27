#!/usr/bin/env python3
"""T70 — de combien la passe 1 se trompe, chiffré sur ses propres verdicts.

    python bench/audit_pass1_t70.py --registry docs/corpus/t70/registre-money.jsonl

## Le critère que ce banc acquitte

La fiche T70 demande que « le biais de la passe 1 (gnubg 3-ply) soit encadré :
un échantillon de ses verdicts est réévalué en passe 2, l'écart chiffré et
publié **avec chaque usage de l'instrument** ».

L'arbitrage collecte déjà la matière : `--audit` rejoue en passe 2 une fraction
des décisions que la passe 1 aurait tranchées seule, et garde LES DEUX lectures
(`audit_pass1`, et les `equities` finales). Personne ne les lisait.

## Ce qui est mesuré, et pourquoi c'est cette quantité-là

Pour chaque décision auditée, on demande : **si l'instrument s'était arrêté à la
passe 1, combien d'équité aurait-il perdu ?**

    pénalité = équité du meilleur coup selon l'arbitrage escaladé
             − équité, selon ce même arbitrage, du coup que la passe 1 disait
               le meilleur

Elle est ≥ 0 par construction, et nulle quand les deux passes désignent le même
coup. C'est exactement l'erreur que l'instrument porterait s'il faisait
confiance à gnubg 3-ply — donc le nombre à publier à côté de toute perte
d'équité mesurée avec lui.

**Les deux échelles se comparent parce qu'on ne compare que DANS une décision.**
`audit_pass1` porte des équités gnubg, les `equities` finales portent des équités
de rollout recalées sur le pivot. Un décalage commun à tous les candidats d'une
même décision disparaît dès qu'on prend un argmax ou une différence — et on ne
fait que cela ici. Comparer les deux colonnes en valeur absolue, en revanche,
n'aurait aucun sens, et ce banc ne le fait nulle part.

## Ce que ce banc ne dit pas

Il mesure l'écart de la passe 1 **à la passe 2**, pas à la vérité. Si le rollout
tronqué était lui-même biaisé, cet écart le manquerait entièrement — c'est le
contrôle de non-biais (`arbiter_bias_t70.py`, contre les tables exactes) qui
répond à cette question-là, et les deux sont nécessaires.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path


def bootstrap(values, weights, draws: int, seed: int):
    """Moyenne pondérée et IC 95 %, le tirage portant sur les décisions."""
    import numpy as np

    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    n = len(v)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean = float((v * w).sum() / w.sum())
    generator = np.random.default_rng(seed)
    picks = generator.integers(0, n, size=(draws, n))
    means = np.sort((v[picks] * w[picks]).sum(axis=1) / w[picks].sum(axis=1))
    return (mean, float(means[int(0.025 * draws)]),
            float(means[int(0.975 * draws) - 1]))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    rows = [json.loads(l) for l in args.registry.read_text().splitlines() if l.strip()]
    audited = [r for r in rows if "audit_pass1" in r]

    print("T70 — le biais de la passe 1, sur ses propres verdicts réaudités")
    print(f"  registre {args.registry.name} : {len(rows)} décisions, "
          f"{len(audited)} auditées "
          f"({100 * len(audited) / len(rows):.1f} %)" if rows else "  registre vide")
    if not audited:
        print("\n  ⚠ AUCUNE décision auditée. L'arbitrage a-t-il tourné avec")
        print("    --audit > 0 ? Sans cet échantillon, le biais de la passe 1")
        print("    n'est pas encadré, et le critère d'acceptation de T70 sur ce")
        print("    point n'est pas rendu — quel que soit le reste.")
        return 1

    penalties, weights, flips, classes = [], [], 0, collections.defaultdict(list)
    for row in audited:
        final = row["equities"]
        first = row["audit_pass1"]
        if len(final) != len(first):
            continue
        best_final = max(range(len(final)), key=lambda i: final[i])
        best_first = max(range(len(first)), key=lambda i: first[i])
        penalty = final[best_final] - final[best_first]
        if best_final != best_first:
            flips += 1
        penalties.append(penalty)
        weights.append(row.get("weight", 1.0))
        classes[row["class"]].append(penalty)

    mean, low, high = bootstrap(penalties, weights, args.bootstrap, args.seed)
    flip_rate = flips / len(penalties) if penalties else 0.0

    print(f"\n  la passe 1 désigne un AUTRE coup que l'arbitrage escaladé :")
    print(f"    {flips}/{len(penalties)} décisions ({100 * flip_rate:.1f} %)")
    print(f"\n  pénalité d'équité si l'instrument s'arrêtait à la passe 1 :")
    print(f"    {mean:.5f} par décision auditée  [{low:.5f} ; {high:.5f}]  "
          f"(IC 95 %, bootstrap {args.bootstrap})")

    # La part des décisions réellement tranchées en passe 1 dans le registre
    # entier : la pénalité ci-dessus ne s'applique qu'à celles-là.
    by_pass = collections.Counter(r["pass_used"] for r in rows)
    share = by_pass.get(1, 0) / len(rows) if rows else 0.0
    print(f"\n  {by_pass.get(1, 0)}/{len(rows)} décisions du registre ont été "
          f"tranchées en passe 1 ({100 * share:.1f} %)")
    print(f"  → contribution au biais du registre entier : "
          f"~{mean * share:.5f} par décision")
    print("    (produit de deux mesures, pas une mesure : la pénalité est")
    print("     estimée sur l'échantillon audité, supposé représentatif des")
    print("     décisions tranchées en passe 1 — ce qu'il est par construction,")
    print("     l'audit étant tiré au hasard parmi elles.)")

    if classes:
        print("\n  par classe de position :")
        for name in sorted(classes, key=lambda k: -len(classes[k])):
            part = classes[name]
            m, lo, hi = bootstrap(part, [1.0] * len(part), args.bootstrap, args.seed)
            print(f"    {name:22s} n={len(part):4d}  {m:.5f}  [{lo:.5f} ; {hi:.5f}]")

    print("\n  ⚠ Ce chiffre mesure l'écart de la passe 1 À LA PASSE 2, jamais à la")
    print("    vérité. Si le rollout tronqué était lui-même biaisé, cet écart le")
    print("    manquerait entièrement — c'est arbiter_bias_t70.py, contre les")
    print("    tables exactes, qui répond à cette question. Les deux sont requis.")

    result = {
        "registry": args.registry.name,
        "decisions": len(rows), "audited": len(penalties),
        "flip_rate": flip_rate, "flips": flips,
        "penalty": mean, "ci95": [low, high],
        "pass1_share": share, "registry_contribution": mean * share,
        "by_pass": {str(k): v for k, v in sorted(by_pass.items())},
        "by_class": {name: {"n": len(part),
                            "penalty": bootstrap(part, [1.0] * len(part),
                                                 args.bootstrap, args.seed)[0]}
                     for name, part in classes.items()},
    }
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"\n  → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
