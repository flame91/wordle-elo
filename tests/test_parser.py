from wordle_elo.parser import (
    LINE_RE,
    USER_RE,
    X_FAIL_GUESSES,
    ParsedSubmission,
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
