#!/usr/bin/env python3
"""Notre camp dans le videau mort à sens unique : taux d'erreur mesuré.

La sonde du 2026-08-21 comparait le chemin API à la ligne de commande de
gnubg — deux fois gnubg. Elle ne posait la question à NOTRE modèle dans
aucun de ses contextes. Ce trou est celui que les 131 paires ont révélé.

État sondé : le joueur au trait possède le videau à 2 et lui reste `away`
points à marquer, avec `away <= 2` : gagner la partie au videau courant
gagne déjà le match, donc redoubler ne peut rien rapporter. Le verdict
correct est « never redouble » sans regarder la position.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from gammonnet.cube import CubeOwner  # noqa: E402
from gammonnet.cubeful import GammonNetCubePlayer  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from probe_gnubg_at_score import build_corpus  # noqa: E402

CASES = [(1, 3), (1, 5), (1, 7), (2, 5), (2, 7), (4, 7)]

def main():
    n_contact = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    corpus = build_corpus(n_contact, n_contact // 3)
    ours = GammonNetCubePlayer(ply=2, filter=(0, 1, 3), cube_ply=2)
    print(f"corpus : {len(corpus)} positions, videau possédé à 2\n")
    for away_mover, away_opp in CASES:
        state_cube = 2
        dead = state_cube >= away_mover and state_cube < away_opp
        bad = 0
        for position, _kind in corpus:
            st = MatchState(away_on_roll=away_mover, away_opponent=away_opp,
                            cube=state_cube, crawford=False)
            if ours.wants_double(position, state_cube, CubeOwner.OWNED, st):
                bad += 1
        tag = "MORT pour le trait" if dead else "vivant"
        rate = 100 * bad / len(corpus)
        print(f"  {away_mover}-away vs {away_opp}-away, videau 2 ({tag:18s}) "
              f": redouble {bad}/{len(corpus)} ({rate:.1f} %)")

if __name__ == "__main__":
    main()
