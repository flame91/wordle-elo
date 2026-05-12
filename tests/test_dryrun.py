"""Tests for the in-memory ELO simulator used by `scripts/dry_run.py`."""

from wordle_elo.dryrun import simulate
from wordle_elo.parser import ParsedMessage, ParsedSubmission


def _msg(puzzle_no: int, *subs):
    return ParsedMessage(
        puzzle_no=puzzle_no,
        submissions=tuple(ParsedSubmission(uid, g, hard) for uid, g, hard in subs),
    )


def test_empty_input_produces_empty_report():
    report = simulate([])
    assert report.players == {}
    assert report.puzzles_processed == 0


def test_single_puzzle_two_players_updates_elo():
    msg = _msg(1, (1, 3, False), (2, 5, False))
    report = simulate([msg], display_names={1: "alice", 2: "bob"})

    alice, bob = report.players[1], report.players[2]
    # Both are new players (games_played_before=0) so K=K_NEW=40, base=±10.
    # alice solves 3/6: base +10, speed +1, streak 0 (streak=1 < 3) → +11
    # bob   solves 5/6: base +10, speed -1, streak 0                → +9
    assert alice.elo == 1011
    assert bob.elo == 1009
    # Both 3/6 and 5/6 are solves (only X=7 counts as a loss for streak/win purposes)
    assert alice.games_won == 1 and bob.games_won == 1
    assert alice.current_streak == 1 and bob.current_streak == 1
    assert alice.winning_guess_total == 3
    assert alice.avg_winning_guesses == 3.0
    assert bob.avg_winning_guesses == 5.0


def test_failure_resets_streak_and_no_win_count():
    # Day 1: alice wins, bob wins
    # Day 2: alice fails (X), bob wins
    msgs = [
        _msg(1, (1, 3, False), (2, 4, False)),
        _msg(2, (1, 7, False), (2, 3, False)),
    ]
    report = simulate(msgs)
    alice = report.players[1]
    bob = report.players[2]
    assert alice.current_streak == 0  # X resets
    assert alice.best_streak == 1     # day 1 win still recorded
    assert bob.current_streak == 2
    assert bob.best_streak == 2
    assert alice.games_won == 1
    assert bob.games_won == 2


def test_avg_winning_guesses_excludes_failures():
    # alice: wins 2/6, 4/6, fails X/6 → avg should be (2+4)/2 = 3.0
    msgs = [
        _msg(1, (1, 2, False), (2, 4, False)),
        _msg(2, (1, 4, False), (2, 4, False)),
        _msg(3, (1, 7, False), (2, 4, False)),
    ]
    report = simulate(msgs)
    alice = report.players[1]
    assert alice.games_played == 3
    assert alice.games_won == 2
    assert alice.avg_winning_guesses == 3.0


def test_chronological_order_independent_of_input_order():
    # Pass messages out of order; simulate must sort by puzzle_no
    msg1 = _msg(1, (1, 3, False), (2, 5, False))
    msg2 = _msg(2, (1, 5, False), (2, 3, False))
    a = simulate([msg1, msg2])
    b = simulate([msg2, msg1])
    assert a.players[1].elo == b.players[1].elo
    assert a.players[2].elo == b.players[2].elo


def test_leaderboard_rows_sorted_desc_by_elo():
    # Three puzzles, alice dominates → highest ELO
    msgs = [
        _msg(i, (1, 2, False), (2, 4, False), (3, 6, False))
        for i in range(1, 6)
    ]
    report = simulate(msgs, display_names={1: "alice", 2: "bob", 3: "carol"})
    rows = report.leaderboard_rows(placement_games=2)
    assert [r["display_name"] for r in rows] == ["alice", "bob", "carol"]
    assert rows[0]["elo"] > rows[1]["elo"] > rows[2]["elo"]
    # All three played 5 games (above placement_games=2), so no "(+)" suffix.
    assert not any(r["tier"].endswith("(+)") for r in rows)


def test_biggest_swings_tracked():
    msgs = [_msg(1, (1, 1, False), (2, 7, False))]
    report = simulate(msgs)
    assert len(report.biggest_swings) == 2
    deltas = sorted(abs(s[2]) for s in report.biggest_swings)
    assert deltas[-1] >= deltas[0]  # sorted by abs delta desc
