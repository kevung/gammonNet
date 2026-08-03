"""T02 — le codec : 196 caractéristiques, Position ID, XGID.

**La tâche la plus critique du projet.** Une erreur ici ne provoque aucun plantage :
elle produit des évaluations plausibles et fausses, et contamine silencieusement
toutes les mesures ultérieures. D'où des critères durs plutôt que raisonnables —
parité **exacte** (`max|Δ| = 0`) et non « proche », et un corpus franchement
asymétrique plutôt que la position d'ouverture, qui ne détecte aucune inversion de
perspective puisqu'elle est son propre miroir.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

from gammonnet import BLACK, NUM_POINTS, WHITE, Position
from gammonnet import codec
from gammonnet import gnubg_board as gb

gnubg_nn = pytest.importorskip("gnubg_nn", reason="gnubg-nn absent — lancer `make venv`")

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "vendor" / "backgammon-ai-engine"

SEED = 20260803
CORPUS_SIZE = 10_000

CANONICAL_OPENING_XGID = "XGID=-b----E-C---eE---c-e----B-:0:0:1:00:0:0:0:0:10"


# ── La référence Python ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def reference_encoder():
    """`encoding.py` du dépôt de référence — celui qui a servi à entraîner le réseau."""
    if not REFERENCE.is_dir():
        pytest.skip("vendor/backgammon-ai-engine absent — lancer `make vendor`")

    sys.path.insert(0, str(REFERENCE))
    try:
        from backgammon_engine import BoardState
        from encoding import Perspective196Encoder

        encoder = Perspective196Encoder()

        def encode(position: Position):
            state = BoardState(
                points=list(position.points),
                bar=list(position.bar),
                off=list(position.off),
                turn=position.turn,
            )
            return encoder.encode(state)

        yield encode
    finally:
        sys.path.remove(str(REFERENCE))


# ── Le corpus ────────────────────────────────────────────────────────


def mirror(position: Position) -> Position:
    """Échange les couleurs et retourne le plateau.

    `points[j]` devient `-points[23 - j]` : le pion de Blanc sur son point k
    devient un pion de Noir sur le point k de Noir. Barre, pions sortis et trait
    suivent. Un encodage correct doit rendre le **même** vecteur pour `p` avec
    Blanc au trait et pour `mirror(p)` avec Noir au trait — c'est toute la
    raison d'être d'un encodage en perspective.
    """
    return Position(
        points=tuple(-position.points[NUM_POINTS - 1 - j] for j in range(NUM_POINTS)),
        bar=(position.bar[BLACK], position.bar[WHITE]),
        off=(position.off[BLACK], position.off[WHITE]),
        turn=BLACK if position.turn == WHITE else WHITE,
    )


def build_corpus(size: int) -> list[Position]:
    """`size` positions tirées de parties aléatoires, à graine fixe.

    Reproductible : la même graine rend le même corpus. Les deux couleurs jouent.
    """
    rng = random.Random(SEED)
    positions: list[Position] = []

    while len(positions) < size:
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()

        for _ in range(400):
            if position.is_over() or len(positions) >= size:
                break
            positions.append(position)

            plays = position.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
            position = rng.choice(plays).result if plays else position.swapped_turn()

    return positions


CORPUS = build_corpus(CORPUS_SIZE)


def is_strongly_asymmetric(position: Position) -> bool:
    """Vraie asymétrie : la position ne ressemble pas à son propre miroir.

    Une position d'ouverture est son propre miroir : elle passerait le test
    d'orientation quelle que soit l'erreur commise. C'est exactement le piège
    que `BRIEF.md` signale.
    """
    reflected = mirror(position)
    if reflected.points == position.points:
        return False
    return abs(position.pip_count(WHITE) - position.pip_count(BLACK)) >= 15


ASYMMETRIC = [p for p in CORPUS if is_strongly_asymmetric(p)]


def test_corpus_is_large_enough_and_reproducible():
    assert len(CORPUS) == CORPUS_SIZE
    assert build_corpus(200) == CORPUS[:200], "le corpus n'est pas reproductible à graine fixe"

    turns = {p.turn for p in CORPUS}
    assert turns == {WHITE, BLACK}, "le corpus ne fait pas jouer les deux couleurs"


def test_corpus_contains_enough_strongly_asymmetric_positions():
    """T02 exige au moins 50 positions franchement asymétriques."""
    assert len(ASYMMETRIC) >= 50, (
        f"{len(ASYMMETRIC)} positions franchement asymétriques, 50 exigées — "
        "une position d'ouverture ne détecte pas une inversion de perspective"
    )


# ── Critère 1 : parité exacte contre la référence Python ─────────────


def test_features_are_bit_for_bit_identical_to_the_reference(reference_encoder):
    """`max|Δ| = 0` sur 10 000 positions. Pas « proche » : identique.

    Le réseau a été entraîné sur ce vecteur exact. Un écart d'un ulp sur une
    caractéristique n'est pas un arrondi bénin, c'est une entrée que le modèle
    n'a jamais vue — et il répondra cinq probabilités parfaitement plausibles.
    """
    worst = 0.0
    worst_position = None

    for position in CORPUS:
        ours = codec.encode(position)
        theirs = reference_encoder(position)

        assert len(ours) == len(theirs) == 196

        for i, (a, b) in enumerate(zip(ours, theirs)):
            delta = abs(a - float(b))
            if delta > worst:
                worst, worst_position = delta, (position, i, a, float(b))

    assert worst == 0.0, (
        f"max|Δ| = {worst!r}, exigé 0. Première divergence : {worst_position}"
    )


def test_reference_parity_holds_for_both_colours_on_roll(reference_encoder):
    """La parité doit tenir pour Noir au trait autant que pour Blanc.

    C'est là que vit le miroitage des indices, et donc l'erreur la plus probable.
    """
    for colour in (WHITE, BLACK):
        sample = [p for p in CORPUS if p.turn == colour][:2000]
        assert sample, f"aucune position avec {colour} au trait"

        for position in sample:
            assert codec.encode(position) == [float(v) for v in reference_encoder(position)]


# ── Critère 2 : aller-retour ─────────────────────────────────────────


def test_decode_inverts_encode():
    """`decode(encode(p), p.turn) == p` sur tout le corpus."""
    for position in CORPUS:
        recovered = codec.decode(codec.encode(position), position.turn)

        assert recovered.points == position.points, f"{position!r} : points perdus"
        assert recovered.bar == position.bar, f"{position!r} : barre perdue"
        assert recovered.off == position.off, f"{position!r} : pions sortis perdus"
        assert recovered.turn == position.turn


# ── Critère 3 : la sentinelle du compte de pips ──────────────────────


def test_pip_count_from_features_matches_the_identifier():
    """Le compte de pips lu dans le vecteur, dans la position, et via l'identifiant.

    Trois chemins indépendants vers le même nombre. Si l'un diverge, tout ce qui
    suivrait serait dépourvu de sens.
    """
    for position in CORPUS:
        features = codec.encode(position)
        opponent = BLACK if position.turn == WHITE else WHITE

        from_features_me = codec.pip_count_from_features(features, codec.SIDE_ON_ROLL)
        from_features_them = codec.pip_count_from_features(features, codec.SIDE_OPPONENT)

        assert from_features_me == position.pip_count(position.turn), (
            f"{position!r} : pips du joueur au trait, vecteur {from_features_me} "
            f"vs position {position.pip_count(position.turn)}"
        )
        assert from_features_them == position.pip_count(opponent), (
            f"{position!r} : pips de l'adversaire, vecteur {from_features_them} "
            f"vs position {position.pip_count(opponent)}"
        )

        # Et via l'identifiant, qui est un quatrième chemin.
        through_id = codec.position_from_id(codec.position_id(position), position.turn)
        assert through_id.pip_count(position.turn) == from_features_me
        assert through_id.pip_count(opponent) == from_features_them


# ── Critère 4 : le test d'asymétrie ──────────────────────────────────


def test_mirrored_position_encodes_identically():
    """`encode(p, Blanc)` et `encode(miroir(p), Noir)` doivent coïncider.

    Sur des positions **franchement asymétriques** uniquement : une position
    symétrique passerait ce test quelle que soit l'erreur d'orientation.
    """
    checked = 0

    for position in ASYMMETRIC:
        reflected = mirror(position)
        assert reflected.turn != position.turn
        assert reflected.is_valid()

        assert codec.encode(position) == codec.encode(reflected), (
            f"{position!r} et son miroir ne produisent pas le même vecteur — "
            "inversion de perspective"
        )
        checked += 1

    assert checked >= 50


def test_mirroring_is_an_involution():
    """`mirror(mirror(p)) == p` — sinon le test d'asymétrie ne teste pas ce qu'il croit."""
    for position in CORPUS[:1000]:
        assert mirror(mirror(position)) == position


# ── Les identifiants ─────────────────────────────────────────────────


def test_position_id_matches_gnubg_exactly():
    """Le Position ID est vérifié contre une implémentation **indépendante**.

    GNU Backgammon est ici un instrument de mesure : on compare notre sortie à la
    sienne, on ne lui emprunte rien.
    """
    for position in CORPUS:
        assert codec.position_id(position) == gnubg_nn.position_id(gb.to_gnubg(position)), (
            f"{position!r} : Position ID différent de celui de GNU Backgammon"
        )


def test_position_id_round_trips():
    for position in CORPUS:
        recovered = codec.position_from_id(codec.position_id(position), position.turn)

        assert recovered.points == position.points
        assert recovered.bar == position.bar
        assert recovered.off == position.off


def test_xgid_reproduces_the_canonical_opening_identifier():
    """L'ancre d'orientation de l'XGID, faute d'oracle disponible.

    Contrairement au Position ID, aucune implémentation indépendante d'XGID
    n'était disponible pour croiser les 10 000 positions. L'orientation est donc
    ancrée sur cet identifiant canonique — vérifié point par point contre la
    position initiale — et sur l'aller-retour. C'est plus faible, et c'est dit.
    """
    initial = Position.initial()

    assert codec.xgid(initial) == CANONICAL_OPENING_XGID

    parsed, fields = codec.position_from_xgid(CANONICAL_OPENING_XGID)
    assert parsed.points == initial.points
    assert parsed.bar == initial.bar
    assert parsed.off == initial.off
    assert parsed.turn == WHITE
    assert fields.match_length == 0 and fields.max_cube == 10


def test_xgid_round_trips():
    for position in CORPUS:
        parsed, _ = codec.position_from_xgid(codec.xgid(position))

        assert parsed.points == position.points, f"{position!r} : XGID ne survit pas"
        assert parsed.bar == position.bar
        assert parsed.off == position.off
        assert parsed.turn == position.turn


def test_xgid_carries_its_non_checker_fields_through():
    """Un identifiant doit survivre entier, pas amputé de la moitié de son sens."""
    fields = codec.XgidFields(
        cube_power=2, cube_owner=-1, turn=-1, die1=5, die2=3,
        score_upper=4, score_lower=2, flags=1, match_length=7, max_cube=10,
    )
    position = CORPUS[500]

    written = codec.xgid(position, fields)
    _, back = codec.position_from_xgid(written)

    assert back == fields, f"{written} : les champs ne survivent pas"


# ── Le contrat de refus ──────────────────────────────────────────────


def test_encoding_refuses_an_invalid_position():
    broken = Position(points=(2,) + (0,) * 23, bar=(0, 0), off=(0, 0), turn=WHITE)

    with pytest.raises(ValueError):
        codec.encode(broken)


def test_decoding_refuses_a_malformed_thermometer():
    """Un thermomètre impossible doit être refusé, jamais interprété au mieux."""
    features = codec.encode(Position.initial())

    # Une unité allumée au-dessus d'une unité éteinte : l'encodeur ne produit
    # jamais cette forme.
    broken = list(features)
    broken[0] = 0.0
    broken[1] = 1.0

    with pytest.raises(ValueError):
        codec.decode(broken, WHITE)


def test_identifiers_refuse_malformed_input():
    with pytest.raises(ValueError):
        codec.position_from_id("pas-un-identifiant", WHITE)
    with pytest.raises(ValueError):
        codec.position_from_xgid("XGID=trop-court:0:0:1:00:0:0:0:0:10")
