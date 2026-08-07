"""T38 — la table branchée dans la recherche, et ce que le branchement change.

`gn_bearoff.h` documente le pointeur de module et le compteur de hits ;
`gn_search.c` et `gn_choose.c` les consultent désormais avant d'interroger le
réseau sur une feuille. Ce fichier vérifie exactement ce que `CLAUDE.md`
demande d'un branchement de ce genre :

* **le défaut n'a pas bougé** — sans `use_shared`, un cycle
  activation/désactivation ne laisse aucune trace sur ce que le 0-ply rend ;
* **la table active répond ce qu'elle doit** — les probabilités qu'expose la
  recherche sur une feuille du domaine sont EXACTEMENT celles de
  `gn_bearoff_probs`, pas une approximation voisine ;
* **hors du domaine, elle se tait** — le réseau répond, les hits
  n'augmentent pas ;
* **le compteur de hits et celui d'évaluations restent deux compteurs** —
  l'un croît quand la table répond, l'autre ne croît plus à sa place.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import pytest

from gammonnet.bearoff import (
    NativeBearoff,
    TwoSidedBearoff,
    disable_shared,
    reset_shared_hits,
    shared_hits,
    use_shared,
)
from gammonnet.infer import Network
from gammonnet.rules import BLACK, NUM_POINTS, WHITE, Position
from gammonnet.search import (
    SearchConfig,
    best_play,
    evaluations,
    reset_evaluations,
    search_plays,
)

ROOT = Path(__file__).resolve().parent.parent
DATABASE = Path(os.environ.get(
    "GNUBG_TS_DATABASE",
    ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd",
))
MODEL_BIN = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"

pytestmark = [
    pytest.mark.skipif(
        not DATABASE.exists(),
        reason=f"base bilatérale absente : {DATABASE}. Voir docs/prerequis.md",
    ),
    pytest.mark.skipif(
        not MODEL_BIN.is_file(), reason=f"{MODEL_BIN} absent — lancer `make model`"
    ),
]

SEED = 20260807
DICE = ((3, 1), (5, 2), (6, 6), (4, 3), (2, 1))


@pytest.fixture(autouse=True)
def clean_shared_table():
    """La table partagée est un pointeur de module, pas un objet de test.

    Chaque test part de l'état par défaut (NULL) et le restaure en sortant,
    pour que l'ordre d'exécution des tests — ici ou dans un autre fichier —
    ne change rien à leur résultat.
    """
    disable_shared()
    yield
    disable_shared()


@pytest.fixture(scope="module")
def network() -> Network:
    with Network.load(MODEL_BIN) as net:
        yield net


@pytest.fixture(scope="module")
def reference():
    """La table Python, utilisée seulement pour générer des positions du domaine."""
    with TwoSidedBearoff(DATABASE) as table:
        yield table


@pytest.fixture(scope="module")
def native_probe():
    """Un second lecteur C, ouvert indépendamment de celui que `use_shared` installe.

    Comparer contre CE lecteur, plutôt que contre l'objet retourné par
    `use_shared`, garantit que la comparaison elle-même ne modifie pas le
    compteur de hits de la table partagée : les deux fichiers sont identiques,
    mais les pointeurs `GnBearoff*` diffèrent, et le compteur ne suit que le
    pointeur installé par `gn_bearoff_set_shared`.
    """
    with NativeBearoff(DATABASE) as table:
        yield table


def race(white_points, black_points, turn=WHITE) -> Position:
    points = [0] * NUM_POINTS
    for i, n in enumerate(white_points):
        points[i] = n
    for j, n in enumerate(black_points):
        points[NUM_POINTS - 1 - j] = -n
    return Position(points=tuple(points), bar=(0, 0),
                    off=(15 - sum(white_points), 15 - sum(black_points)), turn=turn)


def domain_positions(reference: TwoSidedBearoff, count: int, seed: int) -> list[Position]:
    """Des positions du domaine de la table, non terminales.

    Les répartitions sont tirées petites (`randrange(3)` par point, comme
    `tests/test_bearoff_native.py`) plutôt qu'au plus large possible : la
    marge sous `chequers` fait qu'un coup légal, dans ce domaine sans contact,
    ne peut pas faire sortir une position de la table — les pions n'y font que
    descendre vers la sortie.
    """
    rng = random.Random(seed)
    out: list[Position] = []
    while len(out) < count:
        white = [rng.randrange(3) for _ in range(reference.points)]
        black = [rng.randrange(3) for _ in range(reference.points)]
        if not sum(white) or not sum(black):
            continue
        position = race(white, black, turn=WHITE if len(out) % 2 == 0 else BLACK)
        if reference.contains(position):
            out.append(position)
    return out


# ── Le défaut : sans `use_shared`, rien ne bouge ──────────────────────


def test_a_cycle_of_activation_leaves_the_disabled_search_unchanged(network, reference):
    """0-ply, table désactivée, avant et après un aller-retour activé/désactivé.

    C'est le garde-fou du corpus T12 : tant que rien n'a appelé `use_shared`,
    aucun appelant existant ne doit voir un chiffre bouger, et un cycle
    activation puis désactivation ne doit laisser aucune trace.
    """
    positions = domain_positions(reference, 20, SEED)

    def snapshot() -> list[tuple[float, ...]]:
        out = []
        for position in positions:
            for d1, d2 in DICE:
                candidates = search_plays(network, position, d1, d2, SearchConfig(ply=0))
                out.append(tuple(c.equity for c in candidates))
        return out

    before = snapshot()

    table = use_shared(DATABASE)
    assert table.contains(positions[0]), "la table vient de s'ouvrir sur le mauvais domaine"
    disable_shared()

    after = snapshot()

    assert before == after, "un cycle activation/désactivation a changé le 0-ply désactivé"


# ── La table active répond exactement ce que dit `gn_bearoff_probs` ──


def test_active_search_leaves_match_gn_bearoff_probs(network, reference, native_probe):
    """Les cinq sorties d'une feuille, à 0-ply, coïncident avec `gn_bearoff_probs`.

    `Candidate.evaluation` n'est peuplé qu'à `ply=0` -- au-delà, les
    probabilités qu'il porterait seraient un vestige du classement peu
    profond, pas la sortie de la feuille. C'est précisément à `ply=0` que la
    comparaison a un sens.
    """
    use_shared(DATABASE)
    positions = domain_positions(reference, 15, SEED + 1)

    compared = 0
    for position in positions:
        for d1, d2 in DICE:
            candidates = search_plays(network, position, d1, d2, SearchConfig(ply=0))
            for candidate in candidates:
                result = candidate.result
                if result.is_over() or not native_probe.contains(result):
                    continue
                expected = native_probe.probs(result)
                assert expected is not None
                got = candidate.evaluation
                assert got is not None
                assert got.as_tuple() == pytest.approx(expected, abs=1e-9)
                assert (got.win_gammon, got.win_backgammon,
                        got.lose_gammon, got.lose_backgammon) == (0.0, 0.0, 0.0, 0.0)
                compared += 1

    assert compared > 20, f"seulement {compared} comparaisons — corpus trop maigre"


# ── Hors domaine, la table se tait et le réseau répond ────────────────


def test_out_of_domain_position_falls_back_to_the_network(network):
    """Une position de contact : le réseau répond, les hits n'augmentent pas."""
    use_shared(DATABASE)
    reset_shared_hits()
    reset_evaluations()

    position = Position.initial()
    candidates = search_plays(network, position, 3, 1, SearchConfig(ply=0))

    assert candidates, "la position de départ a des coups légaux"
    assert shared_hits() == 0, "la table a répondu sur une position de contact"
    assert evaluations() > 0, "le réseau n'a pas été interrogé hors du domaine"


# ── Les deux compteurs, et ce qu'ils doivent faire séparément ─────────


def test_hits_grow_strictly_during_a_one_ply_search(network, reference):
    """Une recherche à 1-ply sur une position de bearoff fait croître les hits."""
    position = domain_positions(reference, 1, SEED + 2)[0]
    use_shared(DATABASE)
    reset_shared_hits()

    candidates = search_plays(network, position, 4, 2, SearchConfig(ply=1))

    assert candidates
    assert shared_hits() > 0, "la table n'a jamais répondu pendant la recherche"


def test_evaluation_count_drops_when_the_table_is_active(network, reference):
    """À recherche égale, la table active coûte moins d'évaluations réseau.

    Toutes les feuilles d'une recherche sur une position de bearoff sans
    contact tombent dans le domaine de la table -- les coups n'y font que
    rapprocher les pions de la sortie. Le compte d'évaluations doit donc
    tomber à (ou près de) zéro une fois la table active.
    """
    position = domain_positions(reference, 1, SEED + 3)[0]

    reset_evaluations()
    best_play(network, position, 5, 3, SearchConfig(ply=1))
    without_table = evaluations()

    use_shared(DATABASE)
    reset_evaluations()
    best_play(network, position, 5, 3, SearchConfig(ply=1))
    with_table = evaluations()

    assert without_table > 0, "le témoin lui-même n'a rien évalué : test sans valeur"
    assert with_table < without_table, (
        f"{with_table} évaluations avec la table contre {without_table} sans -- "
        "la table ne réduit rien"
    )
    print(f"\névaluations 1-ply sur une décision de bearoff : "
          f"{without_table} sans table, {with_table} avec")
