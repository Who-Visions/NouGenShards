"""PR lease governor + confetti detector.

Phase 1 of the SHANG TSUNG PR-Agent absorption (relay leg
20260908T025803Z__chatgpt-app__g-whoentertains): stop one coherent objective
from spawning one PR per atomic change. One objective -> one branch -> one
PR; pushes to that branch update the existing PR instead of opening another.

State lives in a small JSON file, not a database — this is a governor, not
an analytics store. Tracker metrics (Phase 6) can read the same file.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DEFAULT_STATE_PATH = Path.home() / ".nougen" / "pr_lease_state.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(objective: str) -> str:
    """Normalize an objective string into a stable lease key."""
    s = objective.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80] or "objective"


CHAIN_MIN = 3
CHAIN_MAX = 5


@dataclass
class Lease:
    objective: str
    objective_key: str
    repo: str
    branch: str
    pr_number: Optional[int] = None
    last_reviewed_sha: Optional[str] = None
    commit_count: int = 0
    created_utc: str = field(default_factory=_now)
    updated_utc: str = field(default_factory=_now)
    relay_leg_id: Optional[str] = None
    claim_id: Optional[str] = None
    # Chaining: a lease/branch/PR should bundle CHAIN_MIN..CHAIN_MAX related
    # objectives before it closes, instead of one PR per atomic objective.
    # `objective` above stays the first/primary objective for the lease key;
    # `chained_objectives` holds every objective folded into this same PR.
    chained_objectives: list = field(default_factory=list)

    @property
    def chain_len(self) -> int:
        return len(self.chained_objectives) or 1

    @property
    def chain_status(self) -> str:
        n = self.chain_len
        if n < CHAIN_MIN:
            return "UNDERFILLED"  # ok to keep adding objectives to this PR
        if n <= CHAIN_MAX:
            return "IN_RANGE"     # sweet spot; fine to land
        return "OVERSIZED"        # stop adding, land this one, start a new chain


class LeaseStore:
    """Persists objective -> lease bindings so a repeated objective reuses
    its branch/PR instead of minting a new one each time it's invoked."""

    def __init__(self, path: Path = DEFAULT_STATE_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def _key(self, repo: str, objective_key: str) -> str:
        return f"{repo}::{objective_key}"

    def get(self, repo: str, objective: str) -> Optional[Lease]:
        row = self._data.get(self._key(repo, _slug(objective)))
        return Lease(**row) if row else None

    def lease(
        self,
        repo: str,
        objective: str,
        branch: str,
        pr_number: Optional[int] = None,
        relay_leg_id: Optional[str] = None,
        claim_id: Optional[str] = None,
    ) -> tuple[Lease, bool]:
        """Return (lease, created). Reuses an existing lease for the same
        (repo, objective) pair; only mints a new one when none exists."""
        okey = _slug(objective)
        existing = self.get(repo, objective)
        if existing:
            return existing, False
        lease = Lease(
            objective=objective,
            objective_key=okey,
            repo=repo,
            branch=branch,
            pr_number=pr_number,
            relay_leg_id=relay_leg_id,
            claim_id=claim_id,
            chained_objectives=[objective],
        )
        self._data[self._key(repo, okey)] = asdict(lease)
        self._save()
        return lease, True

    def record_push(self, repo: str, objective: str, sha: str, pr_number: Optional[int] = None) -> Lease:
        okey = _slug(objective)
        key = self._key(repo, okey)
        row = self._data.get(key)
        if not row:
            raise KeyError(f"no lease for objective={objective!r} repo={repo!r}; call lease() first")
        row["last_reviewed_sha"] = sha
        row["commit_count"] = row.get("commit_count", 0) + 1
        row["updated_utc"] = _now()
        if pr_number is not None:
            row["pr_number"] = pr_number
        self._data[key] = row
        self._save()
        return Lease(**row)

    def open_chain(self, repo: str) -> Optional[Lease]:
        """Most recently touched lease in `repo` that still has chain room
        (chain_len < CHAIN_MAX). None if every lease is full or none exist."""
        candidates = [Lease(**r) for r in self._data.values() if r.get("repo") == repo]
        candidates = [c for c in candidates if c.chain_len < CHAIN_MAX]
        if not candidates:
            return None
        candidates.sort(key=lambda c: c.updated_utc, reverse=True)
        return candidates[0]

    def attach_objective(
        self,
        repo: str,
        objective: str,
        branch_hint: Optional[str] = None,
        relay_leg_id: Optional[str] = None,
        claim_id: Optional[str] = None,
    ) -> tuple[Lease, bool]:
        """Fold `objective` into the repo's open chain if one has room
        (< CHAIN_MAX objectives); otherwise start a new chain/branch/PR.
        Returns (lease, started_new_chain)."""
        chain = self.open_chain(repo)
        if chain is not None:
            key = self._key(repo, chain.objective_key)
            row = self._data[key]
            if objective not in row["chained_objectives"]:
                row["chained_objectives"].append(objective)
                row["updated_utc"] = _now()
                self._data[key] = row
                self._save()
            return Lease(**row), False

        okey = _slug(objective)
        branch = branch_hint or f"feat/{okey}"
        lease = Lease(
            objective=objective,
            objective_key=okey,
            repo=repo,
            branch=branch,
            relay_leg_id=relay_leg_id,
            claim_id=claim_id,
            chained_objectives=[objective],
        )
        self._data[self._key(repo, okey)] = asdict(lease)
        self._save()
        return lease, True

    def all_leases(self, repo: Optional[str] = None) -> list[Lease]:
        rows = self._data.values()
        if repo:
            rows = [r for r in rows if r.get("repo") == repo]
        return [Lease(**r) for r in rows]


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _gh_pr_list(repo: str, limit: int = 50) -> list[dict]:
    if not _gh_available():
        raise RuntimeError("gh CLI not found on PATH")
    out = subprocess.run(
        [
            "gh", "pr", "list", "--repo", repo, "--limit", str(limit),
            "--state", "open",
            "--json", "number,title,author,headRefName,createdAt,additions,deletions",
        ],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0:
        raise RuntimeError(f"gh pr list failed: {out.stderr.strip()}")
    return json.loads(out.stdout or "[]")


_STOPWORDS = {
    "the", "a", "an", "fix", "add", "update", "feat", "chore", "for",
    "to", "of", "and", "in", "on", "pr", "wip",
}


def _title_tokens(title: str) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return frozenset(w for w in words if w not in _STOPWORDS and len(w) > 2)


def detect_confetti(repo: str, min_group: int = 3, jaccard_threshold: float = 0.3) -> list[dict]:
    """Flag clusters of open small PRs from the same repo that look like
    fragments of one objective, so they can be consolidated before another
    is opened. Groups by author, then by title-token overlap within that
    author's PRs (Jaccard similarity over normalized title words).

    Returns a list of {author, prs: [...], reason} groups, largest first.
    Small PRs = additions+deletions < 40 (atomic-change heuristic); size is
    advisory, not a hard filter, so an oversized incoherent PR isn't hidden.
    """
    prs = _gh_pr_list(repo)
    by_author: dict[str, list[dict]] = defaultdict(list)
    for pr in prs:
        author = (pr.get("author") or {}).get("login", "unknown")
        by_author[author].append(pr)

    groups = []
    for author, author_prs in by_author.items():
        if len(author_prs) < min_group:
            continue
        used = set()
        for i, pr in enumerate(author_prs):
            if i in used:
                continue
            tok_i = _title_tokens(pr["title"])
            cluster = [pr]
            cluster_idx = {i}
            for j, other in enumerate(author_prs):
                if j == i or j in used:
                    continue
                tok_j = _title_tokens(other["title"])
                if not tok_i or not tok_j:
                    continue
                jaccard = len(tok_i & tok_j) / len(tok_i | tok_j)
                if jaccard >= jaccard_threshold:
                    cluster.append(other)
                    cluster_idx.add(j)
            if len(cluster) >= min_group:
                used |= cluster_idx
                small = sum(1 for p in cluster if (p.get("additions", 0) + p.get("deletions", 0)) < 40)
                groups.append({
                    "author": author,
                    "prs": [{"number": p["number"], "title": p["title"], "branch": p["headRefName"]} for p in cluster],
                    "small_count": small,
                    "total_count": len(cluster),
                    "reason": f"{len(cluster)} open PRs from {author} share overlapping title tokens "
                              f"(>= {jaccard_threshold:.0%} title-word overlap); {small} look atomic-sized. "
                              f"Recommend consolidating into one leased branch/PR.",
                })
    groups.sort(key=lambda g: g["total_count"], reverse=True)
    return groups
