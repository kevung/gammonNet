#!/usr/bin/env python3
"""Ce que coûte une décision, par profondeur et par garde — des deux côtés.

> *« Aucun chiffre de débit, de latence ou de taille ne se tire d'une lecture de
> code ou d'une extrapolation. »* — `CLAUDE.md`, règle 3

Ce banc existe parce que j'ai enfreint cette règle. Le premier pilote de T36
avait repris la **garde 5** de T31 pour toutes les profondeurs, au motif que T31
l'avait mesurée sans aucun désaccord sur 121 décisions. Mais T31 mesurait sa
**qualité**, pas son coût : en 2-ply, une garde 5 à chaque niveau laisse de
l'ordre du million d'évaluations par décision. Le pilote ne terminait pas.

Le chiffre qui dimensionne une mesure est **le coût d'une décision**, et il se
mesure ici, avant d'engager des heures de machine.

Usage :
    python bench/cost_by_depth.py --positions 25
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.arena import BLACK, RandomEngine, opening_roll  # noqa: E402
from gammonnet.gnubg_engine import GnubgEngine  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import Position  # noqa: E402
from gammonnet.search import (  # noqa: E402
    SearchConfig,
    best_play,
    evaluations,
    reset_evaluations,
)

#: Les configurations qu'on envisage réellement d'employer.
#:
#: L'INDEXATION DU FILTRE, qui m'a déjà coûté un pilote. `filter[d]` est le
#: nombre de candidats gardés à un nœud dont la profondeur **restante** vaut
#: `d`. La racine d'une recherche à `k` plies a une profondeur restante de `k`,
#: elle lit donc `filter[k]` — et `filter[0]` n'est **jamais** lu, puisqu'un
#: nœud de profondeur restante nulle n'a rien à filtrer.
#:
#: Écrire `filter=(5,)` pour un 1-ply ne filtre donc rien du tout, et le coût
#: reste celui d'une recherche complète. C'est exactement ce qui est arrivé :
#: quatre configurations « filtrées » ont rendu 14 247 évaluations chacune, à
#: l'unité près — le signe qu'aucune ne filtrait.
CONFIGS = [
    (0, ()),
    (1, ()),
    (1, (0, 8)),
    (1, (0, 5)),
    (1, (0, 3)),
    (2, (0, 5, 8)),
    (2, (0, 2, 8)),
    (2, (0, 2, 5)),
    (2, (0, 1, 5)),
    (2, (0, 1, 3)),
    (2, (0, 1, 1)),
]


def corpus(count: int, seed: int) -> list[tuple[Position, int, int]]:
    """Des positions atteintes par jeu aléatoire, avec au moins six coups légaux.

    Le jeu aléatoire donne un mélange bien plus représentatif que l'ouverture :
    contact, barre, course, bearoff. Une décision d'ouverture ne coûte pas ce que
    coûte une décision de milieu de partie, et dimensionner sur la première
    tromperait.
    """
    rng = random.Random(seed)
    engine = RandomEngine()
    out: list[tuple[Position, int, int]] = []

    position = Position.initial()
    first, d1, d2 = opening_roll(rng)
    if first == BLACK:
        position = position.swapped_turn()

    while len(out) < count:
        if len(position.legal_plays(d1, d2)) >= 6:
            out.append((position, d1, d2))
        play = engine.choose(position, d1, d2, rng)
        position = play.result if play is not None else position.swapped_turn()
        if position.is_over():
            position = Position.initial()
            first, d1, d2 = opening_roll(rng)
            if first == BLACK:
                position = position.swapped_turn()
            continue
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--positions", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260806)
    parser.add_argument("--budget", type=float, default=20.0,
                        help="secondes au-delà desquelles une configuration est abandonnée")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    cases = corpus(args.positions, args.seed)
    legal = [len(p.legal_plays(d1, d2)) for p, d1, d2 in cases]
    print(f"{len(cases)} décisions, médiane {sorted(legal)[len(legal) // 2]} coups légaux "
          f"(min {min(legal)}, max {max(legal)})\n")

    network = Network.load(ROOT / "models" / "cubeless_prob5_512_512_256_128.bin")

    print(f"{'config':<14}{'gammonNet':>26}{'GNU Backgammon':>18}")
    print(f"{'':14}{'éval/déc':>12}{'s/déc':>14}{'s/déc':>18}")

    rows = []
    for ply, filt in CONFIGS:
        label = f"{ply}-ply" + ("/" + "-".join(map(str, filt)) if filt else "")
        config = SearchConfig(ply=ply, filter=filt)

        # ── notre moteur ──
        reset_evaluations()
        start = time.perf_counter()
        done = 0
        for position, d1, d2 in cases:
            best_play(network, position, d1, d2, config)
            done += 1
            if time.perf_counter() - start > args.budget:
                break
        ours = (time.perf_counter() - start) / done
        evals = evaluations() / done

        # ── GNU Backgammon, même profondeur, même garde ──
        engine = GnubgEngine(ply=ply, filter=filt)
        start = time.perf_counter()
        done_g = 0
        for position, d1, d2 in cases:
            engine.choose(position, d1, d2, random.Random(0))
            done_g += 1
            if time.perf_counter() - start > args.budget:
                break
        theirs = (time.perf_counter() - start) / done_g

        note = ""
        if done < len(cases) or done_g < len(cases):
            note = f"  (abandon : {done}/{done_g} sur {len(cases)})"

        print(f"{label:<14}{evals:>12,.0f}{ours:>14.4f}{theirs:>18.4f}{note}")
        rows.append({
            "ply": ply, "filter": list(filt),
            "evaluations_per_decision": evals,
            "seconds_per_decision_ours": ours,
            "seconds_per_decision_gnubg": theirs,
            "decisions_ours": done, "decisions_gnubg": done_g,
        })

    # Ce que cela permet — et surtout ne permet pas — de mesurer.
    print("\nCe qu'une paire de parties coûte, et ce que cela met sur 28 processus :")
    print(f"{'config':<14}{'s/paire':>12}{'2 000 paires':>16}{'50 000 paires':>16}")
    for row in rows:
        label = f"{row['ply']}-ply" + ("/" + "-".join(map(str, row["filter"]))
                                       if row["filter"] else "")
        # Une partie compte environ 55 décisions par camp ; une paire en vaut deux.
        per_pair = 2 * 55 * (row["seconds_per_decision_ours"]
                             + row["seconds_per_decision_gnubg"])
        print(f"{label:<14}{per_pair:>12.1f}"
              f"{per_pair * 2_000 / 28 / 3600:>14.1f} h"
              f"{per_pair * 50_000 / 28 / 3600:>14.1f} h")

    print("\nRappel de précision, extrapolé du volume de T11 (±0,0024 à 10⁶ parties) :")
    for games in (4_000, 20_000, 100_000):
        print(f"  {games:>7} parties → environ ±{0.0024 * (1_000_000 / games) ** 0.5:.4f} ppg")
    print("  L'effet à détecter — l'érosion de +0,0400 — est de l'ordre de 0,02 ppg.")

    if args.out:
        Path(args.out).write_text(json.dumps({"positions": len(cases), "seed": args.seed,
                                              "rows": rows}, indent=2) + "\n")
        print(f"\nécrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
