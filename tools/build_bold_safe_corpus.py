#!/usr/bin/env python3
"""T34 phase 2, étape 3 (c) — le corpus bold/safe, généré et versionné.

§8 exige que l'effet « la possession du videau change le coup choisi » soit
VISIBLE : un corpus non vide, versionné, où le meilleur coup au 0-ply diffère
selon le possesseur. Le constat d'implémentation de §8 dit où le chercher :
dans le domaine de la table bilatérale, où les feuilles sont exactes et où
les points de cash et de prise saturent réellement les courbes — en contact
médian, les courbes possédé/adverse diffèrent d'une constante et l'ordre ne
bouge jamais.

Sortie : `tests/data/t34-bold-safe.json`. Chaque entrée porte la position,
le jet, et le coup choisi sous chaque possesseur ; `tests/test_search_cube.py`
rejoue chaque entrée et vérifie que la différence tient toujours — un
changement de poids ou de modèle qui ferait disparaître l'effet le dirait.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import codec  # noqa: E402
from gammonnet.bearoff import TwoSidedBearoff, disable_shared, use_shared  # noqa: E402
from gammonnet.cube import CubeOwner, decide  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import BLACK, NUM_POINTS, WHITE, Position  # noqa: E402
from gammonnet.search import SearchConfig, best_play  # noqa: E402

DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"
MODEL_BIN = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
OUT = ROOT / "tests" / "data" / "t34-bold-safe.json"

SEED = 20260808
SCAN = 300          # positions de bearoff balayées
X = 0.6             # même valeur de travail que tests/test_search_cube.py


def random_bearoff(rng: random.Random, table: TwoSidedBearoff) -> Position:
    while True:
        points = [0] * NUM_POINTS
        for player in (WHITE, BLACK):
            count = rng.randint(1, table.chequers)
            for _ in range(count):
                point = rng.randrange(table.points)
                if player == WHITE:
                    points[point] += 1
                else:
                    points[NUM_POINTS - 1 - point] -= 1
        white = sum(n for n in points if n > 0)
        black = -sum(n for n in points if n < 0)
        position = Position(points=tuple(points), bar=(0, 0),
                            off=(15 - white, 15 - black), turn=WHITE)
        if table.contains(position):
            return position


def main() -> int:
    rng = random.Random(SEED)
    table = TwoSidedBearoff(DATABASE)
    use_shared(DATABASE)
    network = Network.load(MODEL_BIN)

    configs = {
        owner: SearchConfig(ply=0, use_cube=True, cube_owner=int(owner), cube_x=X)
        for owner in (CubeOwner.OWNED, CubeOwner.OPPONENT)
    }

    entries = []
    for _ in range(SCAN):
        position = random_bearoff(rng, table)
        for d1 in range(1, 7):
            for d2 in range(d1, 7):
                chosen = {}
                for owner, config in configs.items():
                    best = best_play(network, position, d1, d2, config)
                    chosen[owner] = best
                if chosen[CubeOwner.OWNED] is None:
                    continue
                bold = chosen[CubeOwner.OWNED].play.result
                safe = chosen[CubeOwner.OPPONENT].play.result
                if bold != safe:
                    entries.append({
                        "position": codec.position_id(position),
                        "d1": d1, "d2": d2,
                        "owned_result": codec.position_id(bold),
                        "opponent_result": codec.position_id(safe),
                    })

    payload = {
        "task": "T34-phase2-3c",
        "seed": SEED,
        "scanned_positions": SCAN,
        "cube_x": X,
        "note": ("Coups 0-ply divergents selon le possesseur du videau, dans "
                 "le domaine de la table bilatérale (feuilles exactes). Voir "
                 "docs/specs/t34-videau-spec.md §8, constat d'implémentation."),
        "entries": entries,
    }
    OUT.write_text(json.dumps(payload, indent=1))
    print(f"{len(entries)} entrées écrites dans {OUT}")

    disable_shared()
    table.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
