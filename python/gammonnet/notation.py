"""ctypes binding for the move notation: `gn_play_notation`.

Le C est l'autorité, comme pour le codec. Ce fichier n'écrit PAS une notation :
il appelle celle de `src/gn_notation.c`.

Pourquoi ce détour existe. La notation vivait dans `tools/serve.py`
(`format_play`), et le module WebAssembly n'en avait aucune — d'où une
troisième écriture, par différence de plateaux, chez un consommateur, dont
l'auteur documente lui-même qu'elle peut afficher un appariement que la
recherche n'a pas choisi (T86). Le remède n'était pas d'en ajouter une
quatrième : le C l'a maintenant, les deux surfaces publiées l'appellent, et
`tests/test_notation.py` tient l'égalité avec ce que le serveur rendait.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import ctypes

from .rules import _LIB, BLACK, WHITE, Play, _CMove, _CPlay

_NOTATION_LENGTH = 40

_LIB.gn_play_notation.argtypes = [
    ctypes.POINTER(_CPlay),
    ctypes.c_int,
    ctypes.c_char_p,
]
_LIB.gn_play_notation.restype = ctypes.c_int


def play_notation(play: Play, mover: int) -> str:
    """La notation d'un jeu, vue par `mover` — par exemple ``24/18 13/11(2)``.

    Les sous-coups identiques sont regroupés dans l'ordre de leur PREMIÈRE
    apparition, qui est celui que la recherche a produit. Un jeu vide rend la
    chaîne vide : la position où rien n'est jouable existe, et c'est une
    réponse.

    Lève `ValueError` sur un jeu ou un joueur que le C refuse — jamais une
    chaîne approchée.
    """
    if mover not in (WHITE, BLACK):
        raise ValueError(f"joueur inconnu : {mover}")

    c = _CPlay()
    c.num_moves = len(play.moves)
    for i, move in enumerate(play.moves):
        c.moves[i] = _CMove(move.from_, move.to)

    buffer = ctypes.create_string_buffer(_NOTATION_LENGTH)
    if _LIB.gn_play_notation(ctypes.byref(c), mover, buffer) != 0:
        raise ValueError("jeu refusé par gn_play_notation")
    return buffer.value.decode("ascii")
