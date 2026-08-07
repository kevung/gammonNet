#!/usr/bin/env python3
"""T3A — la qualité de tri du réseau d'élagage, et ce qu'elle achète.

## La question

`gn_search` filtre : à chaque nœud, seuls les k meilleurs coups (au sens du
0-ply) descendent en profondeur. Si un réseau ~80x moins cher trie ces coups
presque comme le fait le grand réseau, remplacer le grand réseau par le petit
pour CE tri — et ne garder le grand que pour les k survivants — coûte
beaucoup moins cher pour (presque) le même classement.

Deux choses à mesurer, séparément, puis multipliées :

1. **La qualité du tri** — sur des décisions tenues hors de l'entraînement
   (graine différente de celle de `tools/build_prune_corpus.py`) : le coup que
   le GRAND réseau classe premier au 0-ply est-il dans le top-k du PETIT ?
   Pour k dans {1, 2, 3, 5}, avec intervalle de Wilson.
2. **Le coût** — évaluations par seconde des deux réseaux, chronométrées par
   le même binaire C que `make bench-infer` (`build/bench_infer`), jamais par
   PyTorch : PyTorch mesurerait un chemin que rien ne sert jamais en
   production.

## Contact et course, séparément

Les positions de contact viennent de `bench/decision_loss.corpus()`, réutilisé
tel quel. Les positions de course n'ont pas d'équivalent dans ce module : la
fonction est répliquée ici avec le filtre inversé (`race_corpus`), sur le même
squelette de marche aléatoire au 0-ply.

## Le pilote de dimensionnement

La mesure démarre par une tranche courte (`--pilot`), entièrement
parallélisée, dont le débit observé donne une projection du temps pour le
reste. Rien n'est jeté : la tranche pilote fait partie du résultat final,
elle ne fait que s'exécuter — et se rapporter — en premier.

Usage :
    python bench/prune_quality.py --contact 2000 --race 500 --workers 26
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from decision_loss import corpus, has_contact  # noqa: E402
from gammonnet import codec  # noqa: E402
from gammonnet.arena import BLACK, opening_roll  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import Position  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

GRAND_MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
SMALL_MODEL = ROOT / "models" / "prune_32.bin"
REFERENCE_BIN = ROOT / "build" / "reference.bin"
BENCH_INFER = ROOT / "build" / "bench_infer"

#: Distinct from `tools/build_prune_corpus.BASE_SEED` (20260807) — the point
#: of the measurement is that these positions were never in the training set.
MEASURE_SEED = 20260808

KS = (1, 2, 3, 5)

PROGRESS = Path(os.environ.get("T3A_QUALITY_PROGRESS", "/tmp/t3a-prune-quality-progress.log"))


def race_corpus(count: int, seed: int, network) -> list[tuple[Position, int, int]]:
    """Mirror of `decision_loss.corpus()`, contact filter inverted.

    Same walk — 0-ply self-play with `network`, decisions kept once there are
    at least 3 legal plays — the only change is `not has_contact(position)`
    instead of `has_contact(position)`. Duplicating ~15 lines here beats
    parametrising `corpus()` itself: that function is frozen behind T36's
    published numbers, and a shared knob would risk moving it.
    """
    rng = random.Random(seed)
    out: list[tuple[Position, int, int]] = []

    while len(out) < count:
        position = Position.initial()
        first, d1, d2 = opening_roll(rng)
        if first == BLACK:
            position = position.swapped_turn()

        for _ in range(400):
            if position.is_over():
                break
            plays = position.legal_plays(d1, d2)
            if len(plays) >= 3 and not has_contact(position):
                out.append((position, d1, d2))
                if len(out) >= count:
                    break
            if plays:
                ranked = search_plays(network, position, d1, d2, SearchConfig(ply=0))
                position = ranked[0].play.result
            else:
                position = position.swapped_turn()
            d1, d2 = rng.randint(1, 6), rng.randint(1, 6)

    return out[:count]


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalle de Wilson — voir `bench/analyse_filter.py`, même formule."""
    if total == 0:
        return (float("nan"), float("nan"))
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


# ── Measurement, one worker's slice ──────────────────────────────────


def _measure_chunk(payload):
    cases, grand_path, small_path, worker_id = payload
    grand = Network.load(grand_path)
    small = Network.load(small_path)

    hits = {k: 0 for k in KS}
    n_sum = 0
    n_cases = 0
    ties = 0  # grand's top-1 not found among small's ranking at all (should not happen)

    for position, d1, d2 in cases:
        grand_ranked = search_plays(grand, position, d1, d2, SearchConfig(ply=0))
        small_ranked = search_plays(small, position, d1, d2, SearchConfig(ply=0))
        if not grand_ranked or not small_ranked:
            continue

        grand_top1_id = codec.position_id(grand_ranked[0].play.result)
        small_ids = [codec.position_id(c.play.result) for c in small_ranked]

        try:
            rank = small_ids.index(grand_top1_id)
        except ValueError:
            ties += 1
            rank = None

        n_cases += 1
        n_sum += len(grand_ranked)
        for k in KS:
            if rank is not None and rank < k:
                hits[k] += 1

        with open(PROGRESS, "a") as fh:
            fh.write(f"w{worker_id}\n")

    grand.close()
    small.close()
    return hits, n_sum, n_cases, ties


def run_measurement(cases: list[tuple[Position, int, int]], workers: int,
                    grand_path: str, small_path: str):
    workers = max(1, min(workers, len(cases)))
    chunks = [cases[i::workers] for i in range(workers)]
    payloads = [(chunk, grand_path, small_path, i)
                for i, chunk in enumerate(chunks) if chunk]

    start = time.perf_counter()
    if len(payloads) == 1:
        gathered = [_measure_chunk(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            gathered = list(pool.map(_measure_chunk, payloads))
    elapsed = time.perf_counter() - start

    hits = {k: 0 for k in KS}
    n_sum = 0
    n_cases = 0
    ties = 0
    for part_hits, part_n_sum, part_n_cases, part_ties in gathered:
        for k in KS:
            hits[k] += part_hits[k]
        n_sum += part_n_sum
        n_cases += part_n_cases
        ties += part_ties

    return {"hits": hits, "n_cases": n_cases, "n_sum": n_sum, "ties": ties,
            "elapsed": elapsed}


def combine(a: dict, b: dict) -> dict:
    return {
        "hits": {k: a["hits"][k] + b["hits"][k] for k in KS},
        "n_cases": a["n_cases"] + b["n_cases"],
        "n_sum": a["n_sum"] + b["n_sum"],
        "ties": a["ties"] + b["ties"],
        "elapsed": a["elapsed"] + b["elapsed"],
    }


def measure_category(label: str, cases: list[tuple[Position, int, int]], workers: int,
                     pilot: int, grand_path: str, small_path: str) -> dict:
    print(f"\n  [{label}] {len(cases)} décisions, pilote {min(pilot, len(cases))} d'abord")
    pilot_n = min(pilot, len(cases))
    pilot_cases = cases[:pilot_n]
    rest_cases = cases[pilot_n:]

    pilot_result = run_measurement(pilot_cases, workers, grand_path, small_path)
    rate = pilot_result["n_cases"] / pilot_result["elapsed"] if pilot_result["elapsed"] > 0 else float("inf")
    projected_rest = len(rest_cases) / rate if rate > 0 else float("nan")
    print(f"    pilote : {pilot_result['n_cases']} décisions en {pilot_result['elapsed']:.1f} s "
          f"({rate:.1f} décisions/s) — reste ({len(rest_cases)}) projeté à {projected_rest:.1f} s")

    if rest_cases:
        rest_result = run_measurement(rest_cases, workers, grand_path, small_path)
        result = combine(pilot_result, rest_result)
    else:
        result = pilot_result

    print(f"    total : {result['n_cases']} décisions en {result['elapsed']:.1f} s")
    if result["ties"]:
        print(f"    ATTENTION : {result['ties']} décisions où le top-1 du grand réseau "
              f"n'apparaît dans AUCUN rang du petit (devrait être 0 — même ensemble de "
              f"coups légaux des deux côtés)")
    return result


# ── Cost, via the real C path ────────────────────────────────────────


def ensure_reference() -> None:
    if not REFERENCE_BIN.is_file():
        subprocess.run([sys.executable, "tools/dump_reference.py"], cwd=ROOT, check=True)
    if not BENCH_INFER.is_file():
        subprocess.run(["make", "bench-infer"], cwd=ROOT, check=True)


def measure_cost(model_path: Path) -> dict:
    ensure_reference()
    result = subprocess.run(
        [str(BENCH_INFER), str(model_path), str(REFERENCE_BIN)],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


# ── Report ────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--contact", type=int, default=2000)
    parser.add_argument("--race", type=int, default=500)
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--pilot", type=int, default=300)
    parser.add_argument("--seed", type=int, default=MEASURE_SEED)
    parser.add_argument("--grand", type=Path, default=GRAND_MODEL)
    parser.add_argument("--small", type=Path, default=SMALL_MODEL)
    parser.add_argument("--out", default="docs/mesures/t3a-prune-quality.json")
    args = parser.parse_args()

    if not args.small.is_file():
        print(f"{args.small} absent — lancer tools/train_prune.py d'abord", file=sys.stderr)
        return 1

    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text("")

    print("T3A — qualité de tri et coût du réseau d'élagage")
    print(f"  grand réseau  : {args.grand.name}")
    print(f"  petit réseau  : {args.small.name}")
    print(f"  graine de mesure : {args.seed} (distincte de celle de l'entraînement)")
    print(f"  suivi : {PROGRESS}", flush=True)

    # ── Corpus ────────────────────────────────────────────────────────
    print("\n1. Construction des corpus (0-ply, notre moteur, GRAND réseau)")
    grand = Network.load(str(args.grand))
    t0 = time.perf_counter()
    contact_cases = corpus(args.contact, args.seed, grand)
    t_contact = time.perf_counter() - t0
    print(f"  contact : {len(contact_cases)} décisions en {t_contact:.1f} s")

    t0 = time.perf_counter()
    race_cases = race_corpus(args.race, args.seed + 1, grand)
    t_race = time.perf_counter() - t0
    print(f"  course  : {len(race_cases)} décisions en {t_race:.1f} s")
    grand.close()

    # ── Measurement ──────────────────────────────────────────────────
    print("\n2. Qualité du tri — top-k du petit contient-il le top-1 du grand ?")
    results = {
        "contact": measure_category("contact", contact_cases, args.workers, args.pilot,
                                    str(args.grand), str(args.small)),
        "race": measure_category("course", race_cases, args.workers, args.pilot,
                                 str(args.grand), str(args.small)),
    }

    # ── Cost ─────────────────────────────────────────────────────────
    print("\n3. Coût mesuré d'une évaluation — chemin C réel, build/bench_infer")
    grand_cost = measure_cost(args.grand)
    small_cost = measure_cost(args.small)
    # Le petit réseau est moins CHER : le facteur se lit sur le TEMPS par éval
    # (grand / petit), pas sur les éval/s (qui inverserait le rapport).
    speedup = grand_cost["msPerEval"] / small_cost["msPerEval"]
    print(f"  grand : {grand_cost['evalsPerSecond']:,.1f} éval/s "
          f"({grand_cost['msPerEval']:.6f} ms/éval)")
    print(f"  petit : {small_cost['evalsPerSecond']:,.1f} éval/s "
          f"({small_cost['msPerEval']:.6f} ms/éval)")
    print(f"  petit {speedup:.1f}× moins cher par évaluation (chemin C, build/bench_infer)")

    # ── Report table ─────────────────────────────────────────────────
    print("\n4. Taux top-k, intervalle de Wilson à 95 %, et facture économisée")
    print(f"  {'':8}{'k':>3}  {'taux':>8}  {'IC 95%':>18}  {'N moy.':>7}  "
          f"{'facture économisée':>20}  {'accélération eff.':>18}")
    report_rows = []
    for category in ("contact", "race"):
        r = results[category]
        n_avg = r["n_sum"] / r["n_cases"] if r["n_cases"] else float("nan")
        for k in KS:
            rate = r["hits"][k] / r["n_cases"] if r["n_cases"] else float("nan")
            low, high = wilson(r["hits"][k], r["n_cases"])
            naive_bill = n_avg * grand_cost["msPerEval"]
            new_bill = n_avg * small_cost["msPerEval"] + k * grand_cost["msPerEval"]
            saved_fraction = 1.0 - new_bill / naive_bill if naive_bill > 0 else float("nan")
            eff_speedup = naive_bill / new_bill if new_bill > 0 else float("inf")
            print(f"  {category:8}{k:>3}  {rate * 100:>7.2f}%  "
                  f"[{low * 100:>6.2f} ; {high * 100:>6.2f}]  {n_avg:>7.1f}  "
                  f"{saved_fraction * 100:>19.1f}%  ×{eff_speedup:>16.2f}")
            report_rows.append({
                "category": category, "k": k, "rate": rate, "ci95": [low, high],
                "n_avg": n_avg, "saved_fraction": saved_fraction,
                "effective_speedup": eff_speedup,
            })

    payload = {
        "task": "T3A",
        "measure_seed": args.seed,
        "grand_model": str(args.grand.relative_to(ROOT)),
        "small_model": str(args.small.relative_to(ROOT)),
        "contact": {"decisions": results["contact"]["n_cases"],
                    "hits": results["contact"]["hits"],
                    "n_sum": results["contact"]["n_sum"],
                    "elapsed_seconds": results["contact"]["elapsed"],
                    "ties": results["contact"]["ties"]},
        "race": {"decisions": results["race"]["n_cases"],
                 "hits": results["race"]["hits"],
                 "n_sum": results["race"]["n_sum"],
                 "elapsed_seconds": results["race"]["elapsed"],
                 "ties": results["race"]["ties"]},
        "cost": {"grand": grand_cost, "small": small_cost, "speedup": speedup},
        "rows": report_rows,
    }
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nécrit dans {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
