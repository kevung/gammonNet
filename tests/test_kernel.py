"""T84 — le noyau écrit à la main reste bit à bit, à toutes les largeurs.

Le noyau de `src/gn_kernel_f32.h` est deux à quatre fois plus rapide que ce que
le compilateur produit, et **il ne déplace pas un bit** : vectoriser sur la
dimension du lot ne touche pas l'ordre de sommation (la voie `n` somme sur `j`
dans l'ordre scalaire, indépendamment des autres), et tuiler sur les lignes de
sortie non plus (la ligne `i` est une autre somme).

C'est un argument, et un argument ne suffit pas ici. Une seule façon de le
perdre suffirait à rendre le gain sans valeur : le FMA, qui arrondit une fois
là où multiplier puis additionner arrondit deux fois — et gcc contracte de
lui-même, y compris des intrinsèques écrites explicitement, dès qu'on oublie
`-ffp-contract=off`. Ce test construit le noyau aux trois largeurs et exige
`max|Δ| = 0` contre le chemin scalaire, position par position.

Il garde aussi la largeur : `GN_EVAL_BATCH` est une constante de compilation
surchargeable, et une largeur qui ne serait pas un nombre entier de vecteurs
doit casser le build (assertion de T90) plutôt que produire une queue que
personne n'a mesurée.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
PRUNE = ROOT / "models" / "prune_32.bin"

WIDTHS = [8, 16, 32]
#: Le noyau de base et le noyau écrit à la main. `auto` n'est pas décoratif :
#: si le chemin auto-vectorisé cassait, le test du noyau à la main ne dirait
#: pas lequel des deux a bougé.
KERNELS = ["auto", "intrin"]

MAX_DELTA = re.compile(r"max\|Δ\| = ([0-9.e+-]+)")


@pytest.fixture(scope="module")
def built() -> None:
    if not MODEL.exists() or not PRUNE.exists():
        pytest.skip("modèles absents — `make model` / `make fetch-release`")
    for width in WIDTHS:
        done = subprocess.run(
            ["make", "--no-print-directory", "kernel-variants", f"WIDTH={width}"],
            cwd=ROOT, capture_output=True, text=True,
        )
        if done.returncode != 0:
            pytest.skip(f"variantes de noyau non constructibles :\n{done.stderr[-2000:]}")


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("kernel", KERNELS)
def test_the_kernel_is_bit_for_bit_at_every_width(built, width, kernel):
    binary = ROOT / "build" / "kernel" / f"bench_{kernel}_{width}"
    done = subprocess.run(
        [str(binary), str(MODEL), str(PRUNE), "1", "1"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    delta = float(MAX_DELTA.search(done.stdout).group(1))
    assert delta == 0.0, (
        f"{kernel} à largeur {width} déplace le résultat de {delta:.3e} — "
        "un noyau plus rapide qui répond autre chose ne vaut rien ici"
    )


def test_a_width_that_is_not_a_whole_number_of_vectors_fails_the_build():
    """T90, sur son premier consommateur réel.

    Une largeur de 12 n'est pas un multiple des 8 voies d'un vecteur AVX. Le
    noyau n'a pas de queue scalaire — c'est ce qui garantit UN seul chemin
    compilé et donc un seul ordre de sommation — donc cette largeur doit
    arrêter le build, pas en faire pousser une.
    """
    done = subprocess.run(
        ["gcc", "-std=c11", "-O3", "-march=native", "-ffp-contract=off",
         "-DGN_EVAL_BATCH=12", "-DGN_KERNEL_INTRINSICS",
         "-Isrc", "-Ivendor/backgammon-ai-engine/c_engine",
         "-Ivendor/backgammon-ai-engine/c_inference",
         "-c", "src/gn_infer_reference.c", "-o", "/dev/null"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if "vendor" in done.stderr and "No such file" in done.stderr:
        pytest.skip("sources vendorées absentes")
    assert done.returncode != 0, "une largeur de 12 a compilé — l'assertion de T90 est morte"
    assert "whole number" in done.stderr or "tiles" in done.stderr, done.stderr[-800:]
