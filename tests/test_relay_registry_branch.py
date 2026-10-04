"""find_relay_registry prefers a main checkout over a stale feature-branch clone (2026-10-04)."""
from pathlib import Path

from nougen_shards import cli


def _registry(root: Path, branch: str, worktree: bool = False) -> Path:
    (root / ".handoffs").mkdir(parents=True)
    (root / "src" / "nougen_relay").mkdir(parents=True)
    if worktree:
        gitdir = root.parent / f"{root.name}.gitdir"
        gitdir.mkdir()
        (gitdir / "HEAD").write_text(f"ref: refs/heads/{branch}\n")
        (root / ".git").write_text(f"gitdir: {gitdir}\n")
    else:
        (root / ".git").mkdir()
        (root / ".git" / "HEAD").write_text(f"ref: refs/heads/{branch}\n")
    return root


def _use(monkeypatch, *cands):
    monkeypatch.setattr(cli, "_relay_registry_candidates", lambda: iter(cands))


def test_main_checkout_beats_earlier_stale_clone(tmp_path, monkeypatch, capsys):
    for v in cli.RELAY_DIR_ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    stale = _registry(tmp_path / "NouGenRelay", "pi-remix")
    main = _registry(tmp_path / "NouGenRelay-main", "main", worktree=True)
    _use(monkeypatch, stale, main)
    assert cli.find_relay_registry() == main
    assert "WARNING" not in capsys.readouterr().err


def test_stale_only_is_returned_with_warning(tmp_path, monkeypatch, capsys):
    for v in cli.RELAY_DIR_ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    stale = _registry(tmp_path / "NouGenRelay", "pi-remix")
    _use(monkeypatch, stale)
    assert cli.find_relay_registry() == stale
    err = capsys.readouterr().err
    assert "pi-remix" in err and "NOUGEN_RELAY_DIR" in err


def test_explicit_env_wins_even_off_main(tmp_path, monkeypatch, capsys):
    stale = _registry(tmp_path / "Pinned", "feature-x")
    main = _registry(tmp_path / "NouGenRelay-main", "main")
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(stale))
    _use(monkeypatch, stale, main)
    assert cli.find_relay_registry() == stale
    assert "WARNING" not in capsys.readouterr().err


def test_detached_head_is_not_main(tmp_path):
    repo = tmp_path / "r"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("0123456789abcdef0123456789abcdef01234567\n")
    assert cli._checkout_branch(repo) is None
