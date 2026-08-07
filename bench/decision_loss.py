#!/usr/bin/env python3
"""T36 — l'avantage par décision, et ce que la profondeur lui fait.

## Pourquoi cet instrument et pas un round-robin

La première tentative de T36 comptait des points par partie. Elle demandait
**vingt-quatre heures** pour douze mille parties et aurait rendu ±0,017, quand
l'effet à détecter — l'érosion de l'avantage — vaut de l'ordre de 0,02. Autrement
dit : une journée de machine pour « on ne peut pas conclure ».

Une partie ne rend **qu'un** point de donnée. Elle contient cinquante-cinq
décisions. Ici chaque décision en rend un, et la comparaison est **appariée sur
la même position** — ce qui retire presque toute la variance avant même de
compter.

## Le principe

Pour chaque position du corpus, à profondeur `k` :

    notre coup      = gammonNet à k plies
    leur coup       = GNU Backgammon à k plies

Si les deux coups coïncident, la décision ne sépare pas les moteurs et compte
pour **zéro** — ce qui est vrai, pas une commodité. Sinon il faut un arbitre, et
il en faut **deux**, parce qu'aucun n'est neutre :

| colonne | arbitre | biais |
|---|---|---|
| **nôtre** | rollout à dés communs, conduit par notre réseau | en notre faveur |
| **leur** | GNU Backgammon à profondeur supérieure | en leur faveur |

**Aucune n'est publiée seule** (`PLAN.md`, T39). Le résultat qui vaut quelque
chose est celui où les deux colonnes s'accordent sur le **signe** : si notre
propre arbitre et le leur disent tous deux que nous gagnons de l'équité, la
conclusion survit au choix de l'arbitre.

## Ce que la sortie signifie, et ce qu'elle ne signifie pas

L'unité est le **point d'équité money gagné par décision** contre GNU Backgammon.
Ce n'est pas un ppg et ne s'y convertit pas directement : une partie n'est pas la
somme de ses décisions vues isolément. C'est une mesure **relative**, faite pour
comparer trois profondeurs entre elles — ce que T36 demande.

Usage :
    python bench/decision_loss.py --decisions 2000 --plies 0,1,2 --workers 26
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import gnubg_board as gb  # noqa: E402
from gammonnet.arena import BLACK, opening_roll  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rollout import RolloutConfig, rollout_difference  # noqa: E402
from gammonnet.rules import Position  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

PROGRESS = Path(os.environ.get("T36_PROGRESS", "/tmp/t36-decision-progress.log"))

#: L'indexation du filtre est celle du C : `filter[d]` s'applique à un nœud de
#: profondeur RESTANTE `d`. La racine d'une recherche à k plies lit `filter[k]`.
#: Coûts mesurés par `bench/cost_by_depth.py`.
FILTERS = {0: (), 1: (0, 5), 2: (0, 1, 5)}

#: La profondeur à laquelle GNU Backgammon arbitre. Supérieure à celle des
#: moteurs comparés, sans quoi il arbitrerait avec le même regard que celui qui
#: a choisi — ce qui ne serait pas un arbitrage.
ARBITER_PLY = 3


def corpus(count: int, seed: int, network) -> list[tuple[Position, int, int]]:
    """Des positions de **contact**, atteintes par un jeu plausible.

    Le jeu aléatoire produit des positions que personne ne rencontre. On joue
    donc au 0-ply, ce qui donne des positions réalistes à peu de frais, et on ne
    retient que celles où **le contact subsiste** : deux camps qui se sont
    croisés ne posent plus les questions qui séparent les moteurs, et T38 traite
    déjà la fin de partie avec un arbitre exact.
    """
    rng = random.Random(seed)
    out: list[tuple[Position, int, int]] = []

    while len(out) < count:
        position = Position.initial()
        first, d1, d2 = opening_roll(rng)
        if first == BLACK:
            position = position.swapped_turn()

        for _ in range(200):
            if position.is_over():
                break
            plays = position.legal_plays(d1, d2)
            if len(plays) >= 3 and has_contact(position):
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


def has_contact(position: Position) -> bool:
    """Un pion de chaque camp peut-il encore en frapper un autre ?

    Vrai dès qu'un pion blanc est derrière un pion noir. Sur la barre compte
    toujours : un pion à rentrer est du contact par définition.
    """
    if position.bar[0] or position.bar[1]:
        return True
    white = [i for i, n in enumerate(position.points) if n > 0]
    black = [i for i, n in enumerate(position.points) if n < 0]
    if not white or not black:
        return False
    # Blanc va vers l'indice 0, Noir vers l'indice 23. Il y a contact tant que le
    # pion noir le plus avancé est devant le pion blanc le plus arriéré.
    return max(white) > min(black)


def measure(payload):
    database, model, plies, trials, truncate, seed, cases, arbiter_ply = payload

    from gammonnet.gnubg_engine import GnubgEngine, GnubgSession

    network = Network.load(model)
    session = GnubgSession()
    ours = {p: SearchConfig(ply=p, filter=FILTERS[p]) for p in plies}
    theirs = {p: GnubgEngine(ply=p, filter=FILTERS[p]) for p in plies}

    rows = {p: [] for p in plies}
    disagreements = {p: 0 for p in plies}

    for index, (position, d1, d2) in enumerate(cases):
        for ply in plies:
            ranked = search_plays(network, position, d1, d2, ours[ply])
            if not ranked:
                continue
            mine = ranked[0].play
            yours = theirs[ply].choose(position, d1, d2, random.Random(0))
            if yours is None or mine.result == yours.result:
                # Même coup : la décision ne sépare pas les moteurs. Zéro est la
                # bonne valeur, pas une commodité — et les exclure gonflerait
                # artificiellement la moyenne des désaccords.
                rows[ply].append((0.0, 0.0))
                continue

            disagreements[ply] += 1

            # Colonne 1 — notre arbitre. Dés communs entre les deux coups : la
            # différence est bien mieux déterminée que chacun des deux termes.
            config = RolloutConfig(trials=trials, truncate=truncate,
                                   seed=seed + index, policy=SearchConfig(ply=0))
            ours_says, _ = rollout_difference(network, mine.result, yours.result, config)

            # Colonne 2 — le leur, à profondeur supérieure à celle qui a choisi.
            values = session.evaluate(
                [gb.to_gnubg(mine.result), gb.to_gnubg(yours.result)],
                plies=arbiter_ply, prune=1)
            theirs_says = -(float(values[0][5]) - float(values[1][5]))

            rows[ply].append((ours_says, theirs_says))

        with open(PROGRESS, "a") as fh:
            fh.write("x\n")

    session.close()
    return rows, disagreements


def summarise(values, bootstrap, seed):
    import numpy as np

    array = np.asarray(values, dtype=float)
    n = len(array)
    generator = np.random.default_rng(seed)
    draws = generator.integers(0, n, size=(bootstrap, n))
    means = np.sort(array[draws].mean(axis=1))
    return (float(array.mean()),
            float(means[int(0.025 * bootstrap)]),
            float(means[int(0.975 * bootstrap) - 1]))


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--decisions", type=int, default=2000)
    parser.add_argument("--plies", default="0,1,2")
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--trials", type=int, default=648)
    parser.add_argument("--truncate", type=int, default=11)
    parser.add_argument("--arbiter-ply", type=int, default=ARBITER_PLY)
    parser.add_argument("--seed", type=int, default=20260807)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    plies = [int(p) for p in args.plies.split(",") if p.strip()]
    model = str(ROOT / "models" / "cubeless_prob5_512_512_256_128.bin")

    print("T36 — avantage par décision contre GNU Backgammon")
    print(f"  profondeurs : {', '.join(str(p) for p in plies)}"
          f"   arbitre gnubg à {args.arbiter_ply}-ply")
    print(f"  {args.decisions} décisions de contact, graine {args.seed}, "
          f"{args.workers} processus")
    print(f"  rollout : {args.trials} essais, tronqué à {args.truncate} plies")
    print(f"  suivi : {PROGRESS}", flush=True)

    network = Network.load(model)
    start = time.perf_counter()
    cases = corpus(args.decisions, args.seed, network)
    print(f"  corpus construit en {time.perf_counter() - start:.0f} s\n", flush=True)

    workers = max(1, min(args.workers, len(cases)))
    chunks = [cases[i::workers] for i in range(workers)]
    payloads = [(None, model, plies, args.trials, args.truncate,
                 args.seed + 7919 * i, chunk, args.arbiter_ply)
                for i, chunk in enumerate(chunks) if chunk]

    start = time.perf_counter()
    if len(payloads) == 1:
        gathered = [measure(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            gathered = list(pool.map(measure, payloads))
    elapsed = time.perf_counter() - start

    rows = {p: [] for p in plies}
    disagreements = {p: 0 for p in plies}
    for part_rows, part_disagreements in gathered:
        for p in plies:
            rows[p].extend(part_rows[p])
            disagreements[p] += part_disagreements[p]

    print(f"{'ply':<6}{'désaccord':>11}   {'notre arbitre':^28} {'arbitre gnubg':^28}")
    payload_rows = []
    for ply in plies:
        values = rows[ply]
        if not values:
            continue
        n = len(values)
        mine, mine_low, mine_high = summarise([v[0] for v in values],
                                              args.bootstrap, args.seed)
        yours, yours_low, yours_high = summarise([v[1] for v in values],
                                                 args.bootstrap, args.seed)
        agree = (mine > 0) == (yours > 0)
        print(f"{ply:<6}{disagreements[ply] / n * 100:>9.1f} % "
              f"{f'{mine:+.5f} [{mine_low:+.5f} ; {mine_high:+.5f}]':>29}"
              f"{f'{yours:+.5f} [{yours_low:+.5f} ; {yours_high:+.5f}]':>29}"
              f"{'' if agree else '   ⚠ SIGNES OPPOSÉS'}")
        payload_rows.append({
            "ply": ply, "decisions": n,
            "disagreement_rate": disagreements[ply] / n,
            "ours": {"mean": mine, "ci95": [mine_low, mine_high]},
            "gnubg": {"mean": yours, "ci95": [yours_low, yours_high]},
            "arbiters_agree_on_sign": agree,
        })

    print(f"\n{sum(len(rows[p]) for p in plies)} décisions arbitrées en "
          f"{elapsed / 60:.1f} min sur {args.workers} processus")
    print("\nLecture : points d'équité money gagnés PAR DÉCISION contre GNU")
    print("Backgammon, à profondeur égale. Ce n'est pas un ppg et ne s'y convertit")
    print("pas. Aucune colonne ne vaut seule : ce qui compte est leur accord de signe.")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "task": "T36", "seed": args.seed, "trials": args.trials,
            "truncate": args.truncate, "arbiter_ply": args.arbiter_ply,
            "rows": payload_rows, "elapsed_seconds": elapsed,
        }, indent=2) + "\n")
        print(f"\nécrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
