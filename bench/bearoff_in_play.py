#!/usr/bin/env python3
"""T79 — combien pèse la fin de partie dans une vraie partie, et ce qu'elle coûte.

## La question, et pourquoi elle vient après T78 plutôt qu'avant

T78 a mesuré ce que le réseau perd **par décision de bearoff** : 0,00028 en
moyenne, 0,0919 sur la pire, et le distillé ramène cela à 0,0000017 et 0,0014.
Ces chiffres sont exacts et ils ne suffisent pas à décider quoi que ce soit,
parce qu'il leur manque un multiplicateur : **quelle part des décisions d'une
partie tombe dans ce domaine ?** `BRIEF.md` §9 avertit exactement de cela — un
corpus riche en fins de partie flatte qui a une table.

Ce banc produit le multiplicateur, et le produit **sur la distribution qui
compte** : non pas des positions tirées au hasard dans la table, mais celles
qu'une partie traverse réellement.

## Le joueur et les jugés, séparés — et pourquoi

Ce qui coûte cher, c'est **jouer** la partie : quarante-quatre décisions, dont
quarante-deux hors du domaine. Ce qu'on veut mesurer ne concerne que les deux
autres. La partie est donc jouée par un moteur **0-ply** — qui définit le
chemin, et dont la profondeur ne change presque rien à la fréquence des fins de
partie — tandis que les moteurs **jugés** (`--measure-plies`) ne sont
interrogés que sur les décisions du domaine. Un 2-ply mesuré ainsi coûte
vingt-trois fois moins qu'un 2-ply qui jouerait, pour la même quantité.

Ce que cette séparation assume est nommé : la *distribution* des positions de
fin de partie est celle qu'un moteur 0-ply produit. Elle est mesurée, elle
n'est pas supposée identique à celle d'un 2-ply — mais l'écart porterait sur
la fréquence, pas sur la perte par décision, qui est jugée position par
position.

## Ce qu'il mesure

Des parties d'argent sans videau, jouées par notre moteur. À chaque décision de
coup :

* on compte la décision ;
* si elle est dans le domaine de la table bilatérale, on note **exactement**
  tous les coups légaux, et on relève ce que perdent, sur cette décision, le
  moteur qui joue et le réseau distillé — le second en pure hypothèse, il ne
  touche pas à la partie.

D'où trois chiffres, et c'est le troisième qui décide :

1. la **fraction** des décisions qui tombe dans le domaine ;
2. la perte **par décision du domaine**, sur la vraie distribution — à comparer
   à celle de T78, qui tirait uniformément ;
3. l'**équité perdue par partie** du fait de la fin de partie, aujourd'hui et
   avec le distillé. C'est la seule forme sous laquelle le gain de T78 est
   comparable à quoi que ce soit d'autre dans ce projet.

## Une boucle de partie écrite ici, et pourquoi

`arena.play_game` ne rend que le résultat ; il faut les positions traversées.
La boucle ci-dessous est donc une seconde écriture — délibérément minimale, et
qui reprend `opening_roll`, `game_value` et les moteurs de `arena` plutôt que
de les redire. Son seul écart assumé avec l'originale est qu'elle observe.

Usage :
    python bench/bearoff_in_play.py --games 5000 --workers 26
    python bench/bearoff_in_play.py --games 2000 --ply 1
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from bearoff_distill import distilled_choice  # noqa: E402
from exact_gap import score_all  # noqa: E402
from gammonnet.arena import MAX_TURNS, opening_roll  # noqa: E402
from gammonnet.bearoff import TwoSidedBearoff  # noqa: E402
from gammonnet.bearoff_net import BearoffNet  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import BLACK, WHITE, Position  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

DEFAULT_DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"
DEFAULT_NET = ROOT / "models" / "bearoff_code16_256_128.bin"


def configuration(ply: int) -> SearchConfig:
    """Le réglage de recherche, filtre compris — le filtre a coûté une heure à T38."""
    if ply <= 1:
        return SearchConfig(ply=ply)
    return SearchConfig(ply=ply, filter=(0, 1, 5))


def play_and_observe(payload):
    (database, model, net_path, ply, judged, seed, games, progress) = payload

    table = TwoSidedBearoff(database)
    network = Network.load(model)
    net = BearoffNet.load(net_path)
    search = configuration(ply)
    # Les moteurs jugés : le joueur lui-même, les autres profondeurs demandées,
    # et le distillé. Aucun d'eux ne touche à la partie.
    judged_configs = {f"gammonnet-{p}ply": configuration(p) for p in judged}

    decisions = 0
    forced = 0
    in_domain = 0
    reached = 0
    names = [f"gammonnet-{ply}ply (celui qui joue)"] + list(judged_configs) + ["distillé"]
    losses = {name: [] for name in names}
    # Par partie, pour l'intervalle : les décisions d'une même partie ne sont
    # pas indépendantes, la partie l'est.
    per_game = {name: [] for name in names}
    entry_checkers: list[int] = []
    turns_total = 0
    stalled = 0

    for index in range(games):
        dice = random.Random(seed + 7919 * index)
        rng = random.Random(seed + 104729 * index)
        first, d1, d2 = opening_roll(dice)
        position = Position.initial()
        if first == BLACK:
            position = position.swapped_turn()

        seen_domain = False
        game = {name: 0.0 for name in names}
        turns = 0
        while turns < MAX_TURNS:
            plays = position.legal_plays(d1, d2)
            if len(plays) > 1:
                decisions += 1
                inside = table.contains(position)
                if inside:
                    in_domain += 1
                    if not seen_domain:
                        seen_domain = True
                        reached += 1
                        entry_checkers.append(
                            sum(n for n in position.points if n > 0)
                            if position.turn == WHITE
                            else -sum(n for n in position.points if n < 0))
            elif plays:
                forced += 1
                inside = False
            else:
                inside = False

            ranked = search_plays(network, position, d1, d2, search) if plays else []
            chosen = ranked[0].play if ranked else None

            if inside:
                # Noté exactement : la table donne l'équité de tout coup légal,
                # donc le meilleur, donc ce que le coup joué a coûté.
                scored = score_all(table, position, plays)
                top = max(scored)

                def loss_of(candidate) -> float:
                    for play, equity in zip(plays, scored):
                        if candidate is not None and play.result == candidate.result:
                            return top - equity
                    raise AssertionError("un moteur a joué un coup que nous ne générons pas")

                player_name = names[0]
                losses[player_name].append(loss_of(chosen))
                game[player_name] += losses[player_name][-1]

                for name, config in judged_configs.items():
                    ranked = search_plays(network, position, d1, d2, config)
                    value = loss_of(ranked[0].play if ranked else None)
                    losses[name].append(value)
                    game[name] += value

                # Le distillé ne joue pas : on lui demande seulement ce qu'il
                # aurait fait de cette décision-là.
                distilled = top - scored[distilled_choice(net, position, plays)]
                losses["distillé"].append(distilled)
                game["distillé"] += distilled

            position = chosen.result if chosen is not None else position.swapped_turn()
            turns += 1
            if position.is_over():
                break
            d1, d2 = dice.randint(1, 6), dice.randint(1, 6)
        else:
            stalled += 1
        turns_total += turns
        for name in names:
            per_game[name].append(game[name])

        if progress and (index + 1) % 50 == 0:
            with open(progress, "a") as handle:
                handle.write("x\n")

    table.close()
    return {
        "games": games, "decisions": decisions, "forced": forced,
        "in_domain": in_domain, "reached": reached, "stalled": stalled,
        "turns": turns_total,
        "names": names, "losses": losses, "per_game": per_game,
        "entry_checkers": entry_checkers,
    }


def interval(values: np.ndarray, level: float = 1.96) -> tuple[float, float, float]:
    """Moyenne et intervalle à 95 %, par l'approximation normale.

    Les parties sont indépendantes — graines dérivées, aucune duplication de
    dés ici — donc l'intervalle porte sur leur moyenne. Il est calculé sur la
    **différence appariée** quand on compare deux moteurs, parce qu'ils
    tranchent les mêmes décisions : la variance des parties, qui domine tout,
    s'annule alors.
    """
    n = values.size
    mean = float(values.mean())
    if n < 2:
        return mean, float("nan"), float("nan")
    half = level * float(values.std(ddof=1)) / (n ** 0.5)
    return mean, mean - half, mean + half


def summarise(losses: np.ndarray, games: int) -> dict:
    if losses.size == 0:
        return {}
    wrong = losses[losses > 1e-12]
    return {
        "decisions": int(losses.size),
        "agreement": float((losses <= 1e-12).mean()),
        "mean_loss": float(losses.mean()),
        "mean_loss_when_wrong": float(wrong.mean()) if wrong.size else 0.0,
        "p999": float(np.quantile(losses, 0.999)),
        "worst_loss": float(losses.max()),
        "equity_per_game": float(losses.sum() / games),
    }


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=5000)
    parser.add_argument("--ply", type=int, default=0,
                        help="profondeur du moteur qui joue (0 pour le volume)")
    parser.add_argument("--measure-plies", default="",
                        help="profondeurs JUGÉES sur les seules décisions du "
                             "domaine, ex. « 1,2 » — bien moins cher que de les "
                             "faire jouer")
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    parser.add_argument("--net", default=str(DEFAULT_NET))
    parser.add_argument("--progress", default="/tmp/t79-progress.log")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    model = str(ROOT / "models" / "cubeless_prob5_512_512_256_128.bin")
    workers = max(1, min(args.workers, args.games))
    share = [args.games // workers + (1 if i < args.games % workers else 0)
             for i in range(workers)]
    judged = [int(p) for p in args.measure_plies.split(",") if p.strip()]
    payloads = [(args.database, model, args.net, args.ply, judged,
                 args.seed + 1_000_003 * i, n, args.progress)
                for i, n in enumerate(share) if n]

    print(f"T79 — le poids de la fin de partie dans une vraie partie")
    print(f"  {args.games} parties d'argent sans videau, moteur à {args.ply}-ply, "
          f"{len(payloads)} processus")
    if judged:
        print(f"  jugés en plus, sur les seules décisions du domaine : "
              f"{', '.join(f'{p}-ply' for p in judged)}")
    print(f"  distillé mesuré en parallèle, sans jouer : {Path(args.net).name}")
    print(f"  suivi : {args.progress}\n", flush=True)

    start = time.perf_counter()
    if len(payloads) == 1:
        parts = [play_and_observe(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            parts = list(pool.map(play_and_observe, payloads))
    elapsed = time.perf_counter() - start

    total = {k: sum(p[k] for p in parts)
             for k in ("games", "decisions", "forced", "in_domain", "reached",
                       "stalled", "turns")}
    names = parts[0]["names"]
    losses = {name: np.array([v for p in parts for v in p["losses"][name]])
              for name in names}
    per_game = {name: np.array([v for p in parts for v in p["per_game"][name]])
                for name in names}
    entry = np.array([v for p in parts for v in p["entry_checkers"]])

    print(f"{total['games']} parties en {elapsed / 60:.1f} min "
          f"({total['stalled']} enlisées)\n")
    print(f"décisions de coup (au moins deux coups légaux) : {total['decisions']}")
    print(f"  coups forcés, non comptés                    : {total['forced']}")
    print(f"  dont dans le domaine de la table             : {total['in_domain']}"
          f"  ({total['in_domain'] / total['decisions'] * 100:.2f} %)")
    print(f"  parties qui atteignent le domaine            : {total['reached']}"
          f"  ({total['reached'] / total['games'] * 100:.1f} %)")
    print(f"  décisions du domaine par partie              : "
          f"{total['in_domain'] / total['games']:.3f}")
    if entry.size:
        print(f"  pions restants à l'entrée dans le domaine    : "
              f"médiane {np.median(entry):.0f}, moyenne {entry.mean():.1f}")

    rows = {name: summarise(losses[name], total["games"]) for name in names}
    print(f"\n{'moteur':<34}{'accord':>9}{'perte moy.':>13}{'pire':>10}"
          f"{'équité/partie':>15}")
    for name in names:
        row = rows[name]
        if not row:
            continue
        print(f"{name:<34}{row['agreement'] * 100:>8.1f} %{row['mean_loss']:>13.6f}"
              f"{row['worst_loss']:>10.4f}{row['equity_per_game']:>15.6f}")

    # L'intervalle porte sur la DIFFÉRENCE APPARIÉE avec le distillé : les deux
    # moteurs tranchent les mêmes décisions, donc la variance des parties —
    # qui domine tout — s'annule au lieu d'être comptée deux fois.
    intervals = {}
    print(f"\néquité perdue par partie, du fait de la fin de partie seule "
          f"({total['games']} parties, IC 95 %) :")
    for name in names:
        mean, low, high = interval(per_game[name])
        intervals[name] = [mean, low, high]
        print(f"  {name:<34}{mean:>11.6f}  [{low:.6f} ; {high:.6f}]")
    for name in names[:-1]:
        mean, low, high = interval(per_game[name] - per_game["distillé"])
        intervals[f"gain vs {name}"] = [mean, low, high]
        print(f"  **gain contre {name:<20}{mean:>11.6f}**  [{low:.6f} ; {high:.6f}]")

    print("\nLecture : gain de fin de partie SEUL, en parties d'argent sans videau.")
    print("Il se compare à l'écart entre deux moteurs, jamais à zéro.")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "task": "T79", "seed": args.seed, "ply": args.ply,
            "network": str(args.net), "totals": total,
            "engines": rows, "intervals": intervals,
            "decisions_per_game": total["decisions"] / total["games"],
            "entry_checkers": {"median": float(np.median(entry)) if entry.size else None,
                               "mean": float(entry.mean()) if entry.size else None},
        }, indent=2) + "\n")
        print(f"\nécrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
