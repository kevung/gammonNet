#!/usr/bin/env python3
"""T70 — le corpus figé de décisions disputées.

## Ce que ce fichier produit, et pourquoi ainsi

Un **corpus versionné** de décisions où notre 2-ply et GNU Backgammon 2-ply ne
jouent pas le même coup. Une décision où les deux moteurs s'accordent ne sépare
personne : elle coûterait un arbitrage pour rendre zéro. Ne garder que les
désaccords concentre tout le budget d'arbitrage là où il achète de l'information.

Trois choix méritent d'être défendus.

**Les candidats, pas les deux coups.** Une décision ne retient pas seulement
notre coup et le leur : elle retient les `k` meilleurs au 0-ply, plus ces deux-là
d'office. Sans cela, le corpus ne servirait qu'à comparer *ces* deux moteurs, une
fois ; avec, l'arbitrage payé une seule fois donne l'équité de **tout** coup
qu'un candidat futur pourrait jouer. C'est ce qui fait tenir la promesse de la
fiche — un point de comparaison en heures, pas en jours.

Un candidat qui jouerait hors de cet ensemble n'est **pas** compté zéro : la
décision est marquée `hors-corpus` et rapportée à part. Une entrée manquante qui
vaut zéro par défaut est le bug invisible que `CLAUDE.md` nomme.

**La stratification, et son poids.** Tirer au fil de l'eau donnerait un corpus
fait à 42 % de `contact` et à 1,6 % de `backgame` : les strates rares n'auraient
jamais d'intervalle lisible. On impose donc des quotas — et l'on enregistre pour
chaque décision le **poids** qui rétablit la fréquence naturelle, mesurée en
passe 1. La moyenne pondérée est sans biais ; les strates se lisent séparément.
Sans ce poids, sur-représenter les backgames déplacerait le chiffre global.

**Les contextes de score ne se mélangent pas.** Pondérer money contre 2-away
demanderait une distribution de scores réels, que ce dépôt n'a pas. Chaque
contexte rend donc son chiffre ; il n'existe aucune moyenne « tous contextes ».

## Sortie

`corpus.jsonl` — une décision par ligne — et `manifeste.json` : version, graine,
quotas, distribution naturelle, empreinte SHA-256 du corpus. L'empreinte est ce
qui rend le mot « figé » vérifiable.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import codec  # noqa: E402
from gammonnet.arena import opening_roll  # noqa: E402
from gammonnet.classify import CLASSES, classify, has_contact  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from gammonnet.rules import BLACK, Position  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"

#: Le format du corpus. Toute rupture de compatibilité l'incrémente — un banc
#: qui lirait un corpus d'une autre version rendrait des chiffres muets.
CORPUS_VERSION = 1

#: L'indexation du filtre est celle du C : `filter[d]` s'applique à un nœud de
#: profondeur RESTANTE `d`. Reprise de `bench/decision_loss.py`, sans variante :
#: deux définitions du même joueur seraient deux joueurs.
FILTERS = {0: (), 1: (0, 5), 2: (0, 1, 5), 3: (0, 1, 1, 5)}

#: Les contextes de score. `money` est Jacoby, la convention du dépôt ; les
#: autres sont des scores où la décision de coup est connue pour s'écarter du
#: money. Ils ne se moyennent jamais entre eux.
CONTEXTS = {
    "money": None,
    "2a-2a": MatchState(2, 2),
    "3a-3a": MatchState(3, 3),
    "4a-2a": MatchState(4, 2),
    "2a-4a": MatchState(2, 4),
}


def context_state(name: str) -> MatchState | None:
    return CONTEXTS[name]


def play_positions(rng: random.Random, network, limit: int):
    """Un flux de positions de contact atteintes par un jeu 0-ply plausible.

    Le jeu aléatoire produit des positions que personne ne rencontre ; le 0-ply
    en donne de réalistes à peu de frais. On ne garde que le contact avec au
    moins trois coups légaux : sans choix, il n'y a pas de décision.
    """
    produced = 0
    while produced < limit:
        position = Position.initial()
        first, d1, d2 = opening_roll(rng)
        if first == BLACK:
            position = position.swapped_turn()
        for _ in range(300):
            if position.is_over():
                break
            plays = position.legal_plays(d1, d2)
            if len(plays) >= 3 and has_contact(position):
                yield position, d1, d2
                produced += 1
                if produced >= limit:
                    return
            if plays:
                position = search_plays(network, position, d1, d2,
                                        SearchConfig(ply=0))[0].play.result
            else:
                position = position.swapped_turn()
            d1, d2 = rng.randint(1, 6), rng.randint(1, 6)


def natural_distribution(seed: int, sample: int) -> dict[str, float]:
    """La fréquence de chaque classe **dans les décisions réelles**.

    C'est le dénominateur du poids de stratification, et c'est aussi, telle
    quelle, la colonne « poids de la catégorie » que T77 demande.
    """
    network = Network.load(str(MODEL))
    rng = random.Random(seed)
    counts = collections.Counter()
    for position, _d1, _d2 in play_positions(rng, network, sample):
        counts[classify(position)] += 1
    total = sum(counts.values())
    return {name: counts.get(name, 0) / total for name in CLASSES}


def candidate_results(network, position, d1, d2, ours_play, theirs_play,
                      width: int, state):
    """Les résultats à arbitrer : les `width` meilleurs au 0-ply, plus les deux
    coups choisis, sans doublon et dans un ordre stable.

    L'ordre est celui du 0-ply, notre coup et le leur poussés en tête s'ils
    manquaient : un corpus dont l'ordre dépendrait du hasard ne serait pas figé.
    """
    config = SearchConfig(ply=0, use_match=state is not None, match=state)
    ranked = search_plays(network, position, d1, d2, config)
    chosen: list[Position] = []
    seen: set[str] = set()

    def push(result: Position) -> None:
        key = codec.position_id(result)
        if key not in seen:
            seen.add(key)
            chosen.append(result)

    push(ours_play.result)
    if theirs_play is not None:
        push(theirs_play.result)
    for entry in ranked[:width]:
        push(entry.play.result)
    return chosen


def harvest(payload):
    """Un lot : examine des décisions, rend celles où les deux moteurs divergent."""
    seed, count, context, width, ply, quota, model = payload
    from gammonnet.gnubg_engine import GnubgEngine

    network = Network.load(model)
    state = context_state(context)
    ours_config = SearchConfig(ply=ply, filter=FILTERS[ply],
                               use_match=state is not None, match=state)
    theirs = GnubgEngine(ply=ply, filter=FILTERS[ply])
    gnubg_state = None
    if state is not None:
        from gammonnet.gnubg_engine import gnubg_state as make_state
        # L'état vu par le joueur au trait des positions résultantes, soit
        # l'adversaire de celui qui choisit — la convention sondée en T35.
        gnubg_state = make_state(0, MatchState(state.away_opponent,
                                               state.away_on_roll,
                                               state.cube, state.crawford),
                                 jacoby=False, beavers=False)

    rng = random.Random(seed)
    kept: list[dict] = []
    taken = collections.Counter()
    examined = 0
    coverage = 0

    for position, d1, d2 in play_positions(rng, network, count):
        examined += 1
        klass = classify(position)
        if quota and taken[klass] >= quota.get(klass, 0):
            continue

        ranked = search_plays(network, position, d1, d2, ours_config)
        if not ranked:
            continue
        mine = ranked[0].play
        yours = theirs.choose(position, d1, d2, rng, gnubg_state)
        if yours is None or mine.result == yours.result:
            continue

        results = candidate_results(network, position, d1, d2, mine, yours,
                                    width, state)
        ids = [codec.position_id(r) for r in results]
        coverage += 1
        taken[klass] += 1
        kept.append({
            "position_id": codec.position_id(position),
            "turn": position.turn,
            "dice": [d1, d2],
            "context": context,
            "class": klass,
            "candidates": ids,
            "ours": 0,
            "gnubg": ids.index(codec.position_id(yours.result)),
        })

    return kept, examined, dict(taken), coverage


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", type=int, default=10_000,
                        help="décisions disputées visées, par contexte")
    parser.add_argument("--contexts", default="money")
    parser.add_argument("--ply", type=int, default=2)
    parser.add_argument("--width", type=int, default=6,
                        help="candidats arbitrés par décision, hors les deux coups joués")
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--natural-sample", type=int, default=20_000)
    parser.add_argument("--floor", type=float, default=0.04,
                        help="part minimale de chaque classe peuplée dans le corpus")
    parser.add_argument("--examine-factor", type=float, default=14.0,
                        help="positions examinées par décision visée (taux de désaccord ~9,5 %%)")
    parser.add_argument("--out", default=str(ROOT / "docs" / "corpus" / "t70"))
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    contexts = [c.strip() for c in args.contexts.split(",") if c.strip()]
    for context in contexts:
        if context not in CONTEXTS:
            print(f"contexte inconnu : {context}", file=sys.stderr)
            return 2

    print("T70 — corpus figé de décisions disputées")
    print(f"  contextes : {', '.join(contexts)}   {args.target} décisions visées par contexte")
    print(f"  profondeur {args.ply}, {args.width} candidats, graine {args.seed}", flush=True)

    start = time.perf_counter()
    natural = natural_distribution(args.seed, args.natural_sample)
    print(f"  distribution naturelle mesurée sur {args.natural_sample} décisions "
          f"en {time.perf_counter() - start:.0f} s")
    for name in CLASSES:
        if natural[name]:
            print(f"    {name:22s} {100 * natural[name]:5.2f} %")

    # Les quotas : un plancher pour que chaque classe peuplée ait un intervalle
    # lisible, la fréquence naturelle au-delà. Le poids rétablit ensuite le
    # dénominateur réel — c'est lui qui fait que ce plancher ne biaise rien.
    populated = [name for name in CLASSES if natural[name] > 0]
    share = {name: max(args.floor, natural[name]) for name in populated}
    total_share = sum(share.values())
    quota = {name: max(1, round(args.target * share[name] / total_share))
             for name in populated}
    print("\n  quotas de stratification :")
    for name in populated:
        print(f"    {name:22s} {quota[name]:6d}   poids "
              f"{natural[name] / (quota[name] / sum(quota.values())):.3f}")

    manifest = {
        "version": CORPUS_VERSION,
        "seed": args.seed,
        "ply": args.ply,
        "width": args.width,
        "filters": {str(k): list(v) for k, v in FILTERS.items()},
        "model": MODEL.name,
        "natural_sample": args.natural_sample,
        "natural": natural,
        "quota": quota,
        "contexts": {},
    }

    for context in contexts:
        print(f"\n  ── {context} ──", flush=True)
        workers = max(1, args.workers)
        per_worker_quota = {name: max(1, -(-quota[name] // workers)) for name in quota}
        budget = int(args.target * args.examine_factor / workers) + 1
        # `hash()` d'une chaîne varie d'un processus Python à l'autre
        # (PYTHONHASHSEED) : s'en servir ici rendrait le corpus irreproductible
        # sans que rien ne le signale. L'index du contexte dans CONTEXTS est
        # stable, et c'est tout ce qu'on demandait à ce terme.
        offset = list(CONTEXTS).index(context) * 104_729
        payloads = [(args.seed + 7919 * i + offset, budget, context,
                     args.width, args.ply, per_worker_quota, str(MODEL))
                    for i in range(workers)]

        started = time.perf_counter()
        if workers == 1:
            gathered = [harvest(payloads[0])]
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                gathered = list(pool.map(harvest, payloads))
        elapsed = time.perf_counter() - started

        rows: list[dict] = []
        examined = 0
        for kept, seen, _taken, _cov in gathered:
            rows.extend(kept)
            examined += seen

        counts = collections.Counter(row["class"] for row in rows)
        total = len(rows)
        for index, row in enumerate(rows):
            row["index"] = index
            # Le poids : fréquence naturelle de la strate ÷ sa part ici.
            row["weight"] = (natural[row["class"]] / (counts[row["class"]] / total)
                             if counts[row["class"]] else 0.0)

        path = out / f"corpus-{context}.jsonl"
        with open(path, "w") as fh:
            for row in rows:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()

        rate = total / examined if examined else 0.0
        print(f"    {total} décisions disputées sur {examined} examinées "
              f"({100 * rate:.1f} %) en {elapsed / 60:.1f} min")
        print(f"    {path.name}  sha256 {digest[:16]}…")
        manifest["contexts"][context] = {
            "decisions": total,
            "examined": examined,
            "disagreement_rate": rate,
            "seconds": elapsed,
            "sha256": digest,
            "by_class": dict(counts),
        }

    (out / "manifeste.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"\n  manifeste : {out / 'manifeste.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
