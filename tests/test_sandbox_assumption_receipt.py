import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards import nougen_sandbox  # noqa: E402


def _run(code, language="python", **kwargs):
    # Stub the subprocess layer: this test is about the gate, not the runner.
    with mock.patch.object(nougen_sandbox, "_execute_sandboxed", return_value="42") as runner:
        out = nougen_sandbox.execute_sandboxed(code, language=language, trusted=True,
                                               bypass_gatekeeper=True, **kwargs)
    return out, runner


def test_clean_code_runs_and_returns_output_unchanged():
    out, runner = _run("print(6*7)")
    assert out == "42"
    runner.assert_called_once()


def test_risky_code_is_blocked_before_it_runs():
    out, runner = _run("total = df['x'].fillna(0).sum()")
    assert out.startswith("Error: blocked by assumption check")
    assert "assumption check: 1 risky pattern" in out
    runner.assert_not_called()


def test_reviewer_can_allow_risky_code():
    out, runner = _run("total = df['x'].fillna(0).sum()", allow_assumptions=True)
    assert out == "42"
    runner.assert_called_once()


def test_shell_runtime_is_not_scanned():
    with mock.patch.object(nougen_sandbox, "_execute_sandboxed", return_value="ok") as runner:
        out = nougen_sandbox.execute_sandboxed("x=$(d.get k 0)", language="bash",
                                               trusted=True, bypass_gatekeeper=True)
    assert out == "ok"
    runner.assert_called_once()
