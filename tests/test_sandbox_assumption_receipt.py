import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards import nougen_sandbox  # noqa: E402


def _run(code, language="python"):
    # Stub the subprocess layer: this test is about the receipt, not the runner.
    with mock.patch.object(nougen_sandbox, "_execute_sandboxed", return_value="42"):
        return nougen_sandbox.execute_sandboxed(code, language=language, trusted=True,
                                                bypass_gatekeeper=True)


def test_clean_code_output_is_unchanged():
    assert _run("print(6*7)") == "42"


def test_risky_code_keeps_output_and_appends_receipt():
    out = _run("total = df['x'].fillna(0).sum()")
    assert out.startswith("42")
    assert "assumption check: 1 risky pattern" in out


def test_shell_output_is_never_annotated():
    with mock.patch.object(nougen_sandbox, "_execute_sandboxed", return_value="ok"):
        out = nougen_sandbox.execute_sandboxed("x=$(d.get k 0)", language="bash",
                                               trusted=True, bypass_gatekeeper=True)
    assert out == "ok"
