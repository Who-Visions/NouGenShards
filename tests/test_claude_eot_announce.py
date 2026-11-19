"""tools/voice/claude_eot_announce.py and the lane-aware resolver. No audio, SSH or model is touched."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

VOICE = Path(__file__).resolve().parents[1] / "tools" / "voice"


def _load(name):
    sys.path.insert(0, str(VOICE))
    spec = importlib.util.spec_from_file_location(name, VOICE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


eot = _load("claude_eot_announce")


def line(**kw):
    return json.dumps(kw)


def asst(*blocks):
    return line(type="assistant", message={"content": list(blocks)})


TEXT = lambda t: {"type": "text", "text": t}          # noqa: E731
TOOL = {"type": "tool_use", "name": "Bash", "input": {}}
RESULT = line(type="user", message={"content": [{"type": "tool_result", "content": "ok"}]})
PROMPT = lambda t: line(type="user", message={"content": t})   # noqa: E731


def test_turn_counts_tools_and_takes_the_final_text():
    lines = [PROMPT("older prompt"), asst(TEXT("Old turn."), TOOL), RESULT,
             PROMPT("do the thing"), asst(TOOL), RESULT, asst(TOOL), RESULT, asst(TEXT("Fixed the bug. More detail here."))]
    assert eot.turn_summary(lines) == (2, "Fixed the bug. More detail here.")


def test_turn_stops_at_the_last_plain_user_entry_and_ignores_meta_entries():
    lines = [PROMPT("p1"), asst(TOOL, TEXT("first")), RESULT, PROMPT("p2"), line(type="attachment"), asst(TEXT("just chat"))]
    assert eot.turn_summary(lines) == (0, "just chat")
    assert eot.turn_summary(["not json", "", line(type="queue-operation")]) == (0, "")


@pytest.mark.parametrize("raw,expected", [
    ("**PR #731 is open** with the fix. Tests pass.", "PR number 731 is open with the fix."),
    ("## Result\nAll green.", "Result."),
    ("[#731](https://github.com/o/r/pull/731) merged as abc1234.", "number 731 merged as abc1234."),
    ("```\ncode\n```\nThe resolver reads NOUGEN_LANE from env", "The resolver reads NOUGEN LANE from env."),
    ("- first bullet sentence\n- second", "first bullet sentence."),
    ("", ""),
])
def test_sentence_strips_markdown_and_stays_speakable(raw, expected):
    assert eot.sentence(raw) == expected


def test_sentence_is_bounded_at_a_word_boundary():
    out = eot.sentence("word " * 80)
    assert len(out) <= eot.LIMIT + 3 and out.endswith("...") and not out.endswith(" ...")


def test_silent_when_no_tools_were_used_unless_forced():
    assert eot.announcement(0, "Heartbeat echo, nothing to do.") is None
    assert eot.announcement(0, "Heartbeat echo.", speak_all=True) == "Heartbeat echo."


def test_falls_back_to_a_count_when_there_is_no_text():
    assert eot.announcement(3, "") == "Turn complete, 3 tool calls."
    assert eot.announcement(1, "") == "Turn complete, 1 tool call."


def test_main_speaks_the_summary_of_a_real_shaped_transcript(tmp_path, monkeypatch):
    t = tmp_path / "s.jsonl"
    t.write_text("\n".join([PROMPT("go"), asst(TOOL), RESULT, asst(TEXT("Merged the snapshot fix. Verified on main."))]))
    said = []
    assert eot.main(json.dumps({"transcript_path": str(t)}), speak=said.append) == 0
    assert said == ["Merged the snapshot fix."]


def test_main_is_silent_for_echo_turns_and_survives_bad_input(tmp_path):
    t = tmp_path / "s.jsonl"
    t.write_text("\n".join([PROMPT("heartbeat"), asst(TEXT("Nothing to do."))]))
    said = []
    assert eot.main(json.dumps({"transcript_path": str(t)}), speak=said.append) == 0 and said == []
    assert eot.main("{not json", speak=said.append) == 0
    assert eot.main(json.dumps({"transcript_path": str(tmp_path / "missing.jsonl")}), speak=said.append) == 0
    assert said == []


# --- the resolver: explicit > env > lane > WhoArt favourite > river ---------------------------------

@pytest.fixture
def sync(tmp_path, monkeypatch):
    for var in ("NOUGEN_VOICE", "NOUGEN_VOICE_SPEED", "NOUGEN_LANE"):
        monkeypatch.delenv(var, raising=False)
    mod = _load("whoart_voice_sync")
    monkeypatch.setattr(mod, "LANE_FILE", tmp_path / "lanes.json")
    monkeypatch.setattr(mod, "get_voice_favorites", lambda force_refresh=False: {"female": [{"voice_id": "af_nova", "speed": 0.96}]})
    return mod


def test_lane_preference_beats_the_favourite_but_not_env_or_explicit(sync, monkeypatch, tmp_path):
    (tmp_path / "lanes.json").write_text('{"claude-app": "skye"}')
    assert sync.resolve_dynamic_voice() == ("af_nova", 0.96)                       # no lane known: favourite
    assert sync.resolve_dynamic_voice(lane="claude-app") == ("af_sky", 1.0)         # lane voice wins
    monkeypatch.setenv("NOUGEN_LANE", "claude-app")
    assert sync.resolve_dynamic_voice()[0] == "af_sky"                              # lane from the environment
    monkeypatch.setenv("NOUGEN_VOICE", "adam")
    assert sync.resolve_dynamic_voice()[0] == "am_adam"                             # env beats the lane
    assert sync.resolve_dynamic_voice("river")[0] == "af_river"                     # explicit beats everything


def test_missing_or_garbage_lane_file_falls_back_to_the_favourite(sync, tmp_path):
    assert sync.resolve_dynamic_voice(lane="claude-app")[0] == "af_nova"
    (tmp_path / "lanes.json").write_text("{not json")
    assert sync.resolve_dynamic_voice(lane="claude-app")[0] == "af_nova"
    (tmp_path / "lanes.json").write_text('{"claude-app": 7}')
    assert sync.resolve_dynamic_voice(lane="claude-app")[0] == "af_nova"
