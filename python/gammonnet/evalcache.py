"""ctypes binding for `src/gn_evalcache.h` — le cache d'évaluation (T3A).

Le C fait autorité : rien n'est réimplémenté ici. Ce module gère seulement le
cycle de vie du cache partagé de module — le pendant Python de
`gn_evalcache_set_shared` — sur le modèle de `python/gammonnet/bearoff.py` et
de sa table bilatérale partagée.

**Le cache ne change aucun résultat, seulement son coût.** `gn_evalcache.h`
explique pourquoi la clé peut être la position seule : `evaluate_position`
(le point d'accroche unique de T38 dans `gn_search.c`) rend une distribution
brute, indépendante du score et du videau, qui n'entrent qu'ensuite. Un hit
rend exactement les cinq flottants qu'un miss aurait calculés — c'est ce que
`tests/test_evalcache.py` vérifie au bit près, pas ce que ce module suppose.
"""

from __future__ import annotations

import ctypes as _ctypes
from dataclasses import dataclass

from .rules import _LIB

_LIB.gn_evalcache_create.argtypes = [_ctypes.c_uint]
_LIB.gn_evalcache_create.restype = _ctypes.c_void_p
_LIB.gn_evalcache_free.argtypes = [_ctypes.c_void_p]
_LIB.gn_evalcache_free.restype = None
_LIB.gn_evalcache_hits.argtypes = [_ctypes.c_void_p]
_LIB.gn_evalcache_hits.restype = _ctypes.c_ulong
_LIB.gn_evalcache_misses.argtypes = [_ctypes.c_void_p]
_LIB.gn_evalcache_misses.restype = _ctypes.c_ulong
_LIB.gn_evalcache_stores.argtypes = [_ctypes.c_void_p]
_LIB.gn_evalcache_stores.restype = _ctypes.c_ulong
_LIB.gn_evalcache_reset_counters.argtypes = [_ctypes.c_void_p]
_LIB.gn_evalcache_reset_counters.restype = None
_LIB.gn_evalcache_capacity.argtypes = [_ctypes.c_void_p]
_LIB.gn_evalcache_capacity.restype = _ctypes.c_ulong
_LIB.gn_evalcache_set_shared.argtypes = [_ctypes.c_void_p]
_LIB.gn_evalcache_set_shared.restype = None
_LIB.gn_evalcache_shared.argtypes = []
_LIB.gn_evalcache_shared.restype = _ctypes.c_void_p

#: 2**19 entrées, ~24 Mio — le défaut de `gn_evalcache.h`
#: (`GN_EVALCACHE_DEFAULT_LOG2`), répété ici plutôt que lu dynamiquement : une
#: constante C n'est pas exportée par la bibliothèque partagée, et un chiffre
#: recopié une fois vaut mieux qu'un `ctypes` de plus pour le lire.
DEFAULT_LOG2_ENTRIES = 19


@dataclass(frozen=True)
class CacheStats:
    """Les trois compteurs de `gn_evalcache.h`, à l'instant de l'appel."""

    hits: int
    misses: int
    stores: int
    capacity: int

    @property
    def hit_rate(self) -> float:
        """Hits / (hits + misses), 0.0 si aucune consultation n'a eu lieu."""
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


# ── Le cache partagé de module ─────────────────────────────────────────
#
# Comme `python/gammonnet/bearoff.py` le fait pour la table bilatérale : ce
# module garde vivante la poignée C que `gn_evalcache_set_shared` installe.
# Si cette variable était perdue (l'objet collecté, par exemple), il n'y
# aurait plus aucun moyen de libérer la mémoire native ni de savoir qu'un
# cache est actif -- `gn_evalcache_shared()` répondrait toujours quelque
# chose côté C, mais ce module n'en saurait plus rien côté Python.

_shared: int | None = None


def enable(log2_entries: int = DEFAULT_LOG2_ENTRIES) -> None:
    """Crée un cache de `2**log2_entries` entrées et le branche sur la recherche.

    Remplace un cache déjà actif -- l'ancien est libéré, pas fui. Sans appel à
    cette fonction, `gn_evalcache_shared()` reste `NULL` côté C et la
    recherche se comporte exactement comme avant T3A : c'est le garde-fou que
    `tests/test_evalcache.py` vérifie en premier.
    """
    global _shared
    handle = _LIB.gn_evalcache_create(log2_entries)
    if not handle:
        raise ValueError(f"gn_evalcache_create a refusé log2_entries={log2_entries}")
    disable()
    _shared = handle
    _LIB.gn_evalcache_set_shared(handle)


def disable() -> None:
    """Débranche le cache et libère celui que `enable()` avait créé.

    Un appel sans cache actif ne fait rien -- symétrique de
    `gammonnet.bearoff.disable_shared`.
    """
    global _shared
    _LIB.gn_evalcache_set_shared(None)
    if _shared is not None:
        _LIB.gn_evalcache_free(_shared)
        _shared = None


def clear(log2_entries: int | None = None) -> None:
    """Vide le cache en le recréant -- une table à adressage ouvert n'a pas
    d'autre façon de « tout oublier » qu'un nouveau tableau.

    Garde la taille actuelle si `log2_entries` n'est pas donné. Lève si aucun
    cache n'est actif : vider un cache qui n'existe pas serait un appelant qui
    s'est trompé d'ordre, pas un no-op silencieux.
    """
    if _shared is None:
        raise ValueError("clear() appelé sans cache actif -- voir enable()")
    size = log2_entries
    if size is None:
        # La capacité est une puissance de deux par construction (gn_evalcache.h) ;
        # bit_length() - 1 en est le logarithme en base deux exact.
        size = _LIB.gn_evalcache_capacity(_shared).bit_length() - 1
    enable(size)


def stats() -> CacheStats:
    """Les compteurs du cache actif. Lève si aucun cache n'est branché."""
    if _shared is None:
        raise ValueError("stats() appelé sans cache actif -- voir enable()")
    return CacheStats(
        hits=_LIB.gn_evalcache_hits(_shared),
        misses=_LIB.gn_evalcache_misses(_shared),
        stores=_LIB.gn_evalcache_stores(_shared),
        capacity=_LIB.gn_evalcache_capacity(_shared),
    )


def reset_counters() -> None:
    """Remet hits/misses/stores à zéro sans vider la table elle-même.

    Un appel sans cache actif ne fait rien.
    """
    if _shared is not None:
        _LIB.gn_evalcache_reset_counters(_shared)


def is_enabled() -> bool:
    """Un cache est-il actuellement branché sur la recherche ?"""
    return _shared is not None
