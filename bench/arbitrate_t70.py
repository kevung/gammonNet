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
# `tools/` aussi : les contextes de score sont définis là où le corpus est
# construit, et une seconde définition serait un second joueur.
sys.path.insert(0, str(ROOT))

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

#: L'écart au meilleur, selon gnubg 3-ply, au-delà duquel un candidat est tenu
#: pour DOMINÉ sans qu'aucun rollout ne le vérifie.
#:
#: Mesuré sur le corpus, et le chiffre a renversé la conception : l'écart
#: meilleur/second y a une médiane de **0,0016**, si bien qu'un critère « l'écart
#: est net » à 0,020 ne trancherait **aucune** décision. C'était prévisible après
#: coup — le corpus ne retient que les décisions DISPUTÉES, et deux moteurs
#: divergent précisément là où les coups sont proches. Le corpus sélectionne donc
#: les positions où rien ne domine.
#:
#: L'étendue, elle, a une médiane de 0,048 : les candidats lointains sont
#: franchement mauvais, seuls ceux de tête sont serrés. C'est ce qui rend
#: l'escalade praticable — on écarte les mauvais à la passe 1, et le rollout ne
#: paie que le groupe de tête, deux ou trois candidats au lieu de six.
DOMINANCE_MARGIN = 0.050

#: La cible de la passe 3 : IC 95 % < 0,005, soit un se de 0,005 / 1,96.
FULL_TARGET_SE = 0.005 / 1.96

#: Le se visé par la passe 2. Plus lâche que la passe 3 : son rôle est de
#: trancher ce qui se tranche vite, pas de tout résoudre.
TRUNCATED_TARGET_SE = 0.006


def context_state(context: str) -> MatchState | None:
    from tools.build_corpus_t70 import CONTEXTS  # noqa: PLC0415
    return CONTEXTS[context]


def resolution_of(differences, errors, pivot: int, margin: float) -> list[str]:
    """L'état de chaque candidat : `resolved`, `dominated`, ou `open`.

    Exiger que les six candidats soient connus à ±`margin` rendrait l'arbitrage
    prohibitif — l'estimation de coût donnait des dizaines d'heures là où la
    fiche exige « des heures ». Or ce n'est pas nécessaire : un coup dont on
    sait **avec certitude** qu'il est pire que le pivot d'au moins `margin` est
    tranché, quelle que soit l'imprécision qui reste sur sa valeur exacte.

    Ce que le registre perd, il le dit : un candidat `dominated` porte une
    estimation dont l'intervalle est large, et `bench/measure_t70.py` compte à
    part les décisions où le moteur noté a justement joué un tel coup. Un bon
    moteur ne joue presque jamais un coup manifestement dominé, donc
    l'imprécision se concentre là où elle ne coûte rien — mais elle n'est
    jamais passée sous silence.
    """
    states = []
    for index, (difference, error) in enumerate(zip(differences, errors)):
        if index == pivot:
            states.append("resolved")
        elif 1.96 * error <= margin:
            states.append("resolved")
        elif difference + 1.96 * error < -margin:
            states.append("dominated")
        else:
            states.append("open")
    return states


def decided(differences, errors, pivot: int, margin: float) -> bool:
    """Plus aucun candidat n'est `open` : la décision est tranchée."""
    return "open" not in resolution_of(differences, errors, pivot, margin)


def arbitrate_batch(payload):
    """Une tranche du corpus, arbitrée de bout en bout par un processus."""
    (rows, context, model, seed, net_margin, truncated_trials, full_trials,
     truncate, deep_truncate, margin, audit_indices) = payload

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
            # `.cubeless` et non une équité agrégée : le corpus money est
            # cubeless, et lire ici une des trois colonnes cubeful mêlerait
            # deux échelles. `equity` répond pour le joueur au trait de la
            # position confiée, soit l'adversaire de celui qui a joué : d'où la
            # négation, la même qui court dans tout ce dépôt.
            equities = [-table.equity(r).cubeless for r in results]
            record.update(pass_used=0, equities=equities,
                          errors=[0.0] * len(results),
                          resolution=["resolved"] * len(results),
                          trials=0, seconds=time.perf_counter() - started)
            out.append(record)
            _tick()
            continue

        # ── Passe 1 : gnubg 3-ply ───────────────────────────────────
        values = session.evaluate([gb.to_gnubg(r) for r in results],
                                  plies=ARBITER_PLY, prune=1, state=request_state)
        gnubg_equities = [-float(v[5]) for v in values]
        best_equity = max(gnubg_equities)
        # Le GROUPE DE TÊTE : les candidats que gnubg 3-ply ne condamne pas
        # franchement. Eux seuls iront au rollout ; les autres sont dominés, et
        # leur valeur exacte n'a aucune importance parce qu'aucun moteur
        # raisonnable ne les jouera. Ce tri est ce qui divise le coût du rollout
        # par le rapport entre le nombre de candidats et la taille du groupe.
        head = [i for i, equity in enumerate(gnubg_equities)
                if best_equity - equity <= net_margin]
        spread = best_equity - min(gnubg_equities[i] for i in head)
        audit = row["index"] in audit_indices

        if (len(head) <= 1 or spread < margin) and not audit:
            # Tranché sans rollout — non pas parce qu'on sait QUI gagne, mais
            # parce que l'enjeu entre les prétendants est sous la résolution :
            # la perte de n'importe lequel d'entre eux est alors connue à
            # `margin` près, ce que le registre doit précisément garantir.
            states = ["resolved" if i in head else "dominated"
                      for i in range(len(results))]
            record.update(pass_used=1, equities=gnubg_equities,
                          errors=[0.0] * len(results), spread=spread,
                          head=len(head), resolution=states,
                          trials=0, seconds=time.perf_counter() - started)
            out.append(record)
            _tick()
            continue

        # ── Passe 2 : rollout tronqué, variance réduite ─────────────
        # Sur le groupe de tête SEUL. Les dominés gardent leur équité gnubg et
        # leur étiquette : ils sont pires, on sait de combien à peu près, et
        # c'est tout ce dont le registre a besoin d'eux.
        rolled = [results[i] for i in head]
        pivot_in_head = max(range(len(head)),
                            key=lambda j: gnubg_equities[head[j]])
        pivot = head[pivot_in_head]
        config = RolloutConfig(trials=truncated_trials, truncate=truncate,
                               seed=seed + row["index"], policy=SearchConfig(ply=0),
                               variance_reduction=True,
                               target_se=TRUNCATED_TARGET_SE, min_trials=72,
                               match=state, use_cube=False)
        head_equities, differences, errors, trials = rollout_candidates_paired(
            network, rolled, config, pivot_in_head)
        used, total_trials = 2, trials

        if not decided(differences, errors, pivot_in_head, margin):
            # ── Passe 3 : rollout long ──────────────────────────────
            # Tronqué à `deep_truncate` et non complet. Un rollout non tronqué
            # avec réduction de variance joue cinq fois plus de plis, chacun
            # payant une recherche 1-ply : l'estimation à partir de T39 donne
            # ~6 h par décision, et deux décisions arbitrées l'ont confirmé.
            config = RolloutConfig(trials=full_trials, truncate=deep_truncate,
                                   seed=seed + row["index"],
                                   policy=SearchConfig(ply=0),
                                   variance_reduction=True,
                                   target_se=FULL_TARGET_SE, min_trials=108,
                                   match=state, use_cube=False)
            head_equities, differences, errors, trials = rollout_candidates_paired(
                network, rolled, config, pivot_in_head)
            used, total_trials = 3, trials

        # Recomposer le registre complet : le groupe de tête porte les équités
        # du rollout, les dominés gardent celles de gnubg, recalées sur le pivot
        # pour que les deux moitiés vivent sur la MÊME échelle. Sans ce recalage,
        # une perte se lirait tantôt en unités de rollout tantôt en unités de
        # gnubg, et la moyenne mélangerait deux règles graduées différemment.
        offset = head_equities[pivot_in_head] - gnubg_equities[pivot]
        equities = [gnubg_equities[i] + offset for i in range(len(results))]
        states = ["dominated"] * len(results)
        head_states = resolution_of(differences, errors, pivot_in_head, margin)
        for j, i in enumerate(head):
            equities[i] = head_equities[j]
            states[i] = head_states[j]

        record.update(pass_used=used, equities=equities, head=len(head),
                      errors=[0.0] * len(results), pivot=pivot,
                      trials=total_trials, resolution=states,
                      seconds=time.perf_counter() - started)
        if audit:
            # L'audit garde les DEUX lectures de la même décision : c'est
            # l'écart entre elles qui chiffre le biais de la passe 1.
            record["audit_pass1"] = gnubg_equities
            record["audit_gap"] = gap
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
    parser.add_argument("--net", type=float, default=DOMINANCE_MARGIN,
                        help="écart au meilleur au-delà duquel un candidat est dominé")
    parser.add_argument("--deep-truncate", type=int, default=25,
                        help="troncature de la passe 3 ; 0 serait un rollout complet, "
                             "impraticable avec réduction de variance")
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
    print(f"  dominé au-delà de {args.net}, résolution visée {args.resolution}")
    print(f"  audit de la passe 1 : {len(audit_indices)} décisions rejouées")
    print(f"  suivi : {PROGRESS}", flush=True)

    workers = max(1, min(args.workers, len(rows)))
    chunks = [rows[i::workers] for i in range(workers)]
    payloads = [(chunk, context, str(MODEL), args.seed + 7919 * i, args.net,
                 args.truncated_trials, args.full_trials, args.truncate,
                 args.deep_truncate, args.resolution, audit_indices)
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
    states = [state for record in records for state in record.get("resolution", [])]
    if states:
        dominated = states.count("dominated")
        print(f"    candidats seulement bornés (dominés) : {dominated}/{len(states)} "
              f"({100 * dominated / len(states):.1f} %) — leur valeur exacte n'a pas "
              f"été achetée, on sait seulement qu'ils sont pires.")
    print(f"\n  registre : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
