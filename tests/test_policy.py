"""La politique sans état — `docs/specs/politique-spec.md`.

Trois choses sont tenues ici :

* le **contrat** : chaque cas de la spec §5, chaque refus de §6, et le
  déterminisme (deux appels identiques, mêmes octets) ;
* l'**identité** avec le joueur de T35 (spec §9.1) : à un même réglage, la
  politique prend exactement ses décisions, et une paire dupliquée politique
  contre joueur T35 totalise exactement zéro — la composition n'a rien changé
  à ce que T35 a mesuré ;
* le **corpus de référence** (spec §8) : rejoué sur ce build, octet pour octet.
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

import pytest

from gammonnet import bearoff
from gammonnet.cube import CubeOwner
from gammonnet.cubeful import (GammonNetCubePlayer, play_cubeful_duplicate,
                               play_match_duplicate)
from gammonnet.met import MatchState
from gammonnet.policy import (LEVELS, REQUIRED_CATEGORIES, ActionKind, Decision,
                              Pending, PolicyPlayer, Shape, answer, categories,
                              certain_loss, efficiency, read_corpus, unpack_decision)
from gammonnet.rules import BLACK, WHITE, Position

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "policy_reference.bin"


@pytest.fixture(scope="module")
def player():
    if bearoff._shared is not None:
        pytest.skip("une table bilatérale partagée est installée par un autre test")
    p = PolicyPlayer(level="instant")
    p._load()
    return p


def board(white: dict[int, int], black: dict[int, int], turn=WHITE,
          off=None) -> Position:
    """`white`/`black` : indice -> nombre de pions. Le reste est sorti."""
    points = [0] * 24
    for i, n in white.items():
        points[i] += n
    for i, n in black.items():
        points[i] -= n
    w_off = 15 - sum(white.values())
    b_off = 15 - sum(black.values())
    return Position(points=tuple(points), bar=(0, 0), off=(w_off, b_off), turn=turn)


# ── Le contrat ───────────────────────────────────────────────────────


def test_efficiency_is_the_t34_measurement():
    results = json.loads((ROOT / "docs/mesures/t34-efficacite.json").read_text())["results"]
    assert efficiency(CubeOwner.CENTRED) == results["centered"]["x"]
    assert efficiency(CubeOwner.OWNED) == results["owned"]["x"]
    assert efficiency(CubeOwner.OPPONENT) == results["opponent"]["x"]


@pytest.mark.parametrize("decision", [
    Decision(Position.initial(), Pending.MOVE, 0, 3),                     # dé hors bornes
    Decision(Position.initial(), Pending.MOVE, 3, 7),
    Decision(Position.initial(), Pending.CUBE, cube=2,
             cube_owner=CubeOwner.CENTRED),                              # videau tourné sans maître
    Decision(Position.initial(), Pending.CUBE, cube=1,
             cube_owner=CubeOwner.OWNED),                                # videau à 1 possédé
    Decision(Position.initial(), Pending.CUBE, cube=3, cube_owner=CubeOwner.OWNED),
    Decision(Position.initial(), Pending.CUBE,
             match=MatchState(3, 3, 1, True)),                           # Crawford sans 1-away
    Decision(Position.initial(), Pending.CUBE, cube=2, cube_owner=CubeOwner.OWNED,
             match=MatchState(1, 3, 2, True)),                           # videau en Crawford
    Decision(Position.initial(), Pending.CUBE, match=MatchState(26, 3, 1, False)),
    Decision(Position.initial(), Pending.TAKE, cube=2,
             cube_owner=CubeOwner.OPPONENT),                             # double interdit
    Decision(Position.initial(), Pending.TAKE, match=MatchState(1, 3, 1, True)),
    Decision(Position.initial(), Pending.RESIGN, resign_value=0),
    Decision(Position.initial(), Pending.RESIGN, resign_value=4),
])
def test_refusals(player, decision):
    with pytest.raises(ValueError):
        player.decide(decision)


def test_unknown_level_and_missing_prune_are_refused(player):
    from gammonnet import policy

    d = Decision(Position.initial(), Pending.MOVE, 3, 1)
    with pytest.raises(ValueError):
        policy.decide(player._network, player._prune, "expert", d)
    with pytest.raises(ValueError):
        policy.decide(player._network, None, "normal", d)    # normal élague
    assert policy.decide(player._network, None, "instant", d).kind == ActionKind.MOVE


def test_finished_position_is_refused(player):
    done = board({0: 1}, {})
    with pytest.raises(ValueError):
        player.decide(Decision(done, Pending.CUBE))


def test_determinism(player):
    d = Decision(Position.initial(), Pending.CUBE, match=MatchState(4, 2, 1, False))
    assert player.decide(d).raw == player.decide(d).raw


def test_move_shortcuts(player):
    # Aucun coup légal : un pion sur la barre devant un jan fermé.
    pos = Position(points=tuple([0] * 18 + [-2] * 6), bar=(1, 0), off=(14, 3), turn=WHITE)
    a = player.decide(Decision(pos, Pending.MOVE, 6, 6))
    assert a.kind == ActionKind.MOVE and a.play.moves == () and not a.searched
    assert a.play.result.turn == BLACK and a.play.result.points == pos.points
    # Un seul coup légal : pas de recherche.
    one = board({0: 1}, {23: 1})
    a = player.decide(Decision(one, Pending.MOVE, 1, 2))
    assert a.kind == ActionKind.MOVE and len(a.play.moves) == 1 and not a.searched


@pytest.mark.parametrize("decision", [
    Decision(Position.initial(), Pending.CUBE, cube=2, cube_owner=CubeOwner.OPPONENT),
    Decision(Position.initial(), Pending.CUBE, match=MatchState(1, 4, 1, True)),
    Decision(Position.initial(), Pending.CUBE, cube=2, cube_owner=CubeOwner.OWNED,
             match=MatchState(2, 5, 2, False)),                 # mort pour le joueur au trait
    Decision(Position.initial(), Pending.CUBE, match=MatchState(1, 4, 1, False)),
])
def test_unavailable_cube_costs_nothing(player, decision):
    a = player.decide(decision)
    assert a.kind == ActionKind.ROLL and not a.searched
    assert a.equity_a == 0.0 and a.equity_b == 0.0


def test_take_is_the_t35_comparison(player):
    """La réponse du preneur : prendre ssi la branche prise coûte moins au
    doubleur que la branche passée — exactement `accepts_double` de T35."""
    t35 = GammonNetCubePlayer(ply=0, cube_ply=0, prune_k=0, database=None)
    rng = random.Random(7)
    positions = [Position.initial()]
    pos = Position.initial()
    for _ in range(80):
        plays = pos.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
        pos = rng.choice(plays).result if plays else pos.swapped_turn()
        if pos.is_over():
            break
        positions.append(pos)
    for p in positions:
        for cube, owner, match in ((1, CubeOwner.CENTRED, None),
                                   (2, CubeOwner.OWNED, None),
                                   (1, CubeOwner.CENTRED, MatchState(3, 4, 1, False)),
                                   (2, CubeOwner.OWNED, MatchState(5, 2, 2, False))):
            a = player.decide(Decision(p, Pending.TAKE, cube=cube, cube_owner=owner,
                                       match=match))
            assert (a.kind == ActionKind.TAKE) == t35.accepts_double(p, cube, owner, match)


def test_resign_offer(player):
    pos = Position.initial()
    # Un gammon offert à l'ouverture : on n'y perd rien à l'accepter.
    assert player.decide(Decision(pos, Pending.RESIGN, resign_value=2)).kind == ActionKind.ACCEPT
    # Le joueur au trait finit à ce jet et l'adversaire n'a rien sorti : s'il
    # offre un simple, le décideur, gammonné sinon, accepte.
    winning = board({0: 1}, {23: 15}, turn=WHITE)
    a = player.decide(Decision(winning, Pending.RESIGN, resign_value=1))
    assert a.kind == ActionKind.ACCEPT and a.equity_a > a.equity_b
    # Au score, même lecture.
    a = player.decide(Decision(winning, Pending.RESIGN, resign_value=1,
                               match=MatchState(3, 3, 1, False)))
    assert a.kind == ActionKind.ACCEPT and a.equity_a >= a.equity_b


# ── La défaite certaine, lue exactement (§5.5) ───────────────────────


def test_certain_loss_values():
    far = {12: 15}                                   # 15 pions au 13, rien de sorti
    assert certain_loss(board(far, {23: 2})) == 2    # gammon certain, pas de backgammon
    assert certain_loss(board({12: 9, 22: 6}, {23: 1})) == 3   # backgammon certain
    assert certain_loss(board({12: 14}, {23: 2})) == 1         # un pion déjà sorti
    assert certain_loss(board({12: 13, 22: 1}, {23: 1})) == 1
    # k = 2 : l'adversaire finit sûrement en deux jets, le joueur pas.
    assert certain_loss(board(far, {23: 3})) == 2
    # Valeur incertaine : un pion au 23 sort du jan adverse avec la plupart
    # des jets, pas avec 2-1.
    assert certain_loss(board({12: 14, 22: 1}, {23: 2})) == 0
    # Défaite non certaine : l'adversaire peut ne pas finir.
    assert certain_loss(board(far, {23: 5})) == 0
    # Contact : jamais lu.
    assert certain_loss(board({12: 14, 23: 1}, {20: 1})) == 0
    # Le joueur au trait peut gagner : rien.
    assert certain_loss(board({0: 2}, {23: 2})) == 0


def test_resign_before_rolling(player):
    lost = board({12: 15}, {23: 2})
    a = player.decide(Decision(lost, Pending.CUBE))
    assert a.kind == ActionKind.RESIGN and a.resign_value == 2 and not a.searched
    a = player.decide(Decision(lost, Pending.CUBE, jacoby=True))
    assert a.kind == ActionKind.RESIGN and a.resign_value == 1       # Jacoby, videau centré
    a = player.decide(Decision(lost, Pending.CUBE, jacoby=True, cube=2,
                               cube_owner=CubeOwner.OWNED))
    assert a.resign_value == 2
    a = player.decide(Decision(lost, Pending.CUBE, match=MatchState(3, 2, 1, False)))
    assert a.kind == ActionKind.RESIGN and a.resign_value == 2


# ── L'identité avec le joueur de T35 (§9.1) ──────────────────────────


class _Witness:
    """Pose chaque question aux deux joueurs et exige la même réponse."""

    def __init__(self, policy, t35):
        self.policy, self.t35, self.name = policy, t35, "witness"
        self.asked = 0
        self.optional = 0

    def choose(self, position, d1, d2, rng, match=None):
        a = self.policy.choose(position, d1, d2, rng, match)
        b = self.t35.choose(position, d1, d2, rng, match)
        assert (a.result if a else None) == (b.result if b else None)
        self.asked += 1
        return a

    def wants_double(self, position, cube, owner, match=None):
        a = self.policy.wants_double(position, cube, owner, match)
        b = self.t35.wants_double(position, cube, owner, match)
        if a != b:
            # The one difference the spec allows (§5.2): T35 doubles where
            # doubling is worth exactly what not doubling is.
            action = self.policy.decide(Decision(position, Pending.CUBE, cube=cube,
                                                 cube_owner=owner, jacoby=self.policy.jacoby,
                                                 match=match))
            assert b and not a and action.searched and action.equity_a == action.equity_b
            self.optional += 1
        self.asked += 1
        return a

    def accepts_double(self, position, cube, owner, match=None):
        a = self.policy.accepts_double(position, cube, owner, match)
        assert a == self.t35.accepts_double(position, cube, owner, match)
        self.asked += 1
        return a


def _pair(ply=0, filt=(), prune_k=0):
    shape = Shape(ply=ply, filter=filt, prune_k=prune_k)
    return (PolicyPlayer(level=shape),
            GammonNetCubePlayer(ply=ply, filter=filt, cube_ply=ply, prune_k=prune_k,
                                database=None))


def test_identity_decision_by_decision_0ply(player):
    policy, t35 = _pair()
    w = _Witness(policy, t35)
    for i in range(4):
        play_cubeful_duplicate(w, w, 20261005, i)
        play_match_duplicate(w, w, 1 + i % 5, 7 - i, 20261005, i)
    assert w.asked > 500


def test_identity_duplicate_pairs_total_zero_0ply(player):
    policy, t35 = _pair()
    for i in range(6):
        net, _ = play_cubeful_duplicate(policy, t35, 20261006, i)
        assert net == 0
        net, _ = play_match_duplicate(policy, t35, 2 + i % 4, 3 + i % 3, 20261006, i)
        assert net == 0


@pytest.mark.skipif(not os.environ.get("GN_POLICY_SLOW"),
                    reason="2-ply : GN_POLICY_SLOW=1 pour l'exiger")
def test_identity_t35_shape_2ply(player):
    policy, t35 = _pair(ply=2, filt=(0, 1, 3), prune_k=12)
    w = _Witness(policy, t35)
    play_match_duplicate(w, w, 3, 4, 20261007, 0)
    assert w.asked > 50


# ── Le corpus de référence (§8) ──────────────────────────────────────


def test_corpus_replays_byte_for_byte(player):
    records = read_corpus(CORPUS)
    slow = bool(os.environ.get("GN_POLICY_SLOW"))
    replayed = {name: 0 for name in LEVELS}
    for record in records:
        level, decision = unpack_decision(record)
        if level != "instant" and not slow:
            continue
        assert answer(player._network, player._prune, level, decision) == record, decision
        replayed[level] += 1
    assert replayed["instant"] > 300


def test_corpus_covers_every_category():
    """Un portage vérifié contre un corpus qui n'a jamais posé une question n'a
    rien vérifié sur elle : chaque verdict de videau (money et match), le double
    optionnel, chaque réponse, chaque valeur de défaite certaine et chaque
    régime doivent y figurer."""
    seen = set()
    for record in read_corpus(CORPUS):
        seen |= categories(record)
    missing = REQUIRED_CATEGORIES - seen
    assert not missing, sorted(missing)


def test_exact_table_path_ignores_jacoby_only_where_no_gammon_exists():
    """Le chemin par la table bilatérale (money) n'applique pas Jacoby : il ne
    le peut pas, puisqu'aucun gammon n'existe dans son domaine — et la
    politique ne la consulte que si chaque camp a sorti un pion."""
    db = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"
    if not db.exists() or bearoff._shared is not None:
        pytest.skip("table bilatérale absente")
    p = PolicyPlayer(level="instant")
    p._load()
    race = board({0: 2, 1: 2, 2: 1, 4: 1}, {23: 3, 22: 2, 20: 1})
    bearoff.use_shared(db)
    try:
        with_table = p.decide(Decision(race, Pending.CUBE, jacoby=True))
        without_jacoby = p.decide(Decision(race, Pending.CUBE, jacoby=False))
    finally:
        bearoff.disable_shared()
    assert with_table.raw == without_jacoby.raw
    assert with_table.searched
    model = p.decide(Decision(race, Pending.CUBE, jacoby=True))
    assert model.raw != with_table.raw      # the table really was consulted
