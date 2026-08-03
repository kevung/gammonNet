"""gammonNet — un évaluateur de positions de backgammon.

Ce dépôt évalue une position. Il ne connaît pas ses appelants : aucune notion
d'utilisateur, de compte, de session ni de persistance n'y entre. Une position
entre, une évaluation sort.

Ce paquet est la face Python de la bibliothèque — l'entraînement et la mesure.
Le calcul lui-même vit en C, dans `src/`.
"""

from .rules import BAR, BLACK, NUM_CHECKERS, NUM_POINTS, OFF, WHITE, Move, Play, Position

__all__ = [
    "BAR",
    "BLACK",
    "Move",
    "NUM_CHECKERS",
    "NUM_POINTS",
    "OFF",
    "Play",
    "Position",
    "WHITE",
]
