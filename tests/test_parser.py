from datetime import date, datetime, timezone

from wordle_elo.parser import (
    LINE_RE,
    USER_RE,
    X_FAIL_GUESSES,
    ParsedSubmission,
    UnresolvedSubmission,
    _puzzle_no_from_created_at,
    configure,
    parse_text,
)


def test_basic_screenshot_format():
    content = (
        "Your group is on a 151 day streak! \U0001f525\U0001f525\U0001f525 "
        "Here are yesterday's results:\n"
        "\U0001f451 3/6: <@111111111> <@222222222> <@333333333>\n"
        "4/6: <@444444444>\n"
        "5/6: <@555555555>"
    )
    embed = ["Wordle No. 1783"]

    parsed = parse_text(content, embed)

    assert parsed is not None
    assert parsed.puzzle_no == 1783
    expected = (
        ParsedSubmission(111111111, 3, False),
        ParsedSubmission(222222222, 3, False),
        ParsedSubmission(333333333, 3, False),
        ParsedSubmission(444444444, 4, False),
        ParsedSubmission(555555555, 5, False),
    )
    assert parsed.submissions == expected


def test_failed_x_line():
    content = (
        "Here are yesterday's results:\n"
        "3/6: <@111>\n"
        "X/6: <@222>"
    )
    parsed = parse_text(content, ["Wordle No. 100"])
    assert parsed is not None
    subs = {s.user_id: s for s in parsed.submissions}
    assert subs[111].guesses == 3
    assert subs[222].guesses == X_FAIL_GUESSES
    assert subs[222].won is False


def test_hard_mode_marker():
    content = "4/6*: <@111>\n5/6: <@222>"
    parsed = parse_text(content, ["Wordle No. 1"])
    assert parsed is not None
    subs = {s.user_id: s for s in parsed.submissions}
    assert subs[111].hard_mode is True
    assert subs[222].hard_mode is False


def test_nickname_mention_encoding():
    content = "3/6: <@!12345>"
    parsed = parse_text(content, ["Wordle No. 1"])
    assert parsed is not None
    assert parsed.submissions[0].user_id == 12345


def test_puzzle_no_with_comma():
    content = "3/6: <@111>"
    parsed = parse_text(content, ["Wordle No. 1,234"])
    assert parsed is not None
    assert parsed.puzzle_no == 1234


def test_puzzle_no_in_content_fallback():
    content = "Wordle #500\n3/6: <@1>"
    parsed = parse_text(content, [])
    assert parsed is not None
    assert parsed.puzzle_no == 500


def test_no_results_returns_none():
    content = "Your group is on a streak!"
    assert parse_text(content, ["Wordle No. 1"]) is None


def test_no_puzzle_number_returns_none():
    content = "3/6: <@111>"
    assert parse_text(content, []) is None


def test_dedupe_when_user_appears_twice():
    content = "3/6: <@111> <@111>"
    parsed = parse_text(content, ["Wordle No. 1"])
    assert parsed is not None
    assert len(parsed.submissions) == 1


def test_line_regex_matches_crown_prefix():
    line = "\U0001f451 3/6: <@111>"
    m = LINE_RE.search(line)
    assert m is not None
    assert m.group("guesses") == "3"
    assert USER_RE.findall(m.group("users")) == ["111"]


def test_fallback_puzzle_no_used_when_text_has_none():
    content = "3/6: <@111>"
    parsed = parse_text(content, [], fallback_puzzle_no=1787)
    assert parsed is not None
    assert parsed.puzzle_no == 1787


def test_text_puzzle_no_overrides_fallback():
    content = "Wordle #500\n3/6: <@111>"
    parsed = parse_text(content, [], fallback_puzzle_no=9999)
    assert parsed is not None
    assert parsed.puzzle_no == 500


def test_no_submissions_returns_none_even_with_fallback():
    content = "Foo was playing"
    parsed = parse_text(content, [], fallback_puzzle_no=1787)
    assert parsed is None


def test_plain_text_name_becomes_unresolved():
    # Wordle Activity sometimes renders a user as plain text instead of <@id>.
    content = "5/6: @flame91"
    parsed = parse_text(content, ["Wordle No. 1818"])
    assert parsed is not None
    assert parsed.submissions == ()
    assert parsed.unresolved == (UnresolvedSubmission("flame91", 5, False),)


def test_mixed_mention_and_plain_name_same_line():
    # The <@id> after plain text used to make the whole line fail to match.
    content = "4/6: JohnDoe <@444>"
    parsed = parse_text(content, ["Wordle No. 1"])
    assert parsed is not None
    assert parsed.submissions == (ParsedSubmission(444, 4, False),)
    # "JohnDoe" has no leading @, so it isn't captured as a plain-text name.
    assert parsed.unresolved == ()


def test_mention_then_plain_name_both_captured():
    content = "4/6: <@111> @racingandy"
    parsed = parse_text(content, ["Wordle No. 1"])
    assert parsed is not None
    assert parsed.submissions == (ParsedSubmission(111, 4, False),)
    assert parsed.unresolved == (UnresolvedSubmission("racingandy", 4, False),)


def test_plain_names_carry_guesses_and_fail():
    content = "X/6: @racingandy @leoli"
    parsed = parse_text(content, ["Wordle No. 1"])
    assert parsed is not None
    assert parsed.unresolved == (
        UnresolvedSubmission("racingandy", X_FAIL_GUESSES, False),
        UnresolvedSubmission("leoli", X_FAIL_GUESSES, False),
    )


def test_plain_name_deduped_case_insensitively():
    content = "3/6: @Flame91\n4/6: @flame91"
    parsed = parse_text(content, ["Wordle No. 1"])
    assert parsed is not None
    assert parsed.unresolved == (UnresolvedSubmission("Flame91", 3, False),)


def test_real_broken_day_message():
    # Regression: the exact content of the 2026-06-11 message where flame91,
    # Frankschifflotte, racingandy and leoli came through as plain text.
    content = (
        "**Your group is on a 186 day streak!** \U0001f525\U0001f525\U0001f525 "
        "Here are yesterday's results:\n"
        "\U0001f451 2/6: @Frankschifflotte\n"
        "3/6: <@471445975790256140>\n"
        "4/6: <@1418486736501342288> <@443064200642822144>\n"
        "5/6: @flame91\n"
        "X/6: @racingandy @leoli"
    )
    parsed = parse_text(content, [], fallback_puzzle_no=1818)
    assert parsed is not None
    assert {s.user_id for s in parsed.submissions} == {
        471445975790256140,
        1418486736501342288,
        443064200642822144,
    }
    assert [u.name for u in parsed.unresolved] == [
        "Frankschifflotte",
        "flame91",
        "racingandy",
        "leoli",
    ]


def test_puzzle_no_from_created_at_kst_midnight():
    # Reset module state in case prior tests touched it.
    configure(epoch_date=date(2021, 6, 19), tz_name="Asia/Seoul")
    # 2026-05-11T15:01 UTC = 2026-05-12T00:01 KST → yesterday's puzzle = May 11.
    msg_ts = datetime(2026, 5, 11, 15, 1, tzinfo=timezone.utc)
    assert _puzzle_no_from_created_at(msg_ts) == (date(2026, 5, 11) - date(2021, 6, 19)).days
