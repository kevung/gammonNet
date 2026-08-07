#!/usr/bin/env python3
"""T34 phase 2, étape 3b — nos choix de coups cubeful contre ceux de gnubg.

## La question

§8 attend deux effets du videau dans l'arbre ; le premier est que le choix de
coup devienne sensible à la possession. 3a a validé la mécanique contre la
table exacte ; ce banc mesure la **ressemblance des choix** avec GNU
Backgammon en évaluation cubeful — deux colonnes comme toujours : l'accord ne
prouve qu'une ressemblance, jamais une supériorité.

## La sémantique de `findbestmove`, fixée par sonde

`tools/gnubg_server.py::op_bestmove` documente la sonde : quatre arguments
dont les dés (la documentation embarquée n'en montre que trois), tuple par
paires `(de, vers)`, points 1..24 du point de vue du joueur au trait, `25` la
barre, `0` la sortie. L'appariement à nos coups se fait par RÉSULTAT — les
paires appliquées dans leur ordre (`apply_gnubg_move`), et la position
obtenue doit être l'un des résultats de `gn_legal_plays`, qui reste
l'autorité sur les règles. Un tuple inappariable ARRÊTE la mesure au lieu
d'être deviné ; c'est ce refus qui a révélé, au pilote, que gnubg et notre
générateur gardent parfois deux intermédiaires différents du même coup
composé — ce qui a enterré l'appariement par multiensemble.

## Le protocole

Corpus de `compare_cube.py` (2 000 contact graine 20260807 + 1 000 bearoff
graine 20260808), un jet aléatoire par position (graine 20260809). Quatre
configurations money, 0-ply des deux côtés, réseau d'élagage gnubg désactivé :

  - cubeless (colonne de base : ce que le videau change se lit par contraste)
  - cubeful, videau centré / possédé / adverse — notre `x` mesuré par état
    (t34-efficacite.json), le contexte gnubg `cubeful=1`, même possesseur.

**Jacoby coupé des deux côtés** : notre valuation de feuille ne le porte pas
(il gouverne la décision de doubler, pas la valeur d'un coup), donc le
comparer activé serait comparer deux questions différentes.

Les coups forcés (un seul coup légal) sont comptés à part : l'accord n'y dit
rien. La colonne qui compte est « cube-sensibles » : les décisions où au
moins un des deux moteurs change son propre choix entre cubeless et cubeful —
c'est là que le videau agit, et là que la ressemblance se juge.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from compare_cube import build_corpus, gnubg_state  # noqa: E402

from gammonnet import codec  # noqa: E402
from gammonnet import gnubg_board as gb  # noqa: E402
from gammonnet.bearoff import disable_shared, use_shared  # noqa: E402
from gammonnet.cube import CubeOwner  # noqa: E402
from gammonnet.gnubg_engine import GnubgSession  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import WHITE, Position  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"
MODEL_BIN = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
EFFICIENCY_FILE = ROOT / "docs" / "mesures" / "t34-efficacite.json"

DICE_SEED = 20260809

CONFIGS = ("cubeless", "centred", "owned", "opponent")
OWNER_OF = {"centred": CubeOwner.CENTRED, "owned": CubeOwner.OWNED,
            "opponent": CubeOwner.OPPONENT}


def apply_gnubg_move(position: Position, raw: list[int]) -> Position | None:
    """La position résultante du tuple de `findbestmove`, appliqué paire par
    paire dans l'ordre rendu — (0, 0) est du bourrage (« unused moves are set
    to zero », help embarqué).

    Ceci n'est PAS une seconde lecture des règles : le résultat calculé ici
    doit être l'une des positions résultantes de `gn_legal_plays` (le C fait
    autorité), et tout écart — coup illégal, erreur de convention, erreur
    d'application — se solde par un REFUS de la mesure, jamais par une
    devinette. L'appariement par multiensemble de paires ne suffisait pas :
    gnubg et notre générateur peuvent garder deux intermédiaires différents
    du même coup composé (13/10/8 contre 13/11/8), et le générateur
    déduplique par résultat.
    """
    mover = position.turn
    opponent = 1 - mover
    points = list(position.points)
    bar = list(position.bar)
    off = list(position.off)
    sign = 1 if mover == WHITE else -1

    for i in range(0, len(raw), 2):
        src, dst = raw[i], raw[i + 1]
        if (src, dst) == (0, 0):
            continue
        # 1..24 du point de vue du joueur au trait, 25 la barre, 0 la sortie.
        if src == 25:
            if bar[mover] <= 0:
                return None
            bar[mover] -= 1
        else:
            index = src - 1 if mover == WHITE else 24 - src
            if points[index] * sign <= 0:
                return None
            points[index] -= sign
        if dst == 0:
            off[mover] += 1
        else:
            index = dst - 1 if mover == WHITE else 24 - dst
            if points[index] * sign == -1:
                points[index] = 0
                bar[opponent] += 1
            points[index] += sign

    return Position(points=tuple(points), bar=tuple(bar), off=tuple(off),
                    turn=opponent)


def our_config(name: str, x_of: dict) -> SearchConfig:
    if name == "cubeless":
        return SearchConfig(ply=0)
    owner = OWNER_OF[name]
    return SearchConfig(ply=0, use_cube=True, cube_owner=int(owner),
                        cube_x=x_of[name])


def measure(payload):
    """Un lot de positions, un worker : sa session gnubg, son réseau."""
    positions, x_of = payload

    use_shared(DATABASE)
    network = Network.load(MODEL_BIN)
    session = GnubgSession()

    rows, unmatched = [], []
    for position, origin, d1, d2 in positions:
        plays = position.legal_plays(d1, d2)
        if not plays:
            continue

        legal_results = {play.result for play in plays}
        board = gb.to_gnubg(position)
        row = {"id": codec.position_id(position), "origin": origin,
               "d1": d1, "d2": d2, "forced": len(plays) == 1}

        for name in CONFIGS:
            owner = OWNER_OF.get(name, CubeOwner.CENTRED)
            state = gnubg_state(owner, None, jacoby=False)
            cubeful = 0 if name == "cubeless" else 1
            theirs_raw = session.bestmove(
                [{"board": board, "dice": (d1, d2)}],
                plies=0, cubeful=cubeful, state=state)[0]
            theirs = apply_gnubg_move(position, theirs_raw)
            if theirs is None or theirs not in legal_results:
                unmatched.append({"id": row["id"], "d1": d1, "d2": d2,
                                  "why": f"tuple gnubg inappariable : {theirs_raw}"})
                row = None
                break

            ours = search_plays(network, position, d1, d2,
                                our_config(name, x_of))[0]
            row[name] = {
                "ours": codec.position_id(ours.play.result),
                "theirs": codec.position_id(theirs),
                "agree": ours.play.result == theirs,
            }
        if row is not None:
            rows.append(row)

    session.close()
    disable_shared()
    return rows, unmatched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contact", type=int, default=2000)
    parser.add_argument("--bearoff", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    x_of = {name: json.loads(EFFICIENCY_FILE.read_text())["results"]
            [{"centred": "centered"}.get(name, name)]["x"]
            for name in CONFIGS if name != "cubeless"}

    corpus = build_corpus(args.contact, args.bearoff)
    rng = random.Random(DICE_SEED)
    tagged = [(position, origin, rng.randint(1, 6), rng.randint(1, 6))
              for position, origin in corpus]

    chunk = (len(tagged) + args.workers - 1) // args.workers
    payloads = [(tagged[i:i + chunk], x_of)
                for i in range(0, len(tagged), chunk)]
    with Pool(args.workers) as pool:
        results = pool.map(measure, payloads)

    rows = [r for batch, _ in results for r in batch]
    unmatched = [u for _, batch in results for u in batch]

    if unmatched:
        print(f"REFUS : {len(unmatched)} tuples gnubg inappariables — la "
              f"sémantique sondée est fausse quelque part, rien n'est mesuré.")
        for u in unmatched[:10]:
            print(" ", u)
        return 1

    report = {"task": "T34-phase2-3b", "dice_seed": DICE_SEED,
              "corpus": {"contact": args.contact, "bearoff": args.bearoff},
              "efficiency": x_of, "jacoby": False,
              "n_scored": len(rows),
              "n_forced": sum(1 for r in rows if r["forced"]),
              "per_config": {}, "cube_sensitive": {}}

    open_rows = [r for r in rows if not r["forced"]]
    for name in CONFIGS:
        agreed = sum(1 for r in open_rows if r[name]["agree"])
        report["per_config"][name] = {
            "n": len(open_rows), "agreed": agreed,
            "rate": agreed / len(open_rows)}

    # Le sous-ensemble où le videau AGIT : l'un des deux moteurs au moins
    # change son propre choix entre cubeless et cet état cubeful.
    for name in ("centred", "owned", "opponent"):
        sensitive = [r for r in open_rows
                     if r[name]["ours"] != r["cubeless"]["ours"]
                     or r[name]["theirs"] != r["cubeless"]["theirs"]]
        agreed = sum(1 for r in sensitive if r[name]["agree"])
        ours_moved = sum(1 for r in sensitive
                         if r[name]["ours"] != r["cubeless"]["ours"])
        theirs_moved = sum(1 for r in sensitive
                           if r[name]["theirs"] != r["cubeless"]["theirs"])
        both_moved = sum(1 for r in sensitive
                         if r[name]["ours"] != r["cubeless"]["ours"]
                         and r[name]["theirs"] != r["cubeless"]["theirs"])
        report["cube_sensitive"][name] = {
            "n": len(sensitive),
            "agreed": agreed,
            "rate": agreed / len(sensitive) if sensitive else None,
            "ours_moved": ours_moved, "theirs_moved": theirs_moved,
            "both_moved": both_moved,
        }

    print(json.dumps(report, indent=2))
    if args.out:
        report["disagreements"] = [
            {k: r[k] for k in ("id", "origin", "d1", "d2")}
            | {name: r[name] for name in CONFIGS if not r[name]["agree"]}
            for r in open_rows
            if not all(r[name]["agree"] for name in CONFIGS)
        ][:200]
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"écrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
