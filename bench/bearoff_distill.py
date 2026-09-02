#!/usr/bin/env python3
"""T78 — ce que perd le réseau distillé, contre le même arbitre parfait que T38.

## Le protocole, délibérément non réécrit

Le tirage des positions, la notation exacte des coups et la définition de la
perte sont **importés de `bench/exact_gap.py`**, la mesure de T38. À graine
égale et à découpage égal, ce banc voit donc exactement les mêmes décisions que
celui qui a produit les chiffres publiés — 0,00028 d'équité perdue par décision
au 0-ply, 0,0919 au pire cas, contre 0,0023 pour GNU Backgammon. Un second
tirage « équivalent » aurait suffi à rendre les colonnes incomparables.

## Ce que la table ajoute ici, et ce qu'elle n'ajoute pas

La table bilatérale reste l'arbitre : elle note tout coup légal sans rien
estimer, donc la perte est exacte et sans variance. Elle n'est **jamais**
branchée sur le réseau distillé — c'est précisément ce dont il doit se passer.
Le distillé ne voit que ses 81 Kio de poids.

## Ce que la mesure ne dit pas

Le domaine est celui de la table : bearoff sans contact, au plus onze pions par
camp, tous dans les six premiers points. `BRIEF.md` §9 rappelle qu'un corpus
riche en fins de partie flatte qui a une table ; le chiffre produit ici est le
trou que le distillé comble **dans son domaine**, pas une force globale.

Usage :
    python bench/bearoff_distill.py --decisions 8000 --workers 26
    python bench/bearoff_distill.py --decisions 8000 --baseline --with-gnubg
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

from exact_gap import random_bearoff, score_all  # noqa: E402
from gammonnet.arena import game_value  # noqa: E402
from gammonnet.bearoff import TwoSidedBearoff  # noqa: E402
from gammonnet.bearoff_net import BearoffNet, position_sides  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import WHITE  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

DEFAULT_DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"
DEFAULT_NET = ROOT / "models" / "bearoff_net.bin"

#: Le pire cas de GNU Backgammon dans la mesure T38 : le seuil que la queue
#: doit franchir pour que la distillation ait tenu sa promesse.
GNUBG_WORST = 0.0023


def distilled_choice(net: BearoffNet, position, plays):
    """L'indice du coup que le réseau distillé jouerait.

    Les candidats sont évalués **en un seul lot** : le réseau est minuscule, et
    tout le coût d'une évaluation isolée est dans l'appel, pas dans les 20 544
    multiplications-accumulations.
    """
    mine = []
    theirs = []
    slots = []
    values = [None] * len(plays)

    for index, play in enumerate(plays):
        result = play.result
        if result.is_over():
            # Une position terminale se calcule ; aucune table, aucun réseau.
            values[index] = float(game_value(result, position.turn))
            continue
        white, black = position_sides(result)
        rolled, other = (white, black) if result.turn == WHITE else (black, white)
        mine.append(rolled)
        theirs.append(other)
        slots.append(index)

    if slots:
        # `result.turn` est l'adversaire : ce que la position vaut pour lui,
        # négué, est ce qu'elle vaut pour celui qui vient de jouer.
        batch = -net.equities_from_counts(np.array(mine), np.array(theirs))
        # Un réseau à quatre sorties (T80) rend `(N, 4)` : cubeless, puis les
        # trois cubeful. Le classement des coups ne lit QUE la cubeless — c'est
        # exactement la comparaison que T80 doit soutenir contre le réseau à une
        # sortie de T78, sur le même banc et sans lui laisser d'autre colonne.
        if batch.ndim == 2:
            batch = batch[:, 0]
        for slot, value in zip(slots, batch):
            values[slot] = float(value)

    return int(max(range(len(plays)), key=lambda i: values[i]))


def measure(payload):
    (database, net_path, model, plies, with_gnubg, seed, count, progress) = payload

    rng = random.Random(seed)
    table = TwoSidedBearoff(database)
    net = BearoffNet.load(net_path)

    engines = {"bearoff-net": ("distilled", net)}
    if plies:
        network = Network.load(model)
        for ply in plies:
            configuration = (SearchConfig(ply=ply) if ply <= 1
                             else SearchConfig(ply=ply, filter=(0, 1, 5)))
            engines[f"gammonnet-{ply}ply"] = ("ours", (network, configuration))
    if with_gnubg:
        from gammonnet.gnubg_engine import GnubgEngine
        for ply in (plies or [0]):
            engines[f"gnubg-{ply}ply"] = ("gnubg", GnubgEngine(ply=ply))

    losses = {name: [] for name in engines}
    agreed = {name: 0 for name in engines}
    considered = 0

    while considered < count:
        position = random_bearoff(rng, table)
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = position.legal_plays(d1, d2)
        if len(plays) < 2:
            continue

        scored = score_all(table, position, plays)
        top = max(scored)
        considered += 1

        for name, (kind, handle) in engines.items():
            if kind == "distilled":
                value = scored[distilled_choice(handle, position, plays)]
            else:
                if kind == "ours":
                    network, configuration = handle
                    ranked = search_plays(network, position, d1, d2, configuration)
                    chosen = ranked[0].play if ranked else None
                else:
                    chosen = handle.choose(position, d1, d2, rng)
                if chosen is None:
                    continue
                value = None
                for play, equity in zip(plays, scored):
                    if play.result == chosen.result:
                        value = equity
                        break
                if value is None:
                    raise AssertionError(f"{name} a joué un coup que nous ne générons pas")

            losses[name].append(top - value)
            if abs(top - value) < 1e-12:
                agreed[name] += 1

        if progress and considered % 100 == 0:
            with open(progress, "a") as handle_out:
                handle_out.write("x\n")

    table.close()
    return losses, agreed, considered


def summarise(name: str, values: list[float], agreed: int) -> dict:
    array = np.array(values, dtype=np.float64)
    wrong = array[array > 1e-12]
    return {
        "engine": name,
        "decisions": int(array.size),
        "agreement": agreed / array.size,
        "mean_loss": float(array.mean()),
        "mean_loss_when_wrong": float(wrong.mean()) if wrong.size else 0.0,
        "p99": float(np.quantile(array, 0.99)),
        "p999": float(np.quantile(array, 0.999)),
        "worst_loss": float(array.max()),
        "above_gnubg_worst": int((array > GNUBG_WORST).sum()),
    }


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--decisions", type=int, default=8000)
    parser.add_argument("--seed", type=int, default=20260806,
                        help="la graine de T38 : mêmes décisions, colonnes comparables")
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    parser.add_argument("--net", default=str(DEFAULT_NET))
    parser.add_argument("--baseline", action="store_true",
                        help="mesurer aussi le grand réseau, aux profondeurs --plies")
    parser.add_argument("--plies", default="0,1")
    parser.add_argument("--with-gnubg", action="store_true")
    parser.add_argument("--progress", default="/tmp/t78-progress.log")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    plies = [int(p) for p in args.plies.split(",") if p.strip()] if args.baseline else []
    model = str(ROOT / "models" / "cubeless_prob5_512_512_256_128.bin")
    net = BearoffNet.load(args.net)

    print(f"T78 — perte par décision du réseau distillé, arbitre : la table exacte")
    print(f"  {net.sizes}, {net.parameters} paramètres, {net.macs} MACs, "
          f"{Path(args.net).stat().st_size / 1024:.1f} Kio")
    print(f"  {args.decisions} décisions, graine {args.seed}, "
          f"{args.workers} processus")
    print(f"  suivi : {args.progress}\n", flush=True)

    workers = max(1, min(args.workers, args.decisions))
    share = [args.decisions // workers + (1 if i < args.decisions % workers else 0)
             for i in range(workers)]
    payloads = [(args.database, args.net, model, plies, args.with_gnubg,
                 args.seed + 1000 * i, n, args.progress)
                for i, n in enumerate(share) if n]

    start = time.perf_counter()
    if len(payloads) == 1:
        gathered = [measure(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            gathered = list(pool.map(measure, payloads))
    elapsed = time.perf_counter() - start

    names = list(gathered[0][0])
    losses = {name: [] for name in names}
    agreed = {name: 0 for name in names}
    considered = 0
    for part_losses, part_agreed, part_count in gathered:
        for name in names:
            losses[name].extend(part_losses[name])
            agreed[name] += part_agreed[name]
        considered += part_count

    print(f"{considered} décisions en {elapsed / 60:.1f} min\n")
    print(f"{'moteur':<18}{'accord':>9}{'perte moy.':>13}{'si désacc.':>12}"
          f"{'p99,9':>10}{'pire':>10}{'> gnubg':>9}")
    rows = []
    for name in names:
        if not losses[name]:
            continue
        row = summarise(name, losses[name], agreed[name])
        rows.append(row)
        print(f"{name:<18}{row['agreement'] * 100:>8.1f} %{row['mean_loss']:>13.5f}"
              f"{row['mean_loss_when_wrong']:>12.5f}{row['p999']:>10.4f}"
              f"{row['worst_loss']:>10.4f}{row['above_gnubg_worst']:>9}")

    print(f"\nLecture : perte en points d'équité money, exacte. « > gnubg » compte les")
    print(f"décisions au-delà de {GNUBG_WORST}, le pire cas de GNU Backgammon dans T38.")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "task": "T78", "seed": args.seed, "decisions": considered,
            "network": {"path": str(args.net), "sizes": net.sizes,
                        "parameters": net.parameters, "macs": net.macs,
                        "bytes": Path(args.net).stat().st_size},
            "rows": rows,
        }, indent=2) + "\n")
        print(f"\nécrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
