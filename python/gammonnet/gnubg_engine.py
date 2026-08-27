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
from .cube import CubeAction, CubeOwner
from .met import MatchState
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

    def bestmove(self, items, plies: int = 0, cubeful: int = 1, prune: int = 0,
                 state: dict | None = None):
        """Le meilleur coup de gnubg par (plateau, dés), **non interprété**.

        `items` : liste de `{"board": ..., "dice": (d1, d2)}`. Rend la liste
        des tuples d'entiers de `findbestmove` — paires (de, vers), sémantique
        sondée et documentée dans `tools/gnubg_server.py::op_bestmove`. C'est
        le client (`bench/compare_moves.py`) qui les confronte à ses coups
        légaux, et qui doit refuser tout tuple qu'il ne sait pas apparier.
        """
        request = {"op": "bestmove", "items": items, "plies": plies,
                   "cubeful": cubeful, "prune": prune}
        if state:
            request["state"] = state
        return self.ask(request)["moves"]

    def met(self, match_to: int = 25):
        return self.ask({"op": "met", "match_to": match_to})["met"]

    def classify(self, boards):
        return self.ask({"op": "classify", "boards": boards})["classes"]

    def board_from_xgid(self, identifier: str):
        """Le plateau que gnubg lit dans un XGID, ou None s'il le refuse.

        Un refus est une réponse — c'est ainsi qu'on découvre qu'un XGID
        malformé l'est. L'oracle de T76 doit pouvoir dire « non ».
        """
        reply = self.ask({"op": "xgid", "xgid": identifier})
        return None if "error" in reply else reply["board"]

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
    0-ply, on garde les meilleurs, on les évalue à `ply`. L'indexation est celle
    du C — la racine d'une recherche à `k` plies lit `filter[k]` — et elle vaut
    d'être répétée : la lire comme `filter[0]` a coûté un pilote entier de T36,
    où quatre configurations « filtrées » ont rendu 14 247 évaluations chacune,
    à l'unité près, parce qu'aucune ne filtrait.

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
    #: Même sémantique et même INDEXATION que `SearchConfig.filter` du C :
    #: `filter[d]` est ce qui survit à un nœud de profondeur **restante** `d`.
    #: La racine d'une recherche à `k` plies lit donc `filter[k]`, et
    #: `filter[0]` n'est jamais lu. Vide = aucun filtrage.
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

    def choose(self, position: Position, d1: int, d2: int, rng: random.Random,
               state: dict | None = None) -> Play | None:
        """Le meilleur coup, money (`state=None`) ou au score.

        `state` est un dictionnaire `cubeinfo` décrivant **le joueur au trait
        des positions résultantes** — c'est-à-dire l'adversaire de celui qui
        choisit, puisque `play.result` a déjà rendu le trait. Sondé (T35,
        `docs/mesures/2026-08-09-t35-sonde-emg.md`) : sous un `cubeinfo` de
        match, `evaluate` rend l'équité EMG au score — affine en la MWC du
        joueur au trait, à pente positive. Comme tous les candidats partagent
        le même état, `-eval[5]` classe par la MWC de celui qui choisit
        (`mwc_chooser = 1 - mwc_mover`), et la convention composée de T36 se
        transporte au score sans changer d'arithmétique.
        """
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
        # « 2-ply, garde 5 » désigne le même joueur des deux côtés. Au score,
        # le pré-tri est lui aussi au score — le point mesuré par T31-match.
        keep = self.filter[self.ply] if len(self.filter) > self.ply else 0
        if self.ply > 0 and keep and len(plays) > keep:
            shallow = self._evaluate_at(session, position, plays, 0, state)
            survivors = sorted(range(len(plays)),
                               key=lambda i: shallow[i], reverse=True)[:keep]
        else:
            survivors = list(range(len(plays)))

        candidates = [plays[i] for i in survivors]
        deep = self._evaluate_at(session, position, candidates, self.ply, state)
        return plays[survivors[max(range(len(candidates)), key=lambda j: deep[j])]]

    def _evaluate_at(self, session, position, plays, ply,
                     state: dict | None = None) -> list[float]:
        # Une position terminale se calcule, elle ne s'évalue pas : donner une
        # partie finie à un réseau, c'est lui poser une question qu'il n'a
        # jamais vue, et il répondra. Voir `gn_terminal_equity`.
        #
        # Au score, la valeur en points d'un coup terminal est une
        # approximation NOMMÉE de l'EMG : un gain simple certain vaut
        # exactement +1 sur les deux échelles (c'est la définition de l'EMG) ;
        # un gammon terminal vaut 2 en points contre un EMG dans (1 ; ~1,6] —
        # l'ordre ne peut s'inverser que si un coup NON terminal dépasse
        # l'EMG du gammon terminal, ce qui demande des chances de backgammon
        # au-delà d'un gammon certain, à un score où la différence compte.
        pending, boards = [], []
        equities: list[float] = [0.0] * len(plays)
        for index, play in enumerate(plays):
            if play.result.is_over():
                equities[index] = float(_terminal_points(play.result, position.turn))
            else:
                pending.append(index)
                boards.append(gb.to_gnubg(play.result))

        if boards:
            values = session.evaluate(boards, plies=ply, prune=self.prune,
                                      state=state)
            for index, value in zip(pending, values):
                # `value[5]` est l'équité de la position résultante, vue par le
                # joueur au trait DANS cette position — c'est-à-dire par notre
                # adversaire. La nôtre en est l'opposée (au score : l'EMG est
                # affine en la MWC du mover, donc la négation classe par la
                # MWC du chooser — même arithmétique).
                equities[index] = -float(value[5])

        return equities


def _terminal_points(result: Position, mover: int) -> int:
    """Ce que vaut une partie que `mover` vient de finir. Toujours positif."""
    from .arena import game_value

    return game_value(result, mover)


# ── Les questions de videau, telles que la sonde de T34 les a établies ──
#
# Historique : ces trois définitions vivaient dans `bench/compare_cube.py`, où
# la sonde qui les a établies est documentée (en-tête du fichier — 4000+ appels
# `cfevaluate`, les paires (code, texte) observées, les conventions de
# `cubeinfo`). T35 les fait entrer dans le paquet parce que l'arène cubeful en
# a besoin ; le banc les réimporte d'ici.

#: La convention de propriétaire de `cubeinfo`, établie par sonde :
#: -1 centré, 1 le joueur au trait possède, 0 l'adversaire possède.
_GNUBG_OWNER_OF = {CubeOwner.CENTRED: -1, CubeOwner.OWNED: 1, CubeOwner.OPPONENT: 0}


def classify_gnubg_verdict(text: str) -> CubeAction:
    """Map gnubg's `recommendationtext` to our four-verdict `CubeAction`.

    Order matters: "too good" must be checked before the generic
    double/pass-or-take rule, since "Too good to double, pass" would
    otherwise match the DOUBLE_PASS rule. Everything not recognised raises --
    per `CLAUDE.md` rule 2, an unmapped string is refused, never guessed at.
    The probe that established the vocabulary lives in
    `bench/compare_cube.py` (its `_VERDICTS` table).
    """
    lowered = text.lower()
    if "too good" in lowered:
        return CubeAction.TOO_GOOD
    if "cube not available" in lowered:
        return CubeAction.NO_DOUBLE
    # « Never double » ET « Never redouble », et plus généralement tout verdict
    # que gnubg marque « (dead cube) ». La sonde du 2026-08-21
    # (`bench/probe_gnubg_at_score.py`) a payé cher l'absence du second : la
    # règle générique en dessous lisait « Never redouble, take (dead cube) »
    # comme DOUBLE_TAKE — « redouble » contient « double », et la chaîne
    # contient « take » — c'est-à-dire qu'elle faisait redoubler gnubg
    # exactement là où gnubg dit de ne jamais le faire. Le videau à 1 de la
    # sonde de T34 n'atteignait aucun redoublement, d'où le trou.
    if lowered.startswith("never ") or "dead cube" in lowered:
        return CubeAction.NO_DOUBLE
    if lowered.startswith("no double") or lowered.startswith("no redouble"):
        return CubeAction.NO_DOUBLE
    has_double_word = "double" in lowered or "redouble" in lowered
    if has_double_word and "pass" in lowered:
        return CubeAction.DOUBLE_PASS
    if has_double_word and "take" in lowered:
        return CubeAction.DOUBLE_TAKE
    raise ValueError(
        f"gnubg verdict string not in the mapping established by the T34 "
        f"probe: {text!r}. Refused rather than guessed -- see "
        f"bench/compare_cube.py for the probe and extend the classifier "
        f"deliberately."
    )


def gnubg_state(owner: CubeOwner, match: MatchState | None, jacoby: bool,
                cube: int = 1) -> dict:
    """Build the `state` dict `GnubgSession.cubeful` forwards to `cubeinfo`.

    `move` is fixed at 1 (established by probe: arbitrary but must be
    consistent with the score assignment below). For a match state,
    `score[move]` must be the mover's own score -- also established by probe,
    against the post-Crawford systematic-double signature. `cube` is the
    CURRENT cube value, before any double under consideration.
    """
    state = {"cube": int(cube), "cube_owner": _GNUBG_OWNER_OF[owner], "move": 1}
    if match is None:
        state.update(match_to=0, score=(0, 0), crawford=0, jacoby=int(jacoby))
    else:
        match_to = max(match.away_on_roll, match.away_opponent)
        state.update(
            match_to=match_to,
            score=(match_to - match.away_opponent, match_to - match.away_on_roll),
            crawford=int(match.crawford),
        )
    return state
