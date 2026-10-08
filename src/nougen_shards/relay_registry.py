"""Shared read-only discovery of the canonical fleet relay registry."""
import os
import sys
from pathlib import Path

RELAY_DIR_ENV_VARS = ("NOUGEN_RELAY_DIR", "FLEET_RELAY_DIR")
EX_CONFIG = 78


def _relay_registry_candidates(home_dir=None):
    """Where the fleet registry clone may live, most explicit first.

    A NouGenShards checkout carries its own legacy `.handoffs/` (the older
    per-repo handoff system), so simply running the relay CLI from this repo
    silently reads the wrong board. The registry must be located explicitly.
    """
    for var in RELAY_DIR_ENV_VARS:
        raw = os.environ.get(var, "").strip()
        if raw:
            yield Path(raw).expanduser()
    yield (Path(home_dir) if home_dir is not None else Path.home() / ".nougen") / "relay"
    # An installed (editable) nougen_relay is normally the registry clone's
    # own src/ tree, so the clone is two levels above the package.
    try:
        import nougen_relay as _relay_pkg
    except ImportError:
        _relay_pkg = None
    pkg_file = getattr(_relay_pkg, "__file__", None)
    if pkg_file:
        pkg_path = Path(pkg_file).resolve()
        if len(pkg_path.parents) > 2:
            yield pkg_path.parents[2]
    here = Path(__file__).resolve()
    # src/nougen_shards/cli.py -> repo root is parents[2]; the fleet keeps
    # NouGenRelay either beside the repo or beside the repo's parent folder
    # (The Observatory/NouGenRelay next to The Observatory/NouGen/nougenshards).
    for depth in (3, 4):
        if len(here.parents) > depth:
            yield here.parents[depth] / "NouGenRelay"


RELAY_REGISTRY_BRANCH = os.environ.get("NOUGEN_RELAY_BRANCH", "main")


def _checkout_branch(repo: Path):
    """Current branch of a checkout or worktree from .git/HEAD (no subprocess); None if detached/unknown."""
    git = repo / ".git"
    try:
        if git.is_file():  # worktree: "gitdir: <path>"
            text = git.read_text(encoding="utf-8").strip()
            if not text.startswith("gitdir:"):
                return None
            gitdir = Path(text.split(":", 1)[1].strip())
            git = gitdir if gitdir.is_absolute() else (repo / gitdir)
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return head.rsplit("/", 1)[-1] if head.startswith("ref: refs/heads/") else None


def find_relay_registry(home_dir=None):
    """Return the NouGenRelay clone that holds a `.handoffs/` registry, or None.

    An explicit $NOUGEN_RELAY_DIR / $FLEET_RELAY_DIR always wins. Otherwise a candidate checked
    out on the registry branch ($NOUGEN_RELAY_BRANCH, default main) is preferred: on 2026-10-04 the
    fallback was the installed nougen_relay package's clone, sitting on a feature branch ~4400
    commits behind main, so every leg created through the MCP connector was invisible to the CLI
    ("no matching handoff record found"). A non-main fallback is still returned, but loudly.
    """
    explicit = {Path(os.environ[v].strip()).expanduser() for v in RELAY_DIR_ENV_VARS if os.environ.get(v, "").strip()}
    fallback = None
    for cand in _relay_registry_candidates(home_dir):
        if not ((cand / ".handoffs").is_dir() and (cand / "src" / "nougen_relay").is_dir()):
            continue
        if cand in explicit:
            return cand
        branch = _checkout_branch(cand)
        if branch == RELAY_REGISTRY_BRANCH:
            return cand
        if fallback is None:
            fallback = (cand, branch)
    if fallback is not None:
        cand, branch = fallback
        print(f"WARNING: relay registry {cand} is on branch {branch or 'DETACHED'!r}, not "
              f"{RELAY_REGISTRY_BRANCH!r}; legs created elsewhere may be missing. "
              f"Set NOUGEN_RELAY_DIR to a {RELAY_REGISTRY_BRANCH} checkout.", file=sys.stderr)
        return cand
    return None
