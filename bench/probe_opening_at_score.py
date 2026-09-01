#!/usr/bin/env python3
"""Les jets d'ouverture au score : gammonNet contre GNU Backgammon.

Question posée le 2026-09-02 : « la prise en compte du score dans gammonNet
n'est-elle pas partielle ? » -- le 64 d'ouverture à gammon-go (4-away/2-away)
et à gammon-save (2-away/4-away) ne semblait pas réagir au score.

Pour chaque jet d'ouverture non double (15) et chaque contexte de score (15,
money d'abord), la même décision est posée à :

* **gnubg cubeless** -- `hint`, 2-ply, filtre grand ouvert, `cubeful off` ;
* **gnubg cubeful** -- même chose avec `cubeful on`, ce que gnubg JOUE ;
* **gammonNet `use_match`** -- 2-ply, k=12, filtre (0,1,3), feuilles
  cubeless valuées par la table ;
* **gammonNet `use_match` + `use_cube`** -- même recherche, feuilles
  valuées par le modèle de videau (§9), videau centré, x = 0,688.

Toutes les équités sont ramenées à l'ÉQUITÉ NORMALISÉE (gnubg `mwc2eq`) :
±1 = gagner/perdre le videau courant. Les coups sont appariés par le
déplacement net des pions, pas par la notation (« 24/13 » = « 24/18 18/13 »).

Ce que la mesure dit -- voir docs/mesures/2026-09-02-jets-d-ouverture-au-score.md.

Usage :
    python bench/probe_opening_at_score.py --out docs/mesures/jets-ouverture-au-score.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import Position  # noqa: E402
from gammonnet.cube import CubeOwner  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from gammonnet.rules import BAR, OFF  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
PRUNE = ROOT / "models" / "prune_32.bin"
MATCH_LENGTH = 7
CUBE_X = 0.688

#: (nom, away du joueur au trait, away de l'adversaire, partie de Crawford)
CONTEXTS = [
    ("money", None, None, False), ("7a7a", 7, 7, False), ("4a4a", 4, 4, False),
    ("2a2a", 2, 2, False), ("4a2a_GG", 4, 2, False), ("2a4a_GS", 2, 4, False),
    ("5a2a_GG", 5, 2, False), ("2a5a_GS", 2, 5, False), ("3a2a", 3, 2, False),
    ("2a3a", 2, 3, False), ("pc_2a1a_GG", 2, 1, False), ("pc_1a2a_GS", 1, 2, False),
    ("dmp_1a1a", 1, 1, False), ("cr_1a4a", 1, 4, True), ("cr_4a1a", 4, 1, True),
]
ROLLS = [(6, 4), (6, 3), (6, 2), (6, 1), (6, 5), (5, 4), (5, 3), (5, 2), (5, 1),
         (4, 3), (4, 2), (4, 1), (3, 2), (3, 1), (2, 1)]


# ── gnubg, par sa ligne de commande ─────────────────────────────────────

_HINT = re.compile(
    r"(\d+)\.\s+Cube(?:ful|less) (\d)-ply\s+(.+?)\s+Eq\.:\s+([-+]?\d+\.\d+)"
    r"(?:\s+\(([-+]?\d+\.\d+)\))?\s*$", re.M)


def gnubg_script(me, opp, crawford, cubeful):
    cmds = ["set defaultnames P0 P1", "set player 0 human", "set player 1 human",
            "set automatic roll off", "set automatic game off",
            "set evaluation chequer eval plies 2",
            "set evaluation chequer eval cubeful %s" % ("on" if cubeful else "off"),
            "set evaluation movefilter 2 0 -1 0 0.0",
            "set evaluation movefilter 2 1 -1 0 0.0"]
    for d1, d2 in ROLLS:
        if me is None:
            cmds += ["new session", "set jacoby on", "set beavers 0"]
        else:
            cmds += ["new match %d" % MATCH_LENGTH,
                     "set score %d %d" % (MATCH_LENGTH - opp, MATCH_LENGTH - me)]
            if me == 1 or opp == 1:
                cmds.append("set crawford %s" % ("on" if crawford else "off"))
        cmds += ["set turn 1", "set dice %d %d" % (d1, d2), "hint"]
    return "\n".join(cmds) + "\n"


def gnubg_job(args):
    name, me, opp, crawford, cubeful = args
    out = subprocess.run(["gnubg", "--tty", "--quiet", "--no-rc"],
                         input=gnubg_script(me, opp, crawford, cubeful),
                         capture_output=True, text=True, timeout=3600).stdout
    chunks = out.split("The dice have been set to")[1:]
    if len(chunks) != len(ROLLS):
        raise RuntimeError(f"gnubg {name}: {len(chunks)} réponses pour {len(ROLLS)} jets")
    rows = []
    for (d1, d2), chunk in zip(ROLLS, chunks):
        moves = [{"move": m.group(3).strip(), "equity": float(m.group(4))}
                 for m in _HINT.finditer(chunk)]
        rows.append({"engine": "gnubg_cubeful" if cubeful else "gnubg_cubeless",
                     "context": name, "dice": [d1, d2], "moves": moves})
    return rows


# ── gammonNet ────────────────────────────────────────────────────────────

def notation(play):
    def pt(p):
        return "bar" if p == BAR else "off" if p == OFF else str(p + 1)
    return " ".join(f"{pt(m.from_)}/{pt(m.to)}" for m in play.moves)


def normalised(state):
    """`2·MWC − 1` → équité normalisée, l'échelle de gnubg `mwc2eq`."""
    if state is None:
        return lambda v: v
    cash, pas = state.after(state.cube, True), state.after(state.cube, False)
    return lambda v: (v + 1.0 - cash - pas) / (cash - pas)


def gammonnet_job(args):
    name, me, opp, crawford, cubeful = args
    net, prune = Network.load(MODEL), Network.load(PRUNE)
    state = None if me is None else MatchState(away_on_roll=me, away_opponent=opp,
                                               cube=1, crawford=crawford)
    conv = normalised(state)
    kw = dict(ply=2, filter=(0, 1, 3), prune_net=prune, prune_k=12)
    if state is not None:
        kw.update(use_match=True, match=state)
    if cubeful:
        kw.update(use_cube=True, cube_owner=CubeOwner.CENTRED, cube_x=CUBE_X)
    cfg = SearchConfig(**kw)
    rows = []
    for d1, d2 in ROLLS:
        cands = search_plays(net, Position.initial(), d1, d2, cfg)
        rows.append({"engine": "gammonnet_use_cube" if cubeful else "gammonnet_use_match",
                     "context": name, "dice": [d1, d2],
                     "moves": [{"move": notation(c.play), "equity": conv(c.equity)} for c in cands]})
    return rows


# ── La comparaison ───────────────────────────────────────────────────────

def key(move):
    """Le déplacement net des pions : bar = 25, sortie = 0."""
    delta = defaultdict(int)
    for part in move.replace("*", "").split():
        m = re.match(r"^(\d+|bar)/(.+?)(?:\((\d)\))?$", part)
        if not m:
            continue
        chain = [m.group(1)] + m.group(2).split("/")
        pt = lambda s: 25 if s == "bar" else 0 if s == "off" else int(s)  # noqa: E731
        for _ in range(int(m.group(3) or 1)):
            delta[pt(chain[0])] -= 1
            delta[pt(chain[-1])] += 1
    return tuple(sorted((k, v) for k, v in delta.items() if v))


def compare(rows, test, oracle):
    """Accord du meilleur coup et ce que l'oracle dit que le choix du testé
    lui coûte, par contexte."""
    by = defaultdict(dict)
    for r in rows:
        by[r["engine"]][(r["context"], tuple(r["dice"]))] = r["moves"]
    summary = {}
    for name, *_ in CONTEXTS:
        n = agree = 0
        costs = []
        for (ctx, dice), mine in by[test].items():
            if ctx != name or (ctx, dice) not in by[oracle]:
                continue
            theirs = by[oracle][(ctx, dice)]
            tmap = {key(m["move"]): m["equity"] for m in theirs}
            mk, tk = key(mine[0]["move"]), key(theirs[0]["move"])
            n += 1
            agree += mk == tk
            if mk in tmap:
                costs.append(tmap[tk] - tmap[mk])
        summary[name] = {"n": n, "agree": agree, "mean_cost": sum(costs) / len(costs),
                         "max_cost": max(costs), "over_0.02": sum(c > 0.02 for c in costs)}
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=15)
    args = parser.parse_args()

    jobs = [(n, a, b, c, cf) for (n, a, b, c) in CONTEXTS for cf in (False, True)]
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        gnubg_rows = [r for rs in ex.map(gnubg_job, jobs) for r in rs]
    print(f"  gnubg : {len(gnubg_rows)} décisions", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        gn_rows = [r for rs in ex.map(gammonnet_job, jobs) for r in rs]
    print(f"  gammonNet : {len(gn_rows)} décisions", flush=True)
    rows = gnubg_rows + gn_rows

    pairs = [("gammonnet_use_match", "gnubg_cubeless"),
             ("gammonnet_use_match", "gnubg_cubeful"),
             ("gnubg_cubeless", "gnubg_cubeful"),
             ("gammonnet_use_cube", "gnubg_cubeful")]
    summaries = {}
    for test, oracle in pairs:
        s = compare(rows, test, oracle)
        summaries[f"{test} vs {oracle}"] = s
        print(f"\n== {test} contre {oracle} ==")
        print(f"  {'contexte':12s} {'n':>3s} {'accord':>7s} {'coût moy':>9s} {'coût max':>9s} {'>0,02':>6s}")
        for name, c in s.items():
            print(f"  {name:12s} {c['n']:3d} {c['agree']/c['n']*100:6.0f}% {c['mean_cost']:9.4f} "
                  f"{c['max_cost']:9.4f} {c['over_0.02']:6d}")
        tot_n = sum(c["n"] for c in s.values())
        tot_a = sum(c["agree"] for c in s.values())
        print(f"  {'TOTAL':12s} {tot_n:3d} {tot_a/tot_n*100:6.0f}%   >0,02 : {sum(c['over_0.02'] for c in s.values())}")

    if args.out:
        args.out.write_text(json.dumps({
            "probe": "opening rolls at score: gammonNet vs gnubg 1.08.003",
            "setting": {"ply": 2, "prune_k": 12, "filter": [0, 1, 3], "cube_x": CUBE_X,
                        "gnubg": "2-ply, movefilter wide open, prune on", "match_length": MATCH_LENGTH},
            "summaries": summaries, "rows": rows}, indent=1))
        print(f"\n  écrit : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
