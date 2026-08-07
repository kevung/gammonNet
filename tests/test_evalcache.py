"""T3A — le cache d'évaluation, et ce qu'un branchement de ce genre doit prouver.

`gn_evalcache.h` documente pourquoi la clé peut être la position seule :
`evaluate_position` (T38) rend une distribution BRUTE, indépendante du score
et du videau. Ce fichier vérifie exactement ce que `CLAUDE.md` demande d'un
branchement de ce genre :

* **le cache ne change AUCUN résultat** — coups choisis et équités sont
  identiques, au bit près, cache éteint / allumé (froid) / allumé (chaud) ;
* **les compteurs bougent comme attendu** — misses au premier passage, hits
  au second, sur la même recherche répétée ;
* **le défaut n'a pas bougé** — sans `enable()`, rien ne change ;
* **une collision de seau rend le BON résultat pour chacune** des deux
  positions en cause — la clé complète départage, jamais le seau seul.
"""

from __future__ import annotations

import ctypes
import random
from pathlib import Path

import pytest

from gammonnet import evalcache
from gammonnet.infer import NUM_OUTPUTS, Network
from gammonnet.rules import _LIB, _CPosition
from gammonnet.search import ROLLS, SearchConfig, evaluations, reset_evaluations, search_plays

ROOT = Path(__file__).resolve().parent.parent
MODEL_BIN = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"

SEED = 20260807

# Un sous-ensemble des 21 jets distincts : assez pour dépasser 300 décisions
# sur un corpus modeste, sans payer les 21 jets complets sur chaque position.
DICE = tuple((d1, d2) for d1, d2, _ in ROLLS[:8])


# ── Liaison directe des fonctions bas niveau de gn_evalcache.h ────────
#
# `python/gammonnet/evalcache.py` n'expose que le cycle de vie du cache
# PARTAGÉ (enable/disable/clear/stats) -- c'est ce que la recherche consulte.
# Le test de collision de seau, plus bas, a besoin d'un accès direct à
# `gn_evalcache_lookup` / `_store` sur une table indépendante, pour observer
# le comportement d'un seau précis sans passer par une recherche entière.
# Même logique que `test_search.py` qui lie `gn_best_play_0ply` directement.

_LIB.gn_evalcache_create.argtypes = [ctypes.c_uint]
_LIB.gn_evalcache_create.restype = ctypes.c_void_p
_LIB.gn_evalcache_free.argtypes = [ctypes.c_void_p]
_LIB.gn_evalcache_free.restype = None
_LIB.gn_evalcache_lookup.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(_CPosition), ctypes.POINTER(ctypes.c_float),
]
_LIB.gn_evalcache_lookup.restype = ctypes.c_int
_LIB.gn_evalcache_store.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(_CPosition), ctypes.POINTER(ctypes.c_float),
]
_LIB.gn_evalcache_store.restype = None
_LIB.gn_evalcache_capacity.argtypes = [ctypes.c_void_p]
_LIB.gn_evalcache_capacity.restype = ctypes.c_ulong

_ProbArray = ctypes.c_float * NUM_OUTPUTS


def _fnv1a(data: bytes) -> int:
    """La même FNV-1a 64 bits que `gn_evalcache.c`, en Python -- une seconde
    lecture indépendante de l'algorithme, pas une copie du C."""
    h = 0xCBF29CE484222325
    for byte in data:
        h ^= byte
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def _bucket(position, mask: int) -> int:
    """Le seau qu'occuperait `position` dans une table de `mask + 1` entrées.

    `bytes(position._to_c())` rend les 29 octets bruts de la structure C --
    exactement ce que `gn_evalcache.c` hache -- donc ce calcul, fait en Python
    à côté, est un second témoin de l'index, pas une supposition sur lui.
    """
    return _fnv1a(bytes(position._to_c())) & mask


@pytest.fixture(autouse=True)
def clean_cache():
    """Le cache partagé est un pointeur de module, pas un objet de test --
    même discipline que `test_bearoff_wired.py` pour la table partagée : les
    tests de ce fichier ne doivent rien se transmettre entre eux."""
    evalcache.disable()
    yield
    evalcache.disable()


@pytest.fixture(scope="module")
def network() -> Network:
    if not MODEL_BIN.is_file():
        pytest.skip(f"{MODEL_BIN} absent — lancer `make model`")
    with Network.load(MODEL_BIN) as net:
        yield net


def build_corpus(size: int):
    """Positions de contact, non terminales, à graine fixe.

    Même construction que `tests/test_search.py::build_corpus` : un mélange
    représentatif de milieu de partie, pas seulement l'ouverture.
    """
    from gammonnet.rules import Position

    rng = random.Random(SEED)
    positions = []
    while len(positions) < size:
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()
        for _ in range(60):
            if position.is_over() or len(positions) >= size:
                break
            positions.append(position)
            plays = position.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
            position = rng.choice(plays).result if plays else position.swapped_turn()
    return positions


CORPUS = build_corpus(40)


# ── Le test central : aucun résultat ne bouge ─────────────────────────


def _snapshot(network, config):
    """Coups choisis et équités, pour tout le corpus x DICE.

    Le résultat *complet* d'une recherche, comparé terme à terme : un coup
    identique avec une équité qui aurait bougé d'un seul bit serait déjà un
    cache qui change un résultat, pas seulement le classement final.
    """
    out = []
    for position in CORPUS:
        for d1, d2 in DICE:
            candidates = search_plays(network, position, d1, d2, config)
            out.append(tuple((c.play.result, c.equity) for c in candidates))
    return out


def test_cache_off_matches_cache_on_cold_and_warm(network):
    """LE test : cache éteint / allumé (froid) / allumé (chaud) rendent
    EXACTEMENT les mêmes coups et les mêmes équités.

    >= 300 décisions (40 positions x 8 jets = 320). Une seule différence,
    aussi petite soit-elle, ferait du cache un bug plutôt qu'une optimisation
    -- voir `gn_evalcache.h`. Aucune tolérance n'est appliquée : `==`, pas
    `pytest.approx`.
    """
    config = SearchConfig(ply=1, filter=(0, 5))
    decisions = len(CORPUS) * len(DICE)
    assert decisions >= 300, f"seulement {decisions} décisions -- corpus trop maigre"

    assert not evalcache.is_enabled()
    off = _snapshot(network, config)

    evalcache.enable(16)
    cold = _snapshot(network, config)  # la table se remplit
    warm = _snapshot(network, config)  # tout devrait taper le cache

    assert off == cold, "un résultat a changé dès le premier passage (cache froid)"
    assert off == warm, "un résultat a changé au second passage (cache chaud)"

    stats = evalcache.stats()
    assert stats.hits > 0, "le second passage n'a produit aucun hit -- test sans valeur"
    print(f"\n{decisions} décisions, identiques éteint/froid/chaud -- "
          f"{stats.hits} hits, {stats.misses} misses, {stats.stores} stores")


# ── Les compteurs : misses puis hits sur la même recherche répétée ────


def test_counters_move_as_expected(network):
    """Premier passage : des misses (et déjà quelques hits -- voir plus bas).
    Second passage, exactement la même recherche : très majoritairement des
    hits.

    Un seul appel à `search_plays` à 1-ply explore déjà 21 jets x plusieurs
    coups, et deux branches distinctes peuvent atteindre la MÊME position
    résultante -- une vraie transposition, à l'intérieur d'une seule
    recherche. Le premier passage peut donc légitimement contenir des hits.

    Le second passage n'est pas garanti à ZÉRO miss : la table a une taille
    fixe (remplacement direct, sans chaînage -- `gn_evalcache.h`), et avec
    2**16 seaux pour environ deux mille entrées distinctes, le paradoxe des
    anniversaires prédit une poignée de collisions même à l'intérieur du seul
    premier passage -- une entrée peut en expulser une autre que le second
    passage redemandera, et cela produira alors un miss légitime, pas un bug.
    Le test vérifie donc une amélioration nette et un total de consultations
    inchangé (la recherche elle-même est déterministe), pas un zéro absolu.
    """
    position = CORPUS[0]
    config = SearchConfig(ply=1, filter=(0, 5))

    evalcache.enable(16)
    before = evalcache.stats()
    assert before.hits == before.misses == before.stores == 0

    search_plays(network, position, 3, 1, config)
    after_cold = evalcache.stats()
    assert after_cold.misses > 0, "aucun miss au premier passage"
    assert after_cold.stores > 0, "aucun store au premier passage"
    assert after_cold.stores == after_cold.misses, (
        "chaque miss doit produire un store (aucun autre chemin ne remplit la table) : "
        f"{after_cold.stores} stores contre {after_cold.misses} misses"
    )

    search_plays(network, position, 3, 1, config)
    after_warm = evalcache.stats()
    new_hits = after_warm.hits - after_cold.hits
    new_misses = after_warm.misses - after_cold.misses
    lookups_cold = after_cold.hits + after_cold.misses
    lookups_warm = new_hits + new_misses

    assert lookups_warm == lookups_cold, (
        "la recherche n'a pas exploré le même nombre de feuilles deux fois de suite : "
        f"{lookups_warm} contre {lookups_cold} -- la recherche n'est pas déterministe"
    )
    assert new_hits > after_cold.hits, "le second passage n'a pas fait mieux que le premier"
    hit_fraction = new_hits / lookups_warm
    assert hit_fraction > 0.9, (
        f"seulement {hit_fraction:.1%} de hits au second passage -- "
        "le cache ne retrouve pas ce qu'il vient de stocker"
    )
    print(f"\nfroid : {after_cold.misses} misses, {after_cold.hits} hits (transpositions "
          f"internes) ; chaud : {new_hits}/{lookups_warm} hits ({hit_fraction:.1%})")


# ── Le défaut : rien ne change sans enable() ──────────────────────────


def test_disabled_by_default(network):
    """Sans `enable()`, `is_enabled()` ment jamais, et la recherche est
    déterministe -- deux passages identiques -- exactement comme avant que
    ce module existe."""
    assert not evalcache.is_enabled()

    config = SearchConfig(ply=0)
    position = CORPUS[0]
    first = [(c.play.result, c.equity)
             for c in search_plays(network, position, 4, 2, config)]
    second = [(c.play.result, c.equity)
              for c in search_plays(network, position, 4, 2, config)]
    assert first == second

    with pytest.raises(ValueError):
        evalcache.stats()


def test_disable_after_enable_is_a_clean_no_op(network):
    """Un cycle enable/disable ne laisse aucune trace sur une recherche.

    Même contrôle que `test_bearoff_wired.py` fait pour la table de bearoff :
    le pointeur de module revient à NULL, et rien côté recherche ne le sait.
    """
    config = SearchConfig(ply=0)
    position = CORPUS[1]

    def snapshot():
        return [(c.play.result, c.equity)
                for c in search_plays(network, position, 5, 3, config)]

    before = snapshot()
    evalcache.enable(16)
    evalcache.disable()
    after = snapshot()
    assert before == after


# ── La collision de seau : la clé complète départage ──────────────────


def test_bucket_collision_resolves_to_the_right_position(network):
    """Deux positions DIFFÉRENTES qui hachent au MÊME seau, dans une table de
    2**4 = 16 entrées : chacune doit recevoir sa propre réponse, jamais celle
    de l'autre.

    Construit directement sur une table indépendante (pas le cache partagé)
    pour observer un seau précis : stocker A, vérifier que B (même seau,
    clé différente) rate -- pas un faux hit sur les octets de A -- puis
    stocker B, qui EXPULSE A du seau (remplacement direct, sans chaînage :
    voir `gn_evalcache.h`), et vérifier que relire A rate proprement plutôt
    que de rendre la réponse de B.
    """
    log2 = 4
    mask = (1 << log2) - 1

    buckets: dict[int, object] = {}
    collision = None
    for position in CORPUS:
        for d1, d2 in DICE:
            for candidate in search_plays(network, position, d1, d2, SearchConfig(ply=0)):
                result = candidate.result
                if result.is_over():
                    continue
                b = _bucket(result, mask)
                if b in buckets and buckets[b] != result:
                    collision = (buckets[b], result)
                    break
                buckets[b] = result
            if collision:
                break
        if collision:
            break

    assert collision is not None, (
        "aucune collision trouvée sur 16 seaux -- corpus trop maigre pour ce test"
    )
    pos_a, pos_b = collision
    assert pos_a != pos_b
    assert _bucket(pos_a, mask) == _bucket(pos_b, mask)

    handle = _LIB.gn_evalcache_create(log2)
    assert handle, "gn_evalcache_create a refusé une table de 16 entrées"
    try:
        assert _LIB.gn_evalcache_capacity(handle) == 16

        probs_a = network.evaluate(pos_a)
        probs_b = network.evaluate(pos_b)
        c_probs_a = _ProbArray(*probs_a.as_tuple())
        c_probs_b = _ProbArray(*probs_b.as_tuple())

        out = _ProbArray()

        # A seul dans le seau : un hit, sa propre réponse.
        _LIB.gn_evalcache_store(handle, ctypes.byref(pos_a._to_c()), c_probs_a)
        hit = _LIB.gn_evalcache_lookup(handle, ctypes.byref(pos_a._to_c()), out)
        assert hit == 1
        assert tuple(out) == pytest.approx(probs_a.as_tuple(), abs=0.0)

        # B, même seau, clé différente : PAS un faux hit sur les octets de A.
        miss = _LIB.gn_evalcache_lookup(handle, ctypes.byref(pos_b._to_c()), out)
        assert miss == 0, "B a fait un hit sur l'entrée de A -- la clé n'a pas départagé"

        # B expulse A (remplacement direct, sans chaînage).
        _LIB.gn_evalcache_store(handle, ctypes.byref(pos_b._to_c()), c_probs_b)

        # B : hit, sa propre réponse.
        hit_b = _LIB.gn_evalcache_lookup(handle, ctypes.byref(pos_b._to_c()), out)
        assert hit_b == 1
        assert tuple(out) == pytest.approx(probs_b.as_tuple(), abs=0.0)

        # A : rate proprement -- jamais la réponse (fausse) de B.
        miss_a = _LIB.gn_evalcache_lookup(handle, ctypes.byref(pos_a._to_c()), out)
        assert miss_a == 0, (
            "A a reçu un hit après avoir été expulsé par B -- "
            "la table a rendu la réponse de la mauvaise position"
        )
    finally:
        _LIB.gn_evalcache_free(handle)


# ── Le compteur d'évaluations réseau : un hit n'en est pas une ────────


def test_cache_hits_do_not_count_as_network_evaluations(network):
    """Un hit de cache n'est pas une évaluation réseau -- même règle que la
    table de bearoff (T38) pour `g_evaluations`."""
    position = CORPUS[0]
    config = SearchConfig(ply=1, filter=(0, 5))

    evalcache.enable(16)
    reset_evaluations()
    search_plays(network, position, 3, 1, config)
    cold_evals = evaluations()
    assert cold_evals > 0

    reset_evaluations()
    search_plays(network, position, 3, 1, config)
    warm_evals = evaluations()

    assert warm_evals < cold_evals, (
        f"{warm_evals} évaluations réseau au second passage contre {cold_evals} au "
        "premier -- le cache ne réduit rien"
    )
    print(f"\névaluations réseau : {cold_evals} froid, {warm_evals} chaud")
