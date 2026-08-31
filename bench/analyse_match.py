#!/usr/bin/env python3
"""Le test final — un vrai match, décision par décision, les deux moteurs.

## Ce que ce banc mesure, et ce qu'il ne mesure pas

T35 rend un scalaire sur 50 000 paires : **de combien**. Ce banc dit **où** et
**pourquoi** — coups candidats, classements, équités, et les cinq probabilités
de chaque camp, côte à côte sur les décisions d'une vraie partie. C'est aussi ce
que verra l'utilisateur de l'artefact.

**Ce n'est pas une mesure de force.** Un match de 7 points fait ~130 décisions ;
aucune conclusion de force n'en sort, et la règle 2 de `CLAUDE.md` s'applique.
Sa valeur est de montrer la NATURE des désaccords, pas leur poids.

## La frontière du dépôt, respectée

`CLAUDE.md` place l'**import de matchs** hors de ce dépôt. La lecture du fichier
est donc portée par **gnubg lui-même** : il charge le match, le parcourt, et
nous ne consommons que des identifiants de position, un score et un videau. Rien
ici ne sait lire un `.mat` ni un `.sgf`.

## L'architecture, et pourquoi elle est en deux temps

1. **Un marcheur** conduit gnubg à travers le match et en extrait la liste des
   décisions : `(Position ID, dés, score, videau, Crawford, joueur au trait)`.
2. **Les deux moteurs répondent à la même question**, chacun par son chemin
   déjà testé — notre `search_plays` et le `hints` de `gnubg_cli`.

Le marcheur ne juge rien et les analyseurs ne lisent pas le match. Un défaut de
navigation ne peut donc pas se déguiser en désaccord d'analyse.

Usage :
    python bench/analyse_match.py --match test.sgf --ply 2 --max-decisions 20
"""

from __future__ import annotations

import argparse
import json
import re
import select
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.codec import position_from_id  # noqa: E402
from gammonnet.codec import position_id as codec_id  # noqa: E402
from gammonnet.cube import CubeOwner  # noqa: E402
from gammonnet.gnubg_board import to_gnubg  # noqa: E402
from gammonnet.gnubg_engine import GnubgSession, gnubg_state  # noqa: E402
from gammonnet.gnubg_cli import _PROMPT, GNUBG  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from gammonnet.rules import WHITE  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

#: `op_eval` rend six flottants : les cinq probabilités puis l'équité.
EQUITY = 5

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
PRUNE = ROOT / "models" / "prune_32.bin"

_ID = re.compile(r"Position ID:\s*(\S+)")
_ROLLED = re.compile(r"Rolled (\d)(\d)")
_SCORE = re.compile(r"is:\s*(.+?)\s+(\d+),\s*(.+?)\s+(\d+)\s*\(match to (\d+) points\)")
_CUBE = re.compile(r"The cube is at (\d+)")
_OWNED = re.compile(r"owned by (.+?)\.")
#: gnubg dit « in on roll » ou « in on move » selon l'instant du tour.
_TURN = re.compile(r"^(?:\([^)]*\)\s*)?(.+?)\s+in on (?:roll|move)\.",
                   re.MULTILINE)


_HINT = re.compile(
    r"^\s*\*?\s*\d+\.\s+\S+\s+(?:\d+-ply|Rollout)\s+(.+?)\s+Eq\.:\s*([-+]?\d*\.?\d+)",
    re.MULTILINE)
_PROBS = re.compile(
    r"^\s*(\d\.\d+)\s+(\d\.\d+)\s+(\d\.\d+)\s+-\s+(\d\.\d+)\s+(\d\.\d+)\s+(\d\.\d+)\s*$",
    re.MULTILINE)


def parse_hints(text: str) -> list[dict]:
    """Le classement de gnubg, tel qu'il l'imprime dans le match.

    Les motifs sont ceux de `gnubg_cli`, à une étoile près : dans un match
    gnubg marque d'un `*` le coup effectivement joué, ce qu'une analyse de
    position n'a pas.
    """
    moves = _HINT.findall(text)
    probabilities = _PROBS.findall(text)
    out = []
    for index, (move, equity) in enumerate(moves):
        probs = None
        if index < len(probabilities):
            win, wg, wbg, _lose, lg, lbg = (float(v) for v in probabilities[index])
            probs = [win, wg, wbg, lg, lbg]
        out.append({"move": move.strip(), "equity": float(equity),
                    "probs": probs})
    return out


class MatchWalker:
    """gnubg, conduit à travers un match. Il lit le fichier ; nous non.

    La lecture est celle de `gnubg_cli` et pas une autre : tube binaire NON
    tamponné, `select` avec délai de garde, caractère par caractère jusqu'à
    l'invite. gnubg n'imprime PAS de retour à la ligne après son invite, donc
    tout `readline` bloque pour toujours — c'est le premier piège, et il a été
    payé une fois.
    """

    READ_TIMEOUT = 120.0

    def __init__(self, path: str, binary: str = GNUBG):
        self._process = subprocess.Popen(
            [binary, "--tty", "--quiet", "--no-rc"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=0)
        self._read_until_prompt()
        self.send(f"load match {path}")
        self.send("first game")

    #: L'invite de gnubg. Sans le saut de ligne que `gnubg_cli` exige : ce
    #: marcheur lit aussi des sorties de plateau, après lesquelles l'invite ne
    #: commence pas forcément une ligne.
    PROMPT = re.compile(r"\([^)\n]*\) $")

    def _read_until_prompt(self) -> str:
        """Octets accumulés, décodés UNE fois.

        Décoder caractère par caractère coupe les séquences UTF-8 en deux et
        transforme « Kévin » en « K??vin » — ce qui suffit à faire échouer la
        reconnaissance de l'invite, et à faire attendre le délai de garde
        complet pour rien.
        """
        chunks = bytearray()
        deadline = time.monotonic() + self.READ_TIMEOUT
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select(
                    [self._process.stdout], [], [], remaining)[0]:
                raise RuntimeError(
                    f"gnubg n'a pas rendu l'invite en {self.READ_TIMEOUT:.0f} s ; "
                    f"fin du tampon : {bytes(chunks[-300:])!r}")
            char = self._process.stdout.read(1)
            if not char:
                raise RuntimeError("gnubg s'est arrêté")
            chunks += char
            if char in (b")", b" "):
                text = chunks.decode("utf-8", "replace")
                if self.PROMPT.search(text):
                    return text

    def _drain(self, quiet: float = 0.25) -> str:
        """Ce qui traîne encore, jusqu'à `quiet` secondes de silence.

        `next roll` n'émet pas une invite mais parfois deux — il avance ET
        réaffiche. Compter une invite par commande, comme le fait
        `gnubg_cli`, désynchronise alors tout : chaque réponse arrive décalée
        d'un cran, et le parsing lit le plateau d'une autre décision sans que
        rien ne le signale. Purger de part et d'autre coûte un quart de
        seconde par commande et supprime la classe d'erreur entière.
        """
        chunks = bytearray()
        while select.select([self._process.stdout], [], [], quiet)[0]:
            char = self._process.stdout.read(1)
            if not char:
                break
            chunks += char
        return chunks.decode("utf-8", "replace")

    def send(self, command: str) -> str:
        self._drain(0.05)
        self._process.stdin.write((command + "\n").encode())
        self._process.stdin.flush()
        return self._read_until_prompt() + self._drain()

    def close(self):
        if self._process.poll() is None:
            try:
                self._process.stdin.write(b"quit\n")
                self._process.stdin.flush()
            except (BrokenPipeError, ValueError):
                pass
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()


def state_now(walker: MatchWalker) -> dict | None:
    """L'état courant, ou None s'il n'y a pas de décision de coup ici."""
    # `show board` imprime AUSSI l'analyse que gnubg a du coup — au bon
    # score, au bon videau, dans le bon état de Crawford. Une commande `hint`
    # séparée demanderait une synchronisation de plus, et `next roll` n'émet
    # pas toujours le même nombre d'invites : c'est exactement là que le
    # décalage s'installe sans rien dire.
    board = walker.send("show board")
    identifier = _ID.search(board)
    rolled = _ROLLED.search(board)
    if identifier is None or rolled is None:
        return None

    score_text = walker.send("show score")
    score = _SCORE.search(score_text)
    if score is None:
        return None
    name_a, points_a, name_b, points_b, length = (
        score.group(1), int(score.group(2)), score.group(3),
        int(score.group(4)), int(score.group(5)))

    cube_text = walker.send("show cube")
    cube_value = _CUBE.search(cube_text)
    owner = _OWNED.search(cube_text)

    turn_text = walker.send("show turn")
    on_move = _TURN.search(turn_text)
    if on_move is None:
        return None
    mover = on_move.group(1).strip()

    # L'analyse de gnubg, prise DANS le match : au bon score, au bon videau,
    # dans le bon état de Crawford, sans que rien n'ait à être reconstitué.
    # Reposer ce contexte dans une seconde session était l'autre voie ; elle
    # demande de rejouer `new_match`/`set_score`/`set_turn` à chaque
    # changement de score et de vérifier qu'aucun ne s'est perdu. Ici il n'y a
    # rien à vérifier : c'est gnubg qui tient le match.
    return {
        "hint_text": board,
        "id": identifier.group(1),
        "dice": (int(rolled.group(1)), int(rolled.group(2))),
        "names": (name_a, name_b),
        "points": (points_a, points_b),
        "length": length,
        "cube": int(cube_value.group(1)) if cube_value else 1,
        "cube_owner": owner.group(1).strip() if owner else None,
        "crawford": "Crawford game" in board,
        "mover": mover,
    }


def walk(path: str, limit: int) -> list[dict]:
    walker = MatchWalker(path)
    seen, decisions = set(), []
    try:
        for _ in range(limit * 4):
            state = state_now(walker)
            if state is not None:
                key = (state["id"], state["dice"], state["points"])
                if key not in seen:
                    seen.add(key)
                    decisions.append(state)
                    if len(decisions) >= limit:
                        break
            if "No game" in walker.send("next roll"):
                if "No game" in walker.send("next game"):
                    break
    finally:
        walker.close()
    return decisions


def analyse(decisions: list[dict], ply: int, prune_k: int) -> list[dict]:
    """Les deux moteurs, sur les MÊMES coups, au même score.

    L'appariement est par construction : gnubg n'est pas invité à choisir un
    coup dans sa notation, il est invité à **évaluer nos positions
    résultantes**. Aucune notation n'est analysée — c'est la règle que
    `gnubg_cli.best_play` et `oracle.ranked_plays` suivent déjà, pour la même
    raison : une seconde façon, non vérifiée, de lire un coup est une source
    d'erreur silencieuse.

    Chaque camp classe donc exactement le même ensemble, et un désaccord est
    un vrai désaccord d'évaluation.
    """
    net = Network.load(MODEL)
    small = Network.load(PRUNE) if prune_k else None
    rows = []

    with GnubgSession() as engine:
        for state in decisions:
            position = position_from_id(state["id"], WHITE)
            mover_index = 0 if state["mover"] == state["names"][0] else 1
            away_mover = state["length"] - state["points"][mover_index]
            away_other = state["length"] - state["points"][1 - mover_index]
            match = MatchState(away_on_roll=away_mover,
                               away_opponent=away_other,
                               cube=state["cube"], crawford=state["crawford"])

            d1, d2 = state["dice"]
            plays = position.legal_plays(d1, d2)
            if len(plays) < 2:
                continue

            config = SearchConfig(ply=ply, filter=(0, 1, 3), use_match=True,
                                  match=match, prune_net=small,
                                  prune_k=prune_k)
            started = time.perf_counter()
            ours = search_plays(net, position, d1, d2, config)
            ours_seconds = time.perf_counter() - started

            # Le même ensemble, vu par gnubg. La position résultante a rendu la
            # main : sa valeur est celle de l'ADVERSAIRE, d'où la négation —
            # la même que celle de `gn_search.h`.
            boards = [to_gnubg(play.result) for play in plays]
            # LA PERSPECTIVE, qui se trompe en silence si on l'oublie : la
            # position résultante a rendu la main, donc le score qui la décrit
            # est celui de l'ADVERSAIRE au trait. Un état non retourné ferait
            # optimiser le mauvais joueur, et rendrait des nombres
            # parfaitement plausibles.
            theirs_state = MatchState(away_on_roll=away_other,
                                      away_opponent=away_mover,
                                      cube=state["cube"],
                                      crawford=state["crawford"])
            gstate = gnubg_state(CubeOwner.CENTRED, theirs_state,
                                 jacoby=False, cube=state["cube"])
            started = time.perf_counter()
            values = engine.evaluate(boards, plies=ply, prune=0, state=gstate)
            theirs_seconds = time.perf_counter() - started

            their_ranked = sorted(
                ({"result": codec_id(play.result),
                  "equity": -value[EQUITY],
                  "probs": [1.0 - value[0], value[3], value[4],
                            value[1], value[2]]}
                 for play, value in zip(plays, values)),
                key=lambda row: row["equity"], reverse=True)

            our_ranked = [{"result": codec_id(c.play.result),
                           "equity": c.equity,
                           "probs": (list(c.evaluation.as_tuple())
                                     if c.evaluation else None)}
                          for c in ours]

            rows.append({
                "id": state["id"], "dice": [d1, d2],
                "score": list(state["points"]), "length": state["length"],
                "cube": state["cube"], "crawford": state["crawford"],
                "mover": state["mover"], "away": [away_mover, away_other],
                "legal": len(plays),
                "ours": our_ranked, "theirs": their_ranked,
                "gnubg_text": parse_hints(state["hint_text"])[:3],
                "seconds": {"ours": ours_seconds, "theirs": theirs_seconds},
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--match", default="test.sgf")
    parser.add_argument("--ply", type=int, default=2)
    parser.add_argument("--prune-k", type=int, default=0)
    parser.add_argument("--max-decisions", type=int, default=20)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "docs" / "mesures" / "t3c-analyse-match.json")
    args = parser.parse_args()

    print(f"1. Parcours du match par gnubg — {args.match}")
    decisions = walk(args.match, args.max_decisions)
    print(f"   {len(decisions)} décisions extraites")
    if not decisions:
        print("   aucune décision : la navigation n'a rien rendu.")
        return 1

    print(f"\n2. Analyse par les deux moteurs, {args.ply}-ply")
    rows = analyse(decisions, args.ply, args.prune_k)

    agree = 0
    # LES DEUX ÉCHELLES NE SONT PAS LA MÊME, et les afficher côte à côte sans
    # le dire serait trompeur. La nôtre est l'équité de match `2·MWC − 1` ;
    # celle de gnubg, sous un `cubeinfo` de match, est l'EMG — affine en MWC à
    # pente positive (sonde de T35, 2026-08-09). Les CLASSEMENTS se comparent,
    # les magnitudes non.
    print(f"\n  {'#':>3} {'dés':>4} {'score':>7} {'cpl':>4} "
          f"{'nous (2·MWC−1)':>15} {'gnubg (EMG)':>12}  accord")
    for index, row in enumerate(rows):
        ours, theirs = row["ours"][0], row["theirs"][0]
        same = ours["result"] == theirs["result"]
        agree += same
        print(f"  {index:>3} {row['dice'][0]}{row['dice'][1]:>3} "
              f"{row['score'][0]}-{row['score'][1]:>5} {row['legal']:>4} "
              f"{ours['equity']:>+13.4f} {theirs['equity']:>+12.4f}"
              f"   {'oui' if same else 'NON'}"
              f"   {row['gnubg_text'][0]['move'] if row['gnubg_text'] else ''}")
    print(f"\n  {len(rows)} décisions ; accord sur le meilleur coup : "
          f"{agree}/{len(rows)} ({100 * agree / max(len(rows), 1):.1f} %)")

    args.out.write_text(json.dumps(
        {"task": "T3C", "match": args.match, "ply": args.ply,
         "prune_k": args.prune_k, "decisions": rows}, indent=1,
        ensure_ascii=False))
    print(f"  → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
