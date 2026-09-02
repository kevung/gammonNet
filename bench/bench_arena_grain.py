"""Le nombre de tâches du harnais d'arène, mesuré (T87).

`play_pair` découpait en exactement `workers` tâches, une par processus :
l'oisiveté y était sans rattrapage, puisque le processus qui a fini n'a rien à
prendre. Ce banc chiffre ce que le nombre de tâches vaut réellement.

**Passes ENTRELACÉES.** Le temps absolu de cette machine dérive de plusieurs
dizaines de pour cent d'une minute à l'autre. Comparer deux exécutions
séparées ne mesurerait donc que la charge : les granularités sont mises en
concurrence dans la même passe, et l'on garde la médiane.

**Le résultat est comparé à chaque granularité.** Un ordonnancement qui
déplacerait une mesure de force ne serait pas un ordonnancement ; le banc
échoue plutôt que de publier un temps.

    python bench/bench_arena_grain.py [paires] [workers] [passes]

SPDX-License-Identifier: MIT
"""

import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))

from gammonnet.arena import FirstPlayEngine, RandomEngine, play_pair  # noqa: E402

GRAINS = [1, 2, 4, 8, 16]


def main() -> int:
    pairs = int(sys.argv[1]) if len(sys.argv) > 1 else 2500
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    reps = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    # Deux moteurs BON MARCHÉ, et c'est délibéré : ce qu'on mesure est un
    # ordonnancement, pas un moteur. Ils diffèrent assez pour que le résultat
    # ne soit pas nul (deux moteurs identiques s'annulent exactement).
    a = FirstPlayEngine(name="first-play")
    b = RandomEngine(name="random")

    # Un tour à blanc : le premier démarrage de processus paie l'import.
    play_pair(a, b, pairs=200, base_seed=7, workers=workers, bootstrap=100)

    times: dict[int, list[float]] = {g: [] for g in GRAINS}
    answers: dict[int, object] = {}
    for _ in range(reps):
        for grain in GRAINS:
            start = time.perf_counter()
            result = play_pair(
                a, b, pairs=pairs, base_seed=7, workers=workers,
                bootstrap=100, chunks_per_worker=grain,
            )
            times[grain].append(time.perf_counter() - start)
            answers.setdefault(grain, result)
            if answers[grain] != result:
                print(f"❌ le résultat varie d'une passe à l'autre à {grain} tâches/worker")
                return 1

    reference = answers[GRAINS[0]]
    for grain in GRAINS:
        if answers[grain] != reference:
            print(f"❌ {grain} tâches par worker DÉPLACENT le résultat")
            return 1

    print(f"{pairs} paires · {workers} workers · {reps} passes entrelacées")
    print(f"résultat identique à toutes les granularités : {reference.ppg:+.6f} ppg")
    print("grain  tâches  médiane s   toutes les passes")
    base = statistics.median(times[GRAINS[0]])
    for grain in GRAINS:
        median = statistics.median(times[grain])
        every = " ".join(f"{t:.2f}" for t in sorted(times[grain]))
        print(f"{grain:5}  {workers * grain:6}  {median:9.3f}   {every}   "
              f"{100 * (1 - median / base):+6.2f} %")
    return 0


# forkserver RÉIMPORTE `__main__` : un banc qui s'exécuterait au niveau module
# se relancerait dans chaque processus enfant, et le pool mourrait sur un
# `ConnectionResetError` sans dire pourquoi.
if __name__ == "__main__":
    sys.exit(main())
