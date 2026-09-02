#!/usr/bin/env python3
"""T70 — noter un moteur sur le registre figé : le point de comparaison.

## Ce que ça coûte, et pourquoi c'est le point de la fiche

L'arbitrage (`bench/arbitrate_t70.py`) est payé **une fois**. Noter un moteur ne
demande ensuite aucun rollout : il joue les décisions du corpus, on lit ce que
son coup valait. Le coût d'un point de comparaison tombe donc au coût de N
recherches — ce que la fiche T70 exige de chiffrer, et ce qui fait la différence
entre un instrument utilisable et un instrument théorique.

## La métrique

**La perte d'équité par décision** : pour chaque décision, l'équité du meilleur
candidat au registre, moins celle du coup joué. Toujours ≥ 0. Zéro veut dire
« a joué le meilleur coup connu », jamais « n'a pas été mesuré ».

Deux précautions que le chiffre porte explicitement :

- **La pondération.** Le corpus est stratifié : les backgames y sont
  sur-représentés pour qu'ils aient un intervalle lisible. Chaque décision porte
  le poids qui rétablit sa fréquence naturelle ; la moyenne est pondérée, et le
  bootstrap tire les positions, jamais les coups.

- **Le hors-corpus.** Un moteur peut jouer un coup que l'arbitrage n'a pas prix.
  Cette décision n'est **pas** comptée zéro : elle est comptée à part, et son
  taux est publié avec le résultat. Au-delà de quelques pour cent, le chiffre
  n'est plus une note du moteur mais une note du corpus, et le banc le dit.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT))

from gammonnet import codec  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import BLACK, WHITE  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
FILTERS = {0: (), 1: (0, 5), 2: (0, 1, 5), 3: (0, 1, 1, 5)}

#: Au-delà de cette part de décisions jouées hors du registre, le chiffre cesse
#: de noter le moteur et se met à noter le corpus. Le banc le dit alors haut.
HORS_CORPUS_ALARM = 0.05

#: ─────────────────────────────────────────────────────────────────────────
#: CE CHIFFRE N'EST PAS UN PR, ET NE LE DEVIENT PAS EN LE MULTIPLIANT PAR 500.
#:
#: Le PR d'eXtreme Gammon est « l'équité normalisée perdue par décision × 500 »
#: (retour DS-11, source éditeur). La tentation est donc forte de multiplier la
#: sortie de ce banc par 500 et d'annoncer un PR. Ce serait faux, pour une
#: raison qui tient à la CONSTRUCTION DU CORPUS et non à l'arithmétique.
#:
#: Le corpus de T70 ne retient que les décisions **disputées** — celles où notre
#: 2-ply et gnubg 2-ply divergent, soit 9,75 % des décisions de contact. Le PR,
#: lui, se calcule sur TOUTES les décisions. Et les décisions écartées ne
#: portent pas une perte nulle : les deux moteurs y jouent le même coup, ce qui
#: ne veut pas dire qu'ils jouent le meilleur. Leur perte commune est invisible
#: à ce banc par construction.
#:
#: Multiplier par 500 rendrait donc un nombre à l'échelle d'un PR, calculé sur
#: un dixième des décisions et aveugle aux erreurs partagées — c'est-à-dire
#: précisément le genre de chiffre plausible et faux que ce dépôt refuse.
#:
#: Ce que T70 mesure : la perte d'un moteur RELATIVEMENT au meilleur coup connu,
#: sur les décisions qui séparent les moteurs. C'est l'instrument de comparaison
#: dont T71 a besoin, et il est bon pour cela.
#: Ce que T76 devra construire à part : un corpus NON restreint aux décisions
#: disputées, seul capable de porter un PR absolu — avec, en plus, le filtre de
#: décision « non obvious » d'XG que DS-11 documente sans le spécifier.
#: ─────────────────────────────────────────────────────────────────────────
PR_SCALE = 500.0


def score_batch(payload):
    rows, model, ply, prune_model, prune_k, context = payload
    from tools.build_corpus_t70 import CONTEXTS  # noqa: PLC0415

    network = Network.load(model)
    state = CONTEXTS[context]
    prune_net = Network.load(prune_model) if prune_model else None
    config = SearchConfig(ply=ply, filter=FILTERS[ply],
                          use_match=state is not None, match=state,
                          prune_net=prune_net, prune_k=prune_k)

    scored = []
    for row in rows:
        turn = row["turn"]
        position = codec.position_from_id(row["position_id"], turn)
        d1, d2 = row["dice"]
        ranked = search_plays(network, position, d1, d2, config)
        if not ranked:
            continue
        played = codec.position_id(ranked[0].play.result)
        equities = row["equities"]
        best = max(equities)
        try:
            index = row["candidates"].index(played)
        except ValueError:
            # Hors registre : la valeur du coup n'a pas été achetée. Zéro serait
            # un mensonge silencieux — c'est exactement le bug que la règle 2 de
            # CLAUDE.md nomme.
            scored.append({"index": row["index"], "class": row["class"],
                           "weight": row["weight"], "loss": None,
                           "bounded": False, "open": False,
                           "pass_used": row["pass_used"]})
            continue
        # Le coup joué a-t-il été RÉSOLU, ou seulement borné comme dominé ?
        # Un coup manifestement mauvais n'a pas été prix finement (voir
        # `resolution_of` dans l'arbitre) : sa perte est du bon ordre mais son
        # intervalle est large. Compté, et compté à part.
        states = row.get("resolution")
        state = states[index] if states else "resolved"
        scored.append({"index": row["index"], "class": row["class"],
                       "weight": row["weight"], "loss": best - equities[index],
                       "bounded": state == "dominated", "open": state == "open",
                       "pass_used": row["pass_used"]})
    return scored


def weighted_bootstrap(losses, weights, draws: int, seed: int):
    """Moyenne pondérée et IC 95 %, le tirage portant sur les **positions**.

    Rééchantillonner les coups plutôt que les positions sous-estimerait
    l'intervalle : deux coups de la même décision ne sont pas indépendants.
    """
    import numpy as np

    values = np.asarray(losses, dtype=float)
    w = np.asarray(weights, dtype=float)
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean = float((values * w).sum() / w.sum())
    generator = np.random.default_rng(seed)
    picks = generator.integers(0, n, size=(draws, n))
    sampled = values[picks]
    sampled_w = w[picks]
    means = np.sort((sampled * sampled_w).sum(axis=1) / sampled_w.sum(axis=1))
    return mean, float(means[int(0.025 * draws)]), float(means[int(0.975 * draws) - 1])


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", required=True, help="le registre arbitré (.jsonl)")
    parser.add_argument("--model", default=str(MODEL))
    parser.add_argument("--ply", type=int, default=2)
    parser.add_argument("--prune-model", default="")
    parser.add_argument("--prune-k", type=int, default=0)
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--label", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    registry = Path(args.registry)
    rows = [json.loads(line) for line in registry.read_text().splitlines() if line.strip()]
    if not rows:
        print("registre vide", file=sys.stderr)
        return 2
    context = rows[0]["context"]
    label = args.label or f"{Path(args.model).stem} {args.ply}-ply"

    print(f"T70 — {label} sur {registry.name}")
    print(f"  {len(rows)} décisions, contexte {context}", flush=True)

    workers = max(1, min(args.workers, len(rows)))
    chunks = [rows[i::workers] for i in range(workers)]
    payloads = [(chunk, args.model, args.ply, args.prune_model, args.prune_k, context)
                for chunk in chunks if chunk]

    started = time.perf_counter()
    if len(payloads) == 1:
        gathered = [score_batch(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            gathered = list(pool.map(score_batch, payloads))
    elapsed = time.perf_counter() - started

    scored = [s for part in gathered for s in part]
    inside = [s for s in scored if s["loss"] is not None]
    outside = len(scored) - len(inside)
    rate = outside / len(scored) if scored else 0.0

    mean, low, high = weighted_bootstrap([s["loss"] for s in inside],
                                         [s["weight"] for s in inside],
                                         args.bootstrap, args.seed)

    print(f"\n  perte d'équité par décision : {mean:.5f}  "
          f"[{low:.5f} ; {high:.5f}]  (IC 95 %, bootstrap {args.bootstrap})")
    bounded = sum(1 for s in inside if s.get("bounded"))
    unresolved = sum(1 for s in inside if s.get("open"))
    print(f"  décisions notées : {len(inside)}   hors registre : {outside} "
          f"({100 * rate:.2f} %)")
    print(f"  dont le coup joué n'était que borné (dominé) : {bounded} "
          f"({100 * bounded / max(len(inside), 1):.2f} %)")
    print(f"  dont le coup joué était resté ouvert : {unresolved} "
          f"({100 * unresolved / max(len(inside), 1):.2f} %)")
    if bounded > len(inside) * 0.10:
        print("  ⚠ ce moteur joue souvent des coups que l'arbitrage n'a pas prix "
              "finement — sa perte est estimée grossièrement là où il est mauvais.")
    if unresolved > len(inside) * 0.05:
        print("  ⚠ le registre n'a pas résolu une part notable des coups que ce "
              "moteur joue : relever le plafond d'essais avant de conclure.")
    if rate > HORS_CORPUS_ALARM:
        print(f"  ⚠ au-delà de {100 * HORS_CORPUS_ALARM:.0f} %, ce chiffre note le "
              f"corpus autant que le moteur — élargir --width et ré-arbitrer.")
    print(f"  coût du point de comparaison : {elapsed:.0f} s de mur sur "
          f"{workers} processus, soit {elapsed * workers / 3600:.2f} h·cœur")
    print(f"\n  ⚠ {PR_SCALE:.0f} × ce chiffre ({PR_SCALE * mean:.3f}) N'EST PAS un PR :")
    print("    le corpus ne contient que les décisions disputées (~10 % du total),")
    print("    et les décisions écartées ne portent pas une perte nulle — les deux")
    print("    moteurs y jouent le même coup, pas forcément le meilleur. Voir la")
    print("    note en tête de ce fichier.")

    per_class = collections.defaultdict(list)
    for s in inside:
        per_class[s["class"]].append(s)
    print("\n  par classe de position :")
    for name in sorted(per_class, key=lambda k: -len(per_class[k])):
        part = per_class[name]
        m, lo, hi = weighted_bootstrap([s["loss"] for s in part],
                                       [1.0] * len(part), args.bootstrap, args.seed)
        print(f"    {name:22s} n={len(part):5d}  {m:.5f}  [{lo:.5f} ; {hi:.5f}]")

    result = {
        "label": label, "registry": registry.name, "context": context,
        "model": Path(args.model).name, "ply": args.ply,
        "decisions": len(scored), "scored": len(inside),
        "outside": outside, "outside_rate": rate, "bounded": bounded,
        "unresolved": unresolved,
        "loss": mean, "ci95": [low, high],
        "seconds": elapsed, "workers": workers,
        "core_hours": elapsed * workers / 3600,
        "by_class": {name: {"n": len(part),
                            "loss": weighted_bootstrap([s["loss"] for s in part],
                                                       [1.0] * len(part),
                                                       args.bootstrap, args.seed)[0]}
                     for name, part in per_class.items()},
    }
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"\n  → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
