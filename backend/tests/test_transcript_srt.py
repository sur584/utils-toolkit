import pytest

from transcript.pipeline import (
    _format_srt_time,
    _srt_time_to_seconds,
    parse_srt_segments,
    parse_vtt_segments,
    segments_to_srt,
    segments_to_text,
    synthesize_segments,
)


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("00:01:02,500", 62.5),
        ("01:02.250", 62.25),
        ("1:02:03.004", 3723.004),
        (" 00:00:00,001 ", 0.001),
    ],
)
def test_srt_time_to_seconds_valid(timestamp, expected):
    assert _srt_time_to_seconds(timestamp) == pytest.approx(expected)


@pytest.mark.parametrize("timestamp", ["", "invalid", "00:xx:01,000", "1:2:3:4"])
def test_srt_time_to_seconds_invalid_returns_zero(timestamp):
    assert _srt_time_to_seconds(timestamp) == 0.0


def test_parse_srt_segments_parses_timeline_cleans_tags_and_deduplicates():
    content = """1
00:00:01,250 --> 00:00:03,500
<i>第一句</i>

2
00:00:03,500 --> 00:00:05,000
第一句

3
00:01:02,500 --> 00:01:04,750
<b>第二句</b> &amp; more
"""

    assert parse_srt_segments(content) == [
        {"start": 1.25, "end": 3.5, "text": "第一句"},
        {"start": 62.5, "end": 64.75, "text": "第二句 & more"},
    ]


def test_parse_vtt_segments_handles_header_dot_milliseconds_and_cue_numbers():
    content = """WEBVTT

1
00:00:00.000 --> 00:00:01.250
<i>Hello</i>

2
00:01.250 --> 00:03.500
World
"""

    assert parse_vtt_segments(content) == [
        {"start": 0.0, "end": 1.25, "text": "Hello"},
        {"start": 1.25, "end": 3.5, "text": "World"},
    ]


def test_synthesize_segments_distributes_duration_by_character_ratio():
    segments = synthesize_segments("你好。ABCD!", 8.0)

    assert segments == [
        {"start": 0.0, "end": 3.0, "text": "你好。"},
        {"start": 3.0, "end": 8.0, "text": "ABCD!"},
    ]
    assert segments[-1]["end"] == 8.0


def test_synthesize_segments_estimates_non_positive_duration():
    segments = synthesize_segments("第一句。第二句。", 0)

    assert len(segments) == 2
    assert segments[0]["start"] == 0.0
    assert segments[-1]["end"] == pytest.approx(len("第一句。第二句。") / 5.0)


@pytest.mark.parametrize("text", ["", "   "])
def test_synthesize_segments_empty_text_returns_empty_list(text):
    assert synthesize_segments(text, 10.0) == []


def test_format_srt_time_uses_comma_milliseconds():
    assert _format_srt_time(3723.004) == "01:02:03,004"
    assert _format_srt_time(0.9996) == "00:00:01,000"
    assert _format_srt_time(-1) == "00:00:00,000"


def test_segments_to_srt_is_strict_and_renumbers_after_skipping_empty_text():
    segments = [
        {"start": 0.0, "end": 1.25, "text": " First "},
        {"start": 1.25, "end": 2.0, "text": "   "},
        {"start": 62.5, "end": 64.75, "text": "Second"},
    ]

    assert segments_to_srt(segments) == (
        "1\n"
        "00:00:00,000 --> 00:00:01,250\n"
        "First\n\n"
        "2\n"
        "00:01:02,500 --> 00:01:04,750\n"
        "Second"
    )


def test_segments_to_text_joins_non_empty_segment_text():
    segments = [{"text": "第一句"}, {"text": ""}, {"text": "第二句"}]
    assert segments_to_text(segments) == "第一句 第二句"
