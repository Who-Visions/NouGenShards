"""Evidence chain for NouGen League awards — the part that cannot be self-reported.

GM's league doctrine (relay `20260908T032016Z`) sets an anti-farming law:

    PR count, commits, LOC, tool calls and token burn are TELEMETRY ONLY,
    never score. Awards must be backed by
    relay leg -> claim -> branch -> PR -> merge SHA -> tests -> production
    verification.

This module implements that chain check. It scores nothing and ranks nothing —
standings are a separate concern, and building them on an unverified chain is
how a league becomes a farm.

Why the last link is the whole point
------------------------------------
On 2026-09-07/08 this fleet merged a redaction fix, three nodes independently
verified it, and it ran on **none of them**. Fifteen copies of one module
existed across two machines; one had the fix; no live process imported it.
Every link up to `merge SHA` was green while production was untouched.

So `PRODUCTION` is not an optional final tick. It is the only link a node
cannot assert about itself: it is read from the running service's own
`/health`, which reports the code it actually loaded. Every other link is
checkable from git and the relay, and every one of them can be green while the
thing does not run.

Link states are deliberately three-valued
-----------------------------------------
`VERIFIED`, `BROKEN`, `UNVERIFIABLE` — never a blank and never a default pass.
A node that publishes no health fields is `UNVERIFIABLE`, which is a
conclusion (it runs pre-self-reporting code), not a gap to be scored as zero
and not one to be waved through. Tonight a same-machine lane published
"11 PRs merged and running in RAM" when one request would have returned
`ABSENT`; a scheme that treats absence as success rewards exactly that.

KNOWN LIMITATION — read before scoring anything with this
---------------------------------------------------------
`production` is unreachable for artifacts that do not run: documentation,
developer tooling, and library code no service imports yet. Scored against
this fleet's own 2026-09-08 output the chain returned **3 of 10 eligible**,
and two of the seven rejections were a docs PR and a CLI tool — neither of
which can ever report from a live endpoint.

That is a real gap and it is left OPEN deliberately. The obvious fix is an
exemption for "non-runtime artifacts", and an exemption is precisely where
farming enters: every PR would arrive labelled non-runtime. Whether docs and
tooling get a different chain (say, adopted-by-another-node in place of
production) is a governance decision, not one this module should quietly make.
Until it is decided, a doc PR is `UNVERIFIABLE` at `production` — which is
accurate, not a verdict on its worth.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "LINKS", "TELEMETRY_ONLY", "VERIFIED", "BROKEN", "UNVERIFIABLE",
    "Link", "Chain", "award_eligible",
]

VERIFIED = "VERIFIED"
BROKEN = "BROKEN"
UNVERIFIABLE = "UNVERIFIABLE"

#: In order. Each link is evidence the previous one was actually carried
#: forward; a chain is only as strong as its weakest link, and the order is
#: what makes "merged" insufficient on its own.
LINKS: tuple[str, ...] = (
    "relay_leg",     # the work was announced before it was done
    "claim",         # a lane took it, so two nodes did not do it twice
    "branch",        # it existed as reviewable work
    "pull_request",  # it was offered for review
    "merge_sha",     # it reached the default branch
    "tests",         # CI actually ran and was green -- not "no tests ran"
    "production",    # a live service reports the code it LOADED
)

#: Named explicitly so a future scorer cannot quietly promote them. These are
#: the metrics that go up when someone games the system, which is precisely
#: why they are recorded and never scored. Measured on this fleet: 11 PRs that
#: honestly represented 5 chains -- a PR-count metric would have scored the
#: worst habit of the night as the best.
TELEMETRY_ONLY: frozenset[str] = frozenset({
    "pr_count", "commit_count", "lines_changed", "tool_calls",
    "tokens_spent", "relay_legs", "shards_captured",
})


@dataclass(frozen=True)
class Link:
    """One link, its state, and the evidence that settled it."""

    name: str
    state: str
    evidence: str = ""

    def __post_init__(self) -> None:
        if self.name not in LINKS:
            raise ValueError(f"unknown link {self.name!r}; expected one of {LINKS}")
        if self.state not in (VERIFIED, BROKEN, UNVERIFIABLE):
            raise ValueError(f"unknown state {self.state!r}")


@dataclass
class Chain:
    """The evidence chain behind one award candidate."""

    subject: str
    links: dict[str, Link] = field(default_factory=dict)
    telemetry: dict[str, float] = field(default_factory=dict)

    def record(self, name: str, state: str, evidence: str = "") -> None:
        self.links[name] = Link(name, state, evidence)

    def state_of(self, name: str) -> str:
        """Missing evidence is UNVERIFIABLE, never absent and never a pass."""
        link = self.links.get(name)
        return link.state if link else UNVERIFIABLE

    def weakest(self) -> str:
        """First link that is not VERIFIED, walking the chain in order.

        Reported rather than a score, because the useful output is *which*
        link failed. "Not eligible" tells a lane nothing; "production is
        UNVERIFIABLE" tells it to deploy.
        """
        for name in LINKS:
            if self.state_of(name) != VERIFIED:
                return name
        return ""

    def summary(self) -> list[tuple[str, str, str]]:
        return [(n, self.state_of(n), self.links[n].evidence if n in self.links else "")
                for n in LINKS]


def award_eligible(chain: Chain) -> tuple[bool, str]:
    """Is this chain complete enough to carry an award?

    Returns ``(eligible, reason)``. Eligibility requires **every** link
    VERIFIED. There is deliberately no partial credit and no override:

    - A `BROKEN` link is a failed claim.
    - An `UNVERIFIABLE` link is an unmeasured one, and unmeasured is not a
      lesser form of verified. Tonight's whole failure was treating a green
      proxy as the thing itself.

    Telemetry is ignored here entirely. It cannot raise a chain and cannot
    lower one; it exists so a reader can see effort without effort becoming
    score.
    """
    weak = chain.weakest()
    if not weak:
        return True, "all links verified"

    state = chain.state_of(weak)
    if state == BROKEN:
        return False, f"{weak} is BROKEN: {chain.links[weak].evidence or 'no evidence'}"
    return False, (
        f"{weak} is UNVERIFIABLE — not measured, which is not a weaker form of "
        f"verified. For 'production', query the node's /health: a node that "
        f"publishes no fields is running code from before it could self-report."
    )
