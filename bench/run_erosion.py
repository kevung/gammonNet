#!/usr/bin/env python3
"""T36 — l'érosion de l'avantage avec la profondeur.

Le seul chiffre de force du dépôt — **+0,0400 ppg** contre GNU Backgammon — est
mesuré en 0-ply. Le seul signal disponible sur son transport en profondeur dit
qu'il **rétrécit** : l'auteur du modèle mesure +57,8 mEq/partie en 0-ply contre
+45,0 en 2-ply, et avance que *« gnubg's base networks are more tuned for deep
search than ours »*.

Si l'érosion est forte, le chemin vers l'objectif passe par la phase 4 et non
par le videau. **Mieux vaut le savoir avant d'avoir construit le videau** que
d'attribuer ensuite au mauvais maillon un résultat décevant.

## Ce que ce harnais mesure, et pourquoi il ne le mesure pas trois fois

La quantité voulue est la **pente**, pas les trois niveaux. Trois mesures
indépendantes donneraient à la pente la variance de trois tirages de dés ; les
trois configurations partagent donc leurs dés (`dice_key`), et l'intervalle sur
chaque différence est calculé sur les **mêmes indices de paires** que celui sur
chaque niveau.

Concrètement, un rééchantillonnage bootstrap tire des indices de paires, puis
recalcule dans le même tirage les trois moyennes **et** leurs différences. Deux
mesures qui partagent leurs dés ne sont pas indépendantes, et un intervalle sur
leur différence qui l'ignorerait serait trop large — la façon la plus commune de
rater un effet réel.

## La profondeur est la même des deux côtés

`gammonnet-k-ply` contre `gnubg-k-ply`. Comparer notre 2-ply à leur 0-ply
mesurerait la profondeur, pas les moteurs.

Usage :
    python bench/run_erosion.py --pilot                 # débit, avant de dimensionner
    python bench/run_erosion.py --pairs 20000 --workers 32 --out docs/mesures/t36.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.arena import SearchEngine, play_duplicate  # noqa: E402
from gammonnet.gnubg_engine import GnubgEngine  # noqa: E402

#: La clé de dés partagée par les trois configurations. Une constante, pas les
#: noms des moteurs : c'est tout l'objet de l'appariement.
DICE_KEY = "t36-erosion"

#: Le fichier de suivi. Une mesure qui dure des heures ne doit pas être aveugle :
#: le premier pilote de T36 a tourné vingt minutes sans rien dire, alors qu'il
#: était mal dimensionné et n'aurait jamais fini. Chaque paire terminée y ajoute
#: une ligne — `wc -l` donne l'avancement, et la date de la dernière ligne dit si
#: le calcul progresse encore.
PROGRESS = Path(os.environ.get("T36_PROGRESS", "/tmp/t36-progress.log"))

#: Les configurations comparées, **dimensionnées sur mesure** par
#: `bench/cost_by_depth.py` et non choisies a priori.
#:
#: L'INDEXATION DU FILTRE : `filter[d]` est ce qui survit à un nœud de
#: profondeur **restante** `d`. La racine d'une recherche à `k` plies lit donc
#: `filter[k]`, et `filter[0]` n'est jamais lu. Le premier pilote de T36 a
#: écrit `(5,)` pour un 1-ply, n'a rien filtré du tout, et ne terminait pas.
#:
#: Coûts mesurés, par décision (25 positions, médiane 23 coups légaux) :
#:
#:     0-ply           25 éval    0,0024 s      gnubg 0,258 s
#:     1-ply/0-5    1 898 éval    0,163 s       gnubg 0,312 s
#:     2-ply/0-1-5 38 244 éval    3,290 s       gnubg 0,329 s
#:
#: **Réserve à ne pas perdre.** T31 a mesuré la qualité du filtre à la RACINE
#: seulement — sa référence était un 2-ply dont l'intérieur n'était pas filtré.
#: La garde intérieure de 1 employée ici n'a donc **jamais été mesurée en
#: qualité**. Elle est un choix de coût, et le rapport doit le dire.
DEFAULT_CONFIGS = [
    (0, ()),
    (1, (0, 5)),
    (2, (0, 1, 5)),
]


def _worker(payload):
    """Un processus : toutes les configurations, sur son lot d'indices.

    Les moteurs sont construits **une fois** par processus et non par indice :
    ils chargent le réseau à la première décision et le gardent. Les
    reconstruire relirait les 2 Mio de poids à chaque partie.
    """
    configs, base_seed, indices = payload

    # GNU Backgammon lui-même, et non `gnubg-nn` : celui-ci plante à partir du
    # 1-ply sur les positions de bearoff (trouvé en T36), et sa table d'équité
    # n'est pas la nôtre (T32). Voir `gammonnet.gnubg_engine`.
    pairs = [
        (SearchEngine(ply=ply, filter=filt), GnubgEngine(ply=ply, filter=filt))
        for ply, filt in configs
    ]

    rows, timings = [], [0.0] * len(configs)
    for index in indices:
        row = []
        for slot, (model, oracle) in enumerate(pairs):
            start = time.perf_counter()
            points, stalled = play_duplicate(
                model, oracle, base_seed, index, dice_key=DICE_KEY
            )
            timings[slot] += time.perf_counter() - start
            row.append((points, stalled))
        rows.append(row)
        # Une ligne par paire terminée. `O_APPEND` sur une écriture courte est
        # atomique, donc les processus n'ont pas à se coordonner.
        with open(PROGRESS, "a") as fh:
            fh.write(f"{time.time():.0f} {index}\n")
    return rows, timings


def run(configs, pairs: int, base_seed: int, workers: int):
    """Joue toutes les configurations sur les mêmes `pairs` paires de dés."""
    from concurrent.futures import ProcessPoolExecutor

    indices = list(range(pairs))

    if workers <= 1:
        gathered = [_worker((configs, base_seed, indices))]
        chunks = [indices]
    else:
        chunks = [indices[i::workers] for i in range(workers)]
        chunks = [c for c in chunks if c]
        with ProcessPoolExecutor(max_workers=len(chunks)) as pool:
            gathered = list(
                pool.map(_worker, [(configs, base_seed, c) for c in chunks])
            )

    # Réassemblé dans l'ordre des indices : le résultat ne doit pas dépendre de
    # la façon dont le travail a été réparti.
    by_index = {}
    timings = [0.0] * len(configs)
    for chunk, (rows, chunk_timings) in zip(chunks, gathered):
        by_index.update(dict(zip(chunk, rows)))
        for slot, value in enumerate(chunk_timings):
            timings[slot] += value

    ordered = [by_index[i] for i in indices]
    return ordered, timings


def analyse(ordered, configs, bootstrap: int, seed: int):
    """Niveaux, différences, et leurs intervalles — tirés du même rééchantillonnage."""
    import numpy as np

    n = len(ordered)
    k = len(configs)

    # points[i][j] : points nets du modèle sur la paire i, configuration j.
    points = np.array([[row[j][0] for j in range(k)] for row in ordered], dtype=float)
    stalled = [sum(1 for row in ordered if row[j][1]) for j in range(k)]

    # ppg : une paire vaut deux parties.
    ppg = points.mean(axis=0) / 2.0

    generator = np.random.default_rng(seed)
    draws = generator.integers(0, n, size=(bootstrap, n))
    # (bootstrap, k) — chaque ligne est un univers rééchantillonné complet, donc
    # les k configurations y sont corrélées comme elles le sont dans les données.
    resampled = points[draws].mean(axis=1) / 2.0

    def interval(column):
        ordered_column = np.sort(column)
        return (
            float(ordered_column[int(0.025 * bootstrap)]),
            float(ordered_column[int(0.975 * bootstrap) - 1]),
        )

    levels = [
        {
            "ply": configs[j][0],
            "filter": list(configs[j][1]),
            "ppg": float(ppg[j]),
            "ci95": list(interval(resampled[:, j])),
            "win_rate": float((points[:, j] > 0).mean()
                              + 0.5 * (points[:, j] == 0).mean()),
            "stalled_pairs": stalled[j],
        }
        for j in range(k)
    ]

    # Les différences, sur les mêmes tirages. C'est ici que l'appariement paie.
    differences = []
    for j in range(1, k):
        delta = ppg[j] - ppg[0]
        column = resampled[:, j] - resampled[:, 0]
        low, high = interval(column)
        differences.append({
            "from_ply": configs[0][0],
            "to_ply": configs[j][0],
            "delta_ppg": float(delta),
            "ci95": [low, high],
            # Un intervalle qui ne contient pas zéro établit que la profondeur a
            # déplacé l'avantage. Qu'il le contienne n'établit pas le contraire.
            "significant": not (low <= 0.0 <= high),
        })

    return levels, differences


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pairs", type=int, default=200,
                        help="paires de dés dupliqués ; chacune vaut 2 parties")
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--seed", type=int, default=20260806)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--pilot", action="store_true",
                        help="petit volume, pour mesurer le débit avant de dimensionner")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    configs = DEFAULT_CONFIGS
    pairs = 20 if args.pilot else args.pairs

    def label(ply, filt):
        return f"{ply}-ply" + ("/" + "-".join(map(str, filt[1:])) if filt else "")

    print("T36 — érosion de l'avantage avec la profondeur")
    print("  configurations : " + ", ".join(label(p, f) for p, f in configs))
    print(f"  {pairs} paires de dés partagées = {pairs * 2} parties par configuration")
    print(f"  graine {args.seed}, {args.workers} processus")
    print(f"  démarré à {time.strftime('%H:%M:%S')}", flush=True)
    print(f"  suivi : {PROGRESS}\n", flush=True)

    start = time.perf_counter()
    ordered, timings = run(configs, pairs, args.seed, args.workers)
    elapsed = time.perf_counter() - start

    levels, differences = analyse(ordered, configs, args.bootstrap, args.seed)

    print(f"{'config':<16}{'ppg':>10}{'IC 95 %':>24}{'victoires':>12}{'s/partie':>11}")
    for level, cpu in zip(levels, timings):
        label = f"{level['ply']}-ply" + (
            "/" + "-".join(map(str, level["filter"][1:])) if level["filter"] else "")
        low, high = level["ci95"]
        per_game = cpu / (pairs * 2)
        print(f"{label:<16}{level['ppg']:>+10.4f}"
              f"{f'[{low:+.4f} ; {high:+.4f}]':>24}"
              f"{level['win_rate'] * 100:>11.1f} %{per_game:>11.2f}")
        if level["stalled_pairs"]:
            print(f"  ⚠ {level['stalled_pairs']} paires abandonnées")

    if differences:
        print("\nLa pente — différences appariées, mêmes dés, même rééchantillonnage :")
        for d in differences:
            low, high = d["ci95"]
            verdict = "significative" if d["significant"] else "dans le bruit"
            print(f"  {d['from_ply']}-ply → {d['to_ply']}-ply : "
                  f"{d['delta_ppg']:+.4f} ppg [{low:+.4f} ; {high:+.4f}] — {verdict}")

    total_games = pairs * 2 * len(configs)
    print(f"\n{total_games} parties en {elapsed / 60:.1f} min "
          f"({total_games / elapsed:.1f} parties/s sur {args.workers} processus)")

    if args.pilot:
        print("\nDimensionnement, à partir de ce débit :")
        for level, cpu in zip(levels, timings):
            label = f"{level['ply']}-ply"
            per_pair = cpu / pairs / args.workers
            for target in (10_000, 50_000, 100_000):
                hours = per_pair * target / 3600
                print(f"  {label:<8} {target:>7} paires → {hours:>6.2f} h")

    payload = {
        "task": "T36",
        "seed": args.seed,
        "pairs": pairs,
        "dice_key": DICE_KEY,
        "bootstrap": args.bootstrap,
        "levels": levels,
        "differences": differences,
        "cpu_seconds": timings,
        "elapsed_seconds": elapsed,
        "workers": args.workers,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=2) + "\n")
        print(f"\nécrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
