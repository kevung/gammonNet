"""ctypes binding for `src/gn_met.h` — équité de match.

Le C fait autorité. Le réseau est *cubeless* et aveugle au score : il sort cinq
probabilités, et c'est **ici** que le score et le videau entrent. Voir
`BRIEF.md` §6.

**Ce module est la raison d'être de `Evaluation`.** Un scalaire d'équité money a
déjà perdu ce dont une équité de match a besoin : à 2-away/4-away un gammon
gagne souvent le match, alors qu'en money il vaut deux points comme un autre.
"""

from __future__ import annotations

import ctypes
import struct
from dataclasses import dataclass

from .infer import NUM_OUTPUTS, Evaluation, _ProbArray
from .rules import _LIB

MAX_AWAY = 25


class _CMatchState(ctypes.Structure):
    _fields_ = [
        ("away_on_roll", ctypes.c_int),
        ("away_opponent", ctypes.c_int),
        ("cube", ctypes.c_int),
        ("crawford", ctypes.c_int),
    ]


_LIB.gn_met_pre.argtypes = [ctypes.c_int, ctypes.c_int]
_LIB.gn_met_pre.restype = ctypes.c_double

_LIB.gn_met_post.argtypes = [ctypes.c_int]
_LIB.gn_met_post.restype = ctypes.c_double

_LIB.gn_match_state_is_valid.argtypes = [ctypes.POINTER(_CMatchState)]
_LIB.gn_match_state_is_valid.restype = ctypes.c_int

_LIB.gn_met_after.argtypes = [ctypes.POINTER(_CMatchState), ctypes.c_int, ctypes.c_int]
_LIB.gn_met_after.restype = ctypes.c_double

for _name in ("gn_match_winning_chance", "gn_match_equity"):
    _fn = getattr(_LIB, _name)
    _fn.argtypes = [ctypes.POINTER(_CMatchState), ctypes.POINTER(ctypes.c_float)]
    _fn.restype = ctypes.c_double


@dataclass(frozen=True)
class MatchState:
    """L'état du match, du point de vue du joueur au trait.

    `away` = les points qu'il reste à marquer. 1 signifie « à la balle de
    match ». Un joueur à 0 a déjà gagné, et il n'y a plus rien à évaluer.
    """

    away_on_roll: int
    away_opponent: int
    cube: int = 1
    crawford: bool = False

    def _to_c(self) -> _CMatchState:
        return _CMatchState(
            self.away_on_roll, self.away_opponent, self.cube, int(self.crawford)
        )

    @property
    def is_valid(self) -> bool:
        return bool(_LIB.gn_match_state_is_valid(ctypes.byref(self._to_c())))

    def after(self, points: int, on_roll_wins: bool) -> float:
        """MWC du joueur au trait si la partie rapporte `points` à un camp."""
        value = _LIB.gn_met_after(
            ctypes.byref(self._to_c()), points, int(on_roll_wins)
        )
        if value < 0.0:
            raise ValueError(f"état de match non évaluable : {self}")
        return value

    def winning_chance(self, evaluation: Evaluation) -> float:
        """La conversion : cinq probabilités → chance de gagner le match."""
        buffer = _ProbArray(*evaluation.as_tuple())
        value = _LIB.gn_match_winning_chance(ctypes.byref(self._to_c()), buffer)
        if value < 0.0:
            raise ValueError(f"état de match non évaluable : {self}")
        return value

    def equity(self, evaluation: Evaluation) -> float:
        """`2 × MWC − 1` — l'échelle « équivalent money » que les moteurs affichent."""
        return 2.0 * self.winning_chance(evaluation) - 1.0


def pre_crawford(away_a: int, away_b: int) -> float:
    """MWC du joueur à `away_a` contre un adversaire à `away_b`."""
    value = _LIB.gn_met_pre(away_a, away_b)
    if value < 0.0:
        raise ValueError(f"hors table : {away_a}-away contre {away_b}-away")
    return value


def post_crawford(away_trailer: int) -> float:
    """MWC du **poursuivant**, le meneur étant à 1-away."""
    value = _LIB.gn_met_post(away_trailer)
    if value < 0.0:
        raise ValueError(f"hors table : poursuivant à {away_trailer}-away")
    return value


# ── Changer de table ─────────────────────────────────────────────────
#
# La table compilée est celle de Kazaross ; elle sert par défaut et rien n'a
# besoin d'être appelé pour l'obtenir. T97 en **calcule** une, et doit consulter
# les cellules qu'elle a déjà produites pendant qu'elle produit les suivantes —
# d'où ces fonctions, et d'où `table_name()` : une mesure lancée contre une
# table que personne ne sait nommer après coup n'est pas une mesure.

_MAGIC = b"GNMET1\x00\x00"
_NAME_MAX = 64

_LIB.gn_met_load.argtypes = [ctypes.c_char_p]
_LIB.gn_met_load.restype = ctypes.c_int

_LIB.gn_met_set.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_int,
                            ctypes.POINTER(ctypes.c_double), ctypes.c_int,
                            ctypes.c_char_p]
_LIB.gn_met_set.restype = ctypes.c_int

_LIB.gn_met_reset.argtypes = []
_LIB.gn_met_reset.restype = None

_LIB.gn_met_name.argtypes = []
_LIB.gn_met_name.restype = ctypes.c_char_p

#: Ce que le C refuse — le message porte la raison, jamais le code de retour.
_REFUSALS = {
    -1: "fichier introuvable ou illisible",
    -2: "dimensions différentes de celles que ce build sait lire",
    -3: "une valeur hors de [0, 1] : ce n'est pas une chance de gain",
    -4: "fichier tronqué",
    -5: "ce n'est pas un fichier GNMET1",
}


def _refuse(status: int, what) -> None:
    raise ValueError(f"{what} refusé — {_REFUSALS.get(status, f'code {status}')}")


def table_name() -> str:
    """Le nom de la table active. Jamais vide."""
    return _LIB.gn_met_name().decode()


def load_table(path) -> str:
    """Installer la table du fichier `GNMET1`. Rend son nom."""
    global _ACTIVE_KEY
    _ACTIVE_KEY = _UNKNOWN
    status = _LIB.gn_met_load(str(path).encode())
    if status != 0:
        _refuse(status, path)
    return table_name()


def set_table(pre, post, name: str) -> None:
    """Installer une table tenue en mémoire — `pre[a-1][b-1]`, `post[n-1]`."""
    global _ACTIVE_KEY
    _ACTIVE_KEY = _UNKNOWN
    flat = [value for row in pre for value in row]
    if len(flat) != MAX_AWAY * MAX_AWAY or len(post) != MAX_AWAY:
        raise ValueError(f"table de {len(flat)} et {len(post)} valeurs : "
                         f"{MAX_AWAY * MAX_AWAY} et {MAX_AWAY} attendues")
    c_pre = (ctypes.c_double * len(flat))(*flat)
    c_post = (ctypes.c_double * len(post))(*post)
    status = _LIB.gn_met_set(c_pre, MAX_AWAY, c_post, MAX_AWAY, name.encode())
    if status != 0:
        _refuse(status, name)


def reset_table() -> None:
    """Revenir à la table compilée."""
    global _ACTIVE_KEY
    _ACTIVE_KEY = _UNKNOWN
    _LIB.gn_met_reset()


#: Ce que `use_table` croit servir : un chemin, `None` pour la table compilée,
#: ou `_UNKNOWN` quand quelqu'un d'autre a changé la table. **Les trois états
#: sont distincts, et c'est le point** : confondre « la compilée » et « je ne
#: sais pas » ferait sauter le raccourci au mauvais moment, et `use_table("")`
#: laisserait en place une table posée à la main.
_UNKNOWN = object()
_ACTIVE_KEY = _UNKNOWN
_CACHE: dict[str, tuple[list, list, str]] = {}


def use_table(path) -> None:
    """S'assurer que la table de `path` est celle qui sert. `""` → la compilée.

    **Ce que cette fonction rend possible.** La table active est un état global
    du processus, et une campagne à dés dupliqués veut les deux joueurs dans le
    **même** processus. Un joueur qui porte sa table et l'installe avant chacune
    de ses décisions lève la contradiction : l'installation est un `memcpy` de
    5 200 octets, soit rien du tout devant une recherche.

    Le contenu du fichier est mis en cache — le relire à chaque décision
    coûterait plus cher que la décision.
    """
    global _ACTIVE_KEY
    key = str(path) if path else None
    if key == _ACTIVE_KEY:
        return
    if key is None:
        reset_table()
        _ACTIVE_KEY = None
        return
    if key not in _CACHE:
        load_table(key)
        _CACHE[key] = (*active_table(), table_name())
    pre, post, name = _CACHE[key]
    set_table(pre, post, name)
    _ACTIVE_KEY = key


def write_table(path, pre, post, name: str) -> None:
    """Écrire un fichier `GNMET1`. Le lecteur est en C ; l'écrivain est ici."""
    flat = [value for row in pre for value in row]
    if len(flat) != MAX_AWAY * MAX_AWAY or len(post) != MAX_AWAY:
        raise ValueError("table de dimensions inattendues")

    encoded = name.encode()[:_NAME_MAX - 1]
    with open(path, "wb") as handle:
        handle.write(_MAGIC)
        handle.write(struct.pack("<ii", MAX_AWAY, MAX_AWAY))
        handle.write(encoded + b"\x00" * (_NAME_MAX - len(encoded)))
        handle.write(struct.pack(f"<{len(flat)}d", *flat))
        handle.write(struct.pack(f"<{len(post)}d", *post))


def active_table() -> tuple[list[list[float]], list[float]]:
    """La table active, relue **par les accesseurs du C**.

    Relire par `gn_met_pre` plutôt que par le tampon Python est délibéré : c'est
    ce que le moteur consultera réellement. Une table qu'on croit installée et
    qui ne l'est pas est exactement le mode de défaillance silencieux que la
    règle n°2 vise.
    """
    pre = [[pre_crawford(a, b) for b in range(1, MAX_AWAY + 1)]
           for a in range(1, MAX_AWAY + 1)]
    post = [post_crawford(n) for n in range(1, MAX_AWAY + 1)]
    return pre, post
