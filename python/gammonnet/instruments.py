"""T81/T82 — les instruments de falsification de l'axe « videau appris ».

**Ce module ne fait rien apprendre.** Il extrait d'un moteur — le nôtre
aujourd'hui, un modèle appris demain — les quantités que la théorie du videau
nomme, pour qu'un échec se constate en minutes au lieu de se découvrir en
semaines de campagne.

Le contrôle qui les valide est écrit dans la fiche T82 : **on les passe d'abord
sur la pile classique, dont on connaît la réponse.** Un extracteur qui ne
retrouve pas ce qu'on sait déjà n'instrumente rien.

## Les deux MET, et pourquoi les confondre serait une faute

Il y a **deux** quantités qu'on peut appeler « la MET du moteur », et elles ne
sont pas égales :

- `read_met` — ce que la pile classique **lit** dans sa table. C'est
  Kazaross-XG2 à l'identité, par construction. Son rôle n'est pas de mesurer :
  c'est de **fixer les conventions** (qui est au trait, `away` et non points,
  le drapeau Crawford). Un extracteur qui se trompe d'indexation se trahit ici.
- `implicit_met` — la valeur que le moteur **assigne** au début d'une partie à
  ce score, `V(position initiale, a-away, b-away, videau centré)`. Pour un
  modèle appris, c'est la MET émergée. Pour la pile classique, ce n'est **pas**
  la table : c'est la table vue à travers l'évaluation que le réseau fait de la
  position initiale.

L'écart entre les deux est le **résidu de point fixe** de la pile classique :
de combien son évaluation du début de partie s'écarte de la table sur laquelle
elle est bâtie. Il n'est pas nul, il n'a jamais été mesuré ici, et c'est
exactement la quantité qu'un modèle appris devra battre. Le mesurer sur la pile
classique **avant** d'entraîner quoi que ce soit, c'est se donner le repère
sans lequel le chiffre du modèle appris ne voudrait rien dire.

Kazaross-XG2 est ici un **instrument**, jamais une entrée — le statut que
`CLAUDE.md` accorde à GNU Backgammon comme oracle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from . import met as met_module
from .cube import CubeAction, CubeInputs, CubeOwner, decide
from .cube import value as cube_value
from .infer import Evaluation
from .met import MAX_AWAY, MatchState

#: Le pivot des tables d'équité de match : -2/-1 Crawford. Rockwell-Kazaross y
#: donne 32,31 % pour le poursuivant, vérifié par plusieurs rollouts
#: indépendants (DS-08 §B.2). C'est le repère public de toute MET.
PIVOT_TRAILER_MWC = 0.3231


# ── Les deux MET ─────────────────────────────────────────────────────


def read_met(max_away: int = MAX_AWAY) -> dict[tuple[int, int], float]:
    """La table telle que la pile classique la lit. Identité par construction.

    Rôle : fixer les conventions, pas mesurer. `(a, b)` est vu du **joueur au
    trait**, à `a` points de la victoire contre un adversaire à `b`.
    """
    return {
        (a, b): met_module.pre_crawford(a, b)
        for a in range(1, max_away + 1)
        for b in range(1, max_away + 1)
    }


def implicit_met(
    mwc_at_start: Callable[[MatchState], float],
    max_away: int = MAX_AWAY,
) -> dict[tuple[int, int], float]:
    """La MET que le moteur *assigne*, et non celle qu'il lit.

    `mwc_at_start(state)` rend la chance de gagner le match du joueur au trait
    au **début d'une partie**, videau centré, à l'état `state`. Pour la pile
    classique on lui passe l'évaluation de la position initiale ; pour un
    modèle conscient du score, sa sortie directe.
    """
    out: dict[tuple[int, int], float] = {}
    for a in range(1, max_away + 1):
        for b in range(1, max_away + 1):
            out[(a, b)] = mwc_at_start(MatchState(a, b, cube=1))
    return out


def classic_mwc_at_start(evaluation: Evaluation) -> Callable[[MatchState], float]:
    """Le `mwc_at_start` de la pile classique : les cinq probabilités de la
    position initiale, converties par la table.

    La conversion passe par `MatchState.winning_chance`, donc par le C —
    jamais par une somme refaite ici.
    """

    def _at(state: MatchState) -> float:
        return state.winning_chance(evaluation)

    return _at


def classic_cubeful_mwc_at_start(
    evaluation: Evaluation, efficiency: tuple[float, float, float]
) -> Callable[[MatchState], float]:
    """Le `mwc_at_start` **cubeful** de la pile classique — videau centré.

    La différence avec `classic_mwc_at_start` n'est pas cosmétique : une
    cellule de MET est une MWC *au videau vivant*, puisque les rollouts qui
    l'ont produite jouaient le videau. Convertir une distribution cubeless par
    la table, c'est comparer deux quantités qui ne sont pas la même — et
    l'écart entre les deux conversions dit **ce que le videau vaut à ce
    score**.
    """

    def _at(state: MatchState) -> float:
        equity = cube_value(
            evaluation, CubeOwner.CENTRED, efficiency[int(CubeOwner.CENTRED)], state=state
        )
        return (equity + 1.0) / 2.0

    return _at


@dataclass(frozen=True)
class MetResidual:
    """L'écart cellule par cellule entre les deux MET."""

    cells: dict[tuple[int, int], float]

    @property
    def mean_abs(self) -> float:
        return sum(abs(v) for v in self.cells.values()) / len(self.cells)

    @property
    def worst(self) -> tuple[tuple[int, int], float]:
        return max(self.cells.items(), key=lambda kv: abs(kv[1]))

    def above(self, threshold: float) -> list[tuple[tuple[int, int], float]]:
        """Les cellules qui divergent au-delà d'un seuil **annoncé d'avance**.

        La fiche T82 exige qu'elles soient arbitrées par rollout de match, pas
        expliquées : un écart n'est pas nécessairement une erreur, la table est
        elle-même une mesure.
        """
        return sorted(
            ((k, v) for k, v in self.cells.items() if abs(v) > threshold),
            key=lambda kv: -abs(kv[1]),
        )


def met_residual(
    implicit: dict[tuple[int, int], float],
    reference: dict[tuple[int, int], float],
) -> MetResidual:
    """`implicit − reference`, cellule par cellule, sur les clés communes."""
    keys = implicit.keys() & reference.keys()
    if not keys:
        raise ValueError("aucune cellule commune entre les deux MET")
    return MetResidual({k: implicit[k] - reference[k] for k in keys})


# ── Les points de prise, par balayage plutôt que par formule ──────────


def gammonless(win: float) -> Evaluation:
    """La famille `W = L = 1` : une course sans gammon, paramétrée par `p`.

    C'est le seul domaine où le modèle de videau a une référence exacte dans ce
    dépôt (la table bilatérale, cf. `bench/fit_efficiency.py`), et celui où
    Janowski donne ses valeurs de manuel : TP = 0,25 à videau mort, 0,20 à
    videau vivant.
    """
    return Evaluation(win, 0.0, 0.0, 0.0, 0.0)


def frontier(
    is_above: Callable[[float], bool],
    lo: float = 0.0,
    hi: float = 1.0,
    tolerance: float = 1e-7,
) -> float:
    """La bissection qui trouve où un verdict bascule, sans supposer de formule.

    C'est ce qui rend l'instrument applicable à un modèle appris : on ne lui
    demande pas son point de prise, on **observe** où il change d'avis.
    """
    if is_above(lo) == is_above(hi):
        raise ValueError("pas de bascule dans l'intervalle : rien à trouver")
    above_hi = is_above(hi)
    while hi - lo > tolerance:
        mid = (lo + hi) / 2.0
        if is_above(mid) == above_hi:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def swept_cash_point(
    efficiency: float,
    owner: CubeOwner = CubeOwner.CENTRED,
    state: MatchState | None = None,
    make: Callable[[float], Evaluation] = gammonless,
) -> float:
    """Le point de caisse **observé** : le `p` où le verdict passe de
    « double, prise » à « double, passe ».

    C'est ce qu'on peut observer de l'extérieur, sur n'importe quel moteur : on
    ne lui demande pas son point de prise — on regarde où il change d'avis.
    """

    def _cashes(p: float) -> bool:
        return decide(make(p), owner, efficiency, state=state).action in (
            CubeAction.DOUBLE_PASS,
            CubeAction.TOO_GOOD,
        )

    return frontier(_cashes)


def swept_take_point(
    efficiency: float,
    owner: CubeOwner = CubeOwner.CENTRED,
    state: MatchState | None = None,
    make: Callable[[float], Evaluation] = gammonless,
) -> float:
    """Le point de prise **observé**, par le complément du point de caisse.

    `TP = 1 − CP` n'est vrai que dans la famille symétrique sans gammon, où les
    deux camps voient la même structure — c'est le domaine de `gammonless`, et
    c'est le seul où ce dépôt dispose d'une référence exacte. Hors de lui, le
    complément n'est pas une identité et cet extracteur ne s'emploie pas.
    """
    return 1.0 - swept_cash_point(efficiency, owner, state, make)


def swept_double_point(
    efficiency: float,
    owner: CubeOwner = CubeOwner.CENTRED,
    state: MatchState | None = None,
    make: Callable[[float], Evaluation] = gammonless,
) -> float:
    """Le `p` où le moteur se met à doubler — la borne basse de la fenêtre."""

    def _doubles(p: float) -> bool:
        return decide(make(p), owner, efficiency, state=state).action != CubeAction.NO_DOUBLE

    return frontier(_doubles)


def analytic_cash_point(
    efficiency: float, make: Callable[[float], Evaluation] = gammonless
) -> float:
    """La forme fermée `CP(x)`, pour confronter le balayage — `gn_cube_take_point`."""
    return CubeInputs.from_evaluation(make(0.5)).take_point(CubeOwner.OWNED, efficiency)


def analytic_take_point(
    efficiency: float, make: Callable[[float], Evaluation] = gammonless
) -> float:
    """La forme fermée `TP(x)`. À x = 0 elle vaut 0,25, à x = 1 elle vaut 0,20 —
    les deux valeurs de manuel de Janowski (1993), et le premier contrôle à
    passer."""
    return CubeInputs.from_evaluation(make(0.5)).take_point(
        CubeOwner.OPPONENT, efficiency
    )


# ── Les propriétés, en tests plutôt qu'en échantillons ───────────────


@dataclass(frozen=True)
class PropertyCheck:
    """Le résultat d'une propriété : verte ou non, avec son pire écart nommé."""

    name: str
    passed: bool
    worst_case: str
    worst_error: float
    tolerance: float

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "worst_case": self.worst_case,
            "worst_error": self.worst_error,
            "tolerance": self.tolerance,
        }


def check_antisymmetry(
    table: dict[tuple[int, int], float], tolerance: float = 1e-9
) -> PropertyCheck:
    """`MWC(a, b) + MWC(b, a) = 1`. Ce que je gagne, l'autre le perd."""
    worst_key, worst = ("", 0.0)
    for (a, b), value in table.items():
        mirror = table.get((b, a))
        if mirror is None:
            continue
        error = abs(value + mirror - 1.0)
        if error > worst:
            worst_key, worst = f"{a}-away/{b}-away", error
    return PropertyCheck("antisymétrie", worst <= tolerance, worst_key, worst, tolerance)


def check_monotonicity(
    table: dict[tuple[int, int], float], tolerance: float = 1e-9
) -> PropertyCheck:
    """S'éloigner du but ne peut pas aider : `MWC(a+1, b) ≤ MWC(a, b)`, et
    l'adversaire qui s'en éloigne ne peut pas me nuire."""
    worst_key, worst = ("", 0.0)
    for (a, b), value in table.items():
        further = table.get((a + 1, b))
        if further is not None:
            error = further - value
            if error > worst:
                worst_key, worst = f"{a}→{a+1}-away contre {b}-away", error
        opponent_further = table.get((a, b + 1))
        if opponent_further is not None:
            error = value - opponent_further
            if error > worst:
                worst_key, worst = f"{a}-away contre {b}→{b+1}-away", error
    return PropertyCheck("monotonies", worst <= tolerance, worst_key, worst, tolerance)


def check_dmp(
    mwc: Callable[[MatchState, Evaluation], float], tolerance: float = 1e-9
) -> PropertyCheck:
    """À 1-away/1-away, les gammons ne valent rien : seule `P(gain)` compte.

    Une ancre **exacte**, et gratuite. Deux distributions de même `P(gain)` et
    de gammons opposés doivent rendre la même MWC.
    """
    state = MatchState(1, 1, cube=1)
    worst_key, worst = ("", 0.0)
    for win in (0.20, 0.35, 0.50, 0.65, 0.80):
        plain = Evaluation(win, 0.0, 0.0, 0.0, 0.0)
        gammons = Evaluation(win, win * 0.6, win * 0.1, (1 - win) * 0.6, (1 - win) * 0.1)
        error = abs(mwc(state, plain) - mwc(state, gammons))
        if error > worst:
            worst_key, worst = f"P(gain) = {win}", error
    return PropertyCheck(
        "identité DMP", worst <= tolerance, worst_key, worst, tolerance
    )


def check_pivot(
    table: dict[tuple[int, int], float], tolerance: float = 0.005
) -> PropertyCheck:
    """Le pivot -2/-1 Crawford, le repère public de toute MET.

    C'est la cellule sur laquelle les tables modernes se comparent :
    Rockwell-Kazaross y donne **32,31 %** pour le poursuivant, valeur vérifiée
    par plusieurs rollouts indépendants (DS-08 §B.2). Une table qui s'en écarte
    de plus de la tolérance n'est pas une table moderne — ou l'extracteur s'est
    trompé de convention, ce qui est le défaut que ce contrôle attrape.
    """
    value = table.get((2, 1))
    if value is None:
        raise ValueError("la table ne porte pas la cellule 2-away/1-away")
    error = abs(value - PIVOT_TRAILER_MWC)
    return PropertyCheck(
        "pivot -2/-1 Crawford", error <= tolerance, f"lu {value:.4f}", error, tolerance
    )


def post_crawford_row(max_away: int = MAX_AWAY) -> dict[int, float]:
    """La ligne post-Crawford, vue du **poursuivant**."""
    return {a: met_module.post_crawford(a) for a in range(1, max_away + 1)}


def check_free_drop(row: dict[int, float], tolerance: float = 0.0) -> PropertyCheck:
    """Le *free drop* laisse une signature de **parité** dans la ligne
    post-Crawford, et c'est elle qu'on vérifie.

    Le free drop n'existe que quand le poursuivant est à un nombre **pair** de
    points : le meneur peut alors refuser une partie sans rien risquer. Sa
    trace n'est pas une valeur, c'est un rythme — passer d'un `away` impair au
    pair suivant coûte peu au poursuivant, passer du pair à l'impair suivant
    lui coûte beaucoup. La ligne mesurée le dit sans ambiguïté :
    1→2 coûte 0,0120, 2→3 coûte 0,1654.

    La fiche T82 exige que le modèle appris **trouve** le free drop plutôt
    qu'on le lui injecte. Ce contrôle établit que le repère existe dans la pile
    classique — sans quoi on ne saurait pas reconnaître un modèle qui le rate.
    """
    worst_key, worst = ("", 0.0)
    passed = True
    for a in range(2, max(row), 2):
        if a - 1 not in row or a + 1 not in row:
            continue
        drop_to_even = row[a - 1] - row[a]
        drop_to_odd = row[a] - row[a + 1]
        margin = drop_to_odd - drop_to_even
        if margin <= tolerance:
            passed = False
            if abs(margin) > worst:
                worst_key, worst = (
                    f"{a}-away : {drop_to_even:+.4f} puis {drop_to_odd:+.4f}",
                    abs(margin),
                )
    return PropertyCheck(
        "signature de parité du free drop",
        passed,
        worst_key or "rythme pair/impair présent partout",
        worst,
        tolerance,
    )


def all_properties(
    table: dict[tuple[int, int], float],
    mwc: Callable[[MatchState, Evaluation], float],
    post_row: dict[int, float] | None = None,
) -> list[PropertyCheck]:
    """La batterie complète, dans l'ordre où un échec est le plus parlant."""
    checks = [
        check_antisymmetry(table),
        check_monotonicity(table),
        check_dmp(mwc),
    ]
    if post_row is not None:
        checks.append(check_pivot(table))
        checks.append(check_free_drop(post_row))
    return checks
