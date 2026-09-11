"""Tests for Hardcade Pong Rules Engine and Squad Elevation System.
Covers:
- 11-0 shutout / perfect game
- 11-9 standard victory
- 12-10 deuce victory
- 17-15 extended deuce victory
- Deuce serve rotation (every 2 pts pre-deuce, every 1 pt during deuce)
- Best-of-5 match clinch & sweeps
- Duplicate event rejection (idempotency)
- Impossible 51-0 single game prevention
- Comeback wins and squad progression
"""

import pytest
from nougen_shards.hardcade_pong import (
    HardcadePongMatch,
    HardcadeSquadProgression,
    MatchAlreadyClinchedError,
    InvalidScorerError,
    ImpossibleScoreError
)


def test_shutout_11_0():
    """Verify 11-0 shutout / perfect game."""
    match = HardcadePongMatch(player_a="blade", player_b="whoart", best_of=5)
    for _ in range(11):
        match.record_point(scorer="blade")

    assert len(match.completed_games) == 1
    g1 = match.completed_games[0]
    assert g1.score_a == 11
    assert g1.score_b == 0
    assert g1.winner == "blade"
    assert g1.is_shutout is True
    assert g1.is_deuce_win is False
    assert match.games_a == 1
    assert match.games_b == 0


def test_standard_11_9():
    """Verify 11-9 standard victory without deuce."""
    match = HardcadePongMatch(player_a="phoebus", player_b="blade", best_of=3)
    # 9 points each (18 points total)
    for _ in range(9):
        match.record_point(scorer="phoebus")
        match.record_point(scorer="blade")

    assert match.score_a == 9
    assert match.score_b == 9
    assert match.is_deuce is False

    # Phoebus scores 2 points to win 11-9
    match.record_point(scorer="phoebus")
    match.record_point(scorer="phoebus")

    assert len(match.completed_games) == 1
    g = match.completed_games[0]
    assert g.score_a == 11
    assert g.score_b == 9
    assert g.winner == "phoebus"
    assert g.is_shutout is False
    assert g.is_deuce_win is False


def test_deuce_12_10():
    """Verify 10-10 deuce and 12-10 win by 2."""
    match = HardcadePongMatch(player_a="whoart", player_b="blade", best_of=5)
    for _ in range(10):
        match.record_point(scorer="whoart")
        match.record_point(scorer="blade")

    assert match.score_a == 10
    assert match.score_b == 10
    assert match.is_deuce is True

    # 11-10
    match.record_point(scorer="whoart")
    assert len(match.completed_games) == 0  # Not won yet! Must win by 2!

    # 12-10
    match.record_point(scorer="whoart")
    assert len(match.completed_games) == 1
    g = match.completed_games[0]
    assert g.score_a == 12
    assert g.score_b == 10
    assert g.winner == "whoart"
    assert g.is_deuce_win is True


def test_extended_deuce_17_15():
    """Verify extended deuce up to 17-15."""
    match = HardcadePongMatch(player_a="blade", player_b="phoebus", best_of=5)
    # Reach 15-15
    for _ in range(15):
        match.record_point(scorer="blade")
        match.record_point(scorer="phoebus")

    assert match.score_a == 15
    assert match.score_b == 15
    assert match.is_deuce is True
    assert len(match.completed_games) == 0

    # Blade scores 2 in a row to win 17-15
    match.record_point(scorer="blade")
    assert match.score_a == 16
    assert len(match.completed_games) == 0

    match.record_point(scorer="blade")
    assert len(match.completed_games) == 1
    g = match.completed_games[0]
    assert g.score_a == 17
    assert g.score_b == 15
    assert g.winner == "blade"
    assert g.is_deuce_win is True


def test_deuce_serve_rotation():
    """Verify serve alternates every 2 points before deuce, and every 1 point at deuce."""
    match = HardcadePongMatch(player_a="A", player_b="B", best_of=3, initial_server="A")

    # Point 1: 1-0 (total 1). Total//2 = 0 -> A serves
    match.record_point("A")
    assert match.current_server == "A"

    # Point 2: 2-0 (total 2). Total//2 = 1 -> B serves
    match.record_point("A")
    assert match.current_server == "B"

    # Point 3: 2-1 (total 3). Total//2 = 1 -> B serves
    match.record_point("B")
    assert match.current_server == "B"

    # Point 4: 2-2 (total 4). Total//2 = 2 (mod 2 = 0) -> A serves
    match.record_point("B")
    assert match.current_server == "A"

    # Advance to 10-10
    for _ in range(8):
        match.record_point("A")
        match.record_point("B")

    assert match.score_a == 10
    assert match.score_b == 10
    assert match.is_deuce is True
    # At 10-10 (total 20 points): points_since_deuce = 0 -> A serves
    assert match.current_server == "A"

    # 11-10 (total 21 points): points_since_deuce = 1 -> B serves! Alternates on EVERY point!
    match.record_point("A")
    assert match.current_server == "B"

    # 11-11 (total 22 points): points_since_deuce = 2 -> A serves!
    match.record_point("B")
    assert match.current_server == "A"


def test_best_of_5_sweep_clinch():
    """Verify best-of-5 match clinches at 3-0 sweep and rejects further points."""
    match = HardcadePongMatch(player_a="whoart", player_b="blade", best_of=5)

    # Game 1: 11-0
    for _ in range(11):
        match.record_point("whoart")
    assert match.games_a == 1
    assert match.match_winner is None

    # Game 2: 11-0
    for _ in range(11):
        match.record_point("whoart")
    assert match.games_a == 2
    assert match.match_winner is None

    # Game 3: 11-0
    for _ in range(11):
        match.record_point("whoart")

    assert match.games_a == 3
    assert match.games_b == 0
    assert match.match_winner == "whoart"
    assert match.is_sweep is True

    # Attempting to record any further point must raise MatchAlreadyClinchedError!
    with pytest.raises(MatchAlreadyClinchedError):
        match.record_point("whoart")


def test_duplicate_event_rejection():
    """Verify duplicate event IDs are idempotently returned without changing score."""
    match = HardcadePongMatch(player_a="A", player_b="B", best_of=3)

    ev1 = match.record_point("A", event_id="evt_fixed_1")
    assert match.score_a == 1
    assert match.rally_index == 1

    # Resend duplicate event
    ev1_dup = match.record_point("A", event_id="evt_fixed_1")
    assert match.score_a == 1  # Unchanged!
    assert match.rally_index == 1
    assert ev1_dup.event_id == ev1.event_id


def test_impossible_51_0_prevention():
    """Verify fake single-game scores like 51-0 cannot occur."""
    match = HardcadePongMatch(player_a="A", player_b="B", best_of=5)

    # 11-0 wins Game 1
    for _ in range(11):
        match.record_point("A")
    assert match.games_a == 1
    assert match.score_a == 0  # Reset for game 2!

    # Game 2: 11-0
    for _ in range(11):
        match.record_point("A")
    assert match.games_a == 2

    # Game 3: 11-0
    for _ in range(11):
        match.record_point("A")
    assert match.games_a == 3
    assert match.match_winner == "A"

    # Match clinched at 3 games (33 rallies total).
    # Cannot reach 51 rallies or 51 points!
    with pytest.raises(MatchAlreadyClinchedError):
        for _ in range(18):
            match.record_point("A")


def test_squad_progression_comeback_and_ladder():
    """Verify comeback win and squad ladder ranking."""
    prog = HardcadeSquadProgression()

    # Match 1: blade vs phoebus (blade down 0-2, comes back 3-2)
    match1 = HardcadePongMatch(player_a="blade", player_b="phoebus", best_of=5)
    # Phoebus wins game 1 & 2
    for _ in range(11):
        match1.record_point("phoebus")
    for _ in range(11):
        match1.record_point("phoebus")
    assert match1.games_b == 2

    # Blade wins games 3, 4, 5
    for _ in range(11):
        match1.record_point("blade")
    for _ in range(11):
        match1.record_point("blade")
    for _ in range(11):
        match1.record_point("blade")

    assert match1.games_a == 3
    assert match1.games_b == 2
    assert match1.match_winner == "blade"

    prog.record_match(match1)

    f_blade = prog.get_fighter("blade")
    f_phoebus = prog.get_fighter("phoebus")

    assert f_blade.matches_won == 1
    assert f_blade.comeback_wins == 1
    assert f_blade.elevation_priority > f_phoebus.elevation_priority

    ladder = prog.get_ladder()
    assert ladder[0]["name"] == "blade"
    assert ladder[1]["name"] == "phoebus"
