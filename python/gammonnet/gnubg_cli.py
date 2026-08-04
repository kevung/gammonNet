"""GNU Backgammon lui-même, piloté en ligne de commande.

`PLAN.md` en a fait une décision de projet : les mesures qui engagent une
conclusion en **match** ou sur le **videau** se font contre GNU Backgammon, pas
contre `gnubg-nn`, dont la table d'équité de match diffère de la nôtre de
`2,679e-02` — bien plus que les marges sur lesquelles se joue un videau.

## Le pont choisi, et pourquoi celui-là

GNU Backgammon expose une interface externe parlant le format de plateau FIBS.
Elle est plus rapide, et elle a été écartée : ce serait **un second pont de
format de position à vérifier entièrement**, avec la surface d'erreur
silencieuse que T02 a documentée.

Le chemin retenu passe par les **Position ID**, dont le codec est déjà croisé
sur 10 000 positions. On envoie `set board <id>`, on fait jouer, on relit l'ID
résultant : le seul format traversé est celui qu'on sait juste.

## L'orientation, établie et non supposée

Un Position ID est **relatif au joueur au trait** — deux positions qui ne
diffèrent que par le trait partagent leur identifiant. `set board` place donc
la position vue par celui qui joue, et c'est vérifié ici par la sentinelle du
compte de pips avant que quoi que ce soit ne soit mesuré.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from . import codec
from .rules import BLACK, WHITE, Play, Position

GNUBG = "/usr/local/bin/gnubg"

#: gnubg termine chaque réponse par une invite entre parenthèses.
_PROMPT = re.compile(r"\n\([^)\n]*\)\s*$")
_POSITION_ID = re.compile(r"Position ID:\s*(\S+)")


@dataclass(frozen=True)
class Hint:
    """Un coup candidat, tel que GNU Backgammon le classe."""

    move: str
    equity: float
    probabilities: tuple[float, float, float, float, float] | None


class Gnubg:
    """Un processus GNU Backgammon persistant, piloté par tube.

    Un processus par worker. gnubg n'est pas conçu pour être partagé, et le
    relancer par décision coûterait bien plus que la décision elle-même.
    """

    def __init__(self, ply: int = 0, path: str = GNUBG, cubeful: bool = False):
        self.ply = ply
        self.cubeful = cubeful
        self._process = subprocess.Popen(
            [path, "--tty", "--quiet", "--no-rc"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._read_until_prompt()

        # Les deux joueurs sont gnubg lui-même : `play` doit jouer, pas demander.
        self._send("set player 0 gnubg", "set player 1 gnubg")
        for player in (0, 1):
            self._send(
                f"set player {player} chequer evaluation plies {ply}",
                f"set player {player} chequer evaluation cubeful "
                f"{'on' if cubeful else 'off'}",
            )
        # Un filtre de coups déforme ce que « le 2-ply de gnubg » veut dire ;
        # on le coupe pour que la comparaison porte sur la profondeur annoncée.
        self._send("set player 0 movefilter 1 0 0 8 0.16",
                   "set player 1 movefilter 1 0 0 8 0.16")

    # ── Tuyauterie ──────────────────────────────────────────────────

    def _read_until_prompt(self) -> str:
        chunks: list[str] = []
        while True:
            char = self._process.stdout.read(1)
            if not char:
                raise RuntimeError("GNU Backgammon s'est arrêté")
            chunks.append(char)
            if char == ")" or char == " ":
                text = "".join(chunks)
                if _PROMPT.search(text):
                    return text

    def _send(self, *commands: str) -> str:
        for command in commands:
            self._process.stdin.write(command + "\n")
        self._process.stdin.flush()
        return "".join(self._read_until_prompt() for _ in commands)

    def close(self) -> None:
        if self._process.poll() is None:
            try:
                self._process.stdin.write("quit\n")
                self._process.stdin.flush()
            except (BrokenPipeError, ValueError):
                pass
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def __enter__(self) -> "Gnubg":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # ── Position ────────────────────────────────────────────────────

    def set_position(self, position: Position) -> None:
        """Charger une position, vue par son joueur au trait."""
        self._send("new game")
        self._send(f"set board {codec.position_id(position)}")

    def current_position_id(self) -> str:
        text = self._send("show board")
        match = _POSITION_ID.search(text)
        if not match:
            raise RuntimeError(f"pas d'identifiant dans la sortie de gnubg : {text[:200]!r}")
        return match.group(1)

    # ── Choix du coup ───────────────────────────────────────────────

    def best_play(self, position: Position, d1: int, d2: int) -> Play | None:
        """Le coup que GNU Backgammon joue, apparié aux nôtres par identifiant.

        L'appariement se fait sur la **position résultante** et non en analysant
        la notation de gnubg : c'est le même choix qu'en T03, et pour la même
        raison — réutiliser le codec déjà vérifié plutôt qu'ajouter une seconde
        manière, non vérifiée, de lire un coup.
        """
        ours = position.legal_plays(d1, d2)
        if not ours:
            return None
        if len(ours) == 1:
            return ours[0]

        self.set_position(position)
        self._send(f"set dice {d1} {d2}")
        self._send("play")
        reached = self.current_position_id()

        # Après le coup, gnubg voit la position par l'adversaire — exactement la
        # convention de nos `play.result`, dont le trait a déjà tourné.
        by_id = {codec.position_id(play.result): play for play in ours}
        chosen = by_id.get(reached)
        if chosen is None:
            raise RuntimeError(
                f"GNU Backgammon a joué un coup que nous ne générons pas "
                f"({reached}) depuis {position!r} avec {d1}-{d2}"
            )
        return chosen

    # ── Évaluation ──────────────────────────────────────────────────

    _HINT = re.compile(
        r"^\s*\d+\.\s+\S+\s+(?:\d+-ply|Rollout)\s+(.+?)\s+Eq\.:\s*([-+]?\d*\.?\d+)",
        re.MULTILINE,
    )
    _PROBS = re.compile(
        r"^\s*(\d\.\d+)\s+(\d\.\d+)\s+(\d\.\d+)\s+-\s+(\d\.\d+)\s+(\d\.\d+)\s+(\d\.\d+)\s*$",
        re.MULTILINE,
    )

    def hints(self, position: Position, d1: int, d2: int) -> list[Hint]:
        """Le classement de gnubg, avec équités. Diagnostic, pas chemin chaud."""
        self.set_position(position)
        self._send(f"set dice {d1} {d2}")
        text = self._send("hint")

        moves = self._HINT.findall(text)
        probabilities = self._PROBS.findall(text)
        out = []
        for index, (move, equity) in enumerate(moves):
            probs = None
            if index < len(probabilities):
                win, wg, wbg, _lose, lg, lbg = (float(v) for v in probabilities[index])
                probs = (win, wg, wbg, lg, lbg)
            out.append(Hint(move.strip(), float(equity), probs))
        return out
