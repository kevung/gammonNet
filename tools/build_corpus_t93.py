#!/usr/bin/env python3
"""T93 — le corpus neutre : les décisions où les deux moteurs comparés divergent.

## Ce que ce corpus corrige, par rapport à celui de T70

Le registre de T70 est conditionné sur **nos** désaccords avec GNU Backgammon.
Il est excellent pour ce qu'il fait — mesurer notre progression contre un étalon
fixe — et inutilisable pour arbitrer entre nous et un troisième moteur : ce
dernier y jouerait sans arrêt des coups que le registre n'a pas achetés, et ces
décisions seraient **écartées** plutôt que comptées (2,47 % pour l'int8 de T73,
jusqu'à 8,39 % pour un candidat de T71). Un chiffre dont on retire les endroits
où l'adversaire fait autre chose n'est pas une comparaison.

Ici, les deux plaideurs sont les deux moteurs comparés, et les **deux coups sont
achetés d'avance**. Le taux hors registre est donc nul par construction — ce que
`bench/compare_t93.py` vérifie plutôt que de le supposer.

## Pourquoi ne garder que les décisions disputées ne biaise pas l'écart

Une décision où les deux jouent le même coup contribue exactement **zéro** à la
différence entre les deux. La restreindre au désaccord ne perd donc rien de
l'écart apparié — c'est l'argument de T36 — et concentre tout le budget
d'arbitrage là où il sépare quelque chose.

**Mais le chiffre qui en sort n'est pas un PR** (T70 le dit déjà) : le
dénominateur est la décision *disputée*, pas la décision. Multiplier par 500 ne
le rend pas comparable à un PR publié.

## Le générateur de positions n'appartient à personne

Les parties d'où viennent les positions sont menées **alternativement** par les
deux moteurs, une partie sur deux, à leur niveau le moins cher. Un corpus
engendré par un seul des deux porterait la distribution de ses propres parties —
c'est la réserve principale que l'on peut faire à l'étude publiée d'en face, et
elle ne coûte rien à lever.

Usage :
    python tools/build_corpus_t93.py --depth 0 --target 5000 --workers 26
    python tools/build_corpus_t93.py --depth 2 --target 5000 --workers 26
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT))

from gammonnet import codec  # noqa: E402
from gammonnet.arena import SageEngine, opening_roll  # noqa: E402
from gammonnet.classify import classify, has_contact  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import BLACK, Position  # noqa: E402
from gammonnet.search import SearchConfig, search_plays, search_level  # noqa: E402
from tools.build_corpus_t70 import (  # noqa: E402
    CLASSES,
    MODEL,
    candidate_results,
    natural_distribution,
)

CORPUS_VERSION = 1

#: La profondeur RÉELLE, et ce qu'elle vaut de chaque côté. Leur étiquette est
#: décalée d'un cran (T92) : leur `1ply` est notre 0-ply. Cette table est le seul
#: endroit du dépôt où l'appariement est écrit, pour qu'il n'y en ait qu'un.
PAIRS = {
    0: {"ours": "ply0", "theirs": "1ply"},
    1: {"ours": "ply1", "theirs": "2ply"},
    2: {"ours": "normal", "theirs": "3ply"},
}

#: Notre configuration à chaque profondeur. `normal` est la forme canonique du
#: C (`gn_search_level`) : le 2-ply `(0,1,3)` avec élagage `k=12`, c'est-à-dire
#: **ce que l'artefact sert réellement**. Comparer une configuration que
#: personne ne reçoit flatterait ou punirait sans rien mesurer d'utile.
def our_config(name: str, network_dir: Path) -> tuple[SearchConfig, dict]:
    if name == "ply0":
        return SearchConfig(ply=0), {"ply": 0, "filter": [], "prune_k": 0}
    if name == "ply1":
        # Non filtré, comme `bench/pr.py` : avec `filter[1] = 1` la passe
        # profonde ne rescore qu'un candidat et le coup reste celui du 0-ply.
        return SearchConfig(ply=1), {"ply": 1, "filter": [], "prune_k": 0}
    level = search_level(name)
    prune = Network.load(str(network_dir / "prune_32.bin")) if level.prune_k else None
    return (
        SearchConfig(ply=level.ply, filter=level.filter,
                     prune_net=prune, prune_k=level.prune_k),
        {"ply": level.ply, "filter": list(level.filter), "prune_k": level.prune_k},
    )


def mixed_positions(rng: random.Random, network, sage, limit: int):
    """Positions de contact atteintes par des parties menées **en alternance**.

    Une partie sur deux est conduite par chaque moteur, à son niveau le moins
    cher — l'évaluation statique des deux côtés. Ce n'est pas la politique qu'on
    compare, c'est celle qui **place les pions** : elle doit n'appartenir à
    personne.
    """
    produced = 0
    game = 0
    while produced < limit:
        driver_is_ours = (game % 2 == 0)
        game += 1
        position = Position.initial()
        first, d1, d2 = opening_roll(rng)
        if first == BLACK:
            position = position.swapped_turn()
        for _ in range(300):
            if position.is_over():
                break
            plays = position.legal_plays(d1, d2)
            if len(plays) >= 3 and has_contact(position):
                yield position, d1, d2, driver_is_ours
                produced += 1
                if produced >= limit:
                    return
            if plays:
                if driver_is_ours:
                    position = search_plays(
                        network, position, d1, d2, SearchConfig(ply=0)
                    )[0].play.result
                else:
                    position = sage.choose(position, d1, d2, rng).result
            else:
                position = position.swapped_turn()
            d1, d2 = rng.randint(1, 6), rng.randint(1, 6)


def harvest(payload):
    """Un lot : compare les deux moteurs, garde ce sur quoi ils divergent."""
    seed, count, depth, width, quota, model, out_dir = payload

    network = Network.load(model)
    pair = PAIRS[depth]
    config, ours_spec = our_config(pair["ours"], Path(model).parent)
    theirs = SageEngine(level=pair["theirs"])
    driver = SageEngine(level="1ply")
    rng = random.Random(seed)
    theirs_rng = random.Random(0)

    kept: list[dict] = []
    taken = collections.Counter()
    examined = compared = agreed = 0
    started = time.perf_counter()

    for position, d1, d2, driven_by_us in mixed_positions(rng, network, driver, count):
        examined += 1
        klass = classify(position)
        if quota and taken[klass] >= quota.get(klass, 0):
            continue

        ranked = search_plays(network, position, d1, d2, config)
        if not ranked:
            continue
        mine = ranked[0].play
        yours = theirs.choose(position, d1, d2, theirs_rng)
        compared += 1
        if yours is None or mine.result == yours.result:
            agreed += 1
            continue

        results = candidate_results(network, position, d1, d2, mine, yours,
                                    width, None)
        ids = [codec.position_id(r) for r in results]
        taken[klass] += 1
        kept.append({
            "position_id": codec.position_id(position),
            "turn": position.turn,
            "dice": [d1, d2],
            "context": "money",
            "depth": depth,
            "class": klass,
            "game_plan": _game_plan(position),
            "driven_by_us": driven_by_us,
            "candidates": ids,
            "ours": 0,
            "theirs": ids.index(codec.position_id(yours.result)),
        })

    return {
        "kept": kept,
        "examined": examined,
        "compared": compared,
        "agreed": agreed,
        "illegal_skipped": theirs.illegal_skipped + driver.illegal_skipped,
        "seconds": time.perf_counter() - started,
        "ours_spec": ours_spec,
    }


def _game_plan(position: Position) -> str:
    """Leur propre taxonomie de plan de jeu, relevée sans être adoptée.

    T77 a mesuré que notre découpage ne justifie aucune tête spécialisée. Leur
    découpage n'est pas le même ; le relever ici coûte une microseconde et permet
    à T93 de lire l'erreur dans **les deux** taxonomies. C'est une lecture, pas
    une adoption : rien ici ne s'aiguille dessus.
    """
    import bgsage

    from gammonnet.sage_board import to_sage

    return bgsage.classify_game_plan(to_sage(position))


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--depth", type=int, required=True, choices=sorted(PAIRS))
    parser.add_argument("--target", type=int, default=5_000)
    parser.add_argument("--width", type=int, default=6)
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--seed", type=int, default=20260907)
    parser.add_argument("--natural-sample", type=int, default=20_000)
    parser.add_argument("--floor", type=float, default=0.04)
    parser.add_argument("--examine-factor", type=float, default=14.0)
    parser.add_argument("--out", default=str(ROOT / "docs" / "corpus" / "t93"))
    args = parser.parse_args()

    pair = PAIRS[args.depth]
    out = Path(args.out) / f"depth-{args.depth}"
    out.mkdir(parents=True, exist_ok=True)

    print(f"T93 — corpus neutre, profondeur réelle {args.depth}")
    print(f"  nous « {pair['ours']} »   eux « {pair['theirs']} »  "
          f"(leur étiquette est décalée d'un cran, T92)")
    print(f"  {args.target} décisions disputées visées, graine {args.seed}", flush=True)

    start = time.perf_counter()
    natural = natural_distribution(args.seed, args.natural_sample)
    print(f"  distribution naturelle mesurée en {time.perf_counter() - start:.0f} s")

    populated = [name for name in CLASSES if natural[name] > 0]
    share = {name: max(args.floor, natural[name]) for name in populated}
    total_share = sum(share.values())
    quota = {name: max(1, round(args.target * share[name] / total_share))
             for name in populated}

    workers = max(1, args.workers)
    per_worker_quota = {name: max(1, -(-quota[name] // workers)) for name in quota}
    budget = int(args.target * args.examine_factor / workers) + 1
    payloads = [(args.seed + 7919 * i + 104_729 * args.depth, budget, args.depth,
                 args.width, per_worker_quota, str(MODEL), str(out))
                for i in range(workers)]

    started = time.perf_counter()
    if workers == 1:
        gathered = [harvest(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            gathered = list(pool.map(harvest, payloads))
    elapsed = time.perf_counter() - started

    rows: list[dict] = []
    examined = compared = agreed = illegal = 0
    for chunk in gathered:
        rows.extend(chunk["kept"])
        examined += chunk["examined"]
        compared += chunk["compared"]
        agreed += chunk["agreed"]
        illegal += chunk["illegal_skipped"]

    counts = collections.Counter(row["class"] for row in rows)
    total = len(rows)
    for index, row in enumerate(rows):
        row["index"] = index
        row["weight"] = (natural[row["class"]] / (counts[row["class"]] / total)
                         if counts[row["class"]] else 0.0)

    path = out / "corpus-money.jsonl"
    with open(path, "w") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = {
        "version": CORPUS_VERSION,
        "depth": args.depth,
        "pair": pair,
        "ours_spec": gathered[0]["ours_spec"],
        "seed": args.seed,
        "width": args.width,
        "model": MODEL.name,
        "natural": natural,
        "quota": quota,
        "decisions": total,
        "compared": compared,
        "agreed": agreed,
        "examined": examined,
        "disagreement_rate": (total / compared) if compared else 0.0,
        "illegal_skipped": illegal,
        "by_class": dict(counts),
        "by_game_plan": dict(collections.Counter(r["game_plan"] for r in rows)),
        "driven_by_us": sum(1 for r in rows if r["driven_by_us"]),
        "seconds": elapsed,
        "sha256": digest,
    }
    (out / "manifeste.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n  {total} décisions disputées sur {compared} comparées "
          f"({100 * manifest['disagreement_rate']:.1f} %)")
    print(f"  {examined} positions traversées, {elapsed / 60:.1f} min")
    print(f"  coups illégaux du moteur tiers écartés : {illegal}")
    print(f"  parties menées par nous : {manifest['driven_by_us']} / {total}")
    print(f"  {path}  sha256 {digest[:16]}…")
    for name in sorted(counts, key=lambda k: -counts[k]):
        print(f"    {name:22s} {counts[name]:6d}  (quota {quota.get(name, 0)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
