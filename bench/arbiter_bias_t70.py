#!/usr/bin/env python3
"""T70 — le contrôle sans lequel l'arbitre n'arbitre rien.

> *« Un arbitre qu'on n'a pas vérifié n'arbitre rien. »* — `PLAN.md`, T39

L'arbitre escaladé rend des équités et des intervalles. Rien, dans son
fonctionnement, ne garantit que ces intervalles sont honnêtes : un rollout
biaisé rend des nombres tout aussi présentables qu'un rollout juste, et sur du
contact il n'existe aucune vérité à quoi les comparer.

Il en existe une sur le **domaine de la table bilatérale** : là, l'équité est
calculée exactement, sans variance ni modèle. C'est le seul endroit où l'on peut
demander à l'arbitre de se tromper visiblement, et c'est donc là qu'on
l'interroge.

## Le protocole

Des positions de bearoff tirées dans le domaine, chacune avec plusieurs suites
candidates. Pour chaque décision :

- la **vérité** : les différences d'équité exactes entre candidats, lues dans la
  table ;
- l'**arbitre** : les mêmes différences, mesurées par `rollout_candidates_paired`
  avec les réglages retenus pour la campagne — donc en court-circuitant la passe
  0, qui lirait la table et rendrait le contrôle circulaire.

On rapporte le z de chaque écart, `(arbitre − exact) / erreur-type`. Un arbitre
non biaisé donne des z ~ N(0, 1) : environ 95 % dans ±1,96, moyenne compatible
avec zéro. C'est cela qu'on regarde, pas une impression de proximité.

## Ce que ce banc ne prouve pas

Que l'arbitre est non biaisé **sur le contact**. Il prouve qu'il l'est là où on
peut le vérifier, ce qui est le maximum disponible — et c'est déjà ce qui
distingue un instrument d'une opinion. Le biais propre à la passe 1 (gnubg
3-ply) est mesuré ailleurs, par l'audit de `bench/arbitrate_t70.py`.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from concurrent.futures import ProcessPoolExecutor
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT))

from gammonnet.bearoff import TwoSidedBearoff  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rollout import RolloutConfig, rollout_candidates_paired  # noqa: E402
from gammonnet.rules import BLACK, NUM_POINTS, WHITE, Position  # noqa: E402
from gammonnet.search import SearchConfig  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"


def random_bearoff(rng: random.Random, table: TwoSidedBearoff) -> Position:
    """Le tirage de `bench/exact_gap.py` : uniforme sur le nombre de pions."""
    while True:
        points = [0] * NUM_POINTS
        for player in (WHITE, BLACK):
            count = rng.randint(2, table.chequers)
            for _ in range(count):
                point = rng.randint(1, table.points)
                index = point - 1 if player == WHITE else NUM_POINTS - point
                points[index] += 1 if player == WHITE else -1
        off = (15 - sum(n for n in points if n > 0),
               15 + sum(n for n in points if n < 0))
        position = Position(tuple(points), (0, 0), off, WHITE)
        if position.is_valid() and not position.is_over() and table.contains(position):
            return position


def cases(rng: random.Random, table: TwoSidedBearoff, count: int, width: int):
    """Des décisions de bearoff : une position, ses suites, leurs équités exactes."""
    out = []
    while len(out) < count:
        position = random_bearoff(rng, table)
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = position.legal_plays(d1, d2)
        results = []
        seen = set()
        for play in plays:
            key = play.result.points, play.result.off
            if key in seen or play.result.is_over():
                continue
            if not table.contains(play.result):
                results = []
                break
            seen.add(key)
            results.append(play.result)
            if len(results) >= width:
                break
        if len(results) < 2:
            continue
        # L'équité vue par celui qui a joué : la table répond pour le joueur au
        # trait de la position confiée, soit son adversaire.
        exact = [-table.equity(r).cubeless for r in results]
        out.append((position, results, exact))
    return out



def _bias_batch(payload):
    """La part d'un processus : ses index, et rien d'autre à sérialiser.

    Chaque processus RECONSTRUIT les cas au lieu de les recevoir. `cases()` ne
    fait que des lectures de table — c'est bon marché — tandis que faire voyager
    des `Position` et un réseau ctypes entre processus ne l'est pas, et n'est
    même pas possible sans les encoder. Reconstruire est déterministe : la même
    graine rend la même liste, ce que le test de non-régression vérifie.

    La graine d'une décision vaut `seed + 7919 * index`, donc le résultat ne
    dépend NI du nombre de processus NI du découpage. C'est ce qui rend ce banc
    parallélisable sans changer son chiffre.
    """
    (indices, seed, decisions, width, truncate, trials, target_se,
     min_trials, no_vr) = payload

    table = TwoSidedBearoff(str(DATABASE))
    network = Network.load(str(MODEL))
    try:
        built = cases(random.Random(seed), table, decisions, width)
        wanted = set(indices)
        scores = []
        for index, (_position, results, exact) in enumerate(built):
            if index not in wanted:
                continue
            config = RolloutConfig(
                trials=trials, truncate=truncate,
                seed=seed + 7919 * index, policy=SearchConfig(ply=0),
                variance_reduction=not no_vr,
                target_se=target_se, min_trials=min_trials)
            _eq, differences, errors, _trials = rollout_candidates_paired(
                network, results, config, pivot=0)
            for candidate in range(1, len(results)):
                truth = exact[candidate] - exact[0]
                error = errors[candidate]
                if error <= 0:
                    continue
                scores.append((differences[candidate] - truth) / error)
        return len(built), scores
    finally:
        table.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--decisions", type=int, default=60)
    parser.add_argument("--width", type=int, default=4)
    parser.add_argument("--truncate", type=int, default=11)
    parser.add_argument("--trials", type=int, default=1296)
    parser.add_argument("--target-se", type=float, default=0.006)
    parser.add_argument("--min-trials", type=int, default=72)
    parser.add_argument("--no-vr", action="store_true")
    parser.add_argument("--workers", type=int, default=26,
                        help="processus. Le contrôle est massivement "
                             "parallèle et le laisser mono-cœur fait "
                             "attendre toute la campagne derrière lui.")
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    if not DATABASE.exists():
        print(f"table bilatérale absente : {DATABASE}", file=sys.stderr)
        return 2

    table = TwoSidedBearoff(str(DATABASE))
    network = Network.load(str(MODEL))
    rng = random.Random(args.seed)

    print("T70 — contrôle de non-biais de l'arbitre, contre la table exacte")
    print(f"  {args.decisions} décisions de bearoff, {args.width} candidats max")
    print(f"  tronqué à {args.truncate}, VR {'non' if args.no_vr else 'oui'}, "
          f"se visé {args.target_se}", flush=True)

    built = cases(rng, table, args.decisions, args.width)
    print(f"  {len(built)} cas construits, {args.workers} processus", flush=True)

    started = time.perf_counter()
    common = (args.seed, args.decisions, args.width, args.truncate, args.trials,
              args.target_se, args.min_trials, args.no_vr)
    workers = max(1, min(args.workers, len(built)))
    if workers == 1:
        _count, scores = _bias_batch((list(range(len(built))),) + common)
    else:
        # Réparti en peigne (`i::workers`) et non en blocs : les décisions de
        # bearoff n'ont pas toutes le même coût, et un bloc de positions
        # coûteuses ferait attendre les autres processus. Le résultat ne dépend
        # de toute façon pas du découpage.
        shares = [list(range(len(built)))[i::workers] for i in range(workers)]
        payloads = [(share,) + common for share in shares if share]
        scores = []
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            for _count, part in pool.map(_bias_batch, payloads):
                scores.extend(part)
    elapsed = time.perf_counter() - started

    if not scores:
        print("aucun z calculable", file=sys.stderr)
        return 1

    n = len(scores)
    mean = sum(scores) / n
    variance = sum((z - mean) ** 2 for z in scores) / (n - 1) if n > 1 else 0.0
    deviation = math.sqrt(variance)
    inside = sum(1 for z in scores if abs(z) <= 1.96) / n
    mean_error = deviation / math.sqrt(n)

    print(f"\n  {n} écarts appariés en {elapsed:.0f} s")
    print(f"  moyenne des z : {mean:+.4f} ± {mean_error:.4f} "
          f"(attendu 0)   z de la moyenne = {mean / mean_error:+.2f}")
    print(f"  écart-type des z : {deviation:.4f} (attendu 1)")
    print(f"  dans ±1,96 : {100 * inside:.1f} % (attendu ~95 %)")

    # Le verdict, écrit avant de regarder : |z de la moyenne| < 3, et un
    # écart-type qui n'est ni deux fois trop grand ni deux fois trop petit.
    # Un écart-type trop PETIT n'est pas une bonne nouvelle : il voudrait dire
    # que l'arbitre annonce des intervalles plus larges que sa vraie dispersion,
    # donc qu'il se déclare moins sûr qu'il ne l'est, et la campagne paierait
    # des essais pour rien.
    unbiased = abs(mean / mean_error) < 3.0
    calibrated = 0.5 < deviation < 2.0
    print(f"\n  verdict : "
          f"{'non biaisé' if unbiased else 'BIAIS DÉTECTÉ'}, "
          f"{'intervalles calibrés' if calibrated else 'INTERVALLES MAL CALIBRÉS'}")
    if not (unbiased and calibrated):
        print("  → l'arbitre ne passe pas son propre contrôle. Aucune campagne "
              "ne doit tourner avec ces réglages (T39, règle reprise par T70).")

    result = {"decisions": len(built), "pairs": n, "mean_z": mean,
              "mean_z_error": mean_error, "sd_z": deviation,
              "inside_1_96": inside, "unbiased": unbiased,
              "calibrated": calibrated, "seconds": elapsed,
              "truncate": args.truncate, "variance_reduction": not args.no_vr,
              "target_se": args.target_se, "min_trials": args.min_trials}
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"\n  → {args.out}")
    table.close()
    return 0 if (unbiased and calibrated) else 1


if __name__ == "__main__":
    raise SystemExit(main())
