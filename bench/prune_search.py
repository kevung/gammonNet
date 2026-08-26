#!/usr/bin/env python3
"""T3A branché — ce que le réseau d'élagage rapporte, et ce qu'il coûte.

## Pourquoi ce banc, alors que T3A a déjà mesuré le petit réseau

La fiche du 2026-08-07 a mesuré le petit réseau **au tri**, sur des nœuds
isolés à 0-ply : 92,5× moins cher par évaluation, top-1 du grand dans son top-5
dans 94,2 % des décisions de contact. Elle en a tiré une **projection** — ×4,3
sur la facture à `k=5` — en la marquant comme telle, et en nommant les trois
suppositions qu'elle fait : que la proportion de tri superficiel dans une vraie
recherche ressemble à celle d'un nœud isolé, que `k` reste le bon à chaque
profondeur intérieure, et qu'aucun coût nouveau n'apparaît.

Ce banc ne suppose rien de tout cela : il fait tourner **la vraie recherche**,
élaguée et non élaguée, sur les mêmes décisions.

## Les deux colonnes, et pourquoi aucune ne suffit

| colonne | ce qu'elle mesure |
|---|---|
| **coût** | temps par décision, évaluations du grand réseau, évaluations du petit |
| **qualité** | le coup choisi est-il celui de la recherche non élaguée ; sinon, combien d'équité cela coûte |

Un gain de vitesse annoncé sans la seconde colonne ne veut rien dire : élaguer à
`k=1` est extrêmement rapide et joue mal.

## L'arbitre, et pourquoi c'est le bon

La recherche **non élaguée** est ici la référence, pas un adversaire : l'élagage
est une approximation d'elle, et la question est ce que l'approximation coûte.
Quand les deux coups diffèrent, l'écart est chiffré en évaluant **les deux
coups** à la profondeur de la référence (`gn_search_equity` sur la position
résultante, négation comprise) — donc par le même calcul qui aurait départagé
les deux plays dans la passe profonde. Ce banc ne dit pas si la recherche non
élaguée a raison ; ce n'est pas sa question.

Usage :
    python bench/prune_search.py --contact 300 --race 100 --ks 2,3,5,8 --workers 26
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from decision_loss import corpus, has_contact  # noqa: E402,F401
from prune_quality import race_corpus  # noqa: E402

from gammonnet.arena import bootstrap_ci  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.search import (  # noqa: E402
    SearchConfig,
    evaluations,
    prune_evaluations,
    reset_evaluations,
    position_equity,
    search_plays,
)

GRAND = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
SMALL = ROOT / "models" / "prune_32.bin"

#: Le point de fonctionnement de la campagne T35 : c'est celui dont le coût
#: est publié, donc le seul contre lequel une accélération veut dire quelque
#: chose.
PLY = 2
FILTER = (0, 1, 3)

#: Graine distincte de celle du corpus de distillation (20260807) : mesurer le
#: petit réseau sur les positions qui l'ont entraîné mesurerait sa mémoire.
SEED = 20260826

_G = None
_S = None


def _install(grand_path, small_path):
    global _G, _S
    _G = Network.load(grand_path)
    _S = Network.load(small_path)


def _reference_equity(position, play_result):
    """L'équité d'un coup, à la profondeur de la référence, non élaguée.

    Exactement ce que la passe profonde calcule pour départager deux coups :
    `-V(result, ply)`. La négation est celle de `gn_search.h` — la réponse
    était celle de l'adversaire.
    """
    config = SearchConfig(ply=PLY, filter=FILTER)
    return -position_equity(_G, play_result, config)


def _measure(payload):
    """Une décision, non élaguée puis élaguée à chaque `k`."""
    (position, d1, d2), ks = payload

    plain_config = SearchConfig(ply=PLY, filter=FILTER)
    reset_evaluations()
    start = time.perf_counter()
    plain = search_plays(_G, position, d1, d2, plain_config)
    plain_seconds = time.perf_counter() - start
    plain_big = evaluations()

    if not plain:
        return None

    row = {
        "legal": len(plain),
        "plain": {"seconds": plain_seconds, "big": plain_big, "small": 0},
        "ks": {},
    }
    best_plain = plain[0].play.result
    ref_best = None  # calculée à la demande : la plupart des décisions accordent

    for k in ks:
        config = SearchConfig(ply=PLY, filter=FILTER, prune_net=_S, prune_k=k)
        reset_evaluations()
        start = time.perf_counter()
        pruned = search_plays(_G, position, d1, d2, config)
        seconds = time.perf_counter() - start
        big, small = evaluations(), prune_evaluations()

        if not pruned:
            return None
        agree = pruned[0].play.result == best_plain
        loss = 0.0
        if not agree:
            if ref_best is None:
                ref_best = _reference_equity(position, best_plain)
            loss = ref_best - _reference_equity(position, pruned[0].play.result)
        row["ks"][str(k)] = {
            "seconds": seconds, "big": big, "small": small,
            "agree": bool(agree), "loss": float(loss),
        }
    return row


def summarise(rows: list[dict], ks: list[int], bootstrap: int) -> dict:
    plain_seconds = sum(r["plain"]["seconds"] for r in rows)
    plain_big = sum(r["plain"]["big"] for r in rows)
    n = len(rows)
    out = {
        "decisions": n,
        "legal_mean": sum(r["legal"] for r in rows) / n,
        "plain": {
            "seconds_per_decision": plain_seconds / n,
            "big_per_decision": plain_big / n,
        },
        "ks": {},
    }
    for k in ks:
        key = str(k)
        cells = [r["ks"][key] for r in rows]
        seconds = sum(c["seconds"] for c in cells)
        big = sum(c["big"] for c in cells)
        small = sum(c["small"] for c in cells)
        agree = sum(1 for c in cells if c["agree"])
        losses = [c["loss"] for c in cells]
        lo, hi = bootstrap_ci(losses, resamples=bootstrap, seed=SEED)
        out["ks"][key] = {
            "seconds_per_decision": seconds / n,
            "big_per_decision": big / n,
            "small_per_decision": small / n,
            "speedup_time": plain_seconds / seconds if seconds else 0.0,
            "speedup_big_evals": plain_big / big if big else 0.0,
            "agreement": agree / n,
            "loss_per_decision": sum(losses) / n,
            "loss_ci": [lo, hi],
            "disagreements": n - agree,
        }
    return out


def render(label: str, s: dict) -> None:
    print(f"\n── {label} : {s['decisions']} décisions, "
          f"{s['legal_mean']:.1f} coups légaux en moyenne")
    print(f"   non élaguée : {s['plain']['seconds_per_decision']:.3f} s/décision, "
          f"{s['plain']['big_per_decision']:.0f} évals du grand réseau")
    print(f"   {'k':>3} {'s/déc.':>8} {'grand':>9} {'petit':>9} "
          f"{'×temps':>7} {'×évals':>7} {'accord':>8} {'perte/déc.':>12} "
          f"{'IC 95 %':>22}")
    for key, c in s["ks"].items():
        lo, hi = c["loss_ci"]
        print(f"   {key:>3} {c['seconds_per_decision']:>8.3f} "
              f"{c['big_per_decision']:>9.0f} {c['small_per_decision']:>9.0f} "
              f"{c['speedup_time']:>7.2f} {c['speedup_big_evals']:>7.2f} "
              f"{100 * c['agreement']:>7.1f}% {c['loss_per_decision']:>12.5f} "
              f"  [{lo:>+.5f} ; {hi:>+.5f}]")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contact", type=int, default=300)
    parser.add_argument("--race", type=int, default=100)
    parser.add_argument("--ks", default="2,3,5,8")
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--grand", type=Path, default=GRAND)
    parser.add_argument("--small", type=Path, default=SMALL)
    parser.add_argument("--out", default="docs/mesures/t3a-prune-search.json")
    args = parser.parse_args()

    ks = [int(x) for x in args.ks.split(",") if x.strip()]

    print("1. Construction des corpus (0-ply, GRAND réseau)")
    builder = Network.load(args.grand)
    contact = corpus(args.contact, args.seed, builder) if args.contact else []
    # Graine décalée d'un cran : deux corpus tirés de la même graine se
    # ressembleraient plus qu'il ne faut.
    race = race_corpus(args.race, args.seed + 1, builder) if args.race else []
    print(f"   contact {len(contact)}, course {len(race)}")

    results = {}
    started = time.time()
    with ProcessPoolExecutor(max_workers=args.workers,
                             initializer=_install,
                             initargs=(str(args.grand), str(args.small))) as pool:
        for label, cases in (("contact", contact), ("course", race)):
            if not cases:
                continue
            print(f"\n2. Mesure — {label} ({len(cases)} décisions, "
                  f"{args.workers} ouvriers)")
            payloads = [(case, ks) for case in cases]
            rows = [r for r in pool.map(_measure, payloads, chunksize=1)
                    if r is not None]
            results[label] = summarise(rows, ks, args.bootstrap)
            render(label, results[label])

    report = {
        "task": "T3A",
        "bench": "pruning network wired into gn_search",
        "setting": {"ply": PLY, "filter": list(FILTER), "ks": ks,
                    "seed": args.seed, "workers": args.workers,
                    "grand": str(args.grand), "small": str(args.small),
                    "native_fp": os.environ.get("NATIVE_FP", "")},
        "elapsed_s": time.time() - started,
        "results": results,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1, ensure_ascii=False))
        print(f"\n→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
