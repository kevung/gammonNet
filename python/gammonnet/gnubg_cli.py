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
import select
import subprocess
import time
from dataclasses import dataclass

from . import codec
from .rules import BLACK, WHITE, Play, Position

GNUBG = "/usr/local/bin/gnubg"

#: gnubg termine chaque réponse par une invite entre parenthèses. Elle porte le
#: nom du joueur au trait — c'est la sentinelle de trait la moins chère qui soit.
#:
#: Reconnaître cette invite est plus délicat qu'il n'y paraît, et les deux
#: pièges ont été payés :
#:
#: * plusieurs réglages répondent par une note entre parenthèses en fin de
#:   ligne (« (Note that this setting...) ») — d'où l'espace final exigé ;
#: * `set score` répond « ... (match to 7 points) » puis l'invite **sans
#:   passer à la ligne** : « ...points)(gnubg) ». Exiger un saut de ligne
#:   devant l'invite fait alors attendre indéfiniment, et se contenter de
#:   « ) » prend « (after 0 games) » pour une invite.
#:
#: La règle retenue : l'invite est une parenthèse en fin de tampon dont le
#: contenu est un jeton CONNU — « No game » ou l'un des deux noms de joueurs,
#: que le constructeur fixe lui-même à `_PLAYER_TOKENS` pour qu'aucun mot de
#: phrase ne puisse leur ressembler.
_PROMPT = re.compile(r"\n\(([^)\n]*)\) $")
_PLAYER_TOKENS = ("gnubgP0", "gnubgP1")
#: `gnubg_state` met le joueur au trait sur `move = 1` : la ligne de
#: commande doit donc mettre le joueur au trait sur le joueur 1.
CLI_MOVER = 1
_POSITION_ID = re.compile(r"Position ID:\s*(\S+)")
#: Le videau tel que le plateau l'affiche : sur la ligne du match quand il est
#: centré, sur la ligne d'un joueur quand il lui appartient.
_BOARD_CUBE = re.compile(r"\(Cube: (\d+)\)")
_BOARD_CUBE_OWNER = re.compile(r"([OX]): (\S+) \(Cube: (\d+)\)")


@dataclass(frozen=True)
class Hint:
    """Un coup candidat, tel que GNU Backgammon le classe."""

    move: str
    equity: float
    probabilities: tuple[float, float, float, float, float] | None


@dataclass(frozen=True)
class CubeHint:
    """Une décision de videau, telle que `hint` la rend au score.

    `available` est faux quand gnubg répond « You cannot double » — un videau
    mort (post-Crawford côté meneur, Crawford, ou videau déjà à l'adversaire).
    Les trois équités sont alors nulles : gnubg n'en imprime aucune.
    """

    action: str
    available: bool
    no_double: float | None
    double_take: float | None
    double_pass: float | None
    cubeless: float | None
    text: str


class Gnubg:
    """Un processus GNU Backgammon persistant, piloté par tube.

    Un processus par worker. gnubg n'est pas conçu pour être partagé, et le
    relancer par décision coûterait bien plus que la décision elle-même.
    """

    def __init__(self, ply: int = 0, path: str = GNUBG, cubeful: bool = False,
                 *, manual: bool = False, cube_ply: int | None = None,
                 cube_prune: bool = True):
        self.ply = ply
        self.cubeful = cubeful
        # Tubes binaires NON tamponnés : `select` ne voit que ce que le noyau
        # a, et un tampon Python entre les deux rendrait le délai de garde
        # aveugle. Le décodage se fait ici, caractère par caractère.
        self._process = subprocess.Popen(
            [path, "--tty", "--quiet", "--no-rc"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        self._prompt = _PROMPT
        self._read_until_prompt()

        # Les noms deviennent des jetons que nulle phrase de gnubg ne porte :
        # c'est ce qui rend l'invite reconnaissable sans ambiguïté. Par
        # `defaultnames` et non par `set player N name` : sondé, `new match`
        # rend aux joueurs leurs noms par défaut, et l'invite redevenait alors
        # « (kunger) » au premier match.
        self._send(f"set defaultnames {_PLAYER_TOKENS[0]} {_PLAYER_TOKENS[1]}")
        self._names = _PLAYER_TOKENS
        # « No game », « Game over » et « Match over » sont les invites hors
        # partie ; les deux noms de joueurs sont les invites en partie. Une
        # invite non prévue lèverait au bout de `READ_TIMEOUT` au lieu de
        # bloquer pour toujours — c'est ainsi que « Game over » a été trouvée.
        self._prompt = re.compile(
            r"\((No game|Game over|Match over|"
            + "|".join(_PLAYER_TOKENS) + r")\) $")

        if manual:
            # `manual` sert les sondes : on veut poser des questions à gnubg
            # sans qu'il joue de lui-même. Deux joueurs humains ne bougent
            # jamais tout seuls, et `hint` répond quand même.
            self._send("set player 0 human", "set player 1 human")
        else:
            # Les deux joueurs sont gnubg lui-même : `play` doit jouer, pas demander.
            self._send("set player 0 gnubg", "set player 1 gnubg")

        # gnubg ne doit jamais agir sans qu'on le lui demande : ni lancer les
        # dés, ni enchaîner une partie. Une sonde qui mesure « le coup que
        # gnubg joue » doit être seule à décider quand il joue.
        self._send("set automatic roll off", "set automatic game off")

        if cube_ply is not None:
            # `hint` ne lit PAS les réglages des joueurs — sondé : ils ne
            # s'appliquent qu'à un joueur de type `gnu`. Il lit ceux de
            # `set evaluation cubedecision`, et c'est donc là qu'on nomme le
            # réglage de videau de l'adversaire.
            self._set_checked(f"set evaluation cubedecision eval plies {cube_ply}",
                              f"cube decisions will use {cube_ply} ply")
            self._set_checked(
                f"set evaluation cubedecision eval prune "
                f"{'on' if cube_prune else 'off'}",
                "cube decisions will use pruning" if cube_prune
                else "cube decisions will not use pruning")
            self._set_checked("set evaluation cubedecision eval cubeful on",
                              "cube decisions will use cubeful evaluation")
            self._set_checked("set evaluation cubedecision eval noise 0.0",
                              "cube decisions will use noiseless evaluations")
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

    #: Un 2-ply cubeful sur une machine chargée reste très en deçà ; au-delà,
    #: c'est que l'invite n'a pas été reconnue, et attendre pour toujours
    #: serait la pire façon de le découvrir.
    READ_TIMEOUT = 600.0

    def _read_until_prompt(self) -> str:
        chunks: list[str] = []
        deadline = time.monotonic() + self.READ_TIMEOUT
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select(
                    [self._process.stdout], [], [], remaining)[0]:
                raise RuntimeError(
                    f"GNU Backgammon n'a pas rendu l'invite en "
                    f"{self.READ_TIMEOUT:.0f} s ; fin du tampon : "
                    f"{''.join(chunks)[-300:]!r}")
            char = self._process.stdout.read(1)
            if not char:
                raise RuntimeError("GNU Backgammon s'est arrêté")
            chunks.append(char.decode("utf-8", "replace"))
            if char in (b")", b" "):
                text = "".join(chunks)
                if self._prompt.search(text):
                    return text

    def _send(self, *commands: str) -> str:
        for command in commands:
            self._process.stdin.write((command + "\n").encode())
        self._process.stdin.flush()
        return "".join(self._read_until_prompt() for _ in commands)

    def close(self) -> None:
        if self._process.poll() is None:
            try:
                self._process.stdin.write(b"quit\n")
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

    def _parse_hints(self, text: str) -> list[Hint]:
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

    def hints(self, position: Position, d1: int, d2: int) -> list[Hint]:
        """Le classement de gnubg, avec équités. Diagnostic, pas chemin chaud."""
        self.set_position(position)
        self._send(f"set dice {d1} {d2}")
        return self._parse_hints(self._send("hint"))

    def hints_at_score(self, position: Position, d1: int, d2: int) -> list[Hint]:
        """Le même classement, SANS toucher au contexte de match.

        `hints` passe par `set_position`, qui commence une **nouvelle partie**
        — et perd donc le score, le trait et le videau posés avant. Pour une
        analyse au score il faut la recette de la sonde de T35 : le match est
        posé une fois par `new_match`/`set_score`/`set_turn`, et seule la
        position change ensuite, par `set board` seul.

        La relecture de l'identifiant vérifie du même coup la position **et**
        le trait : l'identifiant est relatif au joueur au trait.
        """
        self._send(f"set board {codec.position_id(position)}")
        self.verify_board(position, cube=1, owner=None, check_cube=False)
        self._send(f"set dice {d1} {d2}")
        return self._parse_hints(self._send("hint"))

    # ── Le match, le score, le videau ────────────────────────────────
    #
    # Tout ce qui suit sert la sonde de T35 : rejouer par l'interface de gnubg
    # lui-même les décisions de videau que la campagne lui demande par
    # `cfevaluate`, pour établir — et non supposer — que les deux chemins
    # disent la même chose au score.
    #
    # Chaque réglage est VÉRIFIÉ sur l'accusé de réception de gnubg. Une
    # commande refusée ne lève pas d'exception ici sans cela : elle imprime
    # « Unknown keyword » et la sonde mesurerait alors un score qui n'a jamais
    # été posé — exactement le mode de défaillance silencieux que le dépôt
    # refuse.

    def _set_checked(self, command: str, expected: str) -> str:
        reply = self._send(command)
        if expected not in reply:
            raise RuntimeError(
                f"gnubg n'a pas accusé réception de {command!r} : attendu "
                f"{expected!r}, reçu {reply.strip()[:200]!r}")
        return reply

    @staticmethod
    def _prompt_name(reply: str) -> str | None:
        match = _PROMPT.search(reply)
        return match.group(1) if match else None

    def new_match(self, length: int) -> None:
        self._set_checked(f"new match {length}", f"new {length} points match")

    def new_money_session(self, jacoby: bool = True, beavers: bool = False) -> None:
        self._set_checked("new session", "A new session has been started")
        self._set_checked(f"set jacoby {'on' if jacoby else 'off'}",
                          "Jacoby rule" )
        self._set_checked(f"set beavers {1 if beavers else 0}", "beaver")

    def set_score(self, score0: int, score1: int, length: int) -> None:
        reply = self._send(f"set score {score0} {score1}")
        expected = f"{self._names[0]} {score0}, {self._names[1]} {score1}"
        if expected not in reply or f"match to {length} points" not in reply:
            raise RuntimeError(
                f"score refusé : attendu {expected!r} dans un match de "
                f"{length} points, reçu {reply.strip()[:200]!r}")

    def set_crawford(self, crawford: bool) -> None:
        self._set_checked(
            f"set crawford {'on' if crawford else 'off'}",
            "This game is the Crawford game" if crawford
            else "This game is not the Crawford game")

    def set_turn(self, player: int) -> None:
        """Donner le trait au joueur 0 ou 1 — vérifié sur l'invite qui suit."""
        reply = self._send(f"set turn {player}")
        if self._prompt_name(reply) != self._names[player]:
            raise RuntimeError(
                f"le trait n'est pas passé à {self._names[player]!r} : "
                f"invite {self._prompt_name(reply)!r}")

    def set_cube(self, value: int, owner: int | None) -> bool:
        """Valeur puis propriétaire — l'ordre est celui que gnubg accepte.

        Rend **faux** quand gnubg refuse de poser un videau parce qu'il n'y en
        a pas : « The cube is disabled during the Crawford game. » C'est une
        réponse, pas une panne — la partie de Crawford se joue sans videau, et
        c'est précisément ce que la sonde veut vérifier des deux côtés.
        """
        reply = self._send(f"set cube value {value}")
        if "disabled" in reply:
            return False
        if owner is None:
            self._set_checked("set cube centre", "cube has been centred")
        else:
            self._set_checked(f"set cube owner {self._names[owner]}",
                              f"{self._names[owner]}")
        return True

    def verify_board(self, position: Position, cube: int,
                     owner: int | None, check_cube: bool = True) -> None:
        """La sentinelle : le plateau que gnubg tient est bien celui qu'on pose.

        L'identifiant de position est relatif au joueur au trait — le relire
        égal à celui qu'on a envoyé contrôle donc la position ET le trait d'un
        seul coup. Le videau se lit sur la ligne où gnubg l'imprime : celle du
        match s'il est centré, celle d'un joueur s'il lui appartient.
        """
        text = self._send("show board")
        found = _POSITION_ID.search(text)
        wanted = codec.position_id(position)
        if not found or found.group(1) != wanted:
            raise RuntimeError(
                f"gnubg tient une autre position que celle posée : "
                f"{found.group(1) if found else None!r} au lieu de {wanted!r}")

        if not check_cube:
            return

        owned = _BOARD_CUBE_OWNER.search(text)
        value = _BOARD_CUBE.search(text)
        if not value or int(value.group(1)) != cube:
            raise RuntimeError(
                f"videau à {value.group(1) if value else None} au lieu de {cube}")
        owner_name = None if owner is None else self._names[owner]
        seen_owner = owned.group(2) if owned else None
        if seen_owner != owner_name:
            raise RuntimeError(
                f"videau possédé par {seen_owner!r} au lieu de {owner_name!r}")

    # ── La décision de videau ────────────────────────────────────────

    _CUBEFUL_LINE = re.compile(r"^\s*\d+\.\s+(.+?)\s\s+([-+]?\d+\.\d+)",
                               re.MULTILINE)
    _PROPER = re.compile(r"Proper cube action:\s*(.+?)\s*$", re.MULTILINE)
    _CUBELESS = re.compile(r"cubeless equity\s+([-+]?\d+\.\d+)")

    def cube_hint(self, position: Position, cube: int = 1,
                  owner: int | None = None) -> CubeHint:
        """Ce que GNU Backgammon fait du videau sur cette position, à ce score.

        Le score, lui, a été posé avant par `new_match`/`set_score`/`set_turn`
        — il vaut pour toutes les positions du même contexte.
        """
        self._send(f"set board {codec.position_id(position)}")
        # `set board` ne remet pas le videau (sondé), mais le reposer coûte
        # deux commandes et retire la question.
        live = self.set_cube(cube, owner)
        self.verify_board(position, cube, owner, check_cube=live)
        if not live:
            return CubeHint("Cube not available", False, None, None, None,
                            None, "cube disabled (Crawford)")

        text = self._send("hint")
        if "cannot double" in text or "Cube not available" in text:
            return CubeHint("Cube not available", False, None, None, None,
                            None, text)

        proper = self._PROPER.search(text)
        if not proper:
            raise RuntimeError(
                f"pas de « Proper cube action » dans la réponse de gnubg : "
                f"{text.strip()[:400]!r}")

        equities: dict[str, float] = {}
        for label, value in self._CUBEFUL_LINE.findall(text):
            lowered = label.lower()
            if lowered.startswith("no double") or lowered.startswith("no redouble"):
                equities["no_double"] = float(value)
            elif "pass" in lowered:
                equities["double_pass"] = float(value)
            elif "take" in lowered:
                equities["double_take"] = float(value)
        cubeless = self._CUBELESS.search(text)

        return CubeHint(
            action=proper.group(1),
            available=True,
            no_double=equities.get("no_double"),
            double_take=equities.get("double_take"),
            double_pass=equities.get("double_pass"),
            cubeless=float(cubeless.group(1)) if cubeless else None,
            text=text,
        )

    def best_play_at_score(self, position: Position, d1: int, d2: int) -> Play | None:
        """Le coup que gnubg joue **au score déjà posé**.

        `best_play` repart d'une `new game`, qui remettrait le match à plat.
        Ici le score, le Crawford et le trait ont été posés une fois pour
        toutes par l'appelant ; seuls le plateau et les dés changent.

        Le videau est donné à l'ADVERSAIRE : gnubg ne peut alors pas doubler,
        et `play` joue forcément un coup. C'est sans effet sur la comparaison
        — le propriétaire du videau ne change pas une évaluation cubeless
        (sondé en T35, `eval[5]` identique au millionième pour les trois
        propriétaires) — et cela retire la seule façon dont `play` pourrait
        rendre autre chose qu'un coup.

        L'appariement se fait par RÉSULTAT, comme `best_play` : le seul format
        traversé reste l'identifiant de position, déjà croisé en T02.

        Rend `None` quand gnubg **abandonne** au lieu de jouer — voir plus bas.
        L'appelant n'appelant cette méthode qu'avec au moins deux coups
        légaux, `None` n'a pas d'autre sens ici.
        """
        ours = position.legal_plays(d1, d2)
        if not ours:
            return None
        if len(ours) == 1:
            return ours[0]

        self.set_turn(CLI_MOVER)
        self._send(f"set board {codec.position_id(position)}")
        self.set_cube(1, 1 - CLI_MOVER)
        self._send(f"set dice {d1} {d2}")
        reply = self._send("play")
        if "resigns" in reply:
            # Dans une course désespérée, `play` ABANDONNE au lieu de jouer —
            # il n'y a pas de réglage pour l'en empêcher (`help set player`,
            # `help set automatic` : aucun n'en parle). L'abandon est refusé
            # pour que la partie reste dans un état propre, et la position est
            # rendue INCOMPARABLE plutôt que devinée : c'est à l'appelant de la
            # compter à part.
            self._send("decline")
            return None
        reached = self.current_position_id()

        by_id = {codec.position_id(play.result): play for play in ours}
        chosen = by_id.get(reached)
        if chosen is None:
            raise RuntimeError(
                f"GNU Backgammon a joué un coup que nous ne générons pas "
                f"({reached}) depuis {position!r} avec {d1}-{d2}")
        return chosen
