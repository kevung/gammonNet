"""La classe d'une position — la stratification de T70, la carte de T77.

## Pourquoi un classificateur maison

`gnubg.classifypos` rend cinq classes (`over`, `bearoff`, `race`, `crashed`,
`contact`) : ce sont les classes de ses **réseaux**, pas celles d'un joueur. T77
demande où l'erreur se concentre — blitz, prime contre prime, holding, backgame,
course avec contact résiduel — et aucune de ces questions ne se lit dans une
classification en cinq cases dont quatre disent « contact ».

Ce sont donc **des conventions de ce dépôt**, pas des définitions canoniques du
backgammon : elles sont écrites ici pour être critiquables et reproductibles, et
gelées avec le corpus qu'elles stratifient. Une position tombe dans **exactement
une** classe — l'ordre des tests ci-dessous est la priorité, et il est délibéré :
un backgame est un backgame même s'il ressemble à un holding.

Les seuils sont ronds à dessein. Aucun n'est ajusté sur un résultat : les régler
pour améliorer un chiffre serait choisir la question après avoir vu la réponse.
"""

from __future__ import annotations

from .rules import BLACK, NUM_POINTS, WHITE, Position

#: Les classes, dans l'ordre de priorité du classificateur. `CLASSES` est
#: l'ordre publié des strates ; s'en écarter changerait la lecture d'un rapport.
CLASSES = (
    "over",
    "bearoff_noncontact",
    "bearoff_contact",
    "race",
    "race_contact",
    "backgame",
    "prime_vs_prime",
    "blitz",
    "holding",
    "crashed",
    "contact",
)

#: Un prime : ce nombre de points consécutifs tenus (2 pions ou plus).
PRIME_LENGTH = 4
#: Un backgame : ce nombre d'ancrages tenus dans le jan intérieur adverse.
BACKGAME_ANCHORS = 2
#: `crashed`, la convention de gnubg reprise telle quelle : moins de ce nombre
#: de pions hors du jan intérieur, jeu en ruine.
CRASHED_OUTSIDE = 3
#: Un blitz : l'adversaire a un pion à rentrer et l'on tient au moins ce nombre
#: de points de son propre jan intérieur.
BLITZ_HOME_POINTS = 3
#: Un holding game : un ancrage tenu à cette distance ou plus (point 18 = midpoint
#: adverse, 20 = golden anchor) alors que l'on est en retard à la course.
HOLDING_ANCHORS = (18, 20, 21, 22)
#: « En retard à la course » : ce déficit de pips au moins.
HOLDING_DEFICIT = 10
#: Un contact résiduel : un seul pion arriéré, et ce nombre de pips ou moins à
#: franchir pour que la course soit pure.
RESIDUAL_CROSSING = 12


def _points_of(position: Position, player: int) -> dict[int, int]:
    """Les pions de `player`, indexés par **son** numéro de point (1 à 24).

    Le point 1 est celui dont il sort, le 24 celui d'où il part. C'est le repère
    du joueur, pas celui du tableau : il rend les deux camps comparables sans
    qu'aucune règle ci-dessous ait à connaître le signe des indices.
    """
    out: dict[int, int] = {}
    for index in range(NUM_POINTS):
        count = position.points[index]
        if player == WHITE and count > 0:
            out[index + 1] = count
        elif player == BLACK and count < 0:
            out[NUM_POINTS - index] = -count
    return out


def _back_checker(own: dict[int, int], bar: int) -> int:
    """Le point du pion le plus arriéré — 25 s'il est sur la barre, 0 s'il n'y a
    plus rien à faire avancer."""
    if bar:
        return 25
    return max(own, default=0)


def _prime_length(own: dict[int, int]) -> int:
    """La plus longue suite de points consécutifs tenus (2 pions au moins)."""
    best = run = 0
    for point in range(1, NUM_POINTS + 1):
        if own.get(point, 0) >= 2:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def _anchors_in_opponent_home(own: dict[int, int]) -> int:
    """Les points tenus dans le jan intérieur adverse — les points 19 à 24 vus
    du joueur."""
    return sum(1 for point in range(19, 25) if own.get(point, 0) >= 2)


def has_contact(position: Position) -> bool:
    """Un pion de chaque camp peut-il encore en croiser un autre ?

    La définition de `bench/decision_loss.py`, reprise ici pour que le corpus et
    la classification ne puissent pas diverger sur ce point.
    """
    if position.bar[0] or position.bar[1]:
        return True
    white = [i for i, n in enumerate(position.points) if n > 0]
    black = [i for i, n in enumerate(position.points) if n < 0]
    if not white or not black:
        return False
    return max(white) > min(black)


def _crossing_gap(position: Position) -> int:
    """De combien de pips il s'en faut que la course soit pure.

    Positif : il reste du contact, et voilà ce qu'il faut franchir. Zéro ou
    moins : les camps se sont croisés.
    """
    white = [i for i, n in enumerate(position.points) if n > 0]
    black = [i for i, n in enumerate(position.points) if n < 0]
    if not white or not black:
        return 0
    return max(white) - min(black)


def _rear_checker_count(own: dict[int, int], bar: int, threshold: int) -> int:
    """Combien de pions au-delà de `threshold` — la barre comprise."""
    return bar + sum(n for point, n in own.items() if point > threshold)


def classify(position: Position, player: int | None = None) -> str:
    """La classe de `position`, **du point de vue de `player`**.

    Par défaut le joueur au trait. Le point de vue compte : un blitz mené est
    un blitz subi de l'autre côté, et la carte d'erreur de T77 lit la décision
    de celui qui joue. Une position rend donc, en général, deux classes
    différentes selon le camp — c'est voulu, pas une ambiguïté.
    """
    if player is None:
        player = position.turn
    other = BLACK if player == WHITE else WHITE

    if position.is_over():
        return "over"

    own = _points_of(position, player)
    opp = _points_of(position, other)
    own_bar = position.bar[player]
    opp_bar = position.bar[other]
    contact = has_contact(position)

    own_back = _back_checker(own, own_bar)
    opp_back = _back_checker(opp, opp_bar)

    # ── Fin de partie ───────────────────────────────────────────────
    # Tous les pions rentrés : la question posée est celle du démarquage, et
    # elle change de nature selon qu'un adversaire peut encore frapper.
    if own_back <= 6:
        return "bearoff_contact" if contact else "bearoff_noncontact"

    # ── Course ──────────────────────────────────────────────────────
    if not contact:
        return "race"

    # Contact résiduel : un seul pion arriéré, à quelques pips de la course pure.
    # C'est le cas que DS-13 vise, et il ne ressemble ni à une course ni à un
    # jeu de contact — d'où sa strate propre.
    gap = _crossing_gap(position)
    rear = _rear_checker_count(own, own_bar, own_back - 1) if own_back else 0
    if not own_bar and not opp_bar and rear <= 1 and 0 < gap <= RESIDUAL_CROSSING:
        return "race_contact"

    # ── Jeux de contact ─────────────────────────────────────────────
    # Backgame d'abord : deux ancrages dans le jan adverse dominent la lecture
    # de la position, quelle que soit la structure devant.
    if _anchors_in_opponent_home(own) >= BACKGAME_ANCHORS:
        return "backgame"

    own_prime = _prime_length(own)
    opp_prime = _prime_length(opp)
    # Prime contre prime : deux murs, et chacun a quelque chose à faire passer.
    if (own_prime >= PRIME_LENGTH and opp_prime >= PRIME_LENGTH
            and own_back >= 19 - PRIME_LENGTH and opp_back >= 19 - PRIME_LENGTH):
        return "prime_vs_prime"

    # Blitz : l'adversaire est sur la barre devant un jan qui se ferme.
    own_home_points = sum(1 for point in range(1, 7) if own.get(point, 0) >= 2)
    if opp_bar and own_home_points >= BLITZ_HOME_POINTS:
        return "blitz"

    # Crashed : la convention de gnubg — le jeu s'est effondré sur lui-même.
    outside = sum(n for point, n in own.items() if point > 6) + own_bar
    if outside < CRASHED_OUTSIDE:
        return "crashed"

    # Holding : un ancrage avancé tenu, et la course perdue — c'est l'ancrage
    # qui vaut le coup, et la question est quand le quitter.
    deficit = position.pip_count(player) - position.pip_count(other)
    if (deficit >= HOLDING_DEFICIT
            and any(own.get(point, 0) >= 2 for point in HOLDING_ANCHORS)):
        return "holding"

    return "contact"
