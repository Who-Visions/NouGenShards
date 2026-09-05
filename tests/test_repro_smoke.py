"""Clean-room reproducibility contract (leg 20260829T045810Z).

The invariant these lock down: a fresh clone of the public repo must build,
import and test itself with NO credentials present. Secrets are deployment
configuration, not build inputs. Conflating the two is what makes a stack look
irreproducible when it is merely unconfigured.
"""
import ast
import json
import subprocess
import sys
from pathlib import Path



ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP = ROOT / "tools" / "bootstrap.py"


def test_bootstrap_command_exists():
    """Doctrine told every agent to run .venv/Scripts/python.exe; nothing made it."""
    assert BOOTSTRAP.is_file(), "a clean clone needs one documented bootstrap command"


def test_bootstrap_is_dependency_free():
    """It runs BEFORE anything is installed, so it may import stdlib only."""
    tree = ast.parse(BOOTSTRAP.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    third_party = imported - set(sys.stdlib_module_names) - {"__future__"}
    assert not third_party, f"bootstrap must be stdlib-only, found {third_party}"


def test_bootstrap_never_embeds_a_secret_value():
    """The contract is secret NAMES only -- no values in the repo, ever."""
    import tools.bootstrap as bs

    for name, why in {**bs.SECRETS, **bs.OPTIONAL_SECRETS}.items():
        assert name.isupper(), name
        assert why and isinstance(why, str), f"{name} needs a human reason"
        # A description, not a credential: no long opaque tokens.
        assert not any(len(tok) > 30 and tok.isalnum() for tok in why.split())


def test_secrets_are_not_required_to_build():
    """A missing credential must never fail the build gate."""
    import tools.bootstrap as bs

    report = []
    bs.verify_secrets(report)
    assert report, "secret presence should be reported"
    assert all(not r["required"] for r in report), (
        "a clean-room clone must build and test with zero credentials"
    )


def test_venv_interpreter_path_is_platform_correct():
    import tools.bootstrap as bs

    p = str(bs.venv_python())
    assert ("Scripts" in p and p.endswith(".exe")) if sys.platform == "win32" else p.endswith("bin/python")


def test_bootstrap_check_emits_machine_readable_report():
    """CI gates on the exit code, so the report has to be parseable and honest."""
    proc = subprocess.run(
        [sys.executable, str(BOOTSTRAP), "--check", "--json"],
        capture_output=True, text=True, cwd=ROOT, timeout=180,
    )
    data = json.loads(proc.stdout)
    assert set(data) >= {"ok", "root", "steps"}
    names = {s["step"] for s in data["steps"]}
    assert {"venv", "install", "cli"} <= names, names
    # Exit code must agree with the report; a green exit on a failed required
    # step is how a broken bootstrap ships unnoticed.
    assert (proc.returncode == 0) == data["ok"]


def test_bootstrap_never_reads_a_credential_value():
    """Presence must be membership, not a read.

    CodeQL flagged three highs (py/clear-text-logging-sensitive-data) when this
    file used os.environ.get on credential names -- correctly, since the value
    entered the process even though only names were printed. A value that is
    never bound cannot be leaked by a later edit.
    """
    src = BOOTSTRAP.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (isinstance(fn, ast.Attribute) and fn.attr == "get"
                and isinstance(fn.value, ast.Attribute) and fn.value.attr == "environ"):
            raise AssertionError(
                f"os.environ.get at line {node.lineno}: use membership, never read the value"
            )
