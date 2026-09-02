#!/usr/bin/env python3
"""T71 étape 1 — le corpus d'étiquettes de la distillation 2-ply.

## Ce que ce programme produit

Des positions de self-play, chacune étiquetée par **le vecteur des cinq
probabilités que notre propre expectiminimax rend à `--ply`**, plus la
**volatilité exacte** de la position sur les 21 jets. Deux étiquettes, un seul
backup : la seconde est ce que la moyenne du premier jette.

Aucune étiquette ne vient d'un moteur extérieur. La règle de licence du dépôt
fait de GNU Backgammon un instrument de mesure et jamais une source
d'apprentissage ; DS-14 recommandait le contraire, et ce retour a été rejeté
par écrit (`docs/recherche/00-plan-depasser-gnubg.md` §15).

## La volatilité, et pourquoi elle est gratuite

`gn_search_probs` forme, à la racine, la distribution de chacun des 21 jets
avant de les moyenner. `gn_search_probs_by_roll` rend ces 21 vecteurs. La
volatilité publiée ici est l'**écart-type pondéré de l'équité money sur les
jets** — la dispersion que la moyenne détruit, et le signal dont T81 a besoin
pour sa tête B. La redemander par 21 recherches séparées coûterait le backup
une deuxième fois ; la lire ici ne coûte rien de plus.

## D'où viennent les positions

Une marche de self-play jouée par le moteur **à `--play-ply`** (0 par défaut,
pour le volume), qui échantillonne une position sur `--stride` décisions. Le
pas évite d'étiqueter deux positions successives d'une même partie, qui ne
sont pas indépendantes et gonfleraient le corpus sans l'enrichir.

Les positions terminées ne sont jamais étiquetées : donner une partie finie au
réseau, c'est lui poser une question sur une entrée qu'il n'a jamais vue, et il
répondra — c'est le mode de défaillance que `CLAUDE.md` nomme. Elles sont
calculées, jamais évaluées, donc elles n'ont rien à apprendre.

## Reproductibilité

Déterministe en (graine, nombre de processus) : le worker `i` tire de
`random.Random(seed + i)` et s'arrête à son quota. Changer `--workers` change
le découpage des graines, donc les positions collectées — le nombre de
processus fait partie de la provenance, il est écrit dans le manifeste.

## Reprise

Chaque worker écrit son propre fichier `.part-<i>.jsonl` au fil de l'eau et
saute ce qu'il a déjà écrit lorsqu'on relance avec la même graine et le même
nombre de processus. Une campagne de plusieurs heures qui perd sa machine ne
recommence donc pas de zéro. `--resume` refuse de repartir si le manifeste
d'une exécution précédente décrit d'autres réglages : reprendre une campagne
avec d'autres paramètres produirait un corpus mixte que rien ne signalerait.

Usage :
    python tools/build_labels_t71.py --count 400000 --workers 30 --out build/t71
    python tools/build_labels_t71.py --count 2000 --workers 4      # à blanc
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
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import Position  # noqa: E402
from gammonnet.search import (  # noqa: E402
    SearchConfig,
    probs_by_roll,
    search_plays,
)

DEFAULT_MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
DEFAULT_PRUNE = ROOT / "models" / "prune_32.bin"
BASE_SEED = 20260902
MAX_PLIES_PER_GAME = 300


def label_position(network, prune, position: Position, ply: int, prune_k: int):
    """Les cinq probabilités à `ply`, et la volatilité sur les 21 jets.

    Un seul backup rend les deux : `probs_by_roll` est la boucle racine de
    `gn_search_probs` prise avant sa somme, et leur moyenne pondérée est cette
    somme au bit près (`tests/test_probs_by_roll.py` tient l'identité).
    """
    config = SearchConfig(ply=ply, prune_net=prune, prune_k=prune_k)
    rolls, weights = probs_by_roll(network, position, config)

    probs = [sum(weights[r] * rolls[r].as_tuple()[k] for r in range(len(rolls)))
             for k in range(5)]
    equities = [rolls[r].money_equity for r in range(len(rolls))]
    mean_equity = sum(weights[r] * equities[r] for r in range(len(rolls)))
    variance = sum(weights[r] * (equities[r] - mean_equity) ** 2
                   for r in range(len(rolls)))
    return probs, variance ** 0.5, mean_equity


def _shard(args) -> tuple[int, int, float]:
    """La part d'un worker : jouer, échantillonner, étiqueter, écrire."""
    (worker_id, seed, quota, model_path, prune_path, ply, play_ply,
     prune_k, stride, out_path, progress_path) = args

    network = Network.load(model_path)
    prune = Network.load(prune_path) if prune_k else None
    play_config = SearchConfig(ply=play_ply, prune_net=prune, prune_k=prune_k)
    rng = random.Random(seed)

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

                # Une position ne s'étiquette que si elle porte une décision et
                # qu'elle tombe sur le pas d'échantillonnage. Les positions
                # successives d'une partie ne sont pas indépendantes.
                if len(plays) >= 2:
                    seen += 1
                    if seen % stride == 0:
                        # On saute ce qui a déjà été écrit lors d'une exécution
                        # précédente : même graine, même marche, mêmes positions.
                        if (seen // stride) > already:
                            probs, volatility, equity = label_position(
                                network, prune, position, ply, prune_k)
                            handle.write(json.dumps({
                                "id": codec.position_id(position),
                                "probs": probs,
                                "volatility": volatility,
                                "equity": equity,
                                "worker": worker_id,
                            }) + "\n")
                            handle.flush()
                            written += 1
                            if written % 25 == 0:
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

    with open(progress_path, "a") as log:
        log.write(f"worker {worker_id}: done, {written}/{quota}\n")
    return worker_id, written, time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=400_000,
                        help="nombre d'étiquettes visé (palier B1 : 400–500 k)")
    parser.add_argument("--workers", type=int, default=30)
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--prune-model", default=str(DEFAULT_PRUNE))
    parser.add_argument("--prune-k", type=int, default=12,
                        help="l'élagage du réglage servi ; 0 le débranche")
    parser.add_argument("--ply", type=int, default=2,
                        help="la profondeur du PROFESSEUR")
    parser.add_argument("--play-ply", type=int, default=0,
                        help="la profondeur qui JOUE la marche de self-play")
    parser.add_argument("--stride", type=int, default=7,
                        help="une décision étiquetée sur N")
    parser.add_argument("--seed", type=int, default=BASE_SEED)
    parser.add_argument("--out", default=str(ROOT / "build" / "t71"))
    parser.add_argument("--resume", action="store_true",
                        help="reprendre une campagne interrompue")
    args = parser.parse_args()

    if args.ply < 1:
        print("REFUS — le professeur doit chercher : --ply >= 1.", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifeste.json"
    settings = {
        "count": args.count, "workers": args.workers, "ply": args.ply,
        "play_ply": args.play_ply, "prune_k": args.prune_k,
        "stride": args.stride, "seed": args.seed,
        "model": Path(args.model).name,
    }

    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text()).get("settings", {})
        if previous != settings:
            if not args.resume:
                print(f"REFUS — {manifest_path} décrit d'autres réglages.\n"
                      f"  précédent : {previous}\n  demandé   : {settings}\n"
                      f"  Reprendre avec d'autres paramètres produirait un corpus\n"
                      f"  mixte que rien ne signalerait. Choisir un autre --out.",
                      file=sys.stderr)
                return 2
            print("⚠ réglages différents et --resume : les parts déjà écrites "
                  "ne correspondent PAS à ces réglages.", file=sys.stderr)

    progress = out / "progression.log"
    quota = [args.count // args.workers] * args.workers
    for i in range(args.count % args.workers):
        quota[i] += 1

    payloads = [
        (i, args.seed + i, quota[i], args.model, args.prune_model, args.ply,
         args.play_ply, args.prune_k, args.stride,
         str(out / f"labels.part-{i:03d}.jsonl"), str(progress))
        for i in range(args.workers) if quota[i] > 0
    ]

    print(f"T71 étape 1 — étiquetage {args.ply}-ply, {args.count} positions, "
          f"{len(payloads)} processus")
    print(f"  professeur : {Path(args.model).name}, prune_k={args.prune_k}, "
          f"marche jouée à {args.play_ply}-ply, une décision sur {args.stride}")
    print(f"  sortie : {out}  (progression : {progress})")

    started = time.perf_counter()
    if len(payloads) == 1:
        results = [_shard(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            results = list(pool.map(_shard, payloads))
    elapsed = time.perf_counter() - started

    total = sum(written for _, written, _ in results)
    manifest = {
        "settings": settings,
        "labels": total,
        "seconds": elapsed,
        "core_hours": elapsed * len(payloads) / 3600.0,
        "parts": [f"labels.part-{i:03d}.jsonl" for i, _, _ in results],
        "date": time.strftime("%Y-%m-%d"),
        "host": os.uname().nodename,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False,
                                        indent=1, sort_keys=True))

    print(f"\n  {total} étiquettes en {elapsed:.0f} s de mur "
          f"({manifest['core_hours']:.2f} h·cœur)")
    print(f"  → {manifest_path}")
    return 0 if total >= args.count else 1


if __name__ == "__main__":
    raise SystemExit(main())
