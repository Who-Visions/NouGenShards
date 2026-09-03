"""Windows UX + Unicode regression guard (GM directive, leg 20260903T015748Z).

Every subprocess spawn under src/ and tools/ must (a) pass CREATE_NO_WINDOW when
it launches a console app (powershell / pwsh / cmd, or shell=True), because a
console child of a windowless parent (pythonw, an MCP server, a hook spawned
with windowsHide) flashes a terminal and steals focus; and (b) set an explicit
encoding when text=True, because the console codepage (cp1252) killed the
relay-live daemon on a curly quote on 2026-09-03. AST-based, so string
mentions in comments or docstrings do not count."""
import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPAWN = ("run", "Popen", "check_output", "check_call", "call")
CONSOLE_MARKERS = ("powershell", "pwsh", "'cmd'", '"cmd"', "cmd.exe")


def _kw(call, name):
    return next((k for k in call.keywords if k.arg == name), None)


def _rel(p):
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def spawn_findings(paths):
    out = []
    for p in paths:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            if name not in SPAWN:
                continue
            mod = ast.unparse(f.value) if isinstance(f, ast.Attribute) else ""
            if mod != "subprocess" and name != "Popen":
                continue
            argv = ast.unparse(n.args[0]).lower() if n.args else ""
            shell = _kw(n, "shell")
            console = any(m in argv for m in CONSOLE_MARKERS) or (shell is not None and ast.unparse(shell.value) == "True")
            flags = ast.unparse(_kw(n, "creationflags").value) if _kw(n, "creationflags") else ""
            text = _kw(n, "text") is not None and ast.unparse(_kw(n, "text").value) == "True"
            if console and "NO_WINDOW" not in flags:
                out.append(f"{_rel(p)}:{n.lineno} console spawn without CREATE_NO_WINDOW: {argv[:60]}")
            if text and _kw(n, "encoding") is None:
                out.append(f"{_rel(p)}:{n.lineno} text=True without encoding=: {argv[:60]}")
    return out


def _py_files():
    return sorted(list((ROOT / "src").rglob("*.py")) + list((ROOT / "tools").rglob("*.py")))


# Files whose spawn fix was applied in the working tree on 2026-09-03 but ride in
# another lane's uncommitted work (shared tree: never sweep a peer's diff into your
# commit). Each entry is removed the moment that lane lands. Keep this list shrinking.
GRANDFATHERED_UNTIL_LANE_LANDS = {
    "src/nougen_shards/hooks.py", "src/nougen_shards/nougenmsg.py", "src/nougen_shards/dav1d_executor.py",
    "src/nougen_shards/vram_gate.py", "tools/start_grid.py", "src/nougen_shards/agy_msg.py",
    "src/nougen_shards/sessions.py", "tools/fleet_heartbeat.py", "tools/harness_eval.py",
}


def test_no_console_spawn_or_cp1252_decode_in_src_and_tools():
    findings = [f for f in spawn_findings(_py_files())
                if f.split(":", 1)[0].replace("\\", "/") not in GRANDFATHERED_UNTIL_LANE_LANDS]
    assert not findings, "\n".join(findings)


def test_grandfather_list_only_names_existing_files():
    missing = [f for f in GRANDFATHERED_UNTIL_LANE_LANDS if not (ROOT / f).exists()]
    assert not missing, f"prune these from GRANDFATHERED_UNTIL_LANE_LANDS: {missing}"


def test_scanner_catches_both_defects(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text(
        'import subprocess\n'
        'subprocess.run(["powershell.exe", "-Command", "x"], capture_output=True, text=True)\n'
        'subprocess.Popen(["git", "status"], text=True)\n'
        'subprocess.run("dir", shell=True)\n',
        encoding="utf-8")
    good = tmp_path / "good.py"
    good.write_text(
        'import subprocess\n'
        'NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)\n'
        'subprocess.run(["powershell.exe", "-Command", "x"], capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)\n'
        'subprocess.run(["git", "status"], capture_output=True, text=True, encoding="utf-8")\n'
        '# powershell.exe mentioned in a comment does not count\n',
        encoding="utf-8")
    f = spawn_findings([bad])
    assert len(f) == 4 and sum("CREATE_NO_WINDOW" in x for x in f) == 2 and sum("encoding=" in x for x in f) == 2
    assert spawn_findings([good]) == []


@pytest.mark.skipif(not hasattr(__import__("subprocess"), "CREATE_NO_WINDOW"), reason="Windows-only flag")
def test_create_no_window_flag_is_usable_alone():
    import subprocess
    r = subprocess.run(["cmd.exe", "/c", "echo", "ok"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=20)
    assert r.returncode == 0 and "ok" in r.stdout
