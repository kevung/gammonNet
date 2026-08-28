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
    (database, model, net_path, ply, seed, games, progress) = payload

    table = TwoSidedBearoff(database)
    network = Network.load(model)
    net = BearoffNet.load(net_path)
    search = configuration(ply)

    decisions = 0
    forced = 0
    in_domain = 0
    reached = 0
    engine_losses: list[float] = []
    distilled_losses: list[float] = []
    # Par partie, pour l'intervalle : les décisions d'une même partie ne sont
    # pas indépendantes, la partie l'est.
    per_game_engine: list[float] = []
    per_game_distilled: list[float] = []
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
        game_engine = 0.0
        game_distilled = 0.0
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
                played = None
                for play, equity in zip(plays, scored):
                    if chosen is not None and play.result == chosen.result:
                        played = equity
                        break
                if played is None:
                    raise AssertionError("le moteur a joué un coup que nous ne générons pas")
                engine_losses.append(top - played)
                game_engine += top - played
                # Le distillé ne joue pas : on lui demande seulement ce qu'il
                # aurait fait de cette décision-là.
                distilled_loss = top - scored[distilled_choice(net, position, plays)]
                distilled_losses.append(distilled_loss)
                game_distilled += distilled_loss

            position = chosen.result if chosen is not None else position.swapped_turn()
            turns += 1
            if position.is_over():
                break
            d1, d2 = dice.randint(1, 6), dice.randint(1, 6)
        else:
            stalled += 1
        turns_total += turns
        per_game_engine.append(game_engine)
        per_game_distilled.append(game_distilled)

        if progress and (index + 1) % 50 == 0:
            with open(progress, "a") as handle:
                handle.write("x\n")

    table.close()
    return {
        "games": games, "decisions": decisions, "forced": forced,
        "in_domain": in_domain, "reached": reached, "stalled": stalled,
        "turns": turns_total,
        "engine_losses": engine_losses, "distilled_losses": distilled_losses,
        "per_game_engine": per_game_engine, "per_game_distilled": per_game_distilled,
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
    payloads = [(args.database, model, args.net, args.ply,
                 args.seed + 1_000_003 * i, n, args.progress)
                for i, n in enumerate(share) if n]

    print(f"T79 — le poids de la fin de partie dans une vraie partie")
    print(f"  {args.games} parties d'argent sans videau, moteur à {args.ply}-ply, "
          f"{len(payloads)} processus")
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
    engine = np.array([v for p in parts for v in p["engine_losses"]])
    distilled = np.array([v for p in parts for v in p["distilled_losses"]])
    game_engine = np.array([v for p in parts for v in p["per_game_engine"]])
    game_distilled = np.array([v for p in parts for v in p["per_game_distilled"]])
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
          f"{total['in_domain'] / total['games']:.2f}")
    if entry.size:
        print(f"  pions restants à l'entrée dans le domaine    : "
              f"médiane {np.median(entry):.0f}, moyenne {entry.mean():.1f}")

    rows = {"grand réseau (celui qui joue)": summarise(engine, total["games"]),
            "distillé T78": summarise(distilled, total["games"])}
    print(f"\n{'moteur':<30}{'accord':>9}{'perte moy.':>12}{'pire':>10}"
          f"{'équité/partie':>15}")
    for name, row in rows.items():
        if not row:
            continue
        print(f"{name:<30}{row['agreement'] * 100:>8.1f} %{row['mean_loss']:>12.6f}"
              f"{row['worst_loss']:>10.4f}{row['equity_per_game']:>15.6f}")

    mean_engine, lo_engine, hi_engine = interval(game_engine)
    mean_distilled, lo_distilled, hi_distilled = interval(game_distilled)
    mean_gain, lo_gain, hi_gain = interval(game_engine - game_distilled)
    intervals = {
        "engine_per_game": [mean_engine, lo_engine, hi_engine],
        "distilled_per_game": [mean_distilled, lo_distilled, hi_distilled],
        "gain_per_game": [mean_gain, lo_gain, hi_gain],
    }

    print(f"\néquité perdue par partie, du fait de la fin de partie seule "
          f"({game_engine.size} parties, IC 95 %) :")
    print(f"  moteur actuel        {mean_engine:.6f}  "
          f"[{lo_engine:.6f} ; {hi_engine:.6f}]")
    print(f"  avec le distillé     {mean_distilled:.6f}  "
          f"[{lo_distilled:.6f} ; {hi_distilled:.6f}]")
    print(f"  **le branchement rapporterait {mean_gain:.6f}**  "
          f"[{lo_gain:.6f} ; {hi_gain:.6f}]  — intervalle apparié")
    print("\nLecture : gain de fin de partie SEUL, en parties d'argent sans videau.")
    print("Il se compare à l'écart entre deux moteurs, jamais à zéro.")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "task": "T79", "seed": args.seed, "ply": args.ply,
            "network": str(args.net), "totals": total,
            "engines": rows, "intervals": intervals,
            "entry_checkers": {"median": float(np.median(entry)) if entry.size else None,
                               "mean": float(entry.mean()) if entry.size else None},
        }, indent=2) + "\n")
        print(f"\nécrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
