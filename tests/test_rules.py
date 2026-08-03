"""T01 — les coups légaux de gammonNet contre ceux de GNU Backgammon.

Le critère d'acceptation de T01 demande un **générateur de référence indépendant**.
Le chemin Python du dépôt de référence n'en est pas un : il partage son auteur, et
donc sa lecture des règles, avec le moteur C que nous reprenons. Si cette lecture
est fausse quelque part, les deux se trompent ensemble et le test passe.

GNU Backgammon est indépendant. C'est un **instrument de mesure**, jamais une
source de code ni de poids (`CLAUDE.md`) — et ici il ne nous apprend rien, il nous
contredit ou nous confirme.

La comparaison porte sur l'**ensemble des positions atteintes**, pas seulement sur
leur nombre : deux générateurs peuvent produire autant de coups en n'étant d'accord
sur aucun.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gammonnet import BLACK, WHITE, Position
from gammonnet import gnubg_board as gb
from gammonnet.rules import MAX_PLAYS

gnubg_nn = pytest.importorskip("gnubg_nn", reason="gnubg-nn absent — lancer `make venv`")

CORPUS = Path(__file__).parent / "data" / "corpus_t01.jsonl"

# Every distinct unordered roll: 15 non-doubles + 6 doubles.
ALL_ROLLS = [(d1, d2) for d1 in range(1, 7) for d2 in range(d1, 7)]


def load_corpus() -> list[tuple[str, str, Position]]:
    entries = []
    for line in CORPUS.read_text().splitlines():
        record = json.loads(line)
        entries.append((
            record["id"],
            record["category"],
            Position(
                points=tuple(record["points"]),
                bar=tuple(record["bar"]),
                off=tuple(record["off"]),
                turn=record["turn"],
            ),
        ))
    return entries


CORPUS_ENTRIES = load_corpus()
BY_ID = {identifier: position for identifier, _, position in CORPUS_ENTRIES}


def by_label(label: str) -> Position:
    return BY_ID[label]


# ── Le corpus lui-même ───────────────────────────────────────────────


def test_corpus_is_large_enough_and_covers_every_category():
    """T01 exige ≥ 200 positions couvrant barre, fermetures, sorties et bearoff."""
    assert len(CORPUS_ENTRIES) >= 200, f"{len(CORPUS_ENTRIES)} positions, 200 exigées"

    categories = {category for _, category, _ in CORPUS_ENTRIES}
    for required in ("bar", "closure", "bearoff", "race", "contact", "no_move"):
        assert required in categories, f"catégorie « {required} » absente du corpus"


def test_corpus_contains_both_colours_on_roll():
    """Une erreur d'orientation qui ne frappe qu'une couleur doit être visible.

    Un corpus où Blanc joue toujours ne la détecterait jamais.
    """
    turns = {position.turn for _, _, position in CORPUS_ENTRIES}
    assert turns == {WHITE, BLACK}, "le corpus ne fait pas jouer les deux couleurs"


@pytest.mark.parametrize("identifier,position", [(i, p) for i, _, p in CORPUS_ENTRIES])
def test_every_corpus_position_is_structurally_valid(identifier, position):
    assert position.is_valid(), f"{identifier} : 15 pions par joueur, une couleur par point"
    assert position.checker_count(WHITE) == 15
    assert position.checker_count(BLACK) == 15


# ── La sentinelle du compte de pips ──────────────────────────────────


@pytest.mark.parametrize("identifier,position", [(i, p) for i, _, p in CORPUS_ENTRIES])
def test_pip_count_survives_translation_to_gnubg(identifier, position):
    """Le compte de pips doit être le même des deux côtés de la traduction.

    `to_gnubg` lève de lui-même si ce n'est pas le cas ; ce test rend la
    vérification explicite plutôt que dépendante d'un effet de bord.
    """
    board = gb.to_gnubg(position)
    opponent = BLACK if position.turn == WHITE else WHITE

    assert gb._gnubg_pip_count(board[1]) == position.pip_count(position.turn)
    assert gb._gnubg_pip_count(board[0]) == position.pip_count(opponent)


@pytest.mark.parametrize("identifier,position", [(i, p) for i, _, p in CORPUS_ENTRIES])
def test_translation_to_gnubg_round_trips(identifier, position):
    """`from_gnubg(to_gnubg(p)) == p`, pions borne off compris."""
    board = gb.to_gnubg(position)
    back = gb.from_gnubg(board, on_roll=position.turn)

    assert back.points == position.points, f"{identifier} : les points ne survivent pas"
    assert back.bar == position.bar
    assert back.off == position.off


# ── Le croisement, position par position ─────────────────────────────


@pytest.mark.parametrize("identifier,position", [(i, p) for i, _, p in CORPUS_ENTRIES])
def test_legal_plays_agree_with_gnubg(identifier, position):
    """Sur les 21 jets, mêmes positions atteintes que GNU Backgammon."""
    for d1, d2 in ALL_ROLLS:
        ours = position.legal_plays(d1, d2)

        # `gnubg_nn.moves` rend ses clés dans l'orientation du joueur qui joue :
        # celui-ci reste en `board[1]` après le coup. Nos positions résultantes
        # ont déjà changé de trait, d'où le `on_roll=position.turn` explicite.
        our_keys = {gb.key(play.result, on_roll=position.turn) for play in ours}
        their_keys = set(gnubg_nn.moves(gb.to_gnubg(position), d1, d2, 0))

        assert len(our_keys) == len(ours), (
            f"{identifier} dés {d1}-{d2} : deux coups atteignent la même position, "
            "la déduplication du générateur est incomplète"
        )
        assert our_keys == their_keys, (
            f"{identifier} dés {d1}-{d2} : désaccord avec GNU Backgammon.\n"
            f"  nous {len(our_keys)} coups, gnubg {len(their_keys)}\n"
            f"  chez nous seulement : {sorted(our_keys - their_keys)}\n"
            f"  chez gnubg seulement : {sorted(their_keys - our_keys)}"
        )


# ── Les cas dégénérés, explicitement ─────────────────────────────────


def test_no_legal_play_at_all():
    """Barre contre plateau fermé : zéro coup légal, sur les 21 jets."""
    position = by_label("aucun-coup-legal-plateau-ferme")

    for d1, d2 in ALL_ROLLS:
        assert position.legal_plays(d1, d2) == [], f"dés {d1}-{d2} : un coup est apparu"
        # `gnubg_nn.moves` rend un tuple vide, pas une liste.
        assert not gnubg_nn.moves(gb.to_gnubg(position), d1, d2, 0), (
            f"dés {d1}-{d2} : GNU Backgammon trouve un coup là où nous n'en trouvons aucun"
        )


def test_single_die_playable():
    """Une seule entrée ouverte : sans ce dé, aucun coup n'existe.

    Rien d'autre ne peut bouger tant qu'un pion attend sur la barre — c'est la
    règle que ce cas isole.
    """
    from gammonnet.rules import BAR

    position = by_label("un-seul-de-jouable-entree-unique")
    ENTRY_DIE = 6  # seul l'index 18 est ouvert, soit un 6 pour Blanc
    ENTRY_INDEX = 18
    seen_entry = False

    for d1, d2 in ALL_ROLLS:
        plays = position.legal_plays(d1, d2)

        if ENTRY_DIE not in (d1, d2):
            assert plays == [], (
                f"dés {d1}-{d2} : un coup est apparu sans le seul dé qui entre"
            )
            continue

        assert plays, f"dés {d1}-{d2} : le {ENTRY_DIE} doit permettre d'entrer"
        for play in plays:
            first = play.moves[0]
            assert first.from_ == BAR and first.to == ENTRY_INDEX, (
                f"dés {d1}-{d2} : le coup ne commence pas par l'entrée sur "
                f"l'index {ENTRY_INDEX}, alors que la barre est prioritaire"
            )
            seen_entry = True

    assert seen_entry, "aucune entrée observée — la position ne teste rien"


def test_must_play_the_larger_die():
    """Les deux dés jouables seuls, jamais ensemble : le plus grand s'impose."""
    position = by_label("obligation-de-jouer-le-plus-grand-de")

    # Le 6 entre sur l'index 18, le 1 sur l'index 23. Chacun seul est légal.
    assert len(position.legal_plays(6, 6)) > 0, "le 6 doit pouvoir entrer"
    assert len(position.legal_plays(1, 1)) > 0, "le 1 doit pouvoir entrer"

    plays = position.legal_plays(6, 1)
    assert len(plays) == 1, f"attendu un seul coup légal, obtenu {len(plays)} : {plays}"

    (move,) = plays[0].moves
    assert move.to == 18, (
        f"le coup retenu entre sur l'index {move.to} ; le 6 entre sur 18 et le 1 sur 23. "
        "Jouer le 1 reviendrait à préférer le petit dé, ce que les règles interdisent."
    )

    # Et GNU Backgammon doit dire exactement la même chose.
    assert len(gnubg_nn.moves(gb.to_gnubg(position), 6, 1, 0)) == 1


def test_doubles_only_partially_playable():
    """Doubles dont on ne peut jouer que les premiers sous-coups."""
    position = by_label("doubles-partiellement-jouables")

    plays = position.legal_plays(1, 1)
    assert plays, "aucun coup légal — la position ne teste rien"
    assert all(len(play.moves) < 4 for play in plays), (
        "les quatre sous-coups d'un double ne devraient pas être jouables ici"
    )

    our_keys = {gb.key(play.result, on_roll=position.turn) for play in plays}
    assert our_keys == set(gnubg_nn.moves(gb.to_gnubg(position), 1, 1, 0))


def test_forced_bear_off_with_a_larger_die():
    """Le pion le plus arriéré sort sur un dé supérieur à sa distance."""
    from gammonnet.rules import OFF

    position = by_label("sortie-forcee-sur-de-superieur")

    plays = position.legal_plays(6, 6)
    assert plays, "aucun coup légal — la position ne teste rien"

    # Le pion le plus arriéré est sur l'index 2 : un 6 le sort par sur-sortie.
    assert any(
        any(move.from_ == 2 and move.to == OFF for move in play.moves)
        for play in plays
    ), "aucune sur-sortie depuis l'index 2 alors qu'un 6 doit l'y autoriser"

    our_keys = {gb.key(play.result, on_roll=position.turn) for play in plays}
    assert our_keys == set(gnubg_nn.moves(gb.to_gnubg(position), 6, 6, 0))


# ── Le contrat de refus ──────────────────────────────────────────────


def test_generation_refuses_an_invalid_position():
    """Un modèle qu'un build ne sait pas évaluer est refusé, jamais approximé."""
    broken = Position(points=(2,) + (0,) * 23, bar=(0, 0), off=(0, 0), turn=WHITE)
    assert not broken.is_valid()

    with pytest.raises(ValueError):
        broken.legal_plays(3, 1)


@pytest.mark.parametrize("d1,d2", [(0, 1), (7, 3), (1, 0), (3, 7), (-1, 2)])
def test_generation_refuses_dice_out_of_range(d1, d2):
    with pytest.raises(ValueError):
        Position.initial().legal_plays(d1, d2)


def test_play_count_stays_far_below_the_buffer_capacity():
    """La capacité de génération doit garder une marge réelle sur le corpus.

    Le moteur amont abandonne les coups au-delà de son tampon **sans le dire**
    (`bg_engine.c:864`), et notre adaptateur refuse donc à capacité pleine. Ce
    test rend visible la marge dont on dispose : c'est une borne mesurée, pas
    une borne prouvée.
    """
    worst = 0
    for _, _, position in CORPUS_ENTRIES:
        for d1, d2 in ALL_ROLLS:
            worst = max(worst, len(position.legal_plays(d1, d2)))

    assert worst < MAX_PLAYS // 4, (
        f"le maximum observé est {worst} pour une capacité de {MAX_PLAYS} : "
        "la marge n'est plus confortable"
    )
    print(f"\nmaximum de coups légaux observé sur le corpus : {worst} (capacité {MAX_PLAYS})")


# ── Cohérence interne ────────────────────────────────────────────────


@pytest.mark.parametrize("identifier,position", [(i, p) for i, _, p in CORPUS_ENTRIES])
def test_every_resulting_position_is_valid_and_switches_turn(identifier, position):
    """Chaque position atteinte reste structurellement valide et change de trait."""
    for d1, d2 in ALL_ROLLS:
        for play in position.legal_plays(d1, d2):
            assert play.result.is_valid(), f"{identifier} {d1}-{d2} : successeur invalide"
            assert play.result.turn != position.turn, (
                f"{identifier} {d1}-{d2} : le trait n'a pas changé"
            )
