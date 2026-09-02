"""T90 — l'arrondi des tuiles : le garde-fou, et la preuve qu'il garde.

Le portage Go a écrit ``outDim & ^(tile-1)`` pour arrondir au multiple
inférieur. C'est correct **seulement** pour une puissance de deux : à tuile 6 la
valeur rendue n'est pas un multiple de la tuile, et la boucle lit une tuile de
poids **hors matrice**. Les tests ne l'ont pas vu parce que la tuile valait 4
quand ils ont été écrits.

Ce module ne raconte pas cette histoire, il l'exécute. ``tests/tile_asan.c``
est compilé à part sous AddressSanitizer — un débordement de trois flottants au
bout d'une ligne est invisible sans redzone — et il a deux volets :

* le volet **positif** : la postcondition de ``gn_round_down_multiple``, le
  masque et l'arrondi qui coïncident sur toute puissance de deux, et un noyau
  tuilé à tuile 6 sur une ligne allouée à la taille exacte ;
* le volet **négatif** (``--trap``) : la forme masquée, sur cette même ligne,
  **doit** mourir. Si elle survit, ce n'est pas que le code est sain, c'est
  qu'ASan ne tourne pas — et alors le volet positif ne prouve rien.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BINARY = ROOT / "build" / "tile_asan"


@pytest.fixture(scope="module")
def tile_asan() -> Path:
    build = subprocess.run(
        ["make", "--no-print-directory", str(BINARY.relative_to(ROOT))],
        cwd=ROOT, capture_output=True, text=True,
    )
    if build.returncode != 0 or not BINARY.exists():
        pytest.skip(f"tile_asan non constructible ici :\n{build.stderr}")
    return BINARY


def test_the_rounding_holds_at_a_tile_that_is_not_a_power_of_two(tile_asan):
    done = subprocess.run([str(tile_asan)], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "tout tient" in done.stdout


def test_the_masked_form_really_does_overrun(tile_asan):
    """Le volet négatif : sans lui, un ASan inactif passerait pour un code sain."""
    done = subprocess.run([str(tile_asan), "--trap"], capture_output=True, text=True)
    assert done.returncode != 0, (
        "la forme masquée n'a pas débordé : ASan ne tourne pas, "
        "donc le volet positif ne prouve rien\n" + done.stdout
    )
    assert "heap-buffer-overflow" in done.stderr
