"""La chance d'un jet, jugée par un réseau de référence fixe.

C'est la correction de T39 (`src/gn_rollout.c`, `roll_luck`), portée aux
tête-à-tête. À chaque tour, la *chance* du jet tiré est l'équité 0-ply du
meilleur coup sous ce jet, moins sa moyenne pondérée sur les 21 jets — du point
de vue du joueur au trait. Sachant la position, chaque terme a une espérance
**exactement nulle**, quel que soit le réseau qui juge : le jet effectif est
l'un des termes de la moyenne. Retrancher la chance cumulée d'une partie ne
déplace donc aucune espérance, seulement la variance.

Le juge doit être **fixe** (le même pour les deux camps, à chaque tour) et
**bon marché**. Il n'a pas à être juste : un juge médiocre ne biaise rien, il
réduit moins la variance, et ça se voit dans l'intervalle.

Les 21 valeurs viennent d'une seule passe 1-ply (`search.probs_by_roll`) : la
distribution du meilleur coup pour chaque jet, choisi par l'équité money
cubeless — exactement `roll_equity` de `gn_rollout.c`, en un appel.
"""

from __future__ import annotations

from pathlib import Path

from .infer import Network
from .met import MatchState
from .rules import Position
from .search import ROLLS, SearchConfig, probs_by_roll

_ROLL_INDEX = {(a, b): r for r, (a, b, _w) in enumerate(ROLLS)}


def roll_index(d1: int, d2: int) -> int:
    """L'index du jet `(d1, d2)` dans l'ordre de `ROLLS`, sans égard à l'ordre des dés."""
    lo, hi = (d1, d2) if d1 <= d2 else (d2, d1)
    return _ROLL_INDEX[(lo, hi)]


class LuckReference:
    """Le juge de la chance : un réseau chargé une fois, pour toute une campagne."""

    def __init__(self, model: str | Path):
        self.model = str(model)
        self.network = Network.load(model)
        self._config = SearchConfig(ply=1)

    def roll_values(self, position: Position) -> tuple[list[float], list[float]]:
        """Les 21 équités du meilleur coup (point de vue du joueur au trait), et leurs poids."""
        dists, weights = probs_by_roll(self.network, position, self._config)
        return [d.money_equity for d in dists], weights

    def luck(self, position: Position, d1: int, d2: int) -> float:
        """La chance du jet `(d1, d2)` à `position`, en points money par unité de videau,
        du point de vue de `position.turn`. D'espérance nulle sachant `position`."""
        values, weights = self.roll_values(position)
        expected = sum(w * v for w, v in zip(weights, values))
        return values[roll_index(d1, d2)] - expected


def match_scale(state: MatchState) -> float:
    """Ce que vaut un point d'équité money en *victoires nettes* de match (±1), au
    videau courant, du point de vue du joueur au trait.

    Le pont de `gn_rollout.c` : gagner plutôt que perdre une partie simple au
    videau courant déplace la MWC de `win − lose` ; les victoires nettes valent
    `2·MWC − 1`, et l'équité money balaie 2 points entre ces deux issues — d'où
    `win − lose` par point. Toute échelle fixe garde la correction centrée ; une
    échelle fausse ne ferait que réduire moins la variance, visiblement.
    """
    return state.after(state.cube, True) - state.after(state.cube, False)
