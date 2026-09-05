"""Les formes canoniques (issue #25) — une source, lue et jamais retapée.

`ply = 2`, `filter = (0,1,3)`, `prune_k = 12` étaient recopiés à la main
jusqu'à cinq fois à travers ce dépôt et ses cibles, et le coût en
qualité de ce réglage — ce qui aurait dû empêcher un `prune_k = 3` "rapide"
introduit sans mesure — ne voyageait avec aucune de ces copies.

Ce fichier ne mesure rien de nouveau : il tient que `gn_search_level`
(`src/gn_search.c`) répond ce que ce fichier même documente en dur ici, en
Python, pour que toute dérive future entre le C et sa lecture Python casse
bruyamment plutôt que de se découvrir sur une décision de videau six mois
après.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.search import (  # noqa: E402
    SearchConfig,
    search_level,
    search_level_names,
)


def test_les_trois_niveaux_canoniques_existent():
    assert search_level_names() == ("instant", "normal", "thorough")


def test_instant_est_le_reseau_seul_sans_elagage():
    level = search_level("instant")
    assert level.ply == 0
    assert level.filter == (0, 0, 0, 0, 0)
    assert level.prune_k == 0
    assert level.prune_equity_loss == 0.0


def test_normal_est_2ply_filtre_013_elague_a_12():
    """Le défaut publié — mesuré T3A, 2026-08-26-T3A-regroupement.md."""
    level = search_level("normal")
    assert level.ply == 2
    assert level.filter == (0, 1, 3, 0, 0)
    assert level.prune_k == 12
    assert level.prune_equity_loss == pytest.approx(0.00023)
    assert level.prune_equity_loss_ci_low == pytest.approx(-0.00000)
    assert level.prune_equity_loss_ci_high == pytest.approx(0.00067)


def test_thorough_est_normal_sans_elagage():
    normal = search_level("normal")
    thorough = search_level("thorough")
    assert thorough.ply == normal.ply
    assert thorough.filter == normal.filter
    assert thorough.prune_k == 0
    assert thorough.prune_equity_loss == 0.0


def test_un_k_reduit_sans_mesure_amont_coute_dix_sept_fois_plus():
    """Le fait central de l'issue #25 : un `k` plus étroit que le défaut
    mesuré n'est PAS gratuit, et le rapport est publié, pas juste `k=12` isolé.

    `k=3` (le mode "rapide" introduit sans mesure amont, et depuis retiré)
    perd +0,00389 d'équité par décision contre
    +0,00023 pour `k=12` — dix-sept fois plus, pour deux fois la vitesse
    seulement (docs/mesures/2026-08-26-T3A-regroupement.md : x8,4 contre
    x3,6-3,9). Ce fichier ne rejoue pas la mesure de `k=3` — elle n'est pas un
    niveau canonique — il documente le nombre qui justifie de ne jamais en
    ajouter un sans lui.
    """
    normal = search_level("normal")
    k3_loss = 0.00389
    assert k3_loss / normal.prune_equity_loss == pytest.approx(16.9, abs=0.5)


def test_niveau_inconnu_refuse_plutot_que_deviner():
    with pytest.raises(ValueError, match="niveau inconnu"):
        search_level("fast")


def test_to_config_rend_une_searchconfig_utilisable():
    level = search_level("normal")
    config = level.to_config()
    assert isinstance(config, SearchConfig)
    assert config.ply == level.ply
    assert config.filter == level.filter
    # to_config() ne charge pas de réseau d'élagage -- c'est à l'appelant de
    # brancher celui qu'il veut avec `prune_net`/`prune_k`.
    assert config.prune_net is None


# ── L'export canonique (`tools/extract_search_levels.py`) ──────────────────


@pytest.fixture(scope="module")
def reference_export():
    """`data/search_levels.json`, l'export canonique, à lire au lieu de
    retranscrire ces nombres à la main -- sur le modèle de
    `data/met_kazaross_xg2.json` (issue #24)."""
    path = ROOT / "data" / "search_levels.json"
    if not path.is_file():
        pytest.skip("export canonique absent — voir tools/extract_search_levels.py")
    return json.loads(path.read_text())


def test_the_export_checksum_pin_is_current():
    """`data/search_levels.sha256` doit nommer l'empreinte réelle de l'export.

    Un pin périmé laisserait une copie embarquée se vérifier contre une
    empreinte qui ne décrit plus ce que ce dépôt génère réellement.
    """
    export = ROOT / "data" / "search_levels.json"
    pin = ROOT / "data" / "search_levels.sha256"
    if not export.is_file() or not pin.is_file():
        pytest.skip("export ou repère absent — voir tools/extract_search_levels.py")
    digest = hashlib.sha256(export.read_bytes()).hexdigest()
    recorded = pin.read_text().split()[0]
    assert digest == recorded, (
        f"data/search_levels.sha256 est périmé : {recorded}, "
        f"attendu {digest} — régénérer avec tools/extract_search_levels.py"
    )


def test_export_matches_gn_search_level_exactly(reference_export):
    """L'export JSON coïncide avec la table C, champ pour champ.

    Un test qui comparerait l'export à lui-même ne prouverait rien : celui-ci
    relit `gn_search_level` par le lien `ctypes` et compare, pour qu'une
    régénération qui aurait oublié un champ, ou un export édité à la main,
    casse ici plutôt que de se découvrir à l'usage.
    """
    for name, entry in reference_export["levels"].items():
        level = search_level(name)
        assert entry["ply"] == level.ply, name
        assert tuple(entry["filter"]) == level.filter[: level.ply + 1], name
        assert entry["prune_k"] == level.prune_k, name
        assert entry["prune_equity_loss"] == pytest.approx(level.prune_equity_loss), name
        assert entry["prune_equity_loss_ci"][0] == pytest.approx(
            level.prune_equity_loss_ci_low), name
        assert entry["prune_equity_loss_ci"][1] == pytest.approx(
            level.prune_equity_loss_ci_high), name
