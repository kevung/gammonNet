"""GNU Backgammon lui-même comme oracle — le client de `tools/gnubg_server.py`.

`PLAN.md` a tranché le 2026-08-04 que les mesures engageant une conclusion en
**match** ou sur le **videau** se font contre GNU Backgammon et non contre
`gnubg-nn`, dont la table d'équité diffère de la nôtre de `2,679e-02`. T36 a
ajouté une seconde raison, plus brutale : **`gnubg-nn` plante à partir du 1-ply
sur les positions de bearoff**, ce qui l'exclut de toute mesure en profondeur.

Ce module ouvre GNU Backgammon en sous-processus, une fois, et lui parle en
JSON. Le coût de démarrage — environ une seconde — est payé une fois par
processus et non par question.

## La convention de profondeur, et pourquoi elle est imposée des deux côtés

`gnubg.findbestmove` est cassé dans ce build : il rend `NULL` sans lever, sous
toutes les formes d'appel essayées. Le choix de coup est donc composé ici, à
partir de `evaluate` :

    pour chaque coup légal, équité = -evaluate(position résultante, k plies)
    le meilleur coup est celui d'équité maximale

C'est **mot pour mot** la convention que `src/gn_search.h` applique à notre
propre moteur : *« a decision with known dice at depth k scores each play at
-V(play.result, k) »*. Composer le choix plutôt que le déléguer n'est donc pas
un pis-aller : c'est ce qui garantit que « 2-ply » désigne le même calcul des
deux côtés. Un adversaire dont la profondeur ne veut pas dire la même chose que
la nôtre rendrait la mesure de T36 ininterprétable.

Les coups légaux viennent de **notre** générateur, celui que T01 a croisé
position par position contre GNU Backgammon. On ne réimplémente pas sa notation
de coups.

## L'élagage est éteint par défaut

Les réseaux d'élagage de gnubg changent ce que la profondeur signifie. Une
comparaison de profondeur doit comparer des profondeurs, donc `prune=0` ici. Le
mesurer avec l'élagage actif est une autre mesure, légitime, et elle se demande
explicitement.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import gnubg_board as gb
from .rules import Play, Position

#: Le binaire. Surchargeable pour une machine qui l'installe ailleurs.
GNUBG = os.environ.get("GNUBG", "gnubg")

_SERVER = Path(__file__).resolve().parent.parent.parent / "tools" / "gnubg_server.py"

#: Le préfixe qui sépare le protocole de la bannière, des tableaux de plateau et
#: des messages que gnubg écrit sur la même sortie.
MARK = "@@"


class GnubgError(RuntimeError):
    pass


class GnubgSession:
    """Un processus GNU Backgammon, tenu ouvert.

    Non réentrant et non partageable entre fils : c'est un tube, et deux
    appelants entrelacés liraient la réponse de l'autre. Le parallélisme se fait
    par **processus**, chacun avec sa session — la même règle que T03 impose
    déjà pour `gnubg-nn`.
    """

    def __init__(self, binary: str = GNUBG, server: Path = _SERVER):
        self._process = subprocess.Popen(
            [binary, "--tty", "--quiet", "--no-rc", "-p", str(server)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        hello = self._read()
        if not hello.get("ready"):
            raise GnubgError(f"GNU Backgammon n'a pas démarré : {hello}")
        self.python = hello.get("python", "?")

    def _read(self) -> dict:
        for line in self._process.stdout:
            if line.startswith(MARK):
                return json.loads(line[len(MARK):])
        raise GnubgError("GNU Backgammon a fermé sa sortie sans répondre")

    def ask(self, request: dict) -> dict:
        if self._process.poll() is not None:
            raise GnubgError(f"processus mort (code {self._process.returncode})")
        self._process.stdin.write(json.dumps(request) + "\n")
        self._process.stdin.flush()
        answer = self._read()
        if "error" in answer:
            raise GnubgError(answer["error"])
        return answer

    # ── Les questions ────────────────────────────────────────────────

    def evaluate(self, boards, plies: int = 0, prune: int = 0, state: dict | None = None):
        """Cinq probabilités et équité, par plateau. Un aller-retour pour le lot.

        Le lot n'est pas une optimisation opportuniste : une décision de coup
        pose la même question sur une vingtaine de positions résultantes, et un
        aller-retour par position paierait vingt fois la latence du tube pour un
        seul choix.
        """
        request = {"op": "eval", "boards": boards, "plies": plies, "prune": prune}
        if state:
            request["state"] = state
        return self.ask(request)["values"]

    def cubeful(self, boards, plies: int = 0, prune: int = 0, state: dict | None = None):
        """L'évaluation cubeful, **non interprétée**. T34 en fixera le sens."""
        request = {"op": "cfeval", "boards": boards, "plies": plies, "prune": prune}
        if state:
            request["state"] = state
        return self.ask(request)["values"]

    def met(self, match_to: int = 25):
        return self.ask({"op": "met", "match_to": match_to})["met"]

    def classify(self, boards):
        return self.ask({"op": "classify", "boards": boards})["classes"]

    def close(self):
        if self._process.poll() is None:
            try:
                self._process.stdin.write('{"op":"quit"}\n')
                self._process.stdin.flush()
                self._process.wait(timeout=10)
            except Exception:
                self._process.kill()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


@dataclass
class GnubgEngine:
    """GNU Backgammon comme joueur d'arène, à profondeur et filtre choisis.

    ## Le filtre est sur les DEUX moteurs, ou la mesure ne veut rien dire

    Notre moteur ne descend en profondeur que sur les `k` meilleurs candidats
    d'un pré-tri peu profond — c'est T31, et c'est ce qui rend le 2-ply
    praticable. Faire évaluer à GNU Backgammon **tous** les coups légaux à
    pleine profondeur, en face, serait deux fautes à la fois :

    * **Injuste.** On comparerait un moteur filtré à un moteur qui ne l'est pas,
      et l'écart mesuré contiendrait le coût du filtre au lieu de la différence
      entre les réseaux.
    * **Infaisable.** Mesuré : évaluer chaque coup candidat au 2-ply non élagué
      revient à un 3-ply, et le pilote de T36 ne terminait pas.

    Le même `filter` est donc appliqué ici, par la même règle : pré-tri au
    0-ply, on garde les `filter[0]` meilleurs, on les évalue à `ply`.

    ## `prune` — l'élagage interne de gnubg

    Actif dès que la profondeur dépasse zéro, parce que **c'est ainsi que GNU
    Backgammon joue réellement**, et que `PLAN.md` exige de nommer le réglage
    de l'adversaire plutôt que de le sous-entendre. Le filtre ci-dessus discipline
    la racine ; `prune` discipline l'intérieur de sa recherche, là où nous n'avons
    pas la main.

    NON CONNECTÉ À LA CONSTRUCTION. Le harnais sérialise les moteurs vers ses
    processus ouvriers, et un sous-processus ouvert ne se sérialise pas. Chaque
    ouvrier ouvre sa propre session à la première décision.
    """

    ply: int = 0
    #: Même sémantique que `SearchEngine.filter` : `filter[0]` candidats
    #: survivent au pré-tri de la racine. Vide = aucun filtrage.
    filter: tuple[int, ...] = ()
    prune: int | None = None
    name: str = field(default="")
    _session: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self.prune is None:
            self.prune = 1 if self.ply > 0 else 0
        if not self.name:
            suffix = "-f" + "/".join(str(k) for k in self.filter) if self.filter else ""
            self.name = f"gnubg-{self.ply}ply{suffix}"

    def __getstate__(self):
        # La session ne traverse pas la frontière de processus.
        state = self.__dict__.copy()
        state["_session"] = None
        return state

    def _connect(self) -> GnubgSession:
        if self._session is None:
            self._session = GnubgSession()
        return self._session

    def choose(self, position: Position, d1: int, d2: int, rng: random.Random) -> Play | None:
        plays = position.legal_plays(d1, d2)
        if not plays:
            return None
        if len(plays) == 1:
            # Un seul coup légal ne demande aucune évaluation, et la position
            # résultante peut être terminale — que gnubg n'a pas à évaluer.
            return plays[0]

        session = self._connect()

        # Le pré-tri de la racine se fait au 0-ply, comme chez nous : c'est la
        # règle de T31, et l'appliquer des deux côtés est ce qui fait que
        # « 2-ply, garde 5 » désigne le même joueur des deux côtés.
        keep = self.filter[0] if self.filter else 0
        if self.ply > 0 and keep and len(plays) > keep:
            shallow = self._evaluate_at(session, position, plays, 0)
            survivors = sorted(range(len(plays)),
                               key=lambda i: shallow[i], reverse=True)[:keep]
        else:
            survivors = list(range(len(plays)))

        candidates = [plays[i] for i in survivors]
        deep = self._evaluate_at(session, position, candidates, self.ply)
        return plays[survivors[max(range(len(candidates)), key=lambda j: deep[j])]]

    def _evaluate_at(self, session, position, plays, ply) -> list[float]:
        # Une position terminale se calcule, elle ne s'évalue pas : donner une
        # partie finie à un réseau, c'est lui poser une question qu'il n'a
        # jamais vue, et il répondra. Voir `gn_terminal_equity`.
        pending, boards = [], []
        equities: list[float] = [0.0] * len(plays)
        for index, play in enumerate(plays):
            if play.result.is_over():
                equities[index] = float(_terminal_points(play.result, position.turn))
            else:
                pending.append(index)
                boards.append(gb.to_gnubg(play.result))

        if boards:
            values = session.evaluate(boards, plies=ply, prune=self.prune)
            for index, value in zip(pending, values):
                # `value[5]` est l'équité de la position résultante, vue par le
                # joueur au trait DANS cette position — c'est-à-dire par notre
                # adversaire. La nôtre en est l'opposée.
                equities[index] = -float(value[5])

        return equities


def _terminal_points(result: Position, mover: int) -> int:
    """Ce que vaut une partie que `mover` vient de finir. Toujours positif."""
    from .arena import game_value

    return game_value(result, mover)
