"""Per-lane tool-availability header.

A model lane with no tools cannot check arithmetic or fetch fresh facts. Asking
it anyway produces a plausible answer with no way to verify it. This module
declares each lane's tools and refuses a task that needs a tool the lane does
not have, so the router sends it elsewhere instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Iterable

# What a task needs in order to be answered honestly.
NEEDS_ARITHMETIC = "arithmetic"      # exact numbers: code interpreter or calculator
NEEDS_FRESH_FACTS = "fresh_facts"    # anything after the model's knowledge cutoff: search
NEEDS_CODE_RUN = "code_run"          # run code to check output: code interpreter

TASK_NEEDS = frozenset({NEEDS_ARITHMETIC, NEEDS_FRESH_FACTS, NEEDS_CODE_RUN})


@dataclass(frozen=True)
class LaneTools:
    lane: str
    tools: FrozenSet[str] = field(default_factory=frozenset)

    def header(self) -> str:
        """One line the lane sees before any task."""
        if not self.tools:
            return (f"[lane {self.lane}] tools: none. Do not give exact arithmetic or "
                    "fresh facts; say when a tool is needed.")
        return f"[lane {self.lane}] tools: {', '.join(sorted(self.tools))}"


def unmet_needs(needs: Iterable[str], lane: LaneTools) -> FrozenSet[str]:
    """Return the task needs this lane cannot meet. Empty means the lane fits."""
    wanted = frozenset(needs)
    unknown = wanted - TASK_NEEDS
    if unknown:
        raise ValueError(f"unknown task need(s): {', '.join(sorted(unknown))}")
    provided = {
        NEEDS_ARITHMETIC: "code_interpreter" in lane.tools or "calculator" in lane.tools,
        NEEDS_FRESH_FACTS: "search" in lane.tools,
        NEEDS_CODE_RUN: "code_interpreter" in lane.tools,
    }
    return frozenset(need for need in wanted if not provided[need])


def route(needs: Iterable[str], lanes: Iterable[LaneTools]) -> LaneTools | None:
    """First lane that meets every need, or None so the caller can say so plainly."""
    needs = tuple(needs)
    for lane in lanes:
        if not unmet_needs(needs, lane):
            return lane
    return None
