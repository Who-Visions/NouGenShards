#!/usr/bin/env python3
"""nougen loop: one deterministic pass of recall -> build -> harden -> commit -> pr -> shard -> dream -> evolve -> handoff.

The stage list, order, and gate rules are fixed code. Nothing runs that writes
(commit, push, PR, shard, dream, handoff) unless --apply is given. Every stage
returns ok / skipped / failed with a reason, and the loop stops at the first
failure unless --keep-going. Tools that are missing (git, gh, pytest, the
nougen CLI) degrade to skipped, so the loop works in any repo.

Usage:
  python tools/nougen_loop.py --goal "fix flaky test" --paths src/x.py tests/test_x.py
  python tools/nougen_loop.py --goal "..." --paths ... --message "fix: ..." --apply
"""
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

STAGES = ["recall", "build", "harden", "commit", "pr", "shard", "dream", "evolve", "handoff"]
WRITE_STAGES = {"commit", "pr", "shard", "dream", "handoff"}

STAGE_TIMEOUT = float(os.environ.get("NOUGEN_LOOP_STAGE_TIMEOUT", "900"))
MAX_FILE_KB = int(os.environ.get("NOUGEN_LOOP_MAX_FILE_KB", "1024"))
LEDGER = Path(os.environ.get("NOUGEN_LOOP_LEDGER", str(Path.home() / ".nougen" / "state" / "loop_ledger.jsonl")))
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SECRET_PATTERNS = [
    re.compile(p) for p in (
        r"AKIA[0-9A-Z]{16}",
        r"(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"ghp_[A-Za-z0-9]{36}",
        r"github_pat_[A-Za-z0-9_]{40,}",
        r"sk-[A-Za-z0-9_-]{20,}",
        r"xox[baprs]-[A-Za-z0-9-]{10,}",
        r"AIza[0-9A-Za-z_-]{35}",
        r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]",
    )
] + [re.compile(p) for p in os.environ.get("NOUGEN_LOOP_EXTRA_SECRET_RE", "").split("||") if p]


@dataclass
class StageResult:
    stage: str
    status: str  # ok | skipped | failed | planned
    reason: str = ""
    evidence: dict = field(default_factory=dict)


def _resolve_exe(cmd: list[str], cwd: Path) -> list[str]:
    exe = cmd[0]
    local = (cwd / exe)
    if not Path(exe).is_absolute() and ("/" in exe or "\\" in exe) and local.exists():
        return [str(local), *cmd[1:]]
    found = shutil.which(exe)
    return [found, *cmd[1:]] if found else cmd


def _run(cmd: list[str], cwd: Path, timeout: float = STAGE_TIMEOUT, stdin: str | None = None) -> subprocess.CompletedProcess:
    cmd = _resolve_exe(cmd, cwd)
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, input=stdin, creationflags=_NO_WINDOW)
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", f"program not found: {cmd[0]}")


def _tail(text: str, n: int = 12) -> str:
    return "\n".join((text or "").strip().splitlines()[-n:])


def nougen_cli() -> list[str] | None:
    env = os.environ.get("NOUGEN_CLI", "").strip()
    if env:
        return env.split()
    if importlib.util.find_spec("nougen_shards") is not None:
        return [sys.executable, "-m", "nougen_shards.cli"]
    exe = shutil.which("nougen")
    return [exe] if exe else None


def git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return _run(["git", *args], cwd, timeout=120)


def default_branch(cwd: Path) -> str:
    r = git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], cwd)
    if r.returncode == 0 and "/" in r.stdout:
        return r.stdout.strip().split("/", 1)[1]
    return os.environ.get("NOUGEN_LOOP_DEFAULT_BRANCH", "main")


def detect_test_cmd(cwd: Path) -> list[str] | None:
    env = os.environ.get("NOUGEN_LOOP_TEST_CMD", "").strip()
    if env:
        return shlex.split(env, posix=os.name != "nt")
    if (cwd / "tests").is_dir() or (cwd / "pytest.ini").exists() or (cwd / "pyproject.toml").exists():
        if importlib.util.find_spec("pytest") is not None:
            return [sys.executable, "-m", "pytest", "-q", "-x"]
    if (cwd / "package.json").exists() and shutil.which("npm"):
        return ["npm", "test", "--silent"]
    return None


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "loop"


def scan_secrets(paths: list[Path]) -> list[dict]:
    findings = []
    for p in paths:
        if not p.is_file():
            continue
        if p.stat().st_size > MAX_FILE_KB * 1024:
            findings.append({"file": str(p), "line": 0, "kind": f"file over {MAX_FILE_KB} KB"})
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for pat in SECRET_PATTERNS:
                if pat.search(line):
                    findings.append({"file": str(p), "line": i, "kind": pat.pattern[:40]})
                    break
    return findings


class Loop:
    def __init__(self, args: argparse.Namespace):
        self.a = args
        self.cwd = Path(args.repo).resolve()
        self.cli = nougen_cli()
        self.results: list[StageResult] = []
        self.sha = ""
        self.pr_url = ""
        self.foreign_branch = ""

    def plan_only(self, stage: str) -> bool:
        return stage in WRITE_STAGES and not self.a.apply

    def st_recall(self) -> StageResult:
        if not self.cli:
            return StageResult("recall", "skipped", "nougen CLI not installed")
        r = _run([*self.cli, "search", self.a.goal], self.cwd, timeout=120)
        if r.returncode != 0:
            return StageResult("recall", "skipped", "search returned nonzero (empty vault?)", {"stderr": _tail(r.stderr, 4)})
        return StageResult("recall", "ok", "", {"top": _tail(r.stdout, 8)})

    def st_build(self) -> StageResult:
        cmd = detect_test_cmd(self.cwd)
        if not cmd:
            return StageResult("build", "skipped", "no test command detected (set NOUGEN_LOOP_TEST_CMD)")
        attempts = int(os.environ.get("NOUGEN_LOOP_BUILD_ATTEMPTS", "2"))
        last = None
        for n in range(1, attempts + 1):
            last = _run(cmd, self.cwd)
            if last.returncode == 0:
                return StageResult("build", "ok", f"attempt {n}", {"cmd": " ".join(cmd), "tail": _tail(last.stdout, 3)})
        return StageResult("build", "failed", f"tests failed after {attempts} attempts",
                           {"cmd": " ".join(cmd), "tail": _tail(last.stdout + last.stderr)})

    def st_harden(self) -> StageResult:
        paths = [self.cwd / p for p in self.a.paths]
        findings = scan_secrets(paths)
        if findings:
            return StageResult("harden", "failed", f"{len(findings)} secret-like or oversize finding(s)", {"findings": findings[:20]})
        return StageResult("harden", "ok", f"{len(paths)} path(s) clean")

    def _ensure_branch(self) -> str | None:
        cur = git(["branch", "--show-current"], self.cwd).stdout.strip()
        base = default_branch(self.cwd)
        if cur and cur != base and (cur.startswith("loop/") or self.a.on_current_branch):
            return cur
        if cur and cur != base:
            self.foreign_branch = cur
            return None
        new = f"loop/{slug(self.a.goal)}-{_dt.date.today().isoformat()}"
        if not self.a.apply:
            return new
        r = git(["checkout", "-b", new], self.cwd)
        return new if r.returncode == 0 else None

    def st_commit(self) -> StageResult:
        if not self.a.paths:
            return StageResult("commit", "skipped", "no --paths given (the loop never runs git add -A)")
        if not shutil.which("git"):
            return StageResult("commit", "skipped", "git not found")
        branch = self._ensure_branch()
        if not branch and self.foreign_branch:
            return StageResult("commit", "failed",
                               f"on branch {self.foreign_branch}, which the loop did not create; "
                               "switch to the default branch, or pass --on-current-branch if it is yours")
        if not branch:
            return StageResult("commit", "failed", "could not create a working branch")
        msg = self.a.message or f"chore: {self.a.goal}"
        if self.plan_only("commit"):
            return StageResult("commit", "planned", f"would commit {len(self.a.paths)} path(s) on {branch}", {"message": msg})
        r = git(["add", "--", *self.a.paths], self.cwd)
        if r.returncode != 0:
            return StageResult("commit", "failed", "git add failed", {"stderr": _tail(r.stderr)})
        if git(["diff", "--cached", "--quiet"], self.cwd).returncode == 0:
            return StageResult("commit", "skipped", "nothing staged")
        r = git(["commit", "-m", msg], self.cwd)
        if r.returncode != 0:
            return StageResult("commit", "failed", "commit rejected (hook?)", {"out": _tail(r.stdout + r.stderr)})
        self.sha = git(["rev-parse", "--short", "HEAD"], self.cwd).stdout.strip()
        return StageResult("commit", "ok", "", {"sha": self.sha, "branch": branch})

    def st_pr(self) -> StageResult:
        if self.a.no_pr:
            return StageResult("pr", "skipped", "--no-pr")
        gh = shutil.which("gh")
        if not gh:
            return StageResult("pr", "skipped", "gh CLI not found")
        branch = git(["branch", "--show-current"], self.cwd).stdout.strip()
        base = default_branch(self.cwd)
        if self.plan_only("pr"):
            return StageResult("pr", "planned", f"would push and open a PR into {base}")
        if not branch or branch == base:
            return StageResult("pr", "failed", f"refusing to push to default branch {base}")
        r = git(["push", "-u", "origin", branch], self.cwd)
        if r.returncode != 0:
            return StageResult("pr", "failed", "push failed", {"stderr": _tail(r.stderr)})
        view = _run([gh, "pr", "view", branch, "--json", "url", "-q", ".url"], self.cwd, timeout=60)
        if view.returncode == 0 and view.stdout.strip():
            self.pr_url = view.stdout.strip()
            return StageResult("pr", "ok", "PR already open, pushed update", {"url": self.pr_url})
        body = self.a.body or f"Goal: {self.a.goal}\n\nOpened by `nougen loop`."
        r = _run([gh, "pr", "create", "--base", base, "--head", branch,
                  "--title", self.a.message or self.a.goal, "--body", body], self.cwd, timeout=120)
        if r.returncode != 0:
            return StageResult("pr", "failed", "gh pr create failed", {"stderr": _tail(r.stderr)})
        self.pr_url = r.stdout.strip().splitlines()[-1]
        return StageResult("pr", "ok", "", {"url": self.pr_url})

    def _summary(self) -> str:
        lines = [f"nougen loop: {self.a.goal}"]
        for res in self.results:
            lines.append(f"- {res.stage}: {res.status}{' - ' + res.reason if res.reason else ''}")
        if self.sha:
            lines.append(f"commit {self.sha}")
        if self.pr_url:
            lines.append(f"pr {self.pr_url}")
        return "\n".join(lines)

    def st_shard(self) -> StageResult:
        if not self.cli:
            return StageResult("shard", "skipped", "nougen CLI not installed")
        if self.plan_only("shard"):
            return StageResult("shard", "planned", "would capture a run summary shard")
        r = _run([*self.cli, "add", "--stdin", "--tags", "nougen-loop"], self.cwd, timeout=120, stdin=self._summary())
        if r.returncode != 0:
            return StageResult("shard", "skipped", "capture returned nonzero", {"stderr": _tail(r.stderr, 4)})
        return StageResult("shard", "ok", "", {"out": _tail(r.stdout, 2)})

    def st_dream(self) -> StageResult:
        if not self.cli:
            return StageResult("dream", "skipped", "nougen CLI not installed")
        if self.plan_only("dream"):
            return StageResult("dream", "planned", "would run nougen dream wake")
        r = _run([*self.cli, "dream", "wake", "--json"], self.cwd)
        return StageResult("dream", "ok" if r.returncode == 0 else "skipped",
                           "" if r.returncode == 0 else "dream returned nonzero", {"tail": _tail(r.stdout, 4)})

    def st_evolve(self) -> StageResult:
        prev = None
        if LEDGER.exists():
            for line in LEDGER.read_text(encoding="utf-8", errors="replace").splitlines()[::-1]:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("repo") == self.cwd.name:
                    prev = rec
                    break
        now = {r.stage: r.status for r in self.results}
        delta = {}
        if prev:
            for stage, status in now.items():
                before = prev.get("stages", {}).get(stage)
                if before and before != status:
                    delta[stage] = f"{before} -> {status}"
        rec = {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(), "repo": self.cwd.name, "goal": self.a.goal,
               "stages": now, "sha": self.sha, "pr": self.pr_url, "applied": bool(self.a.apply)}
        try:
            LEDGER.parent.mkdir(parents=True, exist_ok=True)
            with LEDGER.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
        except OSError as exc:
            return StageResult("evolve", "ok", f"ledger unwritable ({exc}); delta printed only", {"delta": delta})
        return StageResult("evolve", "ok", "first run" if prev is None else f"{len(delta)} stage change(s)", {"delta": delta})

    def st_handoff(self) -> StageResult:
        if not self.cli:
            return StageResult("handoff", "skipped", "nougen CLI not installed")
        if self.plan_only("handoff"):
            return StageResult("handoff", "planned", "would write a handoff")
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write(self._summary())
            note = fh.name
        agent = os.environ.get("NOUGEN_AGENT", "nougen-loop")
        r = _run([*self.cli, "handoff", "create", "-a", agent, "-g", self.a.goal, "-M", note], self.cwd, timeout=120)
        os.unlink(note)
        return StageResult("handoff", "ok" if r.returncode == 0 else "skipped",
                           "" if r.returncode == 0 else "handoff returned nonzero", {"tail": _tail(r.stdout, 2)})

    def run(self) -> int:
        selected = [s for s in STAGES if s not in set(self.a.skip)]
        for stage in selected:
            try:
                res = getattr(self, f"st_{stage}")()
            except subprocess.TimeoutExpired:
                res = StageResult(stage, "failed", f"timeout after {STAGE_TIMEOUT:.0f}s")
            self.results.append(res)
            self._print(res)
            if res.status == "failed" and not self.a.keep_going:
                break
        for s in STAGES:
            if s not in {r.stage for r in self.results}:
                self.results.append(StageResult(s, "skipped", "not reached" if s in selected else "--skip"))
        if self.a.json:
            print(json.dumps([asdict(r) for r in self.results], indent=2))
        failed = [r for r in self.results if r.status == "failed"]
        return 1 if failed else 0

    def _print(self, res: StageResult) -> None:
        if self.a.json:
            return
        icon = {"ok": "OK  ", "skipped": "SKIP", "failed": "FAIL", "planned": "PLAN"}[res.status]
        print(f"[{icon}] {res.stage:<8} {res.reason}")
        for k, v in res.evidence.items():
            if v:
                text = v if isinstance(v, str) else json.dumps(v)
                print(f"         {k}: {text[:400]}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="nougen loop", description=__doc__.splitlines()[0])
    p.add_argument("--goal", required=True, help="one-line goal; used for recall, branch name, PR title fallback")
    p.add_argument("--paths", nargs="*", default=[], help="exact paths to stage (never git add -A)")
    p.add_argument("--message", "-m", default="", help="commit message / PR title")
    p.add_argument("--body", default="", help="PR body")
    p.add_argument("--repo", default=".", help="repo root (default: cwd)")
    p.add_argument("--apply", action="store_true", help="actually run write stages; default is a dry run")
    p.add_argument("--skip", nargs="*", default=[], choices=STAGES, help="stages to skip")
    p.add_argument("--no-pr", action="store_true", help="commit but do not push or open a PR")
    p.add_argument("--on-current-branch", action="store_true",
                   help="allow committing on a non-default branch the loop did not create (it must be yours)")
    p.add_argument("--keep-going", action="store_true", help="continue after a failed stage")
    p.add_argument("--json", action="store_true", help="machine-readable results")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return Loop(parse_args(argv)).run()


if __name__ == "__main__":
    sys.exit(main())
