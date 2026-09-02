"""T73 — les primitives de quantification, et pourquoi les échelles sont des
puissances de deux.

## La contrainte qui commande tout le reste

Une couche quantifiée accumule en int32 le produit de poids int8 par des
activations int8, puis doit ramener ce résultat à l'échelle de la couche
suivante. Cette remise à l'échelle est le seul endroit du chemin int8 où deux
cibles pourraient diverger :

- **facteur quelconque** — il faut multiplier par un flottant, ou par un entier
  suivi d'un arrondi. L'arrondi a une convention, la convention a des variantes,
  et l'égalité bit-à-bit natif↔Wasm redevient quelque chose qu'on espère.
- **puissance de deux** — la remise à l'échelle est un DÉCALAGE. Un décalage
  arithmétique est exact, sans convention, identique partout.

D'où la règle de T73, reprise ici sans exception : toute échelle est `2^-k`. Le
prix est réel — on perd en moyenne un demi-bit de dynamique par tenseur — et il
se paie à l'entraînement, que la QAT est justement là pour faire.

## Par canal, pas par tenseur

L'échelle des poids est calculée **par ligne de sortie**. Un neurone dont les
poids sont petits ne doit pas voir sa précision détruite par un voisin dont les
poids sont grands, et cela ne coûte qu'un entier par ligne. La mesure du
2026-08-04 a chiffré ce que la quantification post-entraînement coûte en jeu —
4,92 % de coups changés, ~12 % de l'avantage du modèle — et c'est précisément
pourquoi T73 exige la QAT plutôt que la PTQ : ici, le réseau apprend à vivre
avec l'arrondi au lieu de le subir.
"""

from __future__ import annotations

import math

#: Le plafond de la ClippedReLU. Les activations vivent dans 0..127, le bit de
#: signe inutilisé, pour qu'un poids int8 les multiplie sans élargissement.
ACTIVATION_MAX = 127

#: Les poids vivent dans -127..127 et non -128..127 : la borne symétrique évite
#: qu'une seule valeur du domaine n'ait pas d'opposé, ce qui rendrait la
#: quantification d'un tenseur et de son opposé non symétriques.
WEIGHT_MAX = 127


def power_of_two_shift(maximum: float, levels: int = WEIGHT_MAX) -> int:
    """Le `k` tel que `2^-k` soit la plus FINE échelle qui ne sature pas.

    « Ne sature pas » veut dire `maximum / 2^-k <= levels`. Parmi les échelles
    qui satisfont cela, on veut la plus fine — c'est-à-dire le plus GRAND `k` —
    parce qu'une échelle plus grossière gaspillerait de la résolution sans rien
    protéger : la saturation est déjà écartée. Monter d'un cran de plus, en
    revanche, écrête ; et un écrêtage silencieux est exactement la perte que la
    mesure du 2026-08-04 a chiffrée à ~12 % de l'avantage du modèle.

    Le premier jet de cette docstring disait « la plus grande échelle », ce qui
    est l'inverse : le code était juste, sa description ne l'était pas, et le
    test écrit d'après la description a échoué — ce pour quoi il était là.

    Un tenseur nul rend 0 : il n'y a rien à représenter, et toute échelle
    convient également.
    """
    if maximum <= 0.0 or not math.isfinite(maximum):
        return 0
    # 2^-k >= maximum / levels  <=>  k <= log2(levels / maximum)
    return max(0, math.ceil(math.log2(maximum / levels)) * -1)


def scale_of(shift: int) -> float:
    """L'échelle `2^-shift`, comme un flottant exact."""
    return 2.0 ** (-shift)


def quantize_per_channel(rows: list[list[float]], levels: int = WEIGHT_MAX):
    """Un tenseur de poids en int8, une échelle par ligne de sortie.

    Rend `(entiers, décalages)`. Chaque ligne porte son propre `2^-k`, et la
    déquantification d'une ligne est `entier * 2^-k` — exacte, puisque les deux
    facteurs le sont.
    """
    quantized: list[list[int]] = []
    shifts: list[int] = []
    for row in rows:
        maximum = max((abs(value) for value in row), default=0.0)
        shift = power_of_two_shift(maximum, levels)
        scale = scale_of(shift)
        # `round` de Python arrondit au pair le plus proche ; c'est la
        # convention retenue et elle n'a pas à changer, car cette fonction ne
        # tourne QUE hors ligne. Le chemin d'exécution, lui, ne voit que des
        # entiers et un décalage.
        line = [max(-levels, min(levels, round(value / scale))) for value in row]
        quantized.append(line)
        shifts.append(shift)
    return quantized, shifts


def dequantize_per_channel(quantized: list[list[int]], shifts: list[int]):
    """L'opération inverse, exacte."""
    return [[value * scale_of(shift) for value in row]
            for row, shift in zip(quantized, shifts)]


def requantization_shift(weight_shift: int, input_shift: int,
                         output_shift: int) -> int:
    """Le décalage qui ramène un accumulateur à l'échelle de la couche suivante.

    L'accumulateur est en unités de `2^-(weight_shift + input_shift)`. La sortie
    doit être en unités de `2^-output_shift`. Le décalage vaut donc la
    différence — et il doit être POSITIF : un décalage négatif serait un
    décalage à gauche, c'est-à-dire de la dynamique inventée là où il n'y en a
    pas. On lève plutôt que de le tolérer, parce qu'un décalage négatif silencieux
    rendrait des activations plausibles et fausses.
    """
    shift = weight_shift + input_shift - output_shift
    if shift < 0:
        raise ValueError(
            f"décalage négatif ({shift}) : l'échelle de sortie 2^-{output_shift} "
            f"est plus fine que ce que l'accumulateur porte "
            f"(2^-{weight_shift + input_shift}). Réduire output_shift.")
    return shift


def clipped_relu(value: float, maximum: int = ACTIVATION_MAX) -> float:
    """L'activation du chemin int8 : `min(max(x, 0), 127)`.

    Ce n'est pas la ReLU du réseau flottant, et la différence n'est pas
    cosmétique : le plafond change ce que le réseau peut représenter. Un réseau
    entraîné en ReLU puis plafonné n'est pas le même réseau — c'est la raison
    pour laquelle T73 exige un entraînement conscient de la quantification, et
    non une conversion après coup.
    """
    return min(max(value, 0.0), float(maximum))


def accumulator_headroom(cols: int) -> float:
    """La marge int32 d'une couche de `cols` entrées, en facteur.

    Répète `gn_gemm_int8_headroom` du C pour que le pipeline d'entraînement
    puisse refuser une architecture que le noyau refuserait — plutôt que de
    l'apprendre à l'exportation, après des heures de GPU.
    """
    if cols <= 0:
        return 0.0
    return 2147483647.0 / (cols * WEIGHT_MAX * ACTIVATION_MAX)
