#!/usr/bin/env python3
"""T3E — le Performance Rating, la métrique que la phase 3 attend depuis le début.

## Ce que le PR est, et pourquoi il n'a jamais tourné

`PLAN.md` libelle la condition de sortie de la phase 3 en PR : **1,06 au 0-ply,
~0,50 au 1-ply, ~0,22 au 2-ply** — les chiffres publiés par l'auteur du modèle.
Et il en fait un test bloquant, pour une raison qui n'est pas cosmétique :

> *« Un PR qui ne bouge pas quand on ajoute un ply signale une recherche fausse.
> C'est le test le plus révélateur de toute la chaîne. »*

Le PR est le **taux d'erreur** d'un joueur, jugé par un analyseur plus fort :

    PR = 500 × (équité moyenne perdue par décision)

Le facteur 500 est une convention d'affichage, pas un calcul : il met un joueur
de club vers 10 et un moteur vers 0,5.

## L'arbitre, et pourquoi il doit être plus fort que le sujet

Un joueur ne peut pas juger ses propres erreurs : il choisirait toujours ce
qu'il croit le meilleur, et son PR serait zéro par construction. L'arbitre est
donc **GNU Backgammon à une profondeur supérieure à toutes celles mesurées** —
le même pour les trois, sinon les trois colonnes ne se compareraient pas entre
elles.

**L'appariement est par construction** : gnubg n'est pas invité à choisir un
coup dans sa notation, il est invité à **évaluer nos positions résultantes**. Il
classe donc exactement l'ensemble où notre moteur a choisi, et la perte est
l'écart entre son meilleur et le nôtre — pas un artefact de lecture.

## Ce que cette mesure ne dit pas

Le PR n'est pas une force en ppg et ne s'y convertit pas. C'est un taux d'erreur
par décision, comparable entre configurations du même moteur et à la référence
publiée. La force, c'est T35 qui la donne.

Usage :
    python bench/pr.py --decisions 2000 --plies 0,1,2 --arbiter-ply 3 --workers 26
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from decision_loss import corpus  # noqa: E402

from gammonnet.arena import bootstrap_ci  # noqa: E402
from gammonnet.gnubg_board import to_gnubg  # noqa: E402
from gammonnet.gnubg_engine import GnubgSession  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
PRUNE = ROOT / "models" / "prune_32.bin"
SEED = 20260827

#: `op_eval` rend six flottants : les cinq probabilités, puis l'équité.
EQUITY = 5

#: La convention d'affichage du PR. Ce n'est pas un calcul.
PR_SCALE = 500.0

#: Les configurations mesurées, telles qu'elles sont réellement employées.
#:
#: LE 1-PLY EST NON FILTRÉ, ET C'EST LE POINT DÉLICAT. Avec `filter[1] = 1` la
#: passe profonde ne rescore qu'un seul candidat — celui que la passe
#: superficielle a mis en tête — donc le coup choisi reste EXACTEMENT celui du
#: 0-ply, et le PR ne bouge pas. Un pilote l'a montré : 0,946 aux deux
#: profondeurs, au chiffre près. `gn_search.c` documente ce piège pour la même
#: raison, et `PLAN.md` traite un PR qui ne descend pas comme la signature
#: d'une recherche fausse — ici c'était la signature d'un filtre mal posé.
#:
#: Le 2-ply porte le filtre de la campagne T35, parce que c'est la
#: configuration dont la force est mesurée.
FILTERS = {0: (), 1: (), 2: (0, 1, 3)}

#: L'élagage n'a de sens qu'à partir du 2-ply : plus bas il ne ferait que
#: tronquer la liste des candidats sans rien accélérer de significatif, et il
#: fausserait la comparaison avec la référence publiée.
PRUNE_FROM_PLY = 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=int, default=2000)
    parser.add_argument("--plies", default="0,1,2")
    parser.add_argument("--arbiter-ply", type=int, default=3)
    parser.add_argument("--prune-k", type=int, default=12)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "docs" / "mesures" / "t3e-pr.json")
    args = parser.parse_args()

    # `--plies 0,1,2,2@0` : la dernière entrée est un 2-ply SANS élagage.
    # L'arbitre ne dépendant pas de la configuration jugée, mesurer plusieurs
    # configurations dans le même passage coûte ce que coûte le sujet — cinq
    # minutes — au lieu d'un second arbitrage d'une heure.
    plies = []
    for token in args.plies.split(","):
        if "@" in token:
            ply, k = token.split("@")
            plies.append((int(ply), int(k)))
        else:
            plies.append((int(token), None))
    if args.arbiter_ply <= max(p for p, _ in plies):
        print(f"REFUSÉ : l'arbitre ({args.arbiter_ply}-ply) doit être PLUS FORT "
              f"que tout ce qu'il juge (jusqu'à {max(p for p, _ in plies)}-ply). Un joueur qui "
              f"s'arbitre lui-même a un PR de zéro par construction.")
        return 2

    print(f"1. Corpus — {args.decisions} décisions de contact")
    net = Network.load(MODEL)
    small = Network.load(PRUNE) if args.prune_k else None
    cases = corpus(args.decisions, SEED, net)
    print(f"   {len(cases)} décisions")

    # L'arbitre coûte l'essentiel du temps — 68 min pour 600 décisions — et il
    # ne dépend QUE du corpus et de sa profondeur, pas de la configuration
    # jugée. Le mettre en cache rend la question « et sans élagage ? »
    # rejouable en cinq minutes au lieu de soixante-dix, ce qui est la
    # différence entre vérifier une hypothèse et la supposer.
    cache = (ROOT / "build" /
             f"pr-arbiter-{args.decisions}-{SEED}-{args.arbiter_ply}ply.json")
    if cache.exists():
        print(f"\n2. L'arbitre : repris du cache {cache.name}")
        reference = json.loads(cache.read_text())
        print(f"   {len(reference)} décisions")
        return _subjects(args, plies, cases, reference, net, small)

    print(f"\n2. L'arbitre : gnubg {args.arbiter_ply}-ply sur tous les coups légaux")
    started = time.time()
    reference: list[dict] = []
    with GnubgSession() as engine:
        for index, (position, d1, d2) in enumerate(cases):
            plays = position.legal_plays(d1, d2)
            if len(plays) < 2:
                reference.append({})
                continue
            boards = [to_gnubg(play.result) for play in plays]
            values = engine.evaluate(boards, plies=args.arbiter_ply, prune=0)
            # La position résultante a rendu la main : sa valeur est celle de
            # l'adversaire, d'où la négation.
            reference.append({
                play.result.id() if hasattr(play.result, "id") else str(play.result):
                -value[EQUITY] for play, value in zip(plays, values)})
            if (index + 1) % 200 == 0:
                print(f"   {index + 1}/{len(cases)}  "
                      f"({time.time() - started:.0f} s)")
    print(f"   {time.time() - started:.0f} s")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(reference))
    return _subjects(args, plies, cases, reference, net, small)


def _subjects(args, plies, cases, reference, net, small) -> int:
    report = {"task": "T3E", "metric": "PR = 500 x equity lost per decision",
              "decisions": len(cases), "arbiter": f"gnubg {args.arbiter_ply}-ply",
              "seed": SEED, "prune_k": args.prune_k, "results": {}}

    print(f"\n3. Le sujet, à chaque profondeur")
    print(f"   {'ply':>4} {'décisions':>10} {'PR':>8} {'IC 95 %':>20} "
          f"{'accord':>8}")
    for ply, override in plies:
        k = args.prune_k if override is None else override
        use_prune = k > 0 and ply >= PRUNE_FROM_PLY
        config = SearchConfig(ply=ply, filter=FILTERS.get(ply, ()),
                              prune_net=small if use_prune else None,
                              prune_k=k if use_prune else 0)
        label = f"{ply}" if override is None else f"{ply}@{override}"
        losses, agree, counted = [], 0, 0
        for (position, d1, d2), table in zip(cases, reference):
            if not table:
                continue
            ranked = search_plays(net, position, d1, d2, config)
            if not ranked:
                continue
            key = str(ranked[0].play.result)
            if key not in table:
                continue           # élagué hors de notre liste : non jugeable
            best = max(table.values())
            losses.append(best - table[key])
            agree += (best - table[key]) < 1e-9
            counted += 1

        mean_loss = statistics.mean(losses)
        lo, hi = bootstrap_ci(losses, resamples=args.bootstrap, seed=SEED)
        report["results"][label] = {
            "decisions": counted, "ply": ply, "prune_k": k if use_prune else 0,
            "pr": PR_SCALE * mean_loss,
            "pr_ci": [PR_SCALE * lo, PR_SCALE * hi],
            "agreement": agree / counted,
            "mean_loss": mean_loss,
        }
        print(f"   {label:>4} {counted:>10} {PR_SCALE * mean_loss:>8.3f} "
              f"[{PR_SCALE * lo:>7.3f} ; {PR_SCALE * hi:>7.3f}] "
              f"{100 * agree / counted:>7.1f}%")

    args.out.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"\n→ {args.out}")

    ordered = [report["results"][f"{p}" if o is None else f"{p}@{o}"]["pr"]
               for p, o in plies if o is None]
    if len(ordered) > 1 and not all(a > b for a, b in zip(ordered, ordered[1:])):
        print("\nATTENTION : le PR ne descend pas à chaque ply. `PLAN.md` traite "
              "cela comme BLOQUANT — c'est la signature d'une recherche fausse.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
