#!/usr/bin/env python3
"""T05 — establish the real throughputs, once.

> **Une conclusion de performance se mesure, elle ne se déduit pas.**

Every figure printed here is tagged **MESURÉ** or **EXTRAPOLÉ**, and the
extrapolated ones say what they were extrapolated from. That distinction is the
point of the task, not a courtesy.

What this bench does **not** measure: gammonNet's own network evaluation rate.
There is no network loaded yet — T10 lives on the browser track. Anything said
about it here would be invention.

Usage:
    python bench/bench_throughput.py                    # full run
    python bench/bench_throughput.py --quick            # smaller samples
"""

from __future__ import annotations

import argparse
import os
import random
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import Position  # noqa: E402
from gammonnet import codec  # noqa: E402
from gammonnet import gnubg_board as gb  # noqa: E402
from gammonnet.arena import OracleEngine, RandomEngine, play_pair  # noqa: E402

import gnubg_nn  # noqa: E402

SEED = 20260803
ALL_CORES = os.cpu_count() or 1


def measured(label: str, value: str) -> None:
    print(f"  {label:<52} {value:>18}   MESURÉ")


def extrapolated(label: str, value: str, basis: str) -> None:
    print(f"  {label:<52} {value:>18}   EXTRAPOLÉ")
    print(f"      ← {basis}")


def rss_mib() -> float:
    """Peak resident set size of this process, in MiB. Linux reports KiB."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def children_rss_mib() -> float:
    return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024.0


# ── 1. La couche de règles et le codec, en C ─────────────────────────


def bench_rules(samples: int) -> dict[str, float]:
    """Legal-play generation and encoding — our own C, one core."""
    rng = random.Random(SEED)
    positions = []
    position = Position.initial()
    while len(positions) < samples:
        if position.is_over():
            position = Position.initial()
        positions.append(position)
        plays = position.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
        position = rng.choice(plays).result if plays else position.swapped_turn()

    dice = [(rng.randint(1, 6), rng.randint(1, 6)) for _ in positions]

    start = time.perf_counter()
    total_plays = 0
    for p, (d1, d2) in zip(positions, dice):
        total_plays += len(p.legal_plays(d1, d2))
    generation = len(positions) / (time.perf_counter() - start)

    # Le même appel, sans construire les objets Python du résultat. L'écart
    # entre les deux est le prix de la liaison, pas celui du moteur — et il
    # faut le connaître avant de conclure quoi que ce soit sur la couche C.
    import ctypes

    from gammonnet.rules import _LIB, _PLAY_BUFFER, MAX_PLAYS

    c_positions = [p._to_c() for p in positions]
    start = time.perf_counter()
    for c, (d1, d2) in zip(c_positions, dice):
        _LIB.gn_legal_plays(ctypes.byref(c), d1, d2, _PLAY_BUFFER, MAX_PLAYS)
    raw_generation = len(positions) / (time.perf_counter() - start)

    start = time.perf_counter()
    for p in positions:
        codec.encode(p)
    encoding = len(positions) / (time.perf_counter() - start)

    start = time.perf_counter()
    for p in positions:
        codec.position_id(p)
    identifiers = len(positions) / (time.perf_counter() - start)

    return {
        "generation": generation,
        "raw_generation": raw_generation,
        "encoding": encoding,
        "identifiers": identifiers,
        "plays_per_position": total_plays / len(positions),
    }


# ── 2. L'oracle, par cœur ────────────────────────────────────────────


def unrelated_positions(count: int) -> list[Position]:
    """One position per game — see T03 on why consecutive plies would lie."""
    rng = random.Random(SEED)
    positions = []
    while len(positions) < count:
        position = Position.initial()
        for _ in range(rng.randint(2, 60)):
            if position.is_over():
                break
            plays = position.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
            position = rng.choice(plays).result if plays else position.swapped_turn()
        if not position.is_over():
            positions.append(position)
    return positions


def bench_oracle(samples: dict[int, int]) -> dict[int, float]:
    pool = unrelated_positions(sum(samples.values()))
    boards = [gb.to_gnubg(p) for p in pool]

    rates = {}
    cursor = 0
    for ply, count in samples.items():
        slice_ = boards[cursor:cursor + count]
        cursor += count
        start = time.perf_counter()
        for board in slice_:
            gnubg_nn.probabilities(board, ply)
        rates[ply] = len(slice_) / (time.perf_counter() - start)
    return rates


# ── 3. Le self-play, un fil puis tous ────────────────────────────────


def bench_self_play(pairs: int, workers: int, engine_name: str) -> float:
    """Duplicate pairs per second, times two for games per second."""
    engine = (
        RandomEngine(name="random") if engine_name == "random"
        else OracleEngine(ply=0)
    )
    # Un moteur contre lui-même : c'est bien du self-play, et c'est aussi le
    # contrôle nul du harnais, donc le résultat doit rester exactement 0.
    start = time.perf_counter()
    result = play_pair(engine, engine, pairs=pairs, base_seed=SEED,
                       workers=workers, bootstrap=1)
    elapsed = time.perf_counter() - start

    if result.ppg != 0.0:
        raise AssertionError(
            f"le contrôle nul rend {result.ppg} au lieu de 0 : le banc mesure "
            "un harnais faux, et son chiffre ne vaut rien"
        )
    return result.games / elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()

    scale = 0.1 if args.quick else 1.0
    n = lambda x: max(50, int(x * scale))  # noqa: E731

    print("=" * 88)
    print("T05 — banc de débit")
    print("=" * 88)
    print(f"machine : {os.uname().nodename} · {ALL_CORES} fils · graine {SEED}")
    print("Chaque chiffre est étiqueté MESURÉ ou EXTRAPOLÉ. Rien n'est déduit d'une")
    print("lecture de code.\n")

    # ── 1 ────────────────────────────────────────────────────────────
    print("1. Couche de règles et codec — notre C, un cœur")
    print("-" * 88)
    rules = bench_rules(n(200_000))
    measured("génération des coups légaux, objets Python construits",
             f"{rules['generation']:,.0f} pos/s")
    measured("génération des coups légaux, appel C seul",
             f"{rules['raw_generation']:,.0f} pos/s")
    measured("  part payée à la liaison Python",
             f"×{rules['raw_generation'] / rules['generation']:.1f}")
    measured("  (coups légaux par position, en moyenne)", f"{rules['plays_per_position']:.1f}")
    measured("encodage en 196 caractéristiques", f"{rules['encoding']:,.0f} pos/s")
    measured("écriture d'un Position ID", f"{rules['identifiers']:,.0f} pos/s")
    print("      Ces débits passent par ctypes depuis Python : ils mesurent la")
    print("      bibliothèque VUE DE LA MESURE, pas le C appelé depuis du C.\n")

    # ── 2 ────────────────────────────────────────────────────────────
    print("2. Oracle GNU Backgammon — évaluations par seconde et par cœur")
    print("-" * 88)
    oracle = bench_oracle({0: n(20_000), 1: n(3_000), 2: n(200)})
    for ply, rate in oracle.items():
        measured(f"{ply}-ply, positions distinctes et non apparentées",
                 f"{rate:,.1f} éval/s")
    print("      Positions non apparentées : une par partie. Des plis consécutifs")
    print("      partagent leurs sous-arbres et se répondent par le cache (T03).\n")

    # ── 3 ────────────────────────────────────────────────────────────
    print("3. Self-play — parties par seconde")
    print("-" * 88)
    single = bench_self_play(n(1_500), 1, "random")
    measured("règles seules (moteur aléatoire), 1 fil", f"{single:,.0f} parties/s")

    full = bench_self_play(n(15_000), ALL_CORES, "random")
    measured(f"règles seules, {ALL_CORES} processus", f"{full:,.0f} parties/s")
    measured("  passage à l'échelle", f"×{full / single:.1f} pour {ALL_CORES} fils")

    oracle_single = bench_self_play(n(150), 1, "gnubg-0ply")
    measured("gnubg 0-ply contre lui-même, 1 fil", f"{oracle_single:,.0f} parties/s")

    oracle_full = bench_self_play(n(2_000), ALL_CORES, "gnubg-0ply")
    measured(f"gnubg 0-ply, {ALL_CORES} processus", f"{oracle_full:,.0f} parties/s")
    measured("  passage à l'échelle", f"×{oracle_full / oracle_single:.1f} pour {ALL_CORES} fils")
    print()

    # ── 4 ────────────────────────────────────────────────────────────
    print("4. Durée d'un round-robin d'un million de parties")
    print("-" * 88)
    for label, rate in (("règles seules", full), ("gnubg 0-ply", oracle_full)):
        hours = 1_000_000 / rate / 3600.0
        extrapolated(
            f"1 M de parties, {label}, {ALL_CORES} processus",
            f"{hours:.2f} h" if hours >= 1 else f"{hours * 60:.1f} min",
            f"débit mesuré de {rate:,.0f} parties/s, supposé constant à l'échelle",
        )
    print()

    # ── 5 ────────────────────────────────────────────────────────────
    print("5. Occupation mémoire")
    print("-" * 88)
    measured("pic du processus principal", f"{rss_mib():,.0f} Mio")
    measured("pic du plus gros processus fils", f"{children_rss_mib():,.0f} Mio")
    extrapolated(
        f"{ALL_CORES} processus simultanés",
        f"{children_rss_mib() * ALL_CORES:,.0f} Mio",
        "pic d'un fils × nombre de processus ; ignore le partage copie-sur-écriture",
    )
    print()

    print("=" * 88)
    print("Ce que ce banc NE mesure PAS")
    print("=" * 88)
    print("Le débit d'évaluation du réseau de gammonNet. Aucun réseau n'est encore")
    print("chargé — T10 vit sur la piste navigateur. En parler ici serait de l'invention.")
    print("La pénalité WebAssembly reste une hypothèse (×1,5 à ×2,5) jusqu'à T21.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
