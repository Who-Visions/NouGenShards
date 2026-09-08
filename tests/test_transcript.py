"""Fixture for VTT capture, and the measurement that justified porting it.

Captions here are SYNTHESISED to reproduce the rolling structure YouTube emits.
No third-party caption text is vendored — the shape is what matters, and real
transcript text in a repo is someone else's content.
"""

import pytest

from nougen_shards import transcript


def vtt(*cues: tuple[str, str, str]) -> str:
    body = "WEBVTT\n\n"
    for start, end, text in cues:
        body += f"{start} --> {end}\n{text}\n\n"
    return body


def test_parses_timestamps_and_strips_formatting_tags():
    """YouTube wraps nearly every word in a colour tag; they break comparison."""
    doc = vtt(("00:00:01.000", "00:00:03.500",
               "the <c.colorE5E5E5>quick</c> brown fox"))
    cues = transcript.parse_vtt(doc)
    assert len(cues) == 1
    assert cues[0]["text"] == "the quick brown fox"
    assert cues[0]["t_start"] == 1.0
    assert cues[0]["t_end"] == 3.5


def test_parses_hour_component():
    doc = vtt(("01:02:03.000", "01:02:04.000", "past the hour"))
    assert transcript.parse_vtt(doc)[0]["t_start"] == 3723.0


def test_identical_cues_collapse_and_extend_the_window():
    doc = vtt(("00:00:01.000", "00:00:02.000", "same words"),
              ("00:00:02.000", "00:00:05.000", "same words"))
    out = transcript.dedupe_cues(transcript.parse_vtt(doc))
    assert len(out) == 1
    assert out[0]["t_end"] == 5.0


def test_rolling_extension_keeps_the_longer_text():
    """The pattern that makes auto-captions triple in size."""
    doc = vtt(("00:00:01.000", "00:00:02.000", "we need future AI to hold"),
              ("00:00:02.000", "00:00:03.000", "we need future AI to hold human values"))
    out = transcript.dedupe_cues(transcript.parse_vtt(doc))
    assert len(out) == 1
    assert out[0]["text"] == "we need future AI to hold human values"


def test_contained_tail_is_dropped():
    doc = vtt(("00:00:01.000", "00:00:02.000", "the window is closing"),
              ("00:00:02.000", "00:00:04.000", "is closing"))
    out = transcript.dedupe_cues(transcript.parse_vtt(doc))
    assert len(out) == 1
    assert out[0]["t_end"] == 4.0


def test_partial_overlap_emits_only_the_new_tail():
    doc = vtt(("00:00:01.000", "00:00:02.000", "your test setup is a signal"),
              ("00:00:02.000", "00:00:03.000", "is a signal the model reads"))
    out = transcript.dedupe_cues(transcript.parse_vtt(doc))
    assert [c["text"] for c in out] == ["your test setup is a signal", "the model reads"]


def test_unrelated_cues_are_both_kept():
    doc = vtt(("00:00:01.000", "00:00:02.000", "first sentence entirely"),
              ("00:00:02.000", "00:00:03.000", "wholly different words"))
    assert len(transcript.dedupe_cues(transcript.parse_vtt(doc))) == 2


def test_short_overlaps_do_not_merge_unrelated_cues():
    """Ordinary repeated words must not be read as a rolling caption.

    With no minimum, "and then the" at the end of one cue and the start of the
    next would silently delete real words from the transcript.
    """
    doc = vtt(("00:00:01.000", "00:00:02.000", "the compute does not sit idle"),
              ("00:00:02.000", "00:00:03.000", "idle hands are unrelated here"))
    out = transcript.dedupe_cues(transcript.parse_vtt(doc))
    assert len(out) == 2
    assert out[1]["text"].startswith("idle hands")


def test_rolling_extension_is_checked_before_contained_tail():
    """Order regression guard.

    Pattern 2 must precede pattern 3. Reversed, a rolling extension can match
    the 'already contained' branch and the NEW words are thrown away instead of
    kept -- silent truncation, which is the worst outcome for a transcript.
    """
    doc = vtt(("00:00:01.000", "00:00:02.000", "alignment is two problems"),
              ("00:00:02.000", "00:00:03.000", "alignment is two problems easy to mix up"))
    out = transcript.dedupe_cues(transcript.parse_vtt(doc))
    assert out[0]["text"].endswith("easy to mix up")


def test_duplication_ratio_reports_what_a_naive_parse_would_have_stored():
    """The number that justified this port.

    A real 15.3-minute auto-captioned video measured 66.6% duplication on
    2026-09-08: 47,216 naive characters down to 15,755. This rebuilds the
    dominant shape -- a caption that GROWS one word at a time before the
    display scrolls -- and asserts the ratio lands in the same band, so a
    regression in the dedupe surfaces as a ratio collapse rather than as
    quietly fatter shards.
    """
    words = ("recursive self improvement is the thing he expects "
             "and no lab is prepared for it").split()
    cues = [(f"00:00:{i:02d}.000", f"00:00:{i + 1:02d}.000", " ".join(words[: i + 1]))
            for i in range(len(words))]
    doc = vtt(*cues)

    ratio = transcript.duplication_ratio(doc)
    assert 0.5 < ratio < 0.99, f"a growing caption is mostly duplication, got {ratio:.3f}"

    # Dedupe must not cost content: every word survives, exactly once, in order.
    assert transcript.transcript_text(doc).split() == words


def test_scrolling_captions_lose_no_words():
    """The other real shape: a fixed-size window that scrolls.

    Here the prefix stops matching once the window slides, so the dedupe falls
    to the partial-overlap branch and emits tails. Exact reconstruction is not
    guaranteed by the algorithm, but NOTHING may be dropped -- every word must
    still appear, in order.
    """
    words = ("the compute does not sit idle it just goes somewhere else "
             "and the window keeps closing").split()
    window, cues = [], []
    for i, word in enumerate(words):
        window.append(word)
        cues.append((f"00:00:{i:02d}.000", f"00:00:{i + 1:02d}.000",
                     " ".join(window[-6:])))
    out = transcript.transcript_text(vtt(*cues)).split()

    assert transcript.duplication_ratio(vtt(*cues)) > 0.5
    position = 0
    for word in words:
        assert word in out[position:], f"{word!r} was dropped by the dedupe"
        position = out.index(word, position) + 1


def test_real_subtitles_show_near_zero_duplication():
    """A ratio near zero means real subtitles, not auto-captions.

    Reported alongside a capture, this distinguishes a clean source from one
    where the naive text would have been mostly repeats.
    """
    doc = vtt(("00:00:01.000", "00:00:03.000", "one complete sentence here"),
              ("00:00:03.000", "00:00:05.000", "another separate sentence follows"),
              ("00:00:05.000", "00:00:07.000", "and a third distinct line"))
    assert transcript.duplication_ratio(doc) == 0.0


@pytest.mark.parametrize("doc", ["", "WEBVTT\n\n", "not a vtt file at all"])
def test_empty_or_junk_input_is_not_an_error(doc):
    """Capture must degrade, never raise on a bad download."""
    assert transcript.parse_vtt(doc) == []
    assert transcript.transcript_text(doc) == ""
    assert transcript.duplication_ratio(doc) == 0.0
