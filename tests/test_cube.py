"""T34 — le modèle de videau, et les propriétés qui le démentiraient.

`docs/specs/t34-videau-spec.md` fixe le modèle à la lettre : ce fichier suit
son plan de vérification, §6, dans l'ordre. Rien ici ne teste un chiffre choisi
au hasard — chaque assertion cite le paragraphe de la spécification dont elle
vérifie l'ancrage, sauf la section « match », où le comportement post-Crawford
est explicitement censé **émerger** plutôt que d'être codé : ces tests
constatent ce que `gn_cube_decide` a produit, une fois lancé et lu, pas ce
qu'on en attendait avant de le lancer.
"""

from __future__ import annotations

import pytest

from gammonnet.cube import CubeAction, CubeInputs, CubeOwner, decide
from gammonnet.infer import Evaluation
from gammonnet.met import MatchState

# Une efficacité de plan de travail — la mesure de T34 (bench/fit_efficiency.py)
# fournit la valeur définitive ; les propriétés vérifiées ici doivent tenir
# pour N'IMPORTE QUELLE efficacité dans (0, 1), donc le choix précis importe peu.
X = 0.68


def gammonless(p: float) -> Evaluation:
    """Une position sans gammon possible des deux côtés, à P(gain) = p."""
    return Evaluation(win=p, win_gammon=0.0, win_backgammon=0.0,
                      lose_gammon=0.0, lose_backgammon=0.0)


def with_gammons(p: float, wg: float, lg: float) -> Evaluation:
    return Evaluation(win=p, win_gammon=wg, win_backgammon=0.0,
                      lose_gammon=lg, lose_backgammon=0.0)


# ── §2 : les deux limites exactes, aux points d'ancrage ──────────────


def test_gammonless_take_and_cash_points():
    """W = L = 1 : TP_dead = 0,25, TP_live = 0,20, CP_dead = 0,75, CP_live = 0,80.

    Les quatre chiffres cités par la spécification, lus directement dans
    `gn_cube_take_point` — `owner=CENTRED`/`OPPONENT` rend `TP(x)`,
    `owner=OWNED` rend `CP(x)` (voir le commentaire de `gn_cube_take_point`
    en C pour pourquoi c'est ce paramètre qui choisit entre les deux).
    """
    inputs = CubeInputs.from_evaluation(gammonless(0.5))
    assert inputs.take_point(CubeOwner.CENTRED, 0.0) == pytest.approx(0.25, abs=1e-12)
    assert inputs.take_point(CubeOwner.CENTRED, 1.0) == pytest.approx(0.20, abs=1e-12)
    assert inputs.take_point(CubeOwner.OWNED, 0.0) == pytest.approx(0.75, abs=1e-12)
    assert inputs.take_point(CubeOwner.OWNED, 1.0) == pytest.approx(0.80, abs=1e-12)


def test_w2_l1_take_points():
    """W = 2, L = 1 : TP_dead = 1/6, TP_live = 1/7 — le second ancrage de §2."""
    # win=0.5 gammon+2/3 des gains -> P(gammon|gain)=1, donc W = 1 + 1 = 2 ;
    # aucune perte-gammon -> L = 1. `CubeInputs.from_evaluation` fait le calcul ;
    # ce test choisit juste une distribution qui le force.
    inputs = CubeInputs.from_evaluation(with_gammons(0.5, wg=0.5, lg=0.0))
    assert inputs.win_points == pytest.approx(2.0)
    assert inputs.lose_points == pytest.approx(1.0)
    assert inputs.take_point(CubeOwner.CENTRED, 0.0) == pytest.approx(1.0 / 6.0, abs=1e-12)
    assert inputs.take_point(CubeOwner.CENTRED, 1.0) == pytest.approx(1.0 / 7.0, abs=1e-12)


def test_redouble_recursion_matches_the_closed_form():
    """La récursion de re-doublement de §2, résolue ICI en Python, coïncide
    avec `TP_live` à 1e-12 — le contrôle d'indépendance que la spécification
    exige : une deuxième implémentation, écrite sans consulter le C.

        TP  = (L - 1/2)(1 - TP') / (1 + L)
        TP' = (W - 1/2)(1 - TP)  / (1 + W)
    """
    for W, L in [(1.0, 1.0), (2.0, 1.0), (1.5, 2.5), (3.0, 1.0)]:
        tp, tp_prime = 0.5, 0.5
        for _ in range(500):
            tp, tp_prime = (
                (L - 0.5) * (1.0 - tp_prime) / (1.0 + L),
                (W - 0.5) * (1.0 - tp) / (1.0 + W),
            )
        closed_form = (L - 0.5) / (W + L + 0.5)
        assert tp == pytest.approx(closed_form, abs=1e-12), f"W={W}, L={L}"

        inputs = CubeInputs(win=0.5, win_points=W, lose_points=L)
        assert inputs.take_point(CubeOwner.CENTRED, 1.0) == pytest.approx(closed_form, abs=1e-12)


# ── §2 : les équités vivantes, à p = 0,5, gammonless ──────────────────


def test_live_equities_at_half_gammonless():
    """Les valeurs classiques du modèle continu : possédé +0,25, adverse
    -0,25, centré 0."""
    inputs = CubeInputs.from_evaluation(gammonless(0.5))
    assert inputs.equity(CubeOwner.OWNED, 1, 1.0) == pytest.approx(0.25, abs=1e-9)
    assert inputs.equity(CubeOwner.OPPONENT, 1, 1.0) == pytest.approx(-0.25, abs=1e-9)
    assert inputs.equity(CubeOwner.CENTRED, 1, 1.0) == pytest.approx(0.0, abs=1e-9)


# ── §6.1 : les propriétés génériques ──────────────────────────────────


_W_L_GRID = [(1.0, 1.0), (2.0, 1.0), (1.0, 2.0), (1.7, 1.3), (2.5, 2.0)]
_P_GRID = [0.01, 0.05, 0.15, 0.25, 0.4, 0.5, 0.6, 0.75, 0.85, 0.95, 0.99]
_X_GRID = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]


def test_take_point_decreases_with_efficiency():
    """`TP(x)` décroît en `x` : un videau plus vivant prend plus de risque à
    laisser vivre, donc on peut se permettre de prendre plus bas."""
    for W, L in _W_L_GRID:
        inputs = CubeInputs(win=0.5, win_points=W, lose_points=L)
        values = [inputs.take_point(CubeOwner.CENTRED, x) for x in _X_GRID]
        assert values == sorted(values, reverse=True), f"W={W}, L={L} : {values}"


def test_equity_lies_between_dead_and_live():
    """`E(x)` est une combinaison convexe de `E(0)` et `E(1)` par construction
    (§3) — le test constate que la valeur intermédiaire reste bornée par les
    deux extrêmes, pour chaque état du videau."""
    for W, L in _W_L_GRID:
        inputs = CubeInputs(win=0.6, win_points=W, lose_points=L)
        for owner in CubeOwner:
            dead = inputs.equity(owner, 1, 0.0)
            live = inputs.equity(owner, 1, 1.0)
            lo, hi = min(dead, live), max(dead, live)
            for x in _X_GRID:
                value = inputs.equity(owner, 1, x)
                assert lo - 1e-9 <= value <= hi + 1e-9, (
                    f"owner={owner}, x={x}: {value} hors de [{lo}, {hi}]"
                )


def test_equity_increases_with_winning_chance():
    """À état de videau et efficacité fixés, gagner plus souvent ne peut
    jamais faire baisser l'équité."""
    for W, L in _W_L_GRID:
        for owner in CubeOwner:
            for x in (0.0, 0.68, 1.0):
                values = [
                    CubeInputs(win=p, win_points=W, lose_points=L).equity(owner, 1, x)
                    for p in _P_GRID
                ]
                assert values == sorted(values), (
                    f"owner={owner}, x={x}, W={W}, L={L} : {values}"
                )


def test_continuity_at_the_breakpoints():
    """La courbe ne saute pas à `TP_live` ni à `CP_live` — échantillonné à
    ±1e-9 de chaque bord, comme le prescrit §6.1."""
    epsilon = 1e-9
    for W, L in _W_L_GRID:
        base = CubeInputs(win=0.5, win_points=W, lose_points=L)
        tp_live = base.take_point(CubeOwner.CENTRED, 1.0)
        cp_live = base.take_point(CubeOwner.OWNED, 1.0)

        for owner in CubeOwner:
            for breakpoint in (tp_live, cp_live):
                if not (epsilon < breakpoint < 1.0 - epsilon):
                    continue
                below = CubeInputs(win=breakpoint - epsilon, win_points=W, lose_points=L)
                above = CubeInputs(win=breakpoint + epsilon, win_points=W, lose_points=L)
                for x in (0.0, 0.5, 1.0):
                    e_below = below.equity(owner, 1, x)
                    e_above = above.equity(owner, 1, x)
                    assert abs(e_above - e_below) < 1e-6, (
                        f"saut à {breakpoint} pour owner={owner}, x={x}, W={W}, L={L}: "
                        f"{e_below} -> {e_above}"
                    )


def test_owned_beats_centred_beats_opponent():
    """Pour toute position, à videau égal, mieux vaut le posséder que le voir
    centré, et mieux vaut le voir centré que chez l'adversaire — un videau
    n'est jamais un handicap."""
    for W, L in _W_L_GRID:
        for p in _P_GRID:
            for x in _X_GRID:
                inputs = CubeInputs(win=p, win_points=W, lose_points=L)
                owned = inputs.equity(CubeOwner.OWNED, 1, x)
                centred = inputs.equity(CubeOwner.CENTRED, 1, x)
                opponent = inputs.equity(CubeOwner.OPPONENT, 1, x)
                assert owned >= centred - 1e-9 >= opponent - 2e-9, (
                    f"p={p}, x={x}, W={W}, L={L}: {owned} / {centred} / {opponent}"
                )


# ── §4 : la décision money ────────────────────────────────────────────


def test_decision_always_carries_branch_equities():
    """« La sortie porte toujours les équités des branches, pas seulement le
    verdict. » — vérifié sur les quatre verdicts possibles."""
    cases = [
        (gammonless(0.99), CubeOwner.OWNED),     # trop bon
        (gammonless(0.80), CubeOwner.CENTRED),   # double, passe
        (gammonless(0.60), CubeOwner.CENTRED),   # double, prend
        (gammonless(0.30), CubeOwner.CENTRED),   # ne double pas
    ]
    for evaluation, owner in cases:
        result = decide(evaluation, owner, X)
        assert result.equity_no_double is not None
        assert result.equity_double is not None
        assert result.take_point is not None


def test_too_good_beats_cashing():
    """Trop bon : `E_nd` dépasse à la fois `E_dp` et `E_double` — jouer vaut
    mieux que doubler, dans les deux branches."""
    result = decide(with_gammons(0.97, wg=0.7, lg=0.0), CubeOwner.OWNED, X)
    assert result.action == CubeAction.TOO_GOOD
    assert result.equity_no_double > result.equity_double


def test_double_pass_beats_double_take_for_the_opponent():
    """Double-passe : l'adversaire choisit de passer parce que prendre lui
    coûterait plus cher (`E_dt >= E_dp`, donc `E_double = E_dp = 1`)."""
    result = decide(gammonless(0.85), CubeOwner.CENTRED, X)
    assert result.action == CubeAction.DOUBLE_PASS
    assert result.equity_double == pytest.approx(1.0)


def test_double_take_beats_not_doubling():
    result = decide(gammonless(0.72), CubeOwner.CENTRED, X)
    assert result.action == CubeAction.DOUBLE_TAKE
    assert result.equity_double > result.equity_no_double


def test_opponent_owned_cube_forces_no_double():
    """Le joueur au trait ne peut pas tourner un videau que l'adversaire
    possède — `gn_cube.h` : `GN_CUBE_OPPONENT`. Le verdict est forcé, quelle
    que soit la position."""
    for p in (0.05, 0.5, 0.95):
        result = decide(gammonless(p), CubeOwner.OPPONENT, X)
        assert result.action == CubeAction.NO_DOUBLE


# ── §4 : Jacoby ────────────────────────────────────────────────────────


def test_jacoby_removes_gammon_value_from_the_no_double_branch():
    """Avec Jacoby actif, `E_nd` est calculée comme si la position était
    gammonless — donc différente de la même position sans Jacoby, dès que la
    position a de vrais gammons."""
    gammon_heavy = with_gammons(0.65, wg=0.4, lg=0.02)
    with_flag = decide(gammon_heavy, CubeOwner.CENTRED, X, jacoby=True)
    without_flag = decide(gammon_heavy, CubeOwner.CENTRED, X, jacoby=False)
    assert with_flag.equity_no_double != pytest.approx(without_flag.equity_no_double)


def test_jacoby_has_no_effect_once_the_cube_has_been_turned():
    """Spec §4 : Jacoby ne s'applique qu'au videau centré, avant le premier
    double — `owner=OWNED`/`OPPONENT` n'en sont pas affectés."""
    gammon_heavy = with_gammons(0.65, wg=0.4, lg=0.02)
    for owner in (CubeOwner.OWNED, CubeOwner.OPPONENT):
        with_flag = decide(gammon_heavy, owner, X, jacoby=True)
        without_flag = decide(gammon_heavy, owner, X, jacoby=False)
        assert with_flag.equity_no_double == pytest.approx(without_flag.equity_no_double)


def test_jacoby_has_no_effect_in_a_match():
    """Spec §4 : « sans objet en match ». Le drapeau est ignoré dès qu'un état
    de match est fourni, y compris videau centré."""
    gammon_heavy = with_gammons(0.65, wg=0.4, lg=0.02)
    state = MatchState(away_on_roll=7, away_opponent=7, cube=1)
    with_flag = decide(gammon_heavy, CubeOwner.CENTRED, X, state=state, jacoby=True)
    without_flag = decide(gammon_heavy, CubeOwner.CENTRED, X, state=state, jacoby=False)
    assert with_flag.equity_no_double == pytest.approx(without_flag.equity_no_double)


# ── §5 : la décision en match ─────────────────────────────────────────


def test_crawford_never_doubles():
    """« On ne double jamais » pendant la partie de Crawford — codé en dur,
    pas émergent, exactement comme la spécification le prescrit."""
    state = MatchState(away_on_roll=3, away_opponent=1, cube=1, crawford=True)
    for p in (0.05, 0.5, 0.95):
        result = decide(gammonless(p), CubeOwner.CENTRED, X, state=state)
        assert result.action == CubeAction.NO_DOUBLE


def test_post_crawford_trailer_at_two_away_doubles_systematically():
    """ÉMERGENT, pas codé : à 2-away contre un meneur à la balle de match, le
    mené double à toute probabilité de gain testée — jamais `NO_DOUBLE`.
    L'enjeu doublé (2) tombe pile sur son compte, donc doubler ne coûte
    jamais rien : c'est le double systématique classique du post-Crawford,
    lu dans le verdict, pas supposé à l'avance.
    """
    state = MatchState(away_on_roll=2, away_opponent=1, cube=1)
    for p in (0.01, 0.05, 0.15, 0.3, 0.5, 0.7, 0.85, 0.95, 0.99):
        result = decide(gammonless(p), CubeOwner.CENTRED, X, state=state)
        assert result.action != CubeAction.NO_DOUBLE, f"p={p} : {result.action}"


def test_post_crawford_trailer_doubles_at_any_away():
    """RÉVISÉ avec la v2 (spec §9). La version v1 de ce test affirmait le
    contraire — que `NO_DOUBLE` survenait à 3-away — et encodait un artefact
    de la v1, pas une propriété du jeu : post-Crawford, le double du mené est
    gratuit à TOUT score, car concéder 1 ou 2 points est indifférent face à
    un meneur à la balle de match. Vérifié par sonde gnubg 1.08.003 AVANT de
    réviser (12 positions de bearoff, p de 0,25 à 0,76, scores 3-away/1-away
    et 5-away/1-away : « Double, take » partout). La spécificité pair/impair
    vit dans le point de prise du meneur — le free drop, testé juste en
    dessous — pas dans le verdict du mené."""
    for away in (2, 3, 5):
        state = MatchState(away_on_roll=away, away_opponent=1, cube=1)
        for p in (0.05, 0.3, 0.5, 0.7, 0.95):
            result = decide(gammonless(p), CubeOwner.CENTRED, X, state=state)
            assert result.action != CubeAction.NO_DOUBLE, (
                f"away={away}, p={p} : {result.action}"
            )


def test_leaders_free_drop_at_even_trailer_scores():
    """Le « free drop » du meneur : son point de prise (rapporté par
    `take_point` lors de la décision du mené) est nettement plus bas à un
    score PAIR de mené qu'à un score IMPAIR, post-Crawford.

    Mécanisme, lu dans les chiffres et non supposé : à score pair, un seul
    point ne change pas la parité qui décide du match, donc passer coûte
    presque rien au meneur ; à score impair, un gammon du mené changerait
    cette parité, ce que `gn_met_post`'s dentelure pair/impair (`test_met.py`)
    documente déjà pour la table elle-même. Ce test vérifie que la
    conséquence sur le VIDEAU en hérite, sans le recoder.
    """
    even_take_points = [
        decide(gammonless(0.5), CubeOwner.CENTRED, X,
               state=MatchState(away_on_roll=away, away_opponent=1, cube=1)).take_point
        for away in (2, 4, 6, 8)
    ]
    odd_take_points = [
        decide(gammonless(0.5), CubeOwner.CENTRED, X,
               state=MatchState(away_on_roll=away, away_opponent=1, cube=1)).take_point
        for away in (3, 5, 7, 9)
    ]
    assert max(even_take_points) < min(odd_take_points), (
        f"pas de séparation pair/impair : pairs={even_take_points}, "
        f"impairs={odd_take_points}"
    )


def test_doubling_window_is_monotone_across_scores():
    """Fenêtre de double monotone sur {2-away/2-away, 4-away/2-away,
    2-away/4-away} : plus je suis loin derrière, moins mon équité sans
    doubler est bonne — la MWC sait ordonner les scores sans qu'on le lui
    dise deux fois (elle le fait déjà dans `test_met.py`)."""
    scores = [(2, 2), (4, 2), (2, 4)]
    equities = []
    for away_on_roll, away_opponent in scores:
        state = MatchState(away_on_roll=away_on_roll, away_opponent=away_opponent, cube=1)
        result = decide(gammonless(0.5), CubeOwner.CENTRED, X, state=state)
        equities.append(result.equity_no_double)

    # Être plus près du but (moins de away) est toujours au moins aussi bon.
    assert equities[0] > equities[1], "4-away devrait valoir moins que 2-away à away adverse égal"
    assert equities[2] > equities[0], "être 2-away contre un adversaire à 4-away devrait valoir plus"


def test_cube_value_is_capped_by_gn_met_after():
    """§5 : gagner plus que `away` points ne vaut pas plus que `away` points.
    Vérifié ici comme le demande la spécification, AVANT toute décision de
    plafonner dans `gn_cube` — et la mesure dit que ce n'est pas nécessaire :
    `gn_met_after` plafonne déjà (`gn_met.c`: `mine <= 0` rend 1.0 quel que
    soit `points`), donc `gn_cube_decide` n'ajoute aucun code de plafond.
    """
    at_two = MatchState(away_on_roll=2, away_opponent=5, cube=2)
    at_four = MatchState(away_on_roll=2, away_opponent=5, cube=4)
    assert at_two.after(2, True) == pytest.approx(1.0)
    assert at_four.after(4, True) == pytest.approx(1.0)
    assert at_two.after(2, True) == at_four.after(4, True)

    # Et la décision de videau, qui consomme gn_met_after, hérite du plafond :
    # doubler un videau déjà à 4 quand 2 suffisait déjà ne change pas le verdict
    # d'une position neutre au même score.
    result_2 = decide(gammonless(0.5), CubeOwner.CENTRED, X, state=at_two)
    result_4 = decide(gammonless(0.5), CubeOwner.CENTRED, X, state=at_four)
    assert result_2.action == result_4.action


# ── §9 : la récursion de re-doublement à score (v2) ───────────────────


def test_two_away_two_away_double_kills_the_cube():
    """Ancre §9-1 : à 2-away/2-away, doubler rend le videau mort (l'enjeu 2
    couvre les deux scores). La branche « double, il prend » doit donc être
    la comparaison MORTE exactement — `M_dead(p; 2) = p`, puisque la partie
    décide alors le match — indépendante de l'efficacité, et le double
    émerger dès que `p` dépasse 0,5."""
    state = MatchState(away_on_roll=2, away_opponent=2, cube=1)
    for p in (0.55, 0.60, 0.65):
        for x in (0.3, X, 0.9):
            result = decide(gammonless(p), CubeOwner.CENTRED, x, state=state)
            assert result.action == CubeAction.DOUBLE_TAKE, f"p={p}, x={x}"
            # e_double = min(e_dt, e_dp) et ici e_dt = p exactement — à la
            # précision float32 près, celle des probabilités d'entrée :
            assert result.equity_double == pytest.approx(p, abs=1e-6), (
                f"p={p}, x={x} : la branche prise n'est pas la MWC morte"
            )


def test_two_away_two_away_take_point_is_the_dead_one():
    """Ancre §9-1, suite : le point de prise rapporté à 2-away/2-away
    (exprimé en `p` du joueur au trait) est celui du videau MORT. Sur le
    niveau doublé, mort, `M_dead(p; 2) = p` ; la bissection vise
    `cash(1) = mwc(gagner 1 sec)`, donc le point de prise EST cette MWC —
    une identité lue dans la table, pas un chiffre recopié. (Côté mené,
    cela fait un point de prise de `1 − cash(1)` ≈ 32 %, le classique du
    videau mort à 2-away/2-away — et plus le 0,80 money de la v1.)"""
    state = MatchState(away_on_roll=2, away_opponent=2, cube=1)
    result = decide(gammonless(0.5), CubeOwner.CENTRED, X, state=state)
    cash_mwc = state.after(1, True)
    assert result.take_point == pytest.approx(cash_mwc, abs=1e-9)


def test_leader_reticence_emerges_at_two_away_four_away():
    """Ancre §9-2, la décisive — celle que la v1 rate. À 2-away/4-away, après
    prise du meneur doublé, le re-doublement du mené est GRATUIT (un videau à
    4 ne change plus rien pour un meneur à 2-away). La récursion doit faire
    émerger la réticence doctrinale du meneur : au pire désaccord mesuré en
    §6.3 (p = 0,543, état possédé, la v1 disait `DOUBLE_TAKE` à marge quasi
    nulle, gnubg *No redouble*), la v2 dit `NO_DOUBLE` — et de même sur toute
    la plage intermédiaire, videau centré comme possédé."""
    state = MatchState(away_on_roll=2, away_opponent=4, cube=1)
    for owner in (CubeOwner.CENTRED, CubeOwner.OWNED):
        for p in (0.5, 0.543, 0.6, 0.7):
            result = decide(gammonless(p), owner, X, state=state)
            assert result.action == CubeAction.NO_DOUBLE, (
                f"owner={owner}, p={p} : {result.action}"
            )
    # La fenêtre existe toujours : très haut, le meneur double et le mené
    # passe (prendre un videau qui ira à 4 ne sauve plus rien à p si haut).
    high = decide(gammonless(0.85), CubeOwner.CENTRED, X, state=state)
    assert high.action == CubeAction.DOUBLE_PASS


def test_trailer_take_point_widens_with_the_free_redouble():
    """Ancre §9-2, le mécanisme : à 2-away/4-away, le point de prise du mené
    est nettement plus LARGE que ce que le videau MORT justifierait au même
    score — c'est le re-doublement gratuit qui paie la prise, et il n'existe
    que dans la récursion. Le point de prise mort se calcule ici même depuis
    la table (`M_dead(p; 2)` croise `cash(1)`) ; le rapporté doit le dépasser
    franchement, en `p` du meneur."""
    state = MatchState(away_on_roll=2, away_opponent=4, cube=1)
    result = decide(gammonless(0.6), CubeOwner.CENTRED, X, state=state)
    cash = state.after(1, True)
    win2, lose2 = state.after(2, True), state.after(2, False)
    dead_take_point = (cash - lose2) / (win2 - lose2)
    assert result.take_point > dead_take_point + 0.05, (
        f"rapporté {result.take_point}, mort {dead_take_point}"
    )


def test_recursion_depth_is_bounded_by_the_table():
    """§9 : la chaîne se termine d'elle-même — `⌈log₂ 25⌉ = 5` doublements au
    plus. Le pire cas de la table (25-away/25-away, videau à 1) doit donc
    répondre, pas déborder ni refuser."""
    state = MatchState(away_on_roll=25, away_opponent=25, cube=1)
    result = decide(gammonless(0.5), CubeOwner.CENTRED, X, state=state)
    assert result.action in CubeAction


# ── Refus plutôt qu'extrapolation ─────────────────────────────────────


def test_match_beyond_the_table_is_refused():
    state = MatchState(away_on_roll=26, away_opponent=5, cube=1)
    with pytest.raises(ValueError):
        decide(gammonless(0.5), CubeOwner.CENTRED, X, state=state)
