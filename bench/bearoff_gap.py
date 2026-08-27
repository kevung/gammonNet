#!/usr/bin/env python3
"""T33 — de combien le réseau se trompe là où une table exacte sait.

C'est la valeur de T33, et elle n'était pas connue. `BRIEF.md` §3.3 le pose sans
le chiffrer : sans table de fin de partie, l'approximation apprise du réseau
porte seule les courses pures et les bearoffs profonds, et elle y est
mesurablement plus faible qu'une table exacte. **Mesurablement** — donc mesurons.

## Ce qui est exact, et pourquoi

Sur une **course pure** — les deux joueurs entièrement dans leur jan intérieur,
plus aucun contact possible — la probabilité de gain se calcule sans réseau et
sans approximation. Chaque camp a une distribution du nombre de jets nécessaires
pour tout sortir ; le joueur au trait gagne si et seulement s'il finit en `i`
jets alors que l'autre en demande `j ≥ i`. Donc :

    P(gain) = Σ_i  D_moi[i] × P(adversaire a besoin d'au moins i jets)

Il n'y a rien à estimer là-dedans. C'est le calcul que le réseau, lui, doit
approcher — et l'écart entre les deux est exactement ce que la table apporte.

## Ce que cette mesure ne dit pas

Elle porte sur `P(gain)` en course pure. Elle ne dit rien des gammons — sans
objet ici, un adversaire déjà dans son jan en ayant sorti au moins un pion — ni
des positions de contact, ni du bearoff avec contact, qui sont un autre travail.

Usage :
    python bench/bearoff_gap.py --positions 3000
"""

from __future__ import annotations

import argparse
import random
import statistics
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import BLACK, NUM_POINTS, WHITE, Position  # noqa: E402
from gammonnet.infer import Network  # noqa: E402

TABLE = ROOT / "models" / "bearoff_one_sided.bin"
MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
SEED = 20260804


def load_table() -> dict[tuple[int, ...], list[float]]:
    """Relire la table écrite par `tools/build_bearoff.py`, indexée par état."""
    import gnubg_nn

    raw = TABLE.read_bytes()
    if raw[:4] != b"GNBO":
        raise SystemExit(f"{TABLE} n'a pas la signature attendue")
    count = struct.unpack_from("<i", raw, 4)[0]

    offset = 8
    distributions: dict[tuple[int, ...], list[float]] = {}
    for identifier in range(1, count + 1):
        length = struct.unpack_from("<i", raw, offset)[0]
        offset += 4
        values = list(struct.unpack_from(f"<{length}d", raw, offset))
        offset += 8 * length
        distributions[tuple(gnubg_nn.bearoff_id_2_pos(identifier))] = values
    return distributions


def home_state(position: Position, player: int) -> tuple[int, ...] | None:
    """Les six points du jan de `player`, ou None s'il en sort encore un pion."""
    if position.bar[player]:
        return None
    home = range(0, 6) if player == WHITE else range(18, NUM_POINTS)
    state = [0] * 6
    for index in range(NUM_POINTS):
        n = position.points[index]
        if n == 0:
            continue
        if (n > 0) != (player == WHITE):
            continue
        if index not in home:
            return None
        # Le slot i porte les pions à (i + 1) pips de la sortie, pour CE joueur.
        slot = index if player == WHITE else NUM_POINTS - 1 - index
        state[slot] += abs(n)
    return tuple(state)


def exact_win_probability(mine: list[float], theirs: list[float]) -> float:
    """P(gain) pour le joueur au trait, en course pure.

    Il gagne s'il finit en `i` jets et que l'autre en demande au moins `i`. Le
    joueur au trait ayant l'avantage du tempo, l'égalité lui revient.
    """
    total = 0.0
    tail = 1.0  # P(l'adversaire a besoin d'au moins i jets), i = 1 au départ
    for i, p in enumerate(mine):
        total += p * tail
        if i < len(theirs):
            tail -= theirs[i]
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=3000)
    args = parser.parse_args()

    if not TABLE.is_file():
        raise SystemExit(f"{TABLE} absent — lancer `python tools/build_bearoff.py`")

    print("chargement de la table…", flush=True)
    table = load_table()

    rng = random.Random(SEED)
    network = Network.load(MODEL)

    errors: list[float] = []
    signed: list[float] = []
    checked = 0
    attempts = 0

    while checked < args.positions and attempts < args.positions * 400:
        attempts += 1
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()
        for _ in range(rng.randint(40, 200)):
            if position.is_over():
                break
            plays = position.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
            position = rng.choice(plays).result if plays else position.swapped_turn()
        if position.is_over():
            continue

        me = position.turn
        opponent = BLACK if me == WHITE else WHITE
        mine = home_state(position, me)
        theirs = home_state(position, opponent)
        if mine is None or theirs is None:
            continue
        if not any(mine) or not any(theirs):
            continue

        exact = exact_win_probability(table[mine], table[theirs])
        predicted = network.evaluate(position).win

        errors.append(abs(predicted - exact))
        signed.append(predicted - exact)
        checked += 1

    if not checked:
        raise SystemExit("aucune course pure rencontrée — le tirage ne convient pas")

    errors.sort()
    print()
    print(f"Écart entre le réseau seul et la table exacte, sur P(gain)")
    print("=" * 72)
    print(f"  courses pures examinées : {checked} (sur {attempts} parties tirées)")
    print(f"  écart moyen             : {statistics.mean(errors):.5f}")
    print(f"  médian                  : {statistics.median(errors):.5f}")
    print(f"  90e centile             : {errors[int(0.90 * len(errors))]:.5f}")
    print(f"  99e centile             : {errors[int(0.99 * len(errors))]:.5f}")
    print(f"  maximum                 : {errors[-1]:.5f}")
    print(f"  biais signé moyen       : {statistics.mean(signed):+.5f}")
    print()
    print("  P(gain) exacte : calcul, pas estimation. L'écart est donc entièrement")
    print("  imputable au réseau — c'est ce que la table apporte en course pure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
