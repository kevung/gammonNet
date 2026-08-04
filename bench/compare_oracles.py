#!/usr/bin/env python3
"""Le test décisif de T11 : `gnubg-nn` est-il le même joueur que GNU Backgammon ?

T11 a mesuré le modèle de référence à **+0,0400 ppg** contre `gnubg-nn`, là où
son auteur publie **+0,0578**. Le harnais du dépôt de référence, exécuté
inchangé sur cette machine, donne le même résultat que le nôtre : l'écart est
donc **en amont des deux harnais**, et le suspect nommé était `gnubg-nn`
1.1.0a9 — une *alpha*, fork ancien de GNU Backgammon.

Rejouer un million de parties contre le vrai GNU Backgammon trancherait. Mais
**comparer les deux oracles sur les mêmes positions tranche aussi**, pour un
coût sans commune mesure : si les deux choisissent les mêmes coups et évaluent
pareil, l'oracle n'explique rien et il faut chercher ailleurs. S'ils divergent,
l'ampleur de la divergence se compare directement à l'écart de 0,018 ppg.

Le pont est le **Position ID**, dont le codec est croisé sur 10 000 positions
(T02). Aucun second format de position n'est introduit — la leçon de T02 étant
qu'un pont non vérifié produit des résultats plausibles et faux.

Mode **batch** : un seul fichier de commandes, un seul lancement de gnubg. Pas
d'interactivité, donc pas d'analyse d'invite, donc rien qui puisse se bloquer.

Usage :
    python bench/compare_oracles.py --positions 2000 --ply 0
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import BLACK, WHITE, Position  # noqa: E402
from gammonnet import codec  # noqa: E402
from gammonnet import gnubg_board as gb  # noqa: E402

import gnubg_nn  # noqa: E402

GNUBG = "/usr/local/bin/gnubg"
SEED = 20260804

_POSITION_ID = re.compile(r"Position ID:\s*(\S+)")


def decision_points(count: int, seed: int = SEED) -> list[tuple[Position, int, int]]:
    """Une décision par partie, à graine fixe, les deux couleurs au trait."""
    rng = random.Random(seed)
    out = []
    while len(out) < count:
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()
        for _ in range(rng.randint(2, 70)):
            if position.is_over():
                break
            plays = position.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
            position = rng.choice(plays).result if plays else position.swapped_turn()
        if position.is_over():
            continue
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        if len(position.legal_plays(d1, d2)) < 2:
            continue
        out.append((position, d1, d2))
    return out


def ask_gnubg(points, ply: int, workdir: Path) -> tuple[list[str], list[str]]:
    """Faire jouer GNU Backgammon sur chaque décision, en un seul lancement.

    Renvoie l'identifiant de la position atteinte pour chaque décision, dans
    l'ordre. Deux `show board` encadrent chaque coup : le premier confirme que
    la position chargée est bien celle qu'on croit — la sentinelle de T02 — et
    le second donne le résultat.
    """
    # Le joueur 0 est gnubg, le joueur 1 est « humain ». Avec les DEUX en gnubg,
    # `play` déroule la partie entière au lieu d'un seul coup — c'est ce qui a
    # produit 4 772 identifiants pour 120 attendus au premier essai.
    commands = [
        "set player 0 gnubg",
        "set player 1 human",
        f"set player 0 chequer evaluation plies {ply}",
        "set player 0 chequer evaluation cubeful off",
        # Le filtre de coups déformerait ce que « le N-ply de gnubg » désigne.
        "set player 0 movefilter 1 0 0 8 0.16",
    ]
    for index, (position, d1, d2) in enumerate(points):
        # Des marqueurs, et non un pas déduit. `play` n'imprime un plateau que
        # s'il joue vraiment : le nombre d'identifiants par décision n'est donc
        # PAS constant, et un pas fixe se serait décalé silencieusement dès la
        # première position où gnubg ne bouge pas.
        commands += [
            f"ZZBEFORE{index:07d}",
            "new game",
            # L'ORDRE COMPTE, et se tromper ne se voit pas. `set board` charge
            # la position vue par le joueur au trait ; `set turn` ensuite change
            # cette perspective, donc la POSITION. Mesuré : l'identifiant passe
            # de `jwoGJg6/DAAKFw` à `vwwAChePCgYmDg` sur la même commande. La
            # position d'ouverture ne le révèle pas — elle est son propre
            # miroir. Fixer le trait d'abord, charger ensuite.
            "set turn 0",
            f"set board {codec.position_id(position)}",
            "show board",
            f"ZZAFTER{index:07d}",
            f"set dice {d1} {d2}",
            "play",
            "show board",
        ]
    commands.append(f"ZZBEFORE{len(points):07d}")
    commands.append("quit")

    script = workdir / "gnubg_batch.txt"
    script.write_text("\n".join(commands) + "\n")

    started = time.perf_counter()
    # `stdbuf -oL` n'est pas un détail. Les marqueurs sortent sur stderr et les
    # plateaux sur stdout ; en tube, stdout est bufferisé par blocs et stderr ne
    # l'est pas, si bien que les marqueurs arriveraient AVANT le texte qu'ils
    # sont censés borner. Forcer le mode ligne rétablit l'ordre d'écriture.
    result = subprocess.run(
        ["stdbuf", "-oL", "-eL", GNUBG, "--tty", "--quiet", "--no-rc"],
        stdin=script.open(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=36000,
    )
    elapsed = time.perf_counter() - started
    print(f"  GNU Backgammon : {len(points)} décisions en {elapsed:.1f} s "
          f"({len(points) / elapsed:.1f}/s)")

    output = result.stdout
    loaded: list[str] = []
    reached: list[str] = []
    stalled = 0

    for index in range(len(points)):
        head = output.find(f"ZZBEFORE{index:07d}")
        middle = output.find(f"ZZAFTER{index:07d}", head)
        tail = output.find(f"ZZBEFORE{index + 1:07d}", middle)
        if head < 0 or middle < 0 or tail < 0:
            raise SystemExit(f"marqueurs introuvables pour la décision {index}")

        before = _POSITION_ID.findall(output[head:middle])
        after = _POSITION_ID.findall(output[middle:tail])
        if not before or not after:
            raise SystemExit(f"décision {index} : identifiant manquant")

        loaded.append(before[-1])
        reached.append(after[-1])
        if after[-1] == before[-1]:
            stalled += 1

    if stalled:
        print(f"  ⚠ {stalled} décisions où la position n'a pas changé — "
              "gnubg n'a pas joué")
    return loaded, reached


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=2000)
    parser.add_argument("--ply", type=int, default=0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    workdir = ROOT / "build"
    workdir.mkdir(exist_ok=True)

    print(f"Comparaison des deux oracles, {args.ply}-ply, graine {SEED}")
    points = decision_points(args.positions)
    print(f"  {len(points)} décisions préparées")

    loaded, reached = ask_gnubg(points, args.ply, workdir)

    agree = 0
    loaded_ok = 0
    compared = 0
    disagreements = []
    unmatched = []

    for index, (position, d1, d2) in enumerate(points):
        before, after = loaded[index], reached[index]

        # Sentinelle : gnubg a-t-il chargé la position qu'on lui a donnée ?
        if before == codec.position_id(position):
            loaded_ok += 1

        ours = position.legal_plays(d1, d2)
        by_id = {codec.position_id(play.result): play for play in ours}
        gnubg_play = by_id.get(after)

        # gnubg-nn, sur exactement la même décision. Ses clés font 20
        # caractères et ne sont PAS des Position ID : ce sont des clés de
        # plateau, dans l'orientation d'après coup (établi en T03). On compare
        # donc chaque oracle dans sa propre monnaie, via le même coup.
        _, candidates = gnubg_nn.best_move(
            gb.to_gnubg(position), d1, d2, args.ply, b"X", 0, 0, 1
        )
        nn_key = candidates[0][0]

        if gnubg_play is None:
            # Compté et rapporté, pas fatal — et surtout pas ignoré. Un coup
            # que nous ne générons pas est soit une anomalie du pilotage, soit
            # un désaccord de règles avec GNU Backgammon ; dans les deux cas le
            # nombre doit être visible et l'exemple conservé.
            unmatched.append((index, position, d1, d2, after))
            continue

        # Les clés de `best_move` sont dans l'orientation d'après coup, donc
        # directement comparables aux identifiants de nos positions résultantes.
        compared += 1
        if nn_key == gb.key(gnubg_play.result):
            agree += 1
        else:
            disagreements.append((index, position, d1, d2, after, nn_key))

    total = len(points)
    print()
    print(f"Sentinelle de chargement : {loaded_ok}/{total} positions rechargées à l'identique")
    if loaded_ok != total:
        print("  ⚠ le pont ne rend pas toujours la position envoyée — "
              "toute mesure bâtie dessus serait sans valeur")
    print(f"Décisions comparables    : {compared}/{total}")
    if unmatched:
        print(f"  ⚠ {len(unmatched)} coups de gnubg absents de notre génération, "
              "exclus du taux et conservés pour examen")
    if compared:
        print(f"Accord sur le coup joué  : {agree}/{compared} "
              f"({100 * agree / compared:.2f} %)")
        print(f"Désaccords               : {compared - agree}")

    if args.out:
        payload = {
            "ply": args.ply,
            "positions": total,
            "loaded_ok": loaded_ok,
            "agree": agree,
            "unmatched": [
                {"index": i, "position_id": codec.position_id(p), "turn": p.turn,
                 "dice": [d1, d2], "gnubg": a}
                for i, p, d1, d2, a in unmatched
            ],
            "compared": compared,
            "disagreements": [
                {"index": i, "position_id": codec.position_id(p), "turn": p.turn,
                 "dice": [d1, d2], "gnubg": a, "gnubg_nn": b}
                for i, p, d1, d2, a, b in disagreements
            ],
        }
        (ROOT / args.out).write_text(json.dumps(payload, indent=2) + "\n")
        print(f"écrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
