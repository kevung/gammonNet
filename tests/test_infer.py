"""T10 — le réseau chargé par notre code répond ce que PyTorch répond.

Ce que ce fichier vérifie, et ce qu'il ne vérifie pas
─────────────────────────────────────────────────────
Les deux côtés reçoivent **le même vecteur de 196 flottants**, produit par notre
encodeur C. Ce test isole donc le **chargement des poids et la passe avant** ;
il ne dit rien de la justesse de l'encodage, qui est le travail de T02 et de
`test_codec.py`. Le dire est important : si les deux côtés partageaient un
encodeur faux, ce test passerait quand même. Il n'est pas conçu pour l'attraper,
et le corpus figé de T12 ne le sera pas davantage.

Ce qui est vérifié ici :

  * parité PyTorch à `max|Δ| < 1e-5` sur ≥ 1 000 positions ;
  * les inégalités d'événements imbriqués tiennent sur **tout** le corpus ;
  * la formule d'équité money coïncide avec la réduction de `nn_eval.c` ;
  * un modèle que ce build ne sait pas évaluer est **refusé**, jamais approximé.
"""

from __future__ import annotations

import random
import struct
import sys
from pathlib import Path

import pytest

from gammonnet import BLACK, WHITE, Position
from gammonnet import codec
from gammonnet.infer import NUM_OUTPUTS, Evaluation, Network, _f32

torch = pytest.importorskip("torch", reason="PyTorch absent — lancer `make venv`")

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "vendor" / "backgammon-ai-engine"
MODEL_PT = REFERENCE / "best_models" / "cubeless_prob5_512_512_256_128.pt"
MODEL_BIN = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"

SEED = 20260803
CORPUS_SIZE = 2_000

# Le critère de T10. Nos poids sont des float32 des deux côtés, mais l'ordre des
# opérations diffère (BLAS contre boucles C), donc l'écart n'est pas nul par
# construction — il est borné.
TOLERANCE = 1e-5


# ── Le corpus ────────────────────────────────────────────────────────


def build_corpus(size: int) -> list[Position]:
    """`size` positions tirées de parties aléatoires, à graine fixe.

    Même construction que `test_codec.py`, pour que les deux tâches parlent des
    mêmes positions. Les deux couleurs jouent : un corpus où Blanc serait
    toujours au trait ne détecterait pas une erreur qui ne frappe qu'une couleur.
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


# ── Les deux côtés ───────────────────────────────────────────────────


@pytest.fixture(scope="module")
def network() -> Network:
    if not MODEL_BIN.is_file():
        pytest.skip(f"{MODEL_BIN} absent — lancer `make model`")
    with Network.load(MODEL_BIN) as net:
        yield net


@pytest.fixture(scope="module")
def torch_forward():
    """La passe avant de référence, telle que le dépôt amont la définit.

    Reproduit exactement `export_weights.verify_export` : sigmoïde si le modèle
    sort des logits bruts, puis `prob5_postprocess`. Le clamp fait partie de la
    référence — c'est lui qui rend la sortie utilisable comme distribution.
    """
    if not MODEL_PT.is_file():
        pytest.skip("vendor/backgammon-ai-engine absent — lancer `make vendor`")

    sys.path.insert(0, str(REFERENCE))
    try:
        from model import load_model, prob5_postprocess

        model = load_model(str(MODEL_PT))
        model.eval()

        def forward(features):
            x = torch.tensor(list(features), dtype=torch.float32)[None, :]
            with torch.no_grad():
                out = model(x)
                if getattr(model, "raw_logits", False):
                    out = torch.sigmoid(out)
                out = prob5_postprocess(out)
            return [float(v) for v in out[0]]

        yield forward
    finally:
        sys.path.remove(str(REFERENCE))


# ── Le corpus lui-même ───────────────────────────────────────────────


def test_corpus_is_reproducible_and_plays_both_colours():
    assert len(CORPUS) == CORPUS_SIZE
    assert build_corpus(200) == CORPUS[:200], "corpus non reproductible à graine fixe"
    assert {p.turn for p in CORPUS} == {WHITE, BLACK}, "une seule couleur au trait"


# ── Le critère central ───────────────────────────────────────────────


def test_five_outputs_match_pytorch(network, torch_forward):
    """`max|Δ| < 1e-5` entre notre code et PyTorch, sur ≥ 1 000 positions."""
    worst = 0.0
    worst_at = None

    for position in CORPUS:
        features = codec.encode(position)
        ours = network.evaluate_features(features).as_tuple()
        theirs = torch_forward(features)

        for k in range(NUM_OUTPUTS):
            delta = abs(ours[k] - theirs[k])
            if delta > worst:
                worst, worst_at = delta, (position, k)

    assert worst < TOLERANCE, (
        f"max|Δ| = {worst:.3e} ≥ {TOLERANCE:.0e}, sortie {worst_at[1]} "
        f"sur {worst_at[0]}"
    )
    print(f"\nmax|Δ| = {worst:.3e} sur {CORPUS_SIZE} positions × {NUM_OUTPUTS} sorties")


def test_evaluate_from_position_agrees_with_evaluate_from_features(network):
    """Les deux portes d'entrée donnent le même résultat, au bit près.

    `gn_evaluate` encode puis évalue ; `gn_evaluate_features` évalue un vecteur
    déjà encodé. La recherche empruntera la seconde. Si elles divergeaient, le
    2-ply n'évaluerait pas ce que le 0-ply évalue.
    """
    for position in CORPUS[:500]:
        assert network.evaluate(position).as_tuple() == pytest.approx(
            network.evaluate_features(codec.encode(position)).as_tuple(), abs=0.0
        )


# ── Les inégalités d'événements imbriqués ────────────────────────────


def test_nested_event_inequalities_hold_everywhere(network):
    """P(gain) ≥ P(gain-gammon) ≥ P(gain-bg), et de même côté perte.

    Les cinq sorties viennent de cinq sigmoïdes **indépendantes** : rien dans le
    réseau ne garantit ces inégalités. C'est le clamp de `nn_eval.c:211-215` qui
    les impose, et ce test vérifie qu'il a réellement tourné. Une distribution
    qui les viole n'est pas une distribution.

    **Les comparaisons se font en float32**, l'arithmétique du réseau et de
    `nn_eval.c`. Les mener en float64 fabriquerait un échec sur un calcul qui
    n'a jamais eu lieu : quand `P(gain)` vaut 1,5e-10, `1.0f - P(gain)` est
    exactement `1.0f`, et un `P(perte-gammon)` de 1,0 satisfait bien
    l'inégalité — le clamp n'avait rien à corriger. Voir
    `test_exclusive_outcomes_are_never_negative` pour l'autre face du problème,
    celle qui compte pour un appelant travaillant en double.
    """
    for position in CORPUS:
        e = network.evaluate(position)
        assert _f32(e.win_gammon) <= _f32(e.win), f"P(wg) > P(win) sur {position}"
        assert _f32(e.win_backgammon) <= _f32(e.win_gammon), f"P(wbg) > P(wg) sur {position}"
        assert _f32(e.lose_gammon) <= _f32(1.0 - _f32(e.win)), f"P(lg) > P(lose) sur {position}"
        assert _f32(e.lose_backgammon) <= _f32(e.lose_gammon), f"P(lbg) > P(lg) sur {position}"
        assert e.is_nested


def test_the_c_side_agrees_that_the_distribution_is_nested(network):
    """`gn_probs_are_nested` confirme, côté C, ce que le test précédent vérifie.

    Le C compare en float32 nativement : c'est la même propriété, établie sans
    passer par notre reproduction Python de son arithmétique.
    """
    from gammonnet.infer import _LIB, _ProbArray

    for position in CORPUS:
        buffer = _ProbArray(*network.evaluate(position).as_tuple())
        assert _LIB.gn_probs_are_nested(buffer) == 1, f"non imbriquée sur {position}"


def test_exclusive_outcomes_are_never_negative(network):
    """Le dénestage ne produit jamais de probabilité négative.

    Trouvé par ce test, sur une position réelle du corpus : `P(gain)` = 1,5e-10
    et `P(perte-gammon)` = 1,0. En float32 — l'arithmétique du moteur —
    `1.0f - P(gain)` vaut exactement `1.0f`, l'inégalité tient, rien n'est
    écrêté, et c'est juste. Mais un appelant qui dénesterait en float64
    obtiendrait `P(perte simple) = -1,5e-10`. Une probabilité négative sur le
    chemin de la table d'équité de match : minuscule, silencieuse, et
    exactement le mode de défaillance que `CLAUDE.md` refuse.
    """
    for position in CORPUS:
        outcomes = network.evaluate(position).exclusive
        for name, value in zip(
            ("wS", "wG", "wBG", "lS", "lG", "lBG"), outcomes.as_tuple()
        ):
            assert value >= 0.0, f"{name} = {value} < 0 sur {position}"


def test_exclusive_outcomes_sum_to_one(network):
    """Les six issues forment une partition. Somme = 1, à l'arrondi float32 près."""
    for position in CORPUS:
        total = network.evaluate(position).exclusive.total
        assert total == pytest.approx(1.0, abs=1e-6), f"somme = {total} sur {position}"


def test_the_two_equity_paths_agree(network):
    """Contrôle croisé : équité depuis les imbriquées = équité depuis les exclusives.

    Deux chemins arithmétiques distincts vers le même nombre. Une divergence
    signalerait que le dénestage a perdu de la masse — ce qu'un simple test de
    signe ne verrait pas.
    """
    for position in CORPUS[:500]:
        evaluation = network.evaluate(position)
        assert evaluation.money_equity == pytest.approx(
            evaluation.exclusive.money_equity, abs=1e-6
        )


def test_clamp_is_not_vacuous(network, torch_forward):
    """Le clamp n'est pas décoratif : sans lui, le corpus violerait les inégalités.

    Un test qui vérifie une propriété que rien ne menace ne prouve rien. Ici on
    prend la sortie **avant** clamp et l'on exige qu'elle viole les inégalités
    au moins une fois — sinon le test précédent serait sans objet, et il faudrait
    le savoir.
    """
    sys.path.insert(0, str(REFERENCE))
    try:
        from model import load_model

        model = load_model(str(MODEL_PT))
        model.eval()

        violations = 0
        for position in CORPUS[:500]:
            x = torch.tensor(list(codec.encode(position)), dtype=torch.float32)[None, :]
            with torch.no_grad():
                raw = model(x)
                if getattr(model, "raw_logits", False):
                    raw = torch.sigmoid(raw)
            p = [float(v) for v in raw[0]]
            if p[1] > p[0] or p[2] > p[1] or p[3] > 1.0 - p[0] or p[4] > p[3]:
                violations += 1
    finally:
        sys.path.remove(str(REFERENCE))

    assert violations > 0, (
        "aucune violation avant clamp sur 500 positions : le test du clamp "
        "ne prouve rien, il faut un corpus qui le mette réellement à l'épreuve"
    )
    print(f"\nclamp non trivial : {violations}/500 positions violaient les inégalités")


# ── L'équité money, dérivée et non primaire ──────────────────────────


def test_money_equity_matches_the_reference_reduction(network):
    """Notre équité coïncide avec `prob5_reduce` de `nn_eval.c:217`."""
    from gammonnet.infer import _LIB, _ProbArray

    for position in CORPUS[:500]:
        e = network.evaluate(position)
        buffer = _ProbArray(*e.as_tuple())
        assert e.money_equity == pytest.approx(_LIB.gn_money_equity(buffer), abs=1e-6)


def test_money_equity_stays_in_range(network):
    """Une équité cubeless money vit dans [-3, +3] — backgammon des deux côtés."""
    for position in CORPUS:
        assert -3.0 <= network.evaluate(position).money_equity <= 3.0


# ── Refuser plutôt qu'approximer ─────────────────────────────────────


def test_a_model_this_build_cannot_evaluate_is_refused(tmp_path):
    """Un modèle non-prob5 est refusé, pas exécuté.

    `CLAUDE.md`, règle 2. Un modèle *cubeful money* sort une équité agrégée : il
    se chargerait, il évaluerait, et il rendrait des nombres inutilisables en
    match — sans le moindre signe extérieur.
    """
    cubeful = REFERENCE / "best_models" / "cubeful_money_512_512_256.pt"
    if not cubeful.is_file():
        pytest.skip("modèle cubeful absent du dépôt de référence")

    import subprocess

    target = tmp_path / "cubeful.bin"
    result = subprocess.run(
        [sys.executable, "export_weights.py", str(cubeful), str(target)],
        cwd=REFERENCE, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    with pytest.raises(ValueError, match="refusé"):
        Network.load(target)


def test_a_truncated_file_is_refused(tmp_path):
    """Un fichier tronqué est refusé, pas complété par des zéros."""
    truncated = tmp_path / "truncated.bin"
    truncated.write_bytes(MODEL_BIN.read_bytes()[: 1 << 12])
    with pytest.raises(ValueError, match="refusé"):
        Network.load(truncated)


def test_a_file_with_a_wrong_magic_is_refused(tmp_path):
    """Le magic `BGNN` est vérifié."""
    corrupted = tmp_path / "corrupted.bin"
    payload = bytearray(MODEL_BIN.read_bytes())
    payload[0:4] = b"XXXX"
    corrupted.write_bytes(bytes(payload))
    with pytest.raises(ValueError, match="refusé"):
        Network.load(corrupted)


def test_the_header_says_what_we_expect(network):
    """L'en-tête du `.bin` décrit bien le modèle que `BRIEF.md` §3.1 retient."""
    with MODEL_BIN.open("rb") as handle:
        magic = handle.read(4)
        num_hidden, input_size, activation, output_mode = struct.unpack("<4i", handle.read(16))
        hidden = struct.unpack(f"<{num_hidden}i", handle.read(4 * num_hidden))

    assert magic == b"BGNN"
    assert input_size == codec.NUM_FEATURES == 196
    assert output_mode == 2, "mode de sortie prob5 attendu"
    assert activation == 0, "relu attendu"
    assert list(hidden) == [512, 512, 256, 128]
    assert network.input_size == 196
