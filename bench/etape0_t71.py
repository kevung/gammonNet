#!/usr/bin/env python3
"""T71 étape 0 — mesurer le professeur, avant de distiller quoi que ce soit.

## Ce que cette fiche interdit de sauter

T71 distille notre recherche 2-ply dans le réseau. Toute la fiche repose sur une
prémisse jamais vérifiée chez nous : **que la recherche joue effectivement mieux
que le réseau nu**. Si elle ne le fait pas, les étiquettes de T71 sont du bruit
coûteux, et la fiche s'arrête — c'est écrit dans son critère d'acceptation, et
c'est un déclencheur §13 du plan de recherche, pas un échec à cacher.

Le contrôle coûte deux notations sur le registre figé de T70, soit deux fois N
recherches et **aucun rollout** : l'arbitrage est déjà payé.

## Pourquoi apparié, et pourquoi ça change tout

Les deux moteurs jouent **les mêmes décisions**, notées par **le même arbitre**.
La différence par décision élimine la variance de la position, qui domine
largement celle du moteur : deux moyennes séparées à ±0,003 chacune ne
sépareraient rien, alors que leur différence appariée se lit à ±0,0002 près.
C'est la même construction que le match dupliqué de T35, un cran plus bas.

`delta = perte(élève) − perte(professeur)`, donc **delta > 0 veut dire que le
professeur joue mieux**. Le seuil de la fiche est `z > 3`.

## Les trois biais que ce banc porte par écrit

1. **Le corpus est conditionné.** T70 ne retient que les décisions où notre
   2-ply et gnubg divergent. Ce n'est pas un échantillon des décisions de
   backgammon : c'est un échantillon des décisions *qui séparent les moteurs*.
   Le chiffre rendu ici compare deux moteurs sur ce terrain-là, et rien de plus.

2. **Le corpus est conditionné SUR LE PROFESSEUR.** Ces décisions ont été
   retenues parce que le 2-ply y disait quelque chose de particulier. Un corpus
   choisi par un moteur peut le flatter. C'est pourquoi le verdict demande
   `z > 3` et non `z > 2` : la marge absorbe une part de ce doute, elle ne le
   supprime pas.

3. **Les décisions hors registre sont écartées, et cet écart n'est pas neutre.**
   Un moteur qui joue un coup que l'arbitrage n'a pas prix perd sa décision pour
   l'appariement. L'élève 0-ply en produit plus que le professeur, et ce sont
   plutôt ses mauvaises. Les écarter **sous-estime** l'avance du professeur : le
   test est conservateur dans le sens du verdict qu'il cherche à établir. Le
   taux est publié ; au-delà du seuil d'alarme, le banc refuse de conclure.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT))

from bench.measure_t70 import MODEL, score_batch  # noqa: E402

#: Au-delà de cette part de décisions non appariables, l'appariement ne porte
#: plus sur le corpus mais sur ce qu'il en reste — et ce reste est choisi par
#: les moteurs eux-mêmes. Le banc rend alors son chiffre en REFUSANT le verdict.
UNPAIRABLE_ALARM = 0.15

#: Le seuil de la fiche T71. Écrit ici pour qu'il se lise, pas pour se régler.
Z_THRESHOLD = 3.0


def paired_bootstrap(deltas, weights, draws: int, seed: int):
    """Moyenne pondérée de la différence appariée, son IC 95 % et son z.

    Le tirage porte sur les **décisions appariées** — l'unité d'indépendance,
    comme dans `measure_t70.weighted_bootstrap` il porte sur les positions. Le
    z est tiré de l'écart-type bootstrap et non d'une formule fermée : les poids
    de stratification rendent la variance analytique fausse.
    """
    import numpy as np

    values = np.asarray(deltas, dtype=float)
    w = np.asarray(weights, dtype=float)
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0
    mean = float((values * w).sum() / w.sum())
    generator = np.random.default_rng(seed)
    picks = generator.integers(0, n, size=(draws, n))
    sampled = values[picks]
    sampled_w = w[picks]
    means = (sampled * sampled_w).sum(axis=1) / sampled_w.sum(axis=1)
    sigma = float(means.std(ddof=1))
    ordered = np.sort(means)
    low = float(ordered[int(0.025 * draws)])
    high = float(ordered[int(0.975 * draws) - 1])
    z = mean / sigma if sigma > 0 else 0.0
    return mean, low, high, z


def score(rows, model: str, ply: int, workers: int, context: str):
    """Noter un moteur sur le registre : renvoie {index: ligne notée} et le mur."""
    from concurrent.futures import ProcessPoolExecutor

    workers = max(1, min(workers, len(rows)))
    chunks = [rows[i::workers] for i in range(workers)]
    payloads = [(chunk, model, ply, "", 0, context) for chunk in chunks if chunk]
    started = time.perf_counter()
    if len(payloads) == 1:
        gathered = [score_batch(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            gathered = list(pool.map(score_batch, payloads))
    elapsed = time.perf_counter() - started
    return {s["index"]: s for part in gathered for s in part}, elapsed, workers


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", required=True, help="le registre arbitré (.jsonl)")
    parser.add_argument("--model", default=str(MODEL))
    parser.add_argument("--teacher-ply", type=int, default=2)
    parser.add_argument("--student-ply", type=int, default=0)
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

    print("T71 étape 0 — le professeur bat-il l'élève ?")
    print(f"  registre {registry.name} : {len(rows)} décisions, contexte {context}")
    print(f"  professeur : {args.teacher_ply}-ply   élève : {args.student_ply}-ply")
    print(f"  même réseau des deux côtés ({Path(args.model).name}) — "
          "ce qu'on mesure est l'apport de la RECHERCHE, rien d'autre.", flush=True)

    teacher, t_wall, workers = score(rows, args.model, args.teacher_ply,
                                     args.workers, context)
    print(f"  professeur noté en {t_wall:.0f} s de mur sur {workers} processus",
          flush=True)
    student, s_wall, _ = score(rows, args.model, args.student_ply,
                               args.workers, context)
    print(f"  élève noté en {s_wall:.0f} s de mur", flush=True)

    deltas, weights, classes = [], [], {}
    dropped_teacher = dropped_student = dropped_both = 0
    for index, t_row in teacher.items():
        s_row = student.get(index)
        if s_row is None:
            continue
        t_out = t_row["loss"] is None
        s_out = s_row["loss"] is None
        if t_out and s_out:
            dropped_both += 1
            continue
        if t_out:
            dropped_teacher += 1
            continue
        if s_out:
            dropped_student += 1
            continue
        delta = s_row["loss"] - t_row["loss"]
        deltas.append(delta)
        weights.append(t_row["weight"])
        classes.setdefault(t_row["class"], []).append(delta)

    total = len(teacher)
    unpairable = dropped_teacher + dropped_student + dropped_both
    rate = unpairable / total if total else 0.0

    mean, low, high, z = paired_bootstrap(deltas, weights, args.bootstrap, args.seed)

    print(f"\n  décisions appariées : {len(deltas)} / {total}")
    print(f"  non appariables : {unpairable} ({100 * rate:.2f} %) — "
          f"élève seul hors registre {dropped_student}, professeur seul "
          f"{dropped_teacher}, les deux {dropped_both}")
    print(f"\n  avance du professeur, par décision : {mean:+.5f}  "
          f"[{low:+.5f} ; {high:+.5f}]  (IC 95 %, bootstrap {args.bootstrap})")
    print(f"  z = {z:.2f}   (seuil de la fiche : z > {Z_THRESHOLD:g})")

    if classes:
        print("\n  par classe de position :")
        for name in sorted(classes, key=lambda k: -len(classes[k])):
            part = classes[name]
            m, lo, hi, _ = paired_bootstrap(part, [1.0] * len(part),
                                            args.bootstrap, args.seed)
            print(f"    {name:22s} n={len(part):5d}  {m:+.5f}  [{lo:+.5f} ; {hi:+.5f}]")

    refused = rate > UNPAIRABLE_ALARM
    if refused:
        print(f"\n  ⚠ REFUS DE CONCLURE — {100 * rate:.1f} % des décisions ne sont pas")
        print(f"    appariables (seuil {100 * UNPAIRABLE_ALARM:.0f} %). Ce qui reste du")
        print("    corpus a été choisi par les moteurs qu'on compare. Élargir --width")
        print("    et ré-arbitrer avant de lire le z ci-dessus.")
        verdict = "refus"
    elif z > Z_THRESHOLD:
        print("\n  ✓ le professeur bat l'élève au seuil de la fiche — l'étape 1 de T71")
        print("    a une prémisse. Rappel : le corpus est conditionné sur le 2-ply,")
        print("    ce z n'est pas une force absolue (voir la note en tête).")
        verdict = "professeur confirmé"
    elif mean > 0:
        print("\n  ✗ avance positive mais SOUS le seuil — la fiche T71 s'arrête ici et")
        print("    le résultat se publie. Distiller une recherche dont l'avantage")
        print("    n'est pas établi produirait des étiquettes plausibles et fausses.")
        verdict = "sous le seuil"
    else:
        print("\n  ✗ le professeur NE bat PAS l'élève sur ce corpus. La fiche T71")
        print("    s'arrête, et c'est un déclencheur §13 du plan de recherche :")
        print("    le résultat se publie tel quel.")
        verdict = "professeur réfuté"

    result = {
        "registry": registry.name, "context": context,
        "model": Path(args.model).name,
        "teacher_ply": args.teacher_ply, "student_ply": args.student_ply,
        "decisions": total, "paired": len(deltas),
        "unpairable": unpairable, "unpairable_rate": rate,
        "dropped_student_only": dropped_student,
        "dropped_teacher_only": dropped_teacher, "dropped_both": dropped_both,
        "teacher_advantage": mean, "ci95": [low, high], "z": z,
        "z_threshold": Z_THRESHOLD, "verdict": verdict,
        "teacher_seconds": t_wall, "student_seconds": s_wall, "workers": workers,
        "core_hours": (t_wall + s_wall) * workers / 3600,
        "by_class": {name: {"n": len(part),
                            "advantage": paired_bootstrap(part, [1.0] * len(part),
                                                          args.bootstrap,
                                                          args.seed)[0]}
                     for name, part in classes.items()},
    }
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"\n  → {args.out}")

    print(f"\n  coût de l'étape 0 : {result['core_hours']:.2f} h·cœur")
    return 0 if verdict == "professeur confirmé" else 1


if __name__ == "__main__":
    raise SystemExit(main())
