"""What this PUBLIC repo is allowed to say about the private machines behind it.

This repository is world-readable. Everything tracked in it is published the
moment it is pushed, and untracking a file later does not unpublish it — the
content stays in history and any clone can still read it.

That is not hypothetical. `CLAUDE.md` and `GEMINI.md` were untracked in #61
because they carry the fleet's operating doctrine and the operator's first
name. They are gone from the working tree and still retrievable from every
clone via `git show <rev>^:GEMINI.md`. Untracking two known files is not the
same as testing the surface, and this file is the difference.

## Why three checks and not one

Each of the three found something the others structurally could not:

- CREDENTIALS  the usual scan. Found nothing — correctly. There are no keys in
               this repo, and two independent audits agreed on that.
- MACHINE      account names and absolute paths. Found
               `C:\\Users\\<name>\\Watchtower\\vault` in a tracked shell script
               that #61 walked straight past, because #61 was a list of two
               filenames rather than a property.
- IDENTITY     a person's name is not credential-shaped and lives in no path.
               Two credential scans called the file clean while the specific
               thing that had been reported about it sat on line 7.

A scan that only looks for `sk-` prefixes will keep reporting a clean surface
while publishing who you are and where you live on disk.

## Why the names are not written in this file

A guard that greps for a real name has to contain that name, and this file is
published too — the check would leak exactly what it exists to prevent. So
IDENTITY takes its terms from `NOUGEN_SURFACE_NAMES` (comma-separated) and
matches nothing when unset. Set it in CI or a local shell:

    NOUGEN_SURFACE_NAMES="firstname,lastname" pytest tests/test_published_surface.py

The structural checks need no configuration and always run.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: Binary and generated files: nothing human-authored to leak.
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf",
                 ".db", ".sqlite", ".sqlite3", ".zip", ".gz", ".whl", ".lock"}

#: Live credential shapes. Deliberately narrow — a loose pattern trains people
#: to add allowlist entries, and an allowlist nobody reads guards nothing.
CREDENTIAL = re.compile(
    r"sk-or-v1-[A-Za-z0-9_-]{20,}"
    r"|sk-ant-api\d{2}-[A-Za-z0-9_-]{20,}"
    r"|sk-proj-[A-Za-z0-9_-]{20,}"
    r"|AIza[0-9A-Za-z_-]{30,}"
    r"|gh[pousr]_[A-Za-z0-9]{30,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)

#: A named human account, or a personal mailbox. `C:\Users\<name>` and
#: `/Users/<name>` both name the operator; `/Users/runner` and friends are CI.
MACHINE = re.compile(
    r"[Cc]:\\+Users\\+(?!Public\b|Default\b|All Users\b)[A-Za-z][A-Za-z0-9._-]*"
    r"|/Users/(?!runner\b|shared\b)[a-z][a-z0-9._-]*"
    r"|/home/(?!runner\b|user\b|ubuntu\b)[a-z][a-z0-9._-]*"
    r"|[A-Za-z0-9._%+-]+@(?:gmail|outlook|hotmail|yahoo|icloud|proton(?:mail)?)\.[a-z]{2,}"
)


def _identity_pattern() -> re.Pattern | None:
    """Names to refuse, supplied by the environment — never written here."""
    raw = (os.environ.get("NOUGEN_SURFACE_NAMES") or "").strip()
    terms = [re.escape(t.strip()) for t in raw.split(",") if t.strip()]
    if not terms:
        return None
    return re.compile(r"\b(?:" + "|".join(terms) + r")\b", re.IGNORECASE)


#: Files reviewed and permitted to contain a matching shape, with the reason.
#: A path here is a decision someone made, not a way to silence the test — the
#: reason is the record of that decision.
ALLOWED = {
    "src/nougen_shards/brain_scan/redaction.py":
        "defines the credential patterns; matching them is its job",
    "ts/src/nougen_shards/brain_scan/redaction.ts":
        "the TypeScript half of the same pattern table",
    "tests/test_brain_scan.py":
        "fixtures that must look like real keys to exercise redaction",
    "ts/src/test/brain_scan.test.ts":
        "same fixtures, TypeScript side",
    "tests/test_audit_fixes.py":
        "asserts the redactor catches these shapes",
    "tests/test_auth_check.py":
        "fixtures must LOOK like real keys — the tests assert a credential "
        "never reaches a Result or a report, which only proves anything if "
        "the value has a credential's shape",
    "docs/AUDIT_DEEP_DIVE.md":
        "prose describing the patterns the redactor looks for",
    "tests/test_published_surface.py":
        "this file: the patterns live here by definition",
    "ops/launchd/com.whovisions.kaedragw.plist":
        "launchd plists take literal absolute paths only — no $HOME or env "
        "expansion in ProgramArguments/WorkingDirectory/StandardOutPath. "
        "bin/kaedra-gateway.sh (the script this launches) self-locates "
        "instead; this file is the one place that genuinely cannot.",
}


def _tracked_files() -> list[str]:
    """Tracked files only.

    Note the consequence: a NEW file is invisible to this guard until it is
    staged, so a fresh test fixture can pass locally and fail in CI. That is
    the correct trade — scanning untracked scratch files would make the guard
    unusable — but run it after `git add`, not before.
    """
    out = subprocess.run(["git", "ls-files"], cwd=REPO,
                         capture_output=True, text=True, check=False)
    return [f for f in out.stdout.splitlines()
            if f and Path(f).suffix.lower() not in SKIP_SUFFIXES]


def _read(rel: str) -> str:
    try:
        return (REPO / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _scan(pattern: re.Pattern) -> list[tuple[str, int]]:
    """Every tracked, non-allowlisted file matching `pattern`, with line number."""
    found = []
    for rel in _tracked_files():
        if rel in ALLOWED:
            continue
        for n, line in enumerate(_read(rel).splitlines(), 1):
            if pattern.search(line):
                found.append((rel, n))
                break
    return found


# --- the three checks -----------------------------------------------------

def test_no_live_credentials_are_published():
    hits = _scan(CREDENTIAL)
    assert not hits, (
        "Credential-shaped strings on a public repo:\n"
        + "\n".join(f"  {f}:{n}" for f, n in hits)
        + "\n\nIf it is a pattern or fixture rather than a key, add the path to "
          "ALLOWED with the reason. If it is a real key, ROTATE IT — untracking "
          "does not unpublish, it stays in history."
    )


def test_no_account_names_or_machine_paths_are_published():
    """The check #61 did not have. It untracked two known filenames; this tests
    the property, and it is what finds the third file nobody remembered."""
    hits = _scan(MACHINE)
    assert not hits, (
        "Account names or personal paths on a public repo:\n"
        + "\n".join(f"  {f}:{n}" for f, n in hits)
        + "\n\nReplace with a placeholder (<user>, ~, %USERPROFILE%). These name "
          "the operator and the layout of their disk."
    )


@pytest.mark.skipif(_identity_pattern() is None,
                    reason="NOUGEN_SURFACE_NAMES unset — see this module's docstring")
def test_no_personal_names_are_published():
    """A name is not credential-shaped and lives in no path, which is how two
    independent scans called a file clean while the reported problem sat in
    line 7 of it."""
    pattern = _identity_pattern()
    assert pattern is not None
    hits = _scan(pattern)
    assert not hits, (
        "Personal names on a public repo:\n"
        + "\n".join(f"  {f}:{n}" for f, n in hits)
        + "\n\nUse a role instead — 'the operator', 'the GM'."
    )


# --- the guard's own integrity --------------------------------------------

def test_the_allowlist_is_not_a_dumping_ground():
    """Every entry must name a file that exists and give a reason. A stale path
    is an exemption nobody is reviewing."""
    tracked = set(_tracked_files())
    for path, reason in ALLOWED.items():
        assert path in tracked, f"ALLOWED names {path}, which is not tracked"
        assert len(reason) > 20, f"{path} needs a real reason, not '{reason}'"


def test_the_checks_actually_fire(tmp_path, monkeypatch):
    """A guard that cannot fail is decoration. Proves each pattern matches."""
    assert CREDENTIAL.search("token = sk-or-v1-" + "a" * 40)
    assert CREDENTIAL.search("-----BEGIN RSA PRIVATE KEY-----")
    assert MACHINE.search(r"path is C:\Users\someone\Watchtower\vault")
    assert MACHINE.search("/Users/someone/Library")
    assert MACHINE.search("mail person@gmail.com today")

    monkeypatch.setenv("NOUGEN_SURFACE_NAMES", "zaphod,beeblebrox")
    pattern = _identity_pattern()
    assert pattern and pattern.search("signed, Zaphod")


def test_ci_paths_and_shared_accounts_are_not_flagged():
    """GitHub runners and Windows system accounts are not people."""
    for benign in ("/Users/runner/work/repo", "/home/runner/.cache",
                   r"C:\Users\Public\Documents", "/home/ubuntu/app"):
        assert not MACHINE.search(benign), f"false positive on {benign}"


def test_placeholders_are_not_flagged():
    """The fix this guard asks for must itself pass."""
    for ok in (r"C:\Users\<user>\Watchtower\vault", "~/Watchtower/vault",
               r"%USERPROFILE%\Watchtower\vault"):
        assert not MACHINE.search(ok), f"false positive on the suggested fix: {ok}"
