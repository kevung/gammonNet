#!/usr/bin/env python3
"""T37 — la calibration de la distribution à cinq sorties, composante par composante.

## Pourquoi ce banc, et pas encore une mesure d'équité agrégée

Toutes les mesures du dépôt jusqu'ici portent sur le choix de coup ou sur
l'équité money — un scalaire. Une décision de videau vit sur `P(gammon)` bien
plus que sur le choix de coup, et rien de ce qui précède ne l'a jamais isolée :
un réseau peut être excellent sur `P(gain)` et biaisé sur les gammons sans
qu'aucune mesure faite jusqu'ici ne le voie, parce qu'elles agrègent les cinq
sorties en une seule équité avant de comparer. Ce banc ne les agrège pas.

## La référence, et sa réserve

La référence est un rollout **non tronqué** (`truncate=0` : la partie se joue
jusqu'au bout, jamais coupée puis notée par un réseau) conduit par **notre**
réseau au 0-ply. C'est un choix de commodité — un arbitre exact n'existe pas en
contact — et il porte un biais possible : les deux camps jouent comme nous, donc
toute lacune systématique de notre politique de 0-ply se retrouve à la fois
dans le jeu et dans la mesure qui le juge.

Deux choses rendent la comparaison honnête malgré cela :

1. **GNU Backgammon est évalué contre la même référence.** Il n'a pas de
   traitement de faveur : ses probabilités au 0-ply sont comparées aux mêmes
   fréquences de rollout que les nôtres. Si gnubg s'avère mieux calibré que
   nous contre *notre propre* arbitre, l'écart est réel *a fortiori* — un
   arbitre biaisé en notre faveur qui nous trouve quand même moins bien
   calibrés ne peut pas être en train de nous flatter.
2. **Le rollout marginalise sur des centaines de parties.** Un biais de
   politique commis à une décision individuelle se répartit sur beaucoup
   d'issues ; il resterait un biais de raisonnement (jouer scientifiquement
   sous-optimal dans une certaine classe de positions), pas un artefact de
   l'échantillonnage.

Ce que ce banc ne peut PAS trancher : si un biais est trouvé, il ne dit pas si
la faute est au réseau qui a produit `P(gammon)`, ou à la politique de jeu qui a
produit la référence à laquelle on le compare — les deux sont le même réseau.
C'est nommé dans le rapport, pas caché.

## Le corpus

Les positions viennent de `bench/decision_loss.corpus` (T36), réutilisé tel
quel : du contact, atteint par un jeu plausible au 0-ply. On ne réécrit pas un
second générateur de positions réalistes pour ce banc — la variante `(d1, d2)`
que `corpus()` renvoie sert au choix de coup dans T36 ; ici on n'a besoin que du
plateau, évalué **avant** que les dés ne soient joués, ce qui est la convention
de `Network.evaluate` (une position ne porte pas de dés — le réseau marginalise
sur le prochain jet).

Usage :
    python bench/calibration.py --positions 500 --trials 324 --workers 26
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
sys.path.insert(0, str(ROOT / "bench"))

from decision_loss import corpus  # noqa: E402
from gammonnet import gnubg_board as gb  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rollout import RolloutConfig, rollout  # noqa: E402
from gammonnet.search import SearchConfig  # noqa: E402

PROGRESS = Path(os.environ.get("T37_PROGRESS", "/tmp/t37-progress.log"))

#: Ordre imposé par `gn_infer.h` / `gn_rollout.h` : imbriqué, du point de vue du
#: joueur au trait. `GnubgSession.evaluate` rend la même convention (`value[5]`
#: est l'équité, `value[0:5]` ces cinq probabilités) — vérifié dans
#: `tools/gnubg_server.py`, qui appelle directement `gnubg.evaluate`.
COMPONENTS = ("win", "win_gammon", "win_backgammon", "lose_gammon", "lose_backgammon")


def positions_from_corpus(count: int, seed: int, network: Network) -> list:
    """Les plateaux du corpus de T36, sans les dés.

    `corpus()` renvoie `(position, d1, d2)` pour servir un choix de coup ; ce
    banc évalue le plateau lui-même, avant que les dés ne soient joués — c'est
    la convention de `Network.evaluate`, qui ne prend pas de dés en entrée.
    """
    return [position for position, _d1, _d2 in corpus(count, seed, network)]


def evaluate_one(network: Network, session, position, roll_seed: int, trials: int,
                  truncate: int) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """Les trois lectures d'une position : réseau, rollout non tronqué, gnubg 0-ply."""
    net = network.evaluate(position).as_tuple()

    config = RolloutConfig(trials=trials, truncate=truncate, seed=roll_seed,
                           policy=SearchConfig(ply=0))
    ref = rollout(network, position, config).frequencies

    board = gb.to_gnubg(position)
    values = session.evaluate([board], plies=0, prune=0)[0]
    gnubg_probs = tuple(float(v) for v in values[:5])

    return net, tuple(ref), gnubg_probs


def measure(payload):
    """Un lot de positions, dans un processus — sa propre session gnubg, son propre réseau."""
    model, items, seed, trials, truncate, progress = payload

    from gammonnet.gnubg_engine import GnubgSession

    network = Network.load(model)
    session = GnubgSession()

    rows = []
    for index, position in items:
        net, ref, gnubg_probs = evaluate_one(network, session, position, seed + index,
                                             trials, truncate)
        rows.append((index, net, ref, gnubg_probs))
        if progress:
            with open(progress, "a") as fh:
                fh.write("x\n")

    session.close()
    return rows


def run_pilot(model: str, items: list, seed: int, trials: int, truncate: int) -> float:
    """Chronomètre la chaîne complète (réseau + rollout + gnubg) sur un petit lot,
    en un seul processus. Rend le débit, en secondes par position.

    Pas de fichier de progression ici : c'est du chronométrage, pas la mesure.
    """
    from gammonnet.gnubg_engine import GnubgSession

    network = Network.load(model)
    session = GnubgSession()
    start = time.perf_counter()
    for index, position in items:
        evaluate_one(network, session, position, seed + index, trials, truncate)
    elapsed = time.perf_counter() - start
    session.close()
    return elapsed / len(items)


def bootstrap_summary(array, bootstrap: int, seed: int):
    """Moyenne et IC 95 % bootstrap, par rééchantillonnage de l'array (1D)."""
    import numpy as np

    n = len(array)
    generator = np.random.default_rng(seed)
    draws = generator.integers(0, n, size=(bootstrap, n))
    means = np.sort(array[draws].mean(axis=1))
    return (float(array.mean()),
            float(means[int(0.025 * bootstrap)]),
            float(means[int(0.975 * bootstrap) - 1]))


def summarise_component(net_vals, gnubg_vals, ref_vals, bootstrap: int, seed: int) -> dict:
    import numpy as np

    net_vals = np.asarray(net_vals, dtype=float)
    gnubg_vals = np.asarray(gnubg_vals, dtype=float)
    ref_vals = np.asarray(ref_vals, dtype=float)

    diff_net = net_vals - ref_vals
    diff_gnubg = gnubg_vals - ref_vals

    bias_net, low_net, high_net = bootstrap_summary(diff_net, bootstrap, seed)
    bias_gnubg, low_gnubg, high_gnubg = bootstrap_summary(diff_gnubg, bootstrap, seed + 1)

    return {
        "ours": {"bias": bias_net, "ci95": [low_net, high_net],
                 "mae": float(np.abs(diff_net).mean())},
        "gnubg": {"bias": bias_gnubg, "ci95": [low_gnubg, high_gnubg],
                  "mae": float(np.abs(diff_gnubg).mean())},
    }


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--positions", type=int, default=500)
    parser.add_argument("--trials", type=int, default=324)
    parser.add_argument("--truncate", type=int, default=0,
                        help="0 = rollout non tronqué (la référence de ce banc)")
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--seed", type=int, default=20260807)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--pilot", type=int, default=30)
    parser.add_argument("--budget-minutes", type=float, default=40.0)
    parser.add_argument("--reduced-trials", type=int, default=216)
    parser.add_argument("--out", default=str(ROOT / "docs" / "mesures" / "t37-calibration.json"))
    args = parser.parse_args()

    model = str(ROOT / "models" / "cubeless_prob5_512_512_256_128.bin")

    print("T37 — calibration de la distribution à cinq sorties, par composante")
    print(f"  corpus : {args.positions} positions de contact, graine {args.seed}")
    print(f"  référence : rollout non tronqué, {args.trials} essais, politique 0-ply")
    print(f"  suivi : {PROGRESS}", flush=True)

    network = Network.load(model)
    start = time.perf_counter()
    positions = positions_from_corpus(args.positions, args.seed, network)
    print(f"  corpus construit en {time.perf_counter() - start:.0f} s "
          f"({len(positions)} positions)\n", flush=True)

    # ── Le pilote ─────────────────────────────────────────────────────
    trials = args.trials
    pilot_items = list(enumerate(positions[: args.pilot]))
    per_position = run_pilot(model, pilot_items, args.seed, trials, args.truncate)
    projected_minutes = per_position * args.positions / max(1, args.workers) / 60.0
    print(f"pilote : {args.pilot} positions, {per_position:.3f} s/position en série")
    print(f"  extrapolation à {args.positions} positions sur {args.workers} processus : "
          f"{projected_minutes:.1f} min")

    if projected_minutes >= args.budget_minutes:
        trials = args.reduced_trials
        per_position = run_pilot(model, pilot_items, args.seed, trials, args.truncate)
        projected_minutes = per_position * args.positions / max(1, args.workers) / 60.0
        print(f"  au-delà du budget de {args.budget_minutes:.0f} min : essais réduits à "
              f"{trials} (au lieu de {args.trials})")
        print(f"  nouvelle extrapolation : {per_position:.3f} s/position, "
              f"{projected_minutes:.1f} min", flush=True)
    else:
        print(f"  sous le budget de {args.budget_minutes:.0f} min : volume complet lancé "
              f"à {trials} essais", flush=True)

    # ── Le volume ─────────────────────────────────────────────────────
    items = list(enumerate(positions))
    workers = max(1, min(args.workers, len(items)))
    chunks = [items[i::workers] for i in range(workers)]
    payloads = [(model, chunk, args.seed, trials, args.truncate, str(PROGRESS))
                for chunk in chunks if chunk]

    volume_start = time.perf_counter()
    if len(payloads) == 1:
        gathered = [measure(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            gathered = list(pool.map(measure, payloads))
    elapsed = time.perf_counter() - volume_start

    rows = [None] * len(items)
    for part in gathered:
        for index, net, ref, gnubg_probs in part:
            rows[index] = (net, ref, gnubg_probs)
    assert all(r is not None for r in rows), "reassemblage incomplet"

    # ── Agrégats, par composante ─────────────────────────────────────
    summaries = {}
    for i, name in enumerate(COMPONENTS):
        net_vals = [r[0][i] for r in rows]
        ref_vals = [r[1][i] for r in rows]
        gnubg_vals = [r[2][i] for r in rows]
        summaries[name] = summarise_component(net_vals, gnubg_vals, ref_vals,
                                               args.bootstrap, args.seed + 1000 * i)

    print(f"\n{len(rows)} positions, {trials} essais/position, "
          f"rollout non tronqué, en {elapsed / 60:.1f} min sur {workers} processus\n")
    bias_w = 31
    print(f"{'composante':<18}{'biais nous':^{bias_w}}{'MAE nous':>10}   "
          f"{'biais gnubg':^{bias_w}}{'MAE gnubg':>10}")
    for name in COMPONENTS:
        s = summaries[name]
        o, g = s["ours"], s["gnubg"]
        ours_text = f"{o['bias']:+.5f} [{o['ci95'][0]:+.5f};{o['ci95'][1]:+.5f}]"
        gnubg_text = f"{g['bias']:+.5f} [{g['ci95'][0]:+.5f};{g['ci95'][1]:+.5f}]"
        print(f"{name:<18}{ours_text:>{bias_w}}{o['mae']:>10.5f}   "
              f"{gnubg_text:>{bias_w}}{g['mae']:>10.5f}")

    print("\nLecture : biais = modèle − fréquence du rollout, moyenné sur le corpus.")
    print("MAE = erreur absolue moyenne. La référence (rollout) est conduite par notre")
    print("propre réseau à 0-ply des deux côtés : voir la réserve dans le module.")

    payload = {
        "task": "T37",
        "seed": args.seed,
        "positions": len(rows),
        "trials": trials,
        "trials_requested": args.trials,
        "truncate": args.truncate,
        "pilot_positions": args.pilot,
        "pilot_seconds_per_position": per_position,
        "projected_minutes": projected_minutes,
        "budget_minutes": args.budget_minutes,
        "workers": workers,
        "elapsed_seconds": elapsed,
        "components": summaries,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nécrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
