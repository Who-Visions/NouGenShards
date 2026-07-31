"""Colour resolution must never guess: it probes, and it stays out of pipes."""
import io

from nougen_shards import theme


class _Tty(io.StringIO):
    def isatty(self):
        return True


class _Pipe(io.StringIO):
    def isatty(self):
        return False


def test_pipe_gets_no_colour_by_default():
    assert theme.colour_enabled(_Pipe(), env={}) is False


def test_tty_gets_colour_by_default():
    assert theme.colour_enabled(_Tty(), env={}) is True


def test_no_color_beats_force_color():
    env = {"NO_COLOR": "1", "FORCE_COLOR": "1"}
    assert theme.colour_enabled(_Tty(), env=env) is False


def test_force_color_survives_a_pipe():
    assert theme.colour_enabled(_Pipe(), env={"FORCE_COLOR": "1"}) is True


def test_nougen_color_never_overrides_a_tty():
    assert theme.colour_enabled(_Tty(), env={"NOUGEN_COLOR": "never"}) is False


def test_dumb_terminal_is_not_coloured():
    assert theme.colour_enabled(_Tty(), env={"TERM": "dumb"}) is False


def test_palette_slot_resolves_from_env_before_constant():
    env = {"NOUGEN_COLOR_ACCENT": "38;5;201"}
    assert theme.palette(env)["accent"] == "38;5;201"
    # Untouched slots keep their fallback.
    assert theme.palette(env)["ok"] == theme._DEFAULT_PALETTE["ok"]


def test_paint_routes_glyphs_to_slots():
    env = {"FORCE_COLOR": "1"}
    pal = theme.palette(env)
    assert theme.paint("✅ saved", stream=_Tty(), env=env).startswith(f"\033[{pal['ok']}m")
    assert theme.paint("❌ failed", stream=_Tty(), env=env).startswith(f"\033[{pal['err']}m")
    assert theme.paint("🔍 Found 3", stream=_Tty(), env=env).startswith(f"\033[{pal['info']}m")
    assert theme.paint("🪩 NouGenShards", stream=_Tty(), env=env).startswith(f"\033[{pal['accent']}m")


def test_unglyphed_line_is_left_alone():
    out = theme.paint(" - DB #1: 16702 shards", stream=_Tty(), env={"FORCE_COLOR": "1"})
    assert out == " - DB #1: 16702 shards"


def test_styled_print_leaves_piped_output_clean():
    pipe = _Pipe()
    theme.styled_print("✅ saved", file=pipe)
    assert pipe.getvalue() == "✅ saved\n"


def test_styled_print_joins_before_painting():
    pipe = _Pipe()
    theme.styled_print("✅", "saved", file=pipe)
    assert pipe.getvalue() == "✅ saved\n"
