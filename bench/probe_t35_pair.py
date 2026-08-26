#!/usr/bin/env python3
"""Rejouer les paires post-Crawford qui atteignent un videau >= 4, et
journaliser QUI redouble, dans quel état, et ce que l'autre camp répond.

Le pilote est déterministe : (graine, index) rejoue la paire bit à bit.
On enveloppe les deux moteurs dans un proxy qui note chaque consultation.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from gammonnet.cubeful import play_match_duplicate  # noqa: E402
from gammonnet.cubeful import GammonNetCubePlayer, GnubgCubePlayer  # noqa: E402
from run_t35 import sampled_score  # noqa: E402

LOG = []


class Spy:
    """Un moteur, plus un carnet."""

    def __init__(self, inner):
        self.inner = inner
        self.name = inner.name

    def wants_double(self, position, cube, owner, state):
        answer = self.inner.wants_double(position, cube, owner, state)
        LOG.append(("wants_double", self.name, cube, owner.name,
                    state.away_on_roll, state.away_opponent, state.crawford,
                    bool(answer)))
        return answer

    def accepts_double(self, position, cube, owner, state):
        answer = self.inner.accepts_double(position, cube, owner, state)
        LOG.append(("accepts", self.name, cube, owner.name,
                    state.away_on_roll, state.away_opponent, state.crawford,
                    bool(answer)))
        return answer

    def choose(self, *a, **k):
        return self.inner.choose(*a, **k)


def main():
    indices = [int(x) for x in sys.argv[1:]]
    ours = GammonNetCubePlayer(ply=2, filter=(0, 1, 3), cube_ply=2)
    theirs = GnubgCubePlayer(ply=2, filter=(0, 1, 3), cube_ply=2)
    # Le proxy ne doit PAS changer la clé de dés : play_match_duplicate la
    # dérive de (a.name, b.name), que Spy recopie tel quel.
    a, b = Spy(ours), Spy(theirs)

    for index in indices:
        LOG.clear()
        away_a, away_b, crawford_done = sampled_score(20260810, index, 7)
        net, stats = play_match_duplicate(a, b, away_a, away_b, 20260810,
                                          index, crawford_done=crawford_done)
        print(f"\n── paire {index} : away {away_a}-{away_b}, "
              f"post-Crawford={crawford_done} → net {net}, {stats}")
        for row in LOG:
            kind, who, cube, owner, mine, theirs_away, crawford, ans = row
            if cube >= 2 and kind == "wants_double":
                mark = "  ⟵ REDOUBLE" if ans else ""
                print(f"   {kind:12s} {who:28s} videau {cube} ({owner}) "
                      f"score {mine}-away vs {theirs_away}-away "
                      f"crawford={crawford} → {ans}{mark}")
            elif cube >= 2 and kind == "accepts":
                print(f"   {kind:12s} {who:28s} videau {cube} ({owner}) "
                      f"score {mine}-away vs {theirs_away}-away → {ans}")
        print(json.dumps({"index": index, "consultations": len(LOG)}))


if __name__ == "__main__":
    main()
