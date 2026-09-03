"""T85 — la valuation du videau par lot : les identités qui l'autorisent.

`gn_cube_value_batch` ne change pas une opération du modèle. Il change
l'ordre dans lequel les opérations de candidats DIFFÉRENTS s'exécutent :
les soixante pas de bissection de chaque candidat sont menés en pas cadencé
plutôt que l'un après l'autre. Ce que ça promet, et ce que ce fichier tient —
mot pour mot ce que `tests/test_batch.py` tient du noyau réseau :

* **Accord avec le scalaire, au bit près.** `value_batch([d0, d1, …])[j]`
  rend EXACTEMENT les bits de `value(dj)`. C'est l'exigence de la fiche : le
  poste est une optimisation, pas une révision du modèle.
* **Invariance au découpage.** Valuer N distributions en un lot, en deux
  moitiés, ou une par une par le même chemin de lot rend les mêmes bits. Sans
  elle, la valeur d'un coup dépendrait du nombre de coups frères — et la
  largeur de voie (`GN_CUBE_BATCH`) deviendrait un paramètre du moteur au
  lieu d'un paramètre de coût.

Les deux couvrent les trois états de possession, plusieurs scores, le videau
déjà tourné, la partie de Crawford et le money — c'est-à-dire chacune des
branches que `gn_cube_value` distingue.

Le corpus est un vrai échantillon de parties évaluées par le réseau : la
récursion §9 est pilotée par le mélange gammon de la distribution, et des
vecteurs synthétiques mesureraient une forme que le moteur ne produit pas.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from gammonnet import Position
from gammonnet.cube import CubeOwner, value as cube_value, value_batch
from gammonnet.infer import Evaluation, Network
from gammonnet.met import MatchState

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"

pytestmark = pytest.mark.skipif(
    not MODEL.is_file(), reason=f"{MODEL.name} absent — lancer `make model`"
)

SEED = 20260902

#: Franchement au-delà de `GN_CUBE_BATCH` (32), pour que le découpage en
#: morceaux soit exercé et qu'un dernier morceau partiel existe.
COUNT = 141

X = 0.688


def _corpus(count: int) -> list[Position]:
    """Des positions de vraies parties, la recette de `test_batch.py`."""
    rng = random.Random(SEED)
    positions: list[Position] = []
    position = Position.initial()
    while len(positions) < count:
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = position.legal_plays(d1, d2)
        position = rng.choice(plays).result if plays else position.swapped_turn()
        if position.is_over():
            position = Position.initial()
            continue
        positions.append(position)
    return positions


@pytest.fixture(scope="module")
def distributions() -> list[Evaluation]:
    with Network.load(MODEL) as net:
        return net.evaluate_batch(_corpus(COUNT))


#: Chaque branche que `gn_cube_value` distingue, et pas une de moins.
STATES = [
    ("money", None),
    ("5-away/5-away", MatchState(5, 5, 1, False)),
    ("2-away/4-away", MatchState(2, 4, 1, False)),
    ("3-away/7-away, videau à 2", MatchState(3, 7, 2, False)),
    ("1-away/1-away", MatchState(1, 1, 1, False)),
    ("4-away/1-away Crawford", MatchState(4, 1, 1, True)),
    ("25-away/25-away", MatchState(25, 25, 1, False)),
]

OWNERS = [CubeOwner.CENTRED, CubeOwner.OWNED, CubeOwner.OPPONENT]


@pytest.mark.parametrize("label,state", STATES, ids=[s[0] for s in STATES])
@pytest.mark.parametrize("owner", OWNERS, ids=[o.name for o in OWNERS])
def test_the_batch_agrees_with_the_scalar_bit_for_bit(
    distributions, label, state, owner
):
    batched = value_batch(distributions, owner, X, state)
    scalar = [cube_value(d, owner, X, state) for d in distributions]

    assert len(batched) == len(scalar) == COUNT
    #: `==` et non `pytest.approx` : la fiche T85 demande le bit près, et une
    #: tolérance ferait passer exactement le défaut qu'elle interdit.
    assert batched == scalar


@pytest.mark.parametrize("label,state", STATES, ids=[s[0] for s in STATES])
def test_the_batch_is_invariant_to_how_it_is_chunked(distributions, label, state):
    owner = CubeOwner.CENTRED

    together = value_batch(distributions, owner, X, state)
    alone = [value_batch([d], owner, X, state)[0] for d in distributions]
    #: Une coupe qui ne tombe PAS sur un multiple de la largeur de voie : si
    #: la largeur fuyait dans le résultat, c'est là qu'elle se verrait.
    halves = (
        value_batch(distributions[:37], owner, X, state)
        + value_batch(distributions[37:], owner, X, state)
    )

    assert together == alone
    assert together == halves


def test_the_corpus_really_exercises_the_recursion(distributions):
    """Sans quoi les deux tests ci-dessus passeraient sur des constantes.

    Le modèle au score est piloté par le mélange gammon ; un corpus dont
    toutes les distributions se ressemblent rendrait les mêmes valeurs
    partout, et l'égalité ne prouverait plus rien.
    """
    state = MatchState(5, 5, 1, False)
    values = value_batch(distributions, CubeOwner.CENTRED, X, state)

    assert len(set(values)) > COUNT // 2
    assert min(values) < -0.15
    assert max(values) > 0.15


def test_the_empty_batch_is_a_batch():
    assert value_batch([], CubeOwner.CENTRED, X, MatchState(5, 5, 1, False)) == []
