"""T38 — les bases de fin de partie de GNU Backgammon, lues telles quelles.

`CLAUDE.md` autorise les tables de fin de partie **quelle que soit leur
origine** : ce sont un calcul exact reproductible, pas une œuvre de création.
Deux implémentations correctes produisent le même fichier, et `makebearoff` les
régénère.

## Ce que ce module lit — et ce qu'il ne lit pas

**La base bilatérale** (`gnubg-TS`) donne, pour chaque couple de positions de
bearoff, l'équité **exacte**, cubeless *et cubeful*. C'est la pièce qui manquait
au videau en course : une décision de videau en fin de course se joue sur des
marges où l'approximation du réseau est la plus grossière, et une table
bilatérale y répond sans modèle intermédiaire.

**La base unilatérale** (`gnubg-OS`) n'est pas lue ici. Son format est comprimé
et indexé, et le dépôt a déjà sa propre table unilatérale — calculée en T33,
croisée contre celle de gnubg, et vérifiée optimale à `7,1e-15` de la valeur de
Bellman. Écrire un second lecteur pour obtenir ce qu'on sait déjà calculer
serait une seconde chose capable de se tromper.

## Comment le format a été établi — sans lire une ligne de code de gnubg

Le protocole de `docs/etudes/` réserve la lecture du code source au dernier
recours. Elle n'a pas été nécessaire :

1. **L'arithmétique du fichier donne la structure.** `1 225 323 048` octets
   moins les 40 de l'en-tête font **exactement** `12 376 x 12 376 x 8`.
2. **L'en-tête est en clair** : `gnubg-TS-06-11-1`, complété de `x` — six
   points, onze pions.
3. **`bearoffdump`, outil documenté et livré avec gnubg**, donne la réponse
   attendue pour n'importe quel index. Il rend « Position 8 / 992 » pour
   l'index 100 000, et `8 x 12376 + 992 = 100000` : l'indexation est confirmée,
   pas supposée.
4. **L'échelle des entiers a été ajustée** sur des positions dont
   `bearoffdump` donne l'équité, et les quatre colonnes concordent.
5. **L'indexation des positions a été validée exhaustivement** : la formule
   ci-dessous rend l'indice de GNU Backgammon sur les **12 376 positions**, sans
   une exception.

`C(6 + 11, 6) = 12 376` : le compte lui-même dit que l'indexation est un rang
combinatoire, une construction mathématique et non une expression protégeable.

## Le repli, qui est le vrai piège de cette tâche

Une position hors table qui recevrait silencieusement une valeur voisine
produirait une équité plausible et fausse — le mode de défaillance que ce projet
traque. `contains` est donc un **prédicat testé**, et `equity` lève plutôt que
d'extrapoler. La table répond, ou elle dit qu'elle ne sait pas.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from math import comb
from pathlib import Path

from .rules import BLACK, NUM_POINTS, WHITE, Position

#: Longueur de l'en-tête ASCII, en octets. Établi par l'arithmétique du fichier.
HEADER_BYTES = 40

#: Quatre entiers de 16 bits non signés, petit-boutiens, par couple de positions.
ENTRY = struct.Struct("<4H")


def bearoff_index(side: tuple[int, ...] | list[int], points: int) -> int:
    """Le rang combinatoire d'une répartition de pions, à la façon de gnubg.

    `side[i]` est le nombre de pions sur le point `i + 1` (le point 1 étant
    celui d'où l'on sort en un pip).

    L'ordre, **déduit de gnubg et vérifié sur les 12 376 positions** : d'abord
    par nombre total de pions croissant, puis lexicographique **décroissant** à
    total égal. Le décalage entre totaux est l'identité du bâton de hockey,
    `sum_{s<t} C(s+p-1, p-1) = C(t+p-1, p)`.
    """
    total = sum(side)
    index = comb(total + points - 1, points)

    remaining = total
    for i in range(points):
        left = points - i - 1
        # Tout ce qui, à ce point, porte plus de pions vient avant.
        for value in range(side[i] + 1, remaining + 1):
            rest = remaining - value
            if left:
                index += comb(rest + left - 1, left - 1)
            elif rest == 0:
                index += 1
        remaining -= side[i]
    return index


@dataclass(frozen=True)
class ExactEquity:
    """L'équité exacte d'une position de bearoff, vue par le joueur au trait.

    Les quatre valeurs sont celles que `bearoffdump` nomme, dans son ordre.
    `cubeless` est l'équité sans videau ; les trois autres sont les équités
    **cubeful** selon qui possède le videau.
    """

    cubeless: float
    owned: float
    centered: float
    opponent_owns: float


class TwoSidedBearoff:
    """La base bilatérale, ouverte en lecture paresseuse.

    Le fichier fait 1,2 Gio. Il n'est ni chargé ni mappé en entier : chaque
    consultation est un `seek` de huit octets. Le noyau met en cache ce qui
    sert, et une mesure qui ne touche qu'une petite partie du domaine ne paie
    pas le reste.

    **Ce n'est pas un artefact distribuable.** 1,2 Gio ne partent pas dans un
    navigateur. C'est un actif natif et de mesure ; la table embarquée reste
    celle que T33 calcule, et cette base est la référence contre laquelle elle
    se mesure.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        with self.path.open("rb") as handle:
            header = handle.read(HEADER_BYTES)

        text = header.decode("ascii", "replace").rstrip("x\n\x00 ")
        parts = text.split("-")
        if len(parts) < 4 or parts[0] != "gnubg" or parts[1] != "TS":
            raise ValueError(f"{self.path} n'est pas une base bilatérale gnubg : {text!r}")

        self.points = int(parts[2])
        self.chequers = int(parts[3])
        self.positions = comb(self.points + self.chequers, self.points)

        expected = HEADER_BYTES + self.positions * self.positions * ENTRY.size
        actual = self.path.stat().st_size
        if actual != expected:
            # Un fichier dont la taille ne correspond pas à son en-tête serait lu
            # de travers d'un bout à l'autre, en rendant des équités plausibles.
            raise ValueError(
                f"{self.path} : {actual} octets, {expected} attendus pour "
                f"{self.points} points et {self.chequers} pions"
            )

        self._handle = self.path.open("rb")

    # ── Appartenance ────────────────────────────────────────────────

    def contains(self, position: Position) -> bool:
        """La table connaît-elle cette position ? Un prédicat, jamais une hypothèse.

        Les deux camps doivent avoir tous leurs pions restants dans leurs
        `points` premiers points, aucun sur la barre, et au plus `chequers`
        pions chacun. Une position qui échoue ici est renvoyée au réseau — elle
        n'est **pas** approximée par une voisine.
        """
        if position.is_over():
            return False
        if position.bar[WHITE] or position.bar[BLACK]:
            return False
        sides = self._sides(position)
        if sides is None:
            return False
        white, black = sides
        return sum(white) <= self.chequers and sum(black) <= self.chequers

    def _sides(self, position: Position) -> tuple[list[int], list[int]] | None:
        """Les deux camps, chacun dans sa propre orientation, ou `None` hors domaine.

        `white[i]` est le nombre de pions blancs sur le point d'où il faut `i+1`
        pips pour sortir, et de même pour Noir depuis son côté. Les deux
        tableaux décrivent des points **physiquement opposés** — c'est la
        convention de gnubg, et la confondre retournerait la table sans rien
        casser ni rien signaler.
        """
        white = [0] * self.points
        black = [0] * self.points
        for i in range(NUM_POINTS):
            n = position.points[i]
            if n > 0:
                if i >= self.points:
                    return None
                white[i] += n
            elif n < 0:
                j = NUM_POINTS - 1 - i
                if j >= self.points:
                    return None
                black[j] += -n
        return white, black

    # ── Consultation ────────────────────────────────────────────────

    def raw(self, player_index: int, opponent_index: int) -> tuple[int, ...]:
        offset = HEADER_BYTES + (player_index * self.positions + opponent_index) * ENTRY.size
        self._handle.seek(offset)
        return ENTRY.unpack(self._handle.read(ENTRY.size))

    def equity(self, position: Position) -> ExactEquity:
        """L'équité exacte, du point de vue de `position.turn`.

        Lève si la position n'est pas dans la table. **Refusé, jamais
        approximé** : une valeur voisine rendue en silence serait exactement le
        mode de défaillance que `CLAUDE.md` proscrit.
        """
        if not self.contains(position):
            raise KeyError(f"hors de la table {self.points}x{self.chequers} : {position!r}")

        white, black = self._sides(position)
        mine, theirs = (white, black) if position.turn == WHITE else (black, white)

        raw = self.raw(bearoff_index(mine, self.points),
                       bearoff_index(theirs, self.points))
        # Échelle établie contre `bearoffdump` : [0, 65535] -> [-1, +1].
        values = [value / 65535.0 * 2.0 - 1.0 for value in raw]
        return ExactEquity(*values)

    def close(self):
        self._handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ── Le lecteur C, et pourquoi il est lié ici ─────────────────────────
#
# Le C est ce qui tourne dans la recherche ; ce module Python est la référence
# lisible. Les deux existent, donc les deux peuvent diverger — et une divergence
# ne se verrait nulle part, puisque chacun rendrait un nombre parfaitement
# plausible. Les exposer côte à côte est ce qui rend le croisement possible.

import ctypes as _ctypes

from .infer import NUM_OUTPUTS as _NUM_OUTPUTS
from .rules import _LIB, _CPosition

_LIB.gn_bearoff_open.argtypes = [_ctypes.c_char_p]
_LIB.gn_bearoff_open.restype = _ctypes.c_void_p
_LIB.gn_bearoff_close.argtypes = [_ctypes.c_void_p]
_LIB.gn_bearoff_close.restype = None
_LIB.gn_bearoff_contains.argtypes = [_ctypes.c_void_p, _ctypes.POINTER(_CPosition)]
_LIB.gn_bearoff_contains.restype = _ctypes.c_int
_LIB.gn_bearoff_equities.argtypes = [_ctypes.c_void_p, _ctypes.POINTER(_CPosition),
                                     _ctypes.POINTER(_ctypes.c_double)]
_LIB.gn_bearoff_equities.restype = _ctypes.c_int
_LIB.gn_bearoff_probs.argtypes = [_ctypes.c_void_p, _ctypes.POINTER(_CPosition),
                                  _ctypes.POINTER(_ctypes.c_float)]
_LIB.gn_bearoff_probs.restype = _ctypes.c_int
_LIB.gn_bearoff_index.argtypes = [_ctypes.POINTER(_ctypes.c_int), _ctypes.c_int]
_LIB.gn_bearoff_index.restype = _ctypes.c_long


class NativeBearoff:
    """Le lecteur C, tel que la recherche l'emploie."""

    def __init__(self, path):
        self._handle = _LIB.gn_bearoff_open(str(path).encode())
        if not self._handle:
            raise ValueError(f"gn_bearoff_open a refusé {path}")

    def contains(self, position) -> bool:
        return bool(_LIB.gn_bearoff_contains(self._handle,
                                             _ctypes.byref(position._to_c())))

    def equities(self, position):
        buffer = (_ctypes.c_double * 4)()
        if not _LIB.gn_bearoff_equities(self._handle,
                                        _ctypes.byref(position._to_c()), buffer):
            return None
        return ExactEquity(*buffer)

    def probs(self, position):
        buffer = (_ctypes.c_float * _NUM_OUTPUTS)()
        if not _LIB.gn_bearoff_probs(self._handle,
                                     _ctypes.byref(position._to_c()), buffer):
            return None
        return tuple(buffer)

    @staticmethod
    def index(side, points):
        array = (_ctypes.c_int * len(side))(*side)
        return _LIB.gn_bearoff_index(array, points)

    def close(self):
        if self._handle:
            _LIB.gn_bearoff_close(self._handle)
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ── La table partagée (T38) ───────────────────────────────────────────
#
# `gn_search.c` et `gn_choose.c` consultent un pointeur de module unique
# (`gn_bearoff_set_shared`) plutôt qu'une table passée explicitement à chaque
# appel. Côté Python, ce module garde la `NativeBearoff` correspondante en vie
# dans une variable de module : le pointeur C que `set_shared` installe est un
# pointeur vers la base mappée, et si l'objet Python était collecté, `close()`
# démapperait le fichier sous les pieds de la recherche sans que rien ne le
# signale.

_LIB.gn_bearoff_set_shared.argtypes = [_ctypes.c_void_p]
_LIB.gn_bearoff_set_shared.restype = None
_LIB.gn_bearoff_shared_hits.argtypes = []
_LIB.gn_bearoff_shared_hits.restype = _ctypes.c_ulong
_LIB.gn_bearoff_shared_reset_hits.argtypes = []
_LIB.gn_bearoff_shared_reset_hits.restype = None

_shared: NativeBearoff | None = None


def use_shared(path) -> NativeBearoff:
    """Ouvre `path` et le branche comme table de la recherche.

    La table reste ouverte tant que `disable_shared()` (ou un nouvel appel à
    `use_shared`) ne la remplace pas -- c'est ce module qui la garde en vie.
    Sans cet appel, `gn_bearoff_shared()` reste NULL côté C et la recherche se
    comporte exactement comme avant T38.
    """
    global _shared
    table = NativeBearoff(path)
    _shared = table
    _LIB.gn_bearoff_set_shared(table._handle)
    return table


def disable_shared() -> None:
    """Débranche la table et referme celle que `use_shared` avait ouverte."""
    global _shared
    _LIB.gn_bearoff_set_shared(None)
    if _shared is not None:
        _shared.close()
        _shared = None


def shared_hits() -> int:
    """Nombre de feuilles servies par la table depuis la dernière remise à zéro."""
    return _LIB.gn_bearoff_shared_hits()


def reset_shared_hits() -> None:
    _LIB.gn_bearoff_shared_reset_hits()
