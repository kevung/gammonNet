#!/usr/bin/env python3
"""T81 — les étiquettes cubeful, par rollout, pour la tête de videau.

## La question de la fiche

**Le videau se réduit-il aux cinq probabilités ?** T81 y répond par deux têtes
à tronc gelé : `B0` ne voit que les cinq probabilités et l'état du videau, `B`
voit en plus les auxiliaires de dispersion. L'écart entre les deux **est** la
mesure de ce que vaut « l'efficacité de videau » — la part de la valeur cubeful
qui dépend de la position et non de la seule distribution. Personne ne l'a
publiée.

Ce programme produit ce dont les deux têtes ont besoin : pour chaque position,
**l'équité cubeful mesurée par rollout** dans les trois états de possession, et
les entrées que les têtes liront.

## Ce qu'une étiquette contient, et pourquoi ces champs-là

- `probs` : les cinq probabilités du tronc **gelé**, au ply de jeu. C'est
  l'entrée de B0, et rien d'autre n'y entre.
- `volatility` : la dispersion exacte sur les 21 jets, sous-produit gratuit du
  backup (`gn_search_probs_by_roll`). C'est l'auxiliaire que B ajoute, et son
  absence dans B0 est exactement ce que l'ablation mesure.
- `e_centred`, `e_owned`, `e_opponent` : l'équité cubeful par rollout dans les
  trois états, en unités du videau initial, avec leurs erreurs standard. Ce
  sont les **cibles**.
- `equity_cubeless` : l'équité money sans videau, pour situer.

Le rollout porte un videau **vivant** — décisions internes exactes dans le
domaine de la table, modèle ajouté ailleurs — et `cube_defer_first` n'est PAS
actif : on veut la valeur d'une position dont le joueur au trait a encore son
option, pas celle d'une branche d'arbitrage.

## Ce que ce programme ne fait pas

Il n'entraîne rien, et il ne compare rien à Janowski. Le témoin classique est
mesuré par `bench/instruments_t81.py` sur les mêmes positions, plus tard. Et il
ne touche pas au tronc : le tronc est gelé, c'est l'ADR 0002.

## Le coût, mesuré et non extrapolé

La fiche T81 demande que le volume soit **mesuré et publié en début de fiche**.
Le manifeste porte donc le temps par étiquette réellement observé. Avec
`--pilot`, le programme ne produit qu'une poignée d'étiquettes et n'écrit que
ce coût : c'est le chiffre qui décide du volume, pas une extrapolation.

Usage :
    python tools/build_labels_t81.py --pilot 12 --workers 12
    python tools/build_labels_t81.py --count 20000 --workers 24 --out build/t81
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import codec  # noqa: E402
from gammonnet.arena import BLACK, opening_roll  # noqa: E402
from gammonnet.cube import CubeOwner  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rollout import RolloutConfig, rollout  # noqa: E402
from gammonnet.rules import Position  # noqa: E402
from gammonnet.search import (  # noqa: E402
    SearchConfig,
    probs_by_roll,
    search_plays,
)

DEFAULT_MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
DEFAULT_PRUNE = ROOT / "models" / "prune_32.bin"
EFFICIENCY = ROOT / "docs" / "mesures" / "t34-efficacite.json"
BASE_SEED = 20260903
MAX_PLIES_PER_GAME = 300

#: Les trois états de possession, vus par le joueur au trait. Les trois se
#: mesurent sur la MÊME position et avec les MÊMES dés : c'est leur différence
#: qui porte l'information de videau, et des dés distincts la noieraient.
STATES = (("centred", CubeOwner.CENTRED, 1.0),
          ("owned", CubeOwner.OWNED, 1.0),
          ("opponent", CubeOwner.OPPONENT, 1.0))


def measured_efficiencies() -> tuple[float, float, float]:
    """Les trois `x` mesurés par T34 — jamais une seule valeur recyclée."""
    if EFFICIENCY.exists():
        results = json.loads(EFFICIENCY.read_text()).get("results", {})
        if {"centered", "owned", "opponent"} <= set(results):
            # L'ordre est celui de `CubeOwner` : CENTRED, OWNED, OPPONENT.
            return (float(results["centered"]["x"]),
                    float(results["owned"]["x"]),
                    float(results["opponent"]["x"]))
    raise FileNotFoundError(
        f"{EFFICIENCY} absent ou incomplet. Les efficacités se MESURENT sur nos "
        f"données (règle T34) ; en coder trois en dur ici ferait passer une "
        f"valeur de repli pour une mesure.")


def label_one(network, prune, position, ply, prune_k, trials, truncate,
              seed, x3):
    """Une position : ses entrées, et les trois équités cubeful par rollout."""
    config = SearchConfig(ply=ply, prune_net=prune, prune_k=prune_k)
    rolls, weights = probs_by_roll(network, position, config)

    probs = [sum(weights[r] * rolls[r].as_tuple()[k] for r in range(len(rolls)))
             for k in range(5)]
    equities = [rolls[r].money_equity for r in range(len(rolls))]
    mean = sum(weights[r] * equities[r] for r in range(len(rolls)))
    variance = sum(weights[r] * (equities[r] - mean) ** 2
                   for r in range(len(rolls)))

    row = {
        "id": codec.position_id(position),
        "probs": probs,
        "volatility": variance ** 0.5,
        "equity_cubeless": mean,
    }

    for name, owner, scale in STATES:
        policy = SearchConfig(ply=0, use_cube=True,
                              cube_owner=int(owner), cube_x=x3[0])
        rollout_config = RolloutConfig(
            trials=trials, truncate=truncate, seed=seed, policy=policy,
            use_cube=True, cube_owner=int(owner), cube_x=x3, jacoby=True,
        )
        result = rollout(network, position, rollout_config)
        row[f"e_{name}"] = scale * result.equity
        row[f"se_{name}"] = scale * result.standard_error
        row[f"stalled_{name}"] = result.stalled

    return row


def _shard(args):
    (worker_id, seed, quota, model_path, prune_path, ply, prune_k, stride,
     trials, truncate, out_path, progress_path) = args

    network = Network.load(model_path)
    prune = Network.load(prune_path) if prune_k else None
    play_config = SearchConfig(ply=0, prune_net=prune, prune_k=prune_k)
    rng = random.Random(seed)
    x3 = measured_efficiencies()

    destination = Path(out_path)
    already = 0
    if destination.exists():
        with destination.open() as handle:
            already = sum(1 for _ in handle)
    if already >= quota:
        return worker_id, already, 0.0

    started = time.perf_counter()
    written = already
    seen = 0
    handle = destination.open("a")
    try:
        while written < quota:
            position = Position.initial()
            first, d1, d2 = opening_roll(rng)
            if first == BLACK:
                position = position.swapped_turn()

            for _ in range(MAX_PLIES_PER_GAME):
                if position.is_over() or written >= quota:
                    break
                plays = position.legal_plays(d1, d2)
                if not plays:
                    position = position.swapped_turn()
                    d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
                    continue

                if len(plays) >= 2:
                    seen += 1
                    if seen % stride == 0:
                        if (seen // stride) > already:
                            row = label_one(network, prune, position, ply,
                                            prune_k, trials, truncate,
                                            seed * 1000 + written, x3)
                            row["worker"] = worker_id
                            handle.write(json.dumps(row) + "\n")
                            handle.flush()
                            written += 1
                            if written % 5 == 0:
                                with open(progress_path, "a") as log:
                                    log.write(f"worker {worker_id}: "
                                              f"{written}/{quota}\n")
                        else:
                            written += 1

                ranked = search_plays(network, position, d1, d2, play_config)
                position = (ranked[0].play.result if ranked
                            else position.swapped_turn())
                d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
    finally:
        handle.close()

    return worker_id, written, time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=20_000)
    parser.add_argument("--pilot", type=int, default=0,
                        help="ne mesurer que le coût, sur N étiquettes")
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--prune-model", default=str(DEFAULT_PRUNE))
    parser.add_argument("--prune-k", type=int, default=12)
    parser.add_argument("--ply", type=int, default=1,
                        help="profondeur du tronc pour les entrées")
    parser.add_argument("--stride", type=int, default=11)
    parser.add_argument("--trials", type=int, default=1296)
    parser.add_argument("--truncate", type=int, default=11)
    parser.add_argument("--seed", type=int, default=BASE_SEED)
    parser.add_argument("--out", default=str(ROOT / "build" / "t81-cubeful"))
    args = parser.parse_args()

    count = args.pilot or args.count
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    progress = out / "progression.log"

    workers = max(1, min(args.workers, count))
    quota = [count // workers] * workers
    for i in range(count % workers):
        quota[i] += 1

    payloads = [
        (i, args.seed + i, quota[i], args.model, args.prune_model, args.ply,
         args.prune_k, args.stride, args.trials, args.truncate,
         str(out / f"labels.part-{i:03d}.jsonl"), str(progress))
        for i in range(workers) if quota[i] > 0
    ]

    print(f"T81 — étiquettes cubeful par rollout, {count} positions, "
          f"{len(payloads)} processus")
    print(f"  tronc à {args.ply}-ply (prune_k={args.prune_k}), rollout "
          f"{args.trials} essais tronqués à {args.truncate}, videau vivant")
    print(f"  efficacités mesurées (T34) : {measured_efficiencies()}")
    if args.pilot:
        print(f"  PILOTE — on ne mesure que le coût par étiquette.")

    started = time.perf_counter()
    if len(payloads) == 1:
        results = [_shard(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            results = list(pool.map(_shard, payloads))
    elapsed = time.perf_counter() - started

    total = sum(written for _, written, _ in results)
    per_label = (elapsed * len(payloads) / total) if total else 0.0
    manifest = {
        "task": "T81 — étiquettes cubeful",
        "settings": {
            "count": count, "workers": args.workers, "ply": args.ply,
            "prune_k": args.prune_k, "stride": args.stride,
            "trials": args.trials, "truncate": args.truncate,
            "seed": args.seed, "pilot": bool(args.pilot),
            "efficiencies": list(measured_efficiencies()),
        },
        "labels": total,
        "seconds": elapsed,
        "core_seconds_per_label": per_label,
        "core_hours": elapsed * len(payloads) / 3600.0,
        "date": time.strftime("%Y-%m-%d"),
        "host": os.uname().nodename,
    }
    name = "manifeste-pilote.json" if args.pilot else "manifeste.json"
    (out / name).write_text(json.dumps(manifest, ensure_ascii=False,
                                       indent=1, sort_keys=True))

    print(f"\n  {total} étiquettes en {elapsed:.0f} s de mur")
    print(f"  coût MESURÉ : {per_label:.2f} s·cœur par étiquette "
          f"({manifest['core_hours']:.2f} h·cœur au total)")
    if args.pilot:
        for volume in (5_000, 20_000, 50_000):
            hours = volume * per_label / 3600.0
            print(f"    {volume:>6} étiquettes = {hours:>7.1f} h·cœur")
        print("  Ces trois lignes sont une multiplication du coût mesuré, pas")
        print("  une mesure : le débit réel dépend de la charge de la machine.")
    print(f"  → {out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
