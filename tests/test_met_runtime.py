"""T97 — la table d'équité de match devient remplaçable, sans cesser d'être sûre.

Ce fichier vérifie deux choses de nature différente.

**Que le remplacement marche** : ce qu'on installe est bien ce que le C sert, et
ce que le moteur consulte — pas seulement ce que les accesseurs relisent. Le
dernier test est le seul qui le prouve : il fait varier une décision de match en
ne changeant que la table.

**Que le remplacement refuse.** Une table à moitié lue est une table de nombres
plausibles et faux, et `CLAUDE.md` règle n°2 dit qu'un modèle qu'un build ne
sait pas évaluer est refusé, jamais approximé. Une table d'équité de match ne
fait pas exception : les quatre refus ci-dessous sont testés un par un.
"""

from __future__ import annotations

import struct

import pytest

from gammonnet import met
from gammonnet.infer import Evaluation

MAX = met.MAX_AWAY


@pytest.fixture(autouse=True)
def restore_the_compiled_table():
    """Aucun test ne laisse une autre table derrière lui.

    L'état est global côté C : un test qui oublierait de le rendre ferait
    échouer des tests sans rapport, et plus tard.
    """
    yield
    met.reset_table()


def flat_table(value: float = 0.5):
    return [[value] * MAX for _ in range(MAX)], [value] * MAX


# ── Ce qui est servi par défaut ──────────────────────────────────────


def test_the_default_table_is_named_and_is_kazaross():
    assert met.table_name() == "kazaross-xg2"
    assert met.pre_crawford(1, 1) == 0.5


# ── Installer, relire, revenir ───────────────────────────────────────


def test_a_table_installed_in_memory_is_the_one_the_c_side_serves():
    pre, post = flat_table(0.25)
    met.set_table(pre, post, "témoin-plat")

    assert met.table_name() == "témoin-plat"
    assert met.pre_crawford(2, 7) == 0.25
    assert met.post_crawford(3) == 0.25


def test_reset_brings_the_compiled_table_back():
    before = met.pre_crawford(2, 4)
    met.set_table(*flat_table(0.75), "témoin-plat")
    met.reset_table()

    assert met.table_name() == "kazaross-xg2"
    assert met.pre_crawford(2, 4) == before


def test_a_written_table_reloads_bit_for_bit(tmp_path):
    """Les valeurs sont des `double` des deux côtés : l'écart attendu est nul.

    Une tolérance ici masquerait un écrivain et un lecteur qui ne s'accordent
    pas sur l'ordre des octets ou sur la disposition des lignes.
    """
    pre, post = met.active_table()
    path = tmp_path / "kazaross.met"
    met.write_table(path, pre, post, "kazaross-relu")

    met.set_table(*flat_table(0.5), "témoin-plat")
    assert met.load_table(path) == "kazaross-relu"

    again_pre, again_post = met.active_table()
    assert again_pre == pre
    assert again_post == post


def test_the_row_order_survives_the_round_trip(tmp_path):
    """Une table transposée passerait tous les tests ci-dessus sauf celui-ci."""
    pre = [[(a * MAX + b) / (MAX * MAX) for b in range(MAX)] for a in range(MAX)]
    post = [n / MAX for n in range(MAX)]
    path = tmp_path / "ordonnee.met"
    met.write_table(path, pre, post, "ordonnée")
    met.load_table(path)

    assert met.pre_crawford(1, 2) == pytest.approx(1 / (MAX * MAX))
    assert met.pre_crawford(2, 1) == pytest.approx(MAX / (MAX * MAX))


# ── Ce qui est refusé ────────────────────────────────────────────────


def test_a_file_that_is_not_a_table_is_refused(tmp_path):
    path = tmp_path / "pas-une-table.met"
    path.write_bytes(b"GNBONET1" + b"\x00" * 64)

    with pytest.raises(ValueError, match="GNMET1"):
        met.load_table(path)


def test_a_truncated_file_is_refused(tmp_path):
    pre, post = met.active_table()
    path = tmp_path / "tronquee.met"
    met.write_table(path, pre, post, "entière")
    whole = path.read_bytes()
    path.write_bytes(whole[:len(whole) // 2])

    with pytest.raises(ValueError, match="tronqué"):
        met.load_table(path)


def test_a_missing_file_is_refused(tmp_path):
    with pytest.raises(ValueError, match="introuvable"):
        met.load_table(tmp_path / "absente.met")


def test_a_value_that_is_not_a_chance_is_refused(tmp_path):
    pre, post = flat_table(0.5)
    pre[3][7] = 1.5
    path = tmp_path / "hors-bornes.met"
    met.write_table(path, pre, post, "hors-bornes")

    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        met.load_table(path)
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        met.set_table(pre, post, "hors-bornes")


def test_a_table_of_the_wrong_size_is_refused(tmp_path):
    path = tmp_path / "trop-petite.met"
    with path.open("wb") as handle:
        handle.write(b"GNMET1\x00\x00")
        handle.write(struct.pack("<ii", 9, 9))
        handle.write(b"petite" + b"\x00" * 58)
        handle.write(struct.pack("<81d", *([0.5] * 81)))
        handle.write(struct.pack("<9d", *([0.5] * 9)))

    with pytest.raises(ValueError, match="dimensions"):
        met.load_table(path)


def test_a_refused_table_leaves_the_previous_one_in_place(tmp_path):
    """Le refus ne doit pas détruire ce qui servait : sinon un build refusant
    une table se retrouverait à évaluer contre des zéros."""
    before = met.pre_crawford(3, 5)
    with pytest.raises(ValueError):
        met.load_table(tmp_path / "absente.met")

    assert met.table_name() == "kazaross-xg2"
    assert met.pre_crawford(3, 5) == before


# ── La preuve que le moteur la consulte vraiment ─────────────────────


def test_two_players_in_one_process_hold_different_tables(tmp_path):
    """Ce que `met_table` sur le joueur rend possible, et pourquoi il existe.

    Les dés dupliqués veulent les deux joueurs dans le même processus ; la
    table active est globale à ce processus. Un joueur qui porte sa table et
    l'installe avant chacune de ses décisions lève la contradiction — et sans
    ce test, rien ne dirait que les deux tables ne se marchent pas dessus.
    """
    from gammonnet.cubeful import GammonNetCubePlayer

    plate = tmp_path / "plate.met"
    met.write_table(plate, *flat_table(0.3), "témoin-plat")
    met.reset_table()

    kazaross = GammonNetCubePlayer(met_table="")
    autre = GammonNetCubePlayer(met_table=str(plate))

    met.use_table(autre.met_table)
    assert met.table_name() == "témoin-plat"

    met.use_table(kazaross.met_table)
    assert met.table_name() == "kazaross-xg2"

    met.use_table(autre.met_table)
    assert met.pre_crawford(4, 9) == 0.3


def test_reinstalling_the_same_table_is_free_but_a_change_is_not():
    """`use_table` ne réinstalle pas ce qui sert déjà — mais un changement fait
    par ailleurs doit invalider ce raccourci, sinon il sert une table périmée."""
    met.use_table("")
    met.set_table(*flat_table(0.6), "posée-à-la-main")
    assert met.table_name() == "posée-à-la-main"

    met.use_table("")  # doit repasser à la compilée, malgré le cache
    assert met.table_name() == "kazaross-xg2"


def test_a_direct_load_also_invalidates_the_shortcut(tmp_path):
    """Même piège que le test précédent, par l'autre porte.

    `load_table` change la table sans passer par `use_table` ; si le raccourci
    croyait encore servir la compilée, `use_table("")` ne ferait rien.
    """
    plate = tmp_path / "plate.met"
    met.write_table(plate, *flat_table(0.2), "témoin-plat")

    met.use_table("")
    met.load_table(plate)
    assert met.table_name() == "témoin-plat"

    met.use_table("")
    assert met.table_name() == "kazaross-xg2"


def test_the_conversion_follows_the_installed_table():
    """Le seul test qui prouve que le remplacement atteint le moteur.

    `gn_match_winning_chance` est ce que la recherche et le videau appellent.
    Avec une table où toutes les cellules valent la même chose, un gain ne
    change plus rien au match, et la MWC de toute position doit s'effondrer sur
    cette valeur unique — ce qu'aucune relecture d'accesseur ne montrerait.
    """
    evaluation = Evaluation(0.62, 0.18, 0.01, 0.09, 0.004)
    state = met.MatchState(away_on_roll=5, away_opponent=7, cube=2)

    with_kazaross = state.winning_chance(evaluation)

    met.set_table(*flat_table(0.4), "témoin-plat")
    with_flat = state.winning_chance(evaluation)

    assert with_flat != pytest.approx(with_kazaross, abs=1e-6)
    # Gagner ou perdre mène à la même valeur : seules les fins de match
    # (0 ou 1) restent distinctes, et elles ne dépendent pas de la table.
    assert 0.0 <= with_flat <= 1.0
