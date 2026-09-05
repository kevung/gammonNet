"""T32 — la table d'équité de match, et les propriétés qui la démentiraient.

Une table de 625 nombres ne se relit pas. Ce qui se vérifie, ce sont ses
**propriétés** — antisymétrie, diagonale, monotonie, point de prise — et sa
concordance avec une implémentation indépendante.

Un chiffre faux dans une table d'équité de match ne fait rien planter : il fait
prendre un videau qu'il fallait passer, une fois sur mille, et personne ne le
voit jamais.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from gammonnet.infer import Evaluation
from gammonnet.met import MAX_AWAY, MatchState, post_crawford, pre_crawford

ROOT = Path(__file__).resolve().parent.parent


# ── Les propriétés de la table ───────────────────────────────────────


def test_antisymmetry_holds_over_the_whole_table():
    """`MET[i][j] + MET[j][i] = 1` — critère de `PLAN.md`, sans tolérance molle.

    Ce que gagne l'un, l'autre le perd. Une table qui viole cette identité
    décrit deux jeux différents selon le côté d'où on la lit.
    """
    worst = 0.0
    for i in range(1, MAX_AWAY + 1):
        for j in range(1, MAX_AWAY + 1):
            worst = max(worst, abs(pre_crawford(i, j) + pre_crawford(j, i) - 1.0))
    assert worst < 1e-12, f"antisymétrie violée de {worst:.3e}"


def test_the_diagonal_is_exactly_even():
    """À score égal, la partie est égale."""
    for away in range(1, MAX_AWAY + 1):
        assert pre_crawford(away, away) == pytest.approx(0.5, abs=1e-12)


def test_being_closer_to_the_finish_is_always_better():
    """Monotonie : à adversaire fixé, moins de points à marquer vaut mieux.

    Trivial à énoncer, et c'est bien pour ça que le test vaut : une inversion
    d'indices dans le générateur de table produirait une table parfaitement
    antisymétrique et pourtant retournée.
    """
    for opponent in range(1, MAX_AWAY + 1):
        values = [pre_crawford(a, opponent) for a in range(1, MAX_AWAY + 1)]
        assert values == sorted(values, reverse=True), (
            f"non monotone contre {opponent}-away"
        )


def test_post_crawford_favours_the_leader():
    """Le poursuivant n'est jamais favori, et d'autant moins qu'il est loin.

    À 1-away contre 1-away le match tient en une partie : 0,5 exactement, et
    non « strictement moins ». Le test l'a d'abord exigé strictement et la
    table l'a démenti — elle avait raison.
    """
    values = [post_crawford(a) for a in range(1, 25)]
    assert values[0] == pytest.approx(0.5, abs=1e-12), (
        "1-away contre 1-away post-Crawford tient en une partie : 0,5"
    )
    assert all(v < 0.5 for v in values[1:]), "le poursuivant serait favori"
    assert values == sorted(values, reverse=True), "non monotone"


def test_the_cube_comes_back_after_crawford():
    """Le post-Crawford est **meilleur** pour le poursuivant que la partie de Crawford.

    C'est l'inverse de ce qu'on suppose spontanément, et ce test a d'abord été
    écrit à l'envers. La règle de Crawford prive le poursuivant du videau
    **pour une seule partie** — celle que décrit `pre(a, 1)`. Une fois passée,
    il le récupère, et c'est précisément ce qui lui rend des chances.

    À 2-away, l'effet est spectaculaire : 0,488 contre 0,323. Le poursuivant
    redouble aussitôt, et une partie gagnée emporte le match.
    """
    for away in range(2, 25):
        assert post_crawford(away) > pre_crawford(away, 1), (
            f"le videau ne reviendrait pas au poursuivant à {away}-away"
        )


def test_post_crawford_has_the_even_odd_sawtooth():
    """Un nombre **pair** de points à marquer vaut bien mieux qu'un impair.

    Propriété classique du post-Crawford, et un bon garde-fou : une table
    lissée par erreur, ou ré-indexée d'un cran, perdrait cette dentelure sans
    perdre sa monotonie.
    """
    for even in range(2, 22, 2):
        drop_after_even = post_crawford(even) - post_crawford(even + 1)
        drop_after_odd = post_crawford(even + 1) - post_crawford(even + 2)
        assert drop_after_even > drop_after_odd, (
            f"pas de dentelure autour de {even}-away : "
            f"{drop_after_even:.5f} contre {drop_after_odd:.5f}"
        )


# ── Le point de prise près du money ──────────────────────────────────


def test_take_point_approaches_25_percent_in_a_long_match():
    """Critère de `PLAN.md` : ~25 % près du money game.

    Le point de prise sans mort du videau est de 25 % : sur un doublement à 2,
    prendre coûte 4 points quand on perd et en rapporte 2 quand on gagne, donc
    on prend dès que `p` dépasse `2 / (2 + 4)`. Dans un match long, l'équité de
    match devient quasi linéaire en points et doit retrouver ce chiffre.

    Le calcul est mené **dans la table**, pas sur une formule : on cherche la
    probabilité de gain à partir de laquelle prendre à 2 vaut mieux que passer.
    """
    away = MAX_AWAY  # aussi loin du match point que la table le permet
    passing = MatchState(away_on_roll=away, away_opponent=away).after(1, False)

    def taking(p: float) -> float:
        """MWC en prenant à 2 : gain simple avec probabilité p, sinon perte."""
        state = MatchState(away_on_roll=away, away_opponent=away, cube=2)
        return p * state.after(2, True) + (1.0 - p) * state.after(2, False)

    low, high = 0.0, 1.0
    for _ in range(60):
        middle = (low + high) / 2.0
        if taking(middle) < passing:
            low = middle
        else:
            high = middle

    assert 0.20 < low < 0.30, f"point de prise à {low:.3f}, ~0,25 attendu"
    print(f"\npoint de prise mesuré dans la table : {low * 100:.2f} %")


# ── Le contrôle croisé, qui est le vrai critère ──────────────────────


@pytest.fixture(scope="module")
def reference_met():
    """L'export canonique `data/met_kazaross_xg2.json` (#24), relu comme repère.

    Il est produit par `tools/extract_met.py` à partir des mêmes `pre`/`post`
    en mémoire que `src/gn_met_table.h` — un test qui comparerait la table C à
    elle-même ne prouverait rien. Ce que ce test vérifie, c'est qu'une
    régénération future n'a pas silencieusement décalé un indice entre les
    deux fichiers dérivés. C'est aussi cet export qu'on lit au lieu de
    retranscrire la table à la main.
    """
    path = ROOT / "data" / "met_kazaross_xg2.json"
    if not path.is_file():
        pytest.skip("export canonique absent — voir tools/extract_met.py")
    return json.loads(path.read_text())


def test_the_export_checksum_pin_is_current():
    """`data/met_kazaross_xg2.sha256` must name the export's actual digest.

    An embedded, byte-identical copy of `data/met_kazaross_xg2.json` is
    meant to be verified against this pin rather than reparsed field by
    field; a stale pin here would let that check pass against a copy that
    has quietly drifted from what this repository actually generates.
    """
    export = ROOT / "data" / "met_kazaross_xg2.json"
    pin = ROOT / "data" / "met_kazaross_xg2.sha256"
    if not export.is_file() or not pin.is_file():
        pytest.skip("export ou repère absent — voir tools/extract_met.py")
    digest = hashlib.sha256(export.read_bytes()).hexdigest()
    recorded = pin.read_text().split()[0]
    assert digest == recorded, (
        f"data/met_kazaross_xg2.sha256 est périmé : {recorded}, "
        f"attendu {digest} — régénérer avec tools/extract_met.py"
    )


def test_values_match_the_independent_implementation(reference_met):
    """Chaque entrée de la bibliothèque C coïncide avec l'export canonique."""
    worst = 0.0
    for entry in reference_met["pre"]:
        ours = pre_crawford(entry["away_a"], entry["away_b"])
        worst = max(worst, abs(ours - entry["mwc"]))
    for entry in reference_met["post"]:
        ours = post_crawford(entry["away"])
        worst = max(worst, abs(ours - entry["mwc"]))
    assert worst < 1e-9, f"écart maximal {worst:.3e} avec l'export canonique"


# ── La conversion, et ce qu'elle rend visible que le money cache ─────


def test_a_gammon_is_worth_more_at_some_scores_than_in_money():
    """À 2-away/2-away, un gammon gagne le match. En money il vaut deux points.

    C'est **la** raison d'être de `gn_met.h`, et la raison pour laquelle
    `gn_infer.h` refuse de rendre un scalaire : cette différence n'existe que si
    l'on a gardé la distribution.
    """
    # Deux évaluations de même équité money, l'une gammonnante, l'autre non.
    plain = Evaluation(win=0.60, win_gammon=0.00, win_backgammon=0.0,
                       lose_gammon=0.00, lose_backgammon=0.0)
    gammonish = Evaluation(win=0.50, win_gammon=0.20, win_backgammon=0.0,
                           lose_gammon=0.00, lose_backgammon=0.0)
    assert plain.money_equity == pytest.approx(gammonish.money_equity, abs=1e-9)

    money_like = MatchState(away_on_roll=25, away_opponent=25)
    assert money_like.winning_chance(plain) == pytest.approx(
        money_like.winning_chance(gammonish), abs=0.005
    ), "loin du match point, les deux devraient se valoir"

    # 2-away/2-away, videau à 1 : un gain simple ramène à 1-away, un gammon
    # marque deux points et **emporte le match**. C'est le score où les gammons
    # comptent le plus.
    #
    # Premier essai : 2-away/4-away avec le videau à 2 — et le test a échoué,
    # à juste titre. À ce score un gain SIMPLE marque déjà deux points et gagne
    # le match : le gammon n'ajoute rien, et seule P(gain) compte. La table
    # avait raison, l'exemple était mal choisi.
    critical = MatchState(away_on_roll=2, away_opponent=2, cube=1)
    assert critical.winning_chance(gammonish) > critical.winning_chance(plain) + 0.02, (
        "à 2-away/2-away le gammon devrait valoir nettement plus"
    )


def test_winning_chance_is_a_probability():
    """Toujours dans [0, 1], sur tous les scores et tous les videaux."""
    evaluation = Evaluation(0.55, 0.18, 0.02, 0.14, 0.01)
    for a in range(1, MAX_AWAY + 1):
        for b in range(1, MAX_AWAY + 1):
            for cube in (1, 2, 4):
                mwc = MatchState(a, b, cube).winning_chance(evaluation)
                assert 0.0 <= mwc <= 1.0, f"MWC = {mwc} à {a}/{b}, cube {cube}"


def test_a_certain_win_is_a_certain_match_win_at_match_point():
    """À 1-away, gagner la partie gagne le match. Sans table à consulter."""
    certain = Evaluation(win=1.0, win_gammon=0.0, win_backgammon=0.0,
                         lose_gammon=0.0, lose_backgammon=0.0)
    assert MatchState(1, 5).winning_chance(certain) == pytest.approx(1.0)

    certain_loss = Evaluation(win=0.0, win_gammon=0.0, win_backgammon=0.0,
                              lose_gammon=0.0, lose_backgammon=0.0)
    assert MatchState(5, 1).winning_chance(certain_loss) == pytest.approx(0.0)


def test_the_cube_scales_the_stakes():
    """Doubler le videau rapproche des deux extrémités du match."""
    evaluation = Evaluation(0.70, 0.20, 0.01, 0.05, 0.0)
    one = MatchState(5, 5, cube=1).winning_chance(evaluation)
    two = MatchState(5, 5, cube=2).winning_chance(evaluation)
    assert two > one, "avec l'avantage, doubler la mise devrait aider"


# ── Refuser plutôt qu'extrapoler ─────────────────────────────────────


def test_a_match_beyond_the_table_is_refused():
    """Au-delà de 25 points, refusé — jamais extrapolé.

    `BRIEF.md` prévoit un repli sur le modèle de Zadeh ; il n'est pas
    implémenté, et l'écart est consigné. Rendre une valeur inventée serait
    exactement le mode de défaillance que `CLAUDE.md` interdit.
    """
    with pytest.raises(ValueError):
        pre_crawford(26, 5)
    assert not MatchState(26, 5).is_valid

    evaluation = Evaluation(0.5, 0.1, 0.0, 0.1, 0.0)
    with pytest.raises(ValueError):
        MatchState(26, 5).winning_chance(evaluation)


def test_a_nonsensical_cube_is_refused():
    """Un videau qui n'est pas une puissance de deux mettrait toutes les mises
    à l'échelle de travers, silencieusement."""
    assert not MatchState(5, 5, cube=3).is_valid
    assert not MatchState(5, 5, cube=0).is_valid
    assert MatchState(5, 5, cube=8).is_valid


def test_a_finished_match_is_refused():
    """Un joueur à 0-away a déjà gagné : il n'y a rien à évaluer."""
    assert not MatchState(0, 5).is_valid
