"""T86 — la notation de coup : une seule écriture, et c'est celle du C.

**Ce que ce fichier protège.** La notation n'existait qu'en Python, dans
`tools/serve.py`. Le module WebAssembly n'en avait aucune, et un consommateur
en a donc écrit une TROISIÈME, par différence de plateaux — dont l'auteur
documente lui-même qu'une position ambiguë peut lui faire afficher un
appariement que la recherche n'a pas choisi.

Le remède retenu n'a pas été d'en ajouter une quatrième : elle est descendue
en C (`src/gn_notation.c`), et les deux surfaces publiées de gammonNet
l'appellent. Ce test tient les deux moitiés de cette affirmation :

  1. le C rend EXACTEMENT ce que `format_play` rendait — l'oracle ci-dessous
     est la copie littérale de l'implémentation Python d'avant, gardée ici
     pour cela et pour rien d'autre ;
  2. `tools/serve.py` délègue effectivement, plutôt que d'avoir gardé une
     seconde écriture qui coïnciderait aujourd'hui.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gammonnet import BLACK, WHITE, Position
from gammonnet.notation import play_notation
from gammonnet.rules import BAR, OFF

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "data" / "corpus_t01.jsonl"


# ── L'oracle : l'écriture Python d'avant T86, littéralement ──────────
#
# Elle n'est PAS importée de `tools/serve.py` : ce module délègue maintenant au
# C, et l'importer ferait comparer le C à lui-même. Une copie figée est le seul
# oracle possible pour un remplacement.


def _point_number(index: int, mover: int) -> str:
    if index == BAR:
        return "bar"
    if index == OFF:
        return "off"
    return str(index + 1) if mover == WHITE else str(24 - index)


def _format_play_python(play, mover: int) -> str:
    counts: dict[tuple[str, str], int] = {}
    order: list[tuple[str, str]] = []
    for move in play.moves:
        pair = (_point_number(move.from_, mover), _point_number(move.to, mover))
        if pair not in counts:
            order.append(pair)
        counts[pair] = counts.get(pair, 0) + 1
    if not order:
        return ""
    parts = []
    for src, dst in order:
        n = counts[(src, dst)]
        parts.append(f"{src}/{dst}" + (f"({n})" if n > 1 else ""))
    return " ".join(parts)


# ── Le corpus de jeux ────────────────────────────────────────────────


def _positions():
    """Les positions du corpus T01, plus l'ouverture des deux couleurs.

    Le corpus T01 est celui des cas de bord des règles — barre, sortie, aucun
    coup légal — donc exactement là où une notation se trompe : `bar/` et
    `/off` sont les deux seuls symboles que la renumérotation ne produit pas.
    """
    import json

    yield Position.initial()
    yield Position(points=Position.initial().points, bar=(0, 0), off=(0, 0), turn=BLACK)
    if CORPUS.is_file():
        with CORPUS.open() as handle:
            for line in handle:
                record = json.loads(line)
                yield Position(
                    points=tuple(record["points"]),
                    bar=tuple(record["bar"]),
                    off=tuple(record["off"]),
                    turn=record["turn"],
                )


ALL_ROLLS = [(d1, d2) for d1 in range(1, 7) for d2 in range(d1, 7)]


def test_c_notation_reproduit_le_python_sur_tout_le_corpus():
    """L'égalité, sur chaque jeu légal de chaque position et de chaque lancer.

    Pas un échantillon : la notation est une fonction totale d'un jeu, et un
    échantillon laisserait passer précisément le cas rare — un jeu à quatre
    sous-coups dont deux seulement coïncident.
    """
    compared = 0
    with_bar = 0
    with_off = 0
    with_group = 0

    for position in _positions():
        for d1, d2 in ALL_ROLLS:
            for play in position.legal_plays(d1, d2):
                expected = _format_play_python(play, position.turn)
                got = play_notation(play, position.turn)
                assert got == expected, (
                    f"{position.turn} {d1}-{d2} : « {got} » au lieu de « {expected} »"
                )
                compared += 1
                if "bar" in got:
                    with_bar += 1
                if "off" in got:
                    with_off += 1
                if "(" in got:
                    with_group += 1

    # Un test qui n'aurait comparé que des coups ordinaires ne dirait rien des
    # trois formes qui distinguent cette notation d'une simple paire d'entiers.
    assert compared > 10_000, f"corpus trop maigre : {compared} jeux"
    assert with_bar > 0, "aucun coup depuis la barre dans le corpus"
    assert with_off > 0, "aucune sortie dans le corpus"
    assert with_group > 0, "aucun sous-coup répété dans le corpus"


def _corpus_position(identifier: str) -> Position:
    """Une position NOMMÉE du corpus T01, jamais une position inventée.

    Fabriquer un plateau à la main pour un test de notation, c'est risquer de
    tester une position que `gn_legal_plays` refuse — le corpus, lui, est
    valide par construction et ses cas de bord sont ceux qu'on veut.
    """
    import json

    if not CORPUS.is_file():
        pytest.skip("corpus T01 absent — lancer `make corpus`")
    with CORPUS.open() as handle:
        for line in handle:
            record = json.loads(line)
            if record["id"] == identifier:
                return Position(
                    points=tuple(record["points"]),
                    bar=tuple(record["bar"]),
                    off=tuple(record["off"]),
                    turn=record["turn"],
                )
    pytest.skip(f"position « {identifier} » absente du corpus")


def test_les_trois_formes_qui_comptent():
    """Les cas nommés, écrits en clair — un échec ici se lit sans déboguer."""
    opening = Position.initial()
    plays = {play_notation(p, WHITE) for p in opening.legal_plays(3, 1)}
    assert "6/5 8/5" in plays, plays

    doubles = {play_notation(p, WHITE) for p in opening.legal_plays(5, 5)}
    assert "8/3(2) 13/8(2)" in doubles, doubles

    # Depuis la barre : la renumérotation et le symbole `bar` en même temps,
    # c'est-à-dire les deux choses qui s'inversent le plus vite.
    from_bar = _corpus_position("un-seul-de-jouable-entree-unique")
    entries = {
        play_notation(p, from_bar.turn)
        for d1, d2 in ALL_ROLLS
        for p in from_bar.legal_plays(d1, d2)
    }
    assert any(n.startswith("bar/") for n in entries), entries


def test_un_jeu_vide_rend_la_chaine_vide():
    """La position où rien n'est jouable existe, et la réponse est vide.

    Elle n'est pas « pas de réponse » : un appelant doit pouvoir distinguer
    « aucun coup » d'une erreur, et une notation vide est la façon dont le
    Python le disait déjà (`if not order: return ""`).
    """
    from gammonnet import Play

    closed = _corpus_position("aucun-coup-legal-plateau-ferme")
    empty = Play(moves=(), result=closed)
    assert play_notation(empty, closed.turn) == ""
    assert _format_play_python(empty, closed.turn) == ""


def test_serve_delegue_vraiment_au_c():
    """Pas de seconde écriture qui coïnciderait par chance.

    Le contrôle est structurel, et il vise le mode d'échec réel : quelqu'un
    remet un jour une implémentation dans `tools/serve.py` « pour éviter une
    dépendance », les deux coïncident le jour même, et divergent six mois plus
    tard sans qu'aucun test ne le voie.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    source = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
    assert "play_notation" in source, "serve.py n'appelle plus la notation du C"
    assert "_point_number" not in source, (
        "serve.py a de nouveau sa propre renumérotation — c'est la deuxième "
        "vérité que T86 a supprimée"
    )
