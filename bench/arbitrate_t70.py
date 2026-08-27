#!/usr/bin/env python3
"""T70 — l'arbitre escaladé : le registre d'équité du corpus figé.

## Le principe

Le corpus (`tools/build_corpus_t70.py`) dit **quelles** décisions sont
disputées et **quels coups** y sont plausibles. Ce banc dit ce que chaque coup
vaut. Le résultat est un registre : une ligne par décision, l'équité de chaque
candidat, l'erreur sur son écart au pivot, et la passe qui l'a tranchée.

Le registre est ce qui rend un point de comparaison rapide. Une fois payé, noter
un moteur candidat ne demande plus aucun rollout : il joue, on lit.

## L'escalade, et pourquoi elle a trois marches

Un rollout complet à IC 95 % < 0,005 sur toutes les décisions coûterait des
jours. Or la plupart des décisions ne le méritent pas : quand un coup domine
franchement, un instrument grossier le voit aussi bien qu'un instrument fin.

| passe | instrument | quand |
|---|---|---|
| **0** | table bilatérale exacte | tous les candidats dans son domaine |
| **1** | gnubg 3-ply | l'écart meilleur/second dépasse `--net` |
| **2** | rollout tronqué, variance réduite, dés communs | sinon |
| **3** | rollout complet, dés communs | ce que la passe 2 n'a pas tranché |

La passe 0 est sans variance ni réserve. La passe 1 est **biaisée en faveur de
gnubg** — c'est son instrument qui parle — et ce biais n'est pas supposé petit :
il est mesuré, par `--audit`, qui rejoue en passe 2 un échantillon de ce que la
passe 1 a tranché. L'écart est publié avec chaque usage du registre. Un arbitre
qu'on n'a pas vérifié n'arbitre rien (règle T39).

## Ce que ce banc ne fait pas

Il ne rend aucun verdict de force. Il produit l'échelle ; la lecture est dans
`bench/measure_t70.py`.
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

from gammonnet import codec  # noqa: E402
from gammonnet import gnubg_board as gb  # noqa: E402
from gammonnet.bearoff import TwoSidedBearoff  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from gammonnet.rollout import RolloutConfig, rollout_candidates_paired  # noqa: E402
from gammonnet.rules import BLACK, WHITE, Position  # noqa: E402
from gammonnet.search import SearchConfig  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"
PROGRESS = Path(os.environ.get("T70_PROGRESS", "/tmp/t70-arbitrage-progress.log"))

#: La profondeur de la passe 1. Supérieure à celle des moteurs comparés (2-ply),
#: sans quoi elle arbitrerait avec le regard de l'un des deux plaideurs.
ARBITER_PLY = 3

#: L'écart meilleur/second, en équité money, au-dessus duquel la passe 1 tranche
#: seule. Choisi rond, et **avant** d'avoir vu un résultat ; sa justesse est
#: précisément ce que `--audit` mesure.
NET_MARGIN = 0.020

#: La cible de la passe 3 : IC 95 % < 0,005, soit un se de 0,005 / 1,96.
FULL_TARGET_SE = 0.005 / 1.96

#: Le se visé par la passe 2. Plus lâche que la passe 3 : son rôle est de
#: trancher ce qui se tranche vite, pas de tout résoudre.
TRUNCATED_TARGET_SE = 0.006


def context_state(context: str) -> MatchState | None:
    from tools.build_corpus_t70 import CONTEXTS  # noqa: PLC0415
    return CONTEXTS[context]


def _load_contexts():
    sys.path.insert(0, str(ROOT))
    from tools.build_corpus_t70 import CONTEXTS  # noqa: PLC0415
    return CONTEXTS


def decided(differences, errors, pivot: int, margin: float) -> bool:
    """Le classement est-il déterminé ?

    Non pas « le meilleur est-il connu » — on veut l'équité de **tous** les
    candidats, puisque le registre servira à noter des moteurs qui n'existent
    pas encore. La décision porte donc sur le pire intervalle : tant qu'un seul
    candidat reste flou, la décision n'est pas tranchée.
    """
    for index, error in enumerate(errors):
        if index == pivot:
            continue
        if 1.96 * error > margin:
            return False
    return True


def arbitrate_batch(payload):
    """Une tranche du corpus, arbitrée de bout en bout par un processus."""
    (rows, context, model, seed, net_margin, truncated_trials, full_trials,
     truncate, resolution, audit_indices) = payload

    from gammonnet.gnubg_engine import GnubgSession, gnubg_state

    network = Network.load(model)
    session = GnubgSession()
    table = TwoSidedBearoff(str(DATABASE)) if DATABASE.exists() else None
    state = context_state(context)
    request_state = None
    if state is not None:
        request_state = gnubg_state(0, MatchState(state.away_opponent,
                                                  state.away_on_roll,
                                                  state.cube, state.crawford),
                                    jacoby=False, beavers=False)

    out = []
    for row in rows:
        turn = row["turn"]
        mover = turn
        opponent = BLACK if mover == WHITE else WHITE
        # Les candidats sont des positions APRÈS coup : le trait est passé.
        results = [codec.position_from_id(pid, opponent) for pid in row["candidates"]]
        record = dict(row)
        started = time.perf_counter()

        # ── Passe 0 : la table exacte ───────────────────────────────
        if (table is not None and state is None
                and all(table.contains(r) for r in results)):
            # `equity` répond pour le joueur au trait de la position confiée,
            # soit l'adversaire de celui qui a joué : d'où la négation, la même
            # qui court dans tout ce dépôt.
            equities = [-table.equity(r).equity for r in results]
            record.update(pass_used=0, equities=equities,
                          errors=[0.0] * len(results),
                          trials=0, seconds=time.perf_counter() - started)
            out.append(record)
            _tick()
            continue

        # ── Passe 1 : gnubg 3-ply ───────────────────────────────────
        values = session.evaluate([gb.to_gnubg(r) for r in results],
                                  plies=ARBITER_PLY, prune=1, state=request_state)
        gnubg_equities = [-float(v[5]) for v in values]
        ordered = sorted(gnubg_equities, reverse=True)
        margin = ordered[0] - ordered[1] if len(ordered) > 1 else float("inf")
        audit = row["index"] in audit_indices

        if margin >= net_margin and not audit:
            record.update(pass_used=1, equities=gnubg_equities,
                          errors=[0.0] * len(results), margin=margin,
                          trials=0, seconds=time.perf_counter() - started)
            out.append(record)
            _tick()
            continue

        # ── Passe 2 : rollout tronqué, variance réduite ─────────────
        pivot = max(range(len(results)), key=lambda i: gnubg_equities[i])
        config = RolloutConfig(trials=truncated_trials, truncate=truncate,
                               seed=seed + row["index"], policy=SearchConfig(ply=0),
                               variance_reduction=True,
                               target_se=TRUNCATED_TARGET_SE, min_trials=216,
                               match=state, use_cube=False)
        equities, differences, errors, trials = rollout_candidates_paired(
            network, results, config, pivot)
        used, total_trials = 2, trials

        if not decided(differences, errors, pivot, resolution):
            # ── Passe 3 : rollout complet ───────────────────────────
            config = RolloutConfig(trials=full_trials, truncate=0,
                                   seed=seed + row["index"],
                                   policy=SearchConfig(ply=0),
                                   variance_reduction=True,
                                   target_se=FULL_TARGET_SE, min_trials=648,
                                   match=state, use_cube=False)
            equities, differences, errors, trials = rollout_candidates_paired(
                network, results, config, pivot)
            used, total_trials = 3, trials

        record.update(pass_used=used, equities=equities, differences=differences,
                      errors=errors, pivot=pivot, trials=total_trials,
                      seconds=time.perf_counter() - started)
        if audit:
            # L'audit garde les DEUX lectures de la même décision : c'est
            # l'écart entre elles qui chiffre le biais de la passe 1.
            record["audit_pass1"] = gnubg_equities
            record["audit_margin"] = margin
        out.append(record)
        _tick()

    session.close()
    if table is not None:
        table.close()
    return out


def _tick():
    try:
        with open(PROGRESS, "a") as fh:
            fh.write("x\n")
    except OSError:
        pass


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", required=True, help="le .jsonl à arbitrer")
    parser.add_argument("--out", default="", help="registre de sortie (.jsonl)")
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--net", type=float, default=NET_MARGIN)
    parser.add_argument("--resolution", type=float, default=0.005,
                        help="largeur d'IC 95 %% en deçà de laquelle on s'arrête")
    parser.add_argument("--truncated-trials", type=int, default=1296)
    parser.add_argument("--full-trials", type=int, default=5184)
    parser.add_argument("--truncate", type=int, default=11)
    parser.add_argument("--audit", type=float, default=0.05,
                        help="part des décisions tranchées en passe 1 rejouées en passe 2")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    corpus = Path(args.corpus)
    rows = [json.loads(line) for line in corpus.read_text().splitlines() if line.strip()]
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        print("corpus vide", file=sys.stderr)
        return 2
    context = rows[0]["context"]

    rng = random.Random(args.seed)
    audit_indices = {row["index"] for row in rows if rng.random() < args.audit}

    out = Path(args.out) if args.out else corpus.with_name(
        corpus.name.replace("corpus-", "registre-"))
    PROGRESS.unlink(missing_ok=True)

    print("T70 — arbitrage escaladé du corpus figé")
    print(f"  {len(rows)} décisions, contexte {context}, {args.workers} processus")
    print(f"  passe 1 nette au-delà de {args.net}, résolution visée {args.resolution}")
    print(f"  audit de la passe 1 : {len(audit_indices)} décisions rejouées")
    print(f"  suivi : {PROGRESS}", flush=True)

    workers = max(1, min(args.workers, len(rows)))
    chunks = [rows[i::workers] for i in range(workers)]
    payloads = [(chunk, context, str(MODEL), args.seed + 7919 * i, args.net,
                 args.truncated_trials, args.full_trials, args.truncate,
                 args.resolution, audit_indices)
                for i, chunk in enumerate(chunks) if chunk]

    started = time.perf_counter()
    if len(payloads) == 1:
        gathered = [arbitrate_batch(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            gathered = list(pool.map(arbitrate_batch, payloads))
    elapsed = time.perf_counter() - started

    records = sorted((r for part in gathered for r in part), key=lambda r: r["index"])
    with open(out, "w") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")

    by_pass = {}
    for record in records:
        by_pass.setdefault(record["pass_used"], []).append(record)
    print(f"\n  arbitré en {elapsed / 60:.1f} min "
          f"({elapsed * args.workers / max(len(records), 1):.1f} s·cœur par décision)")
    for used in sorted(by_pass):
        part = by_pass[used]
        seconds = sum(r["seconds"] for r in part) / len(part)
        print(f"    passe {used} : {len(part):6d} décisions "
              f"({100 * len(part) / len(records):5.1f} %)  {seconds:7.2f} s·cœur en moyenne")
    print(f"\n  registre : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
