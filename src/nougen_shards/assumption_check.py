"""Silent-assumption check before a number or plot is reported.

Generated code can answer with a plausible value after making a silent
assumption: a missing value filled with 0, a fallback that substitutes a
guess, a default that hides a unit. The number then looks like a result.
This module scans source for those patterns so the reporting lane can see
them before it states a figure. It is a static gate, not a proof: a clean
scan means no known pattern was found, not that the number is right.

Evidence rule (Rule 0.13): a reported number needs its scan receipt next to
it, so a reader can see what was checked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple

# (pattern, why it is risky). Each pattern names a place where missing or
# unknown input quietly becomes a real-looking value.
RISKY_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"\.fillna\(\s*0(\.0+)?\s*\)", "missing values filled with zero"),
    (r"\.get\([^,()]+,\s*0(\.0+)?\s*\)", "dict lookup defaults to zero"),
    (r"\bor\s+0(\.\d+)?\b", "falsy value replaced with a literal number"),
    (r"\bexcept\s*(\w+\s*)?:\s*\n?\s*(return|=)\s*0(\.\d+)?\b", "exception swallowed into a zero"),
    (r"\.dropna\(\s*\)", "rows with missing values silently dropped"),
    (r"\bnan_to_num\(", "NaN converted to a number"),
    (r"\bfloat\(\s*['\"]nan['\"]\s*\)\s*\bor\b", "NaN replaced with a fallback"),
)


@dataclass(frozen=True)
class Finding:
    line: int
    text: str
    reason: str


@dataclass(frozen=True)
class AssumptionReceipt:
    """What the scan checked and what it found. Attach it to any reported number."""
    scanned_lines: int
    findings: Tuple[Finding, ...] = field(default_factory=tuple)

    @property
    def clean(self) -> bool:
        return not self.findings

    def render(self) -> str:
        if self.clean:
            return f"assumption check: clean ({self.scanned_lines} lines, known patterns only)"
        lines = [f"assumption check: {len(self.findings)} risky pattern(s) in {self.scanned_lines} lines"]
        lines += [f"  line {f.line}: {f.reason}: {f.text.strip()}" for f in self.findings]
        return "\n".join(lines)


def scan_source(source: str) -> AssumptionReceipt:
    """Scan source text for silent-assumption patterns, line by line."""
    compiled = [(re.compile(pattern), reason) for pattern, reason in RISKY_PATTERNS]
    lines = source.splitlines()
    findings: List[Finding] = []
    for number, text in enumerate(lines, start=1):
        for regex, reason in compiled:
            if regex.search(text):
                findings.append(Finding(number, text, reason))
                break
    return AssumptionReceipt(scanned_lines=len(lines), findings=tuple(findings))


def gate_report(source: str, allow_findings: bool = False) -> AssumptionReceipt:
    """Return the receipt, raising if risky patterns are present and not allowed.

    Callers that report a number should pass the source the number came from.
    ``allow_findings=True`` is for a reviewer who has already read each finding.
    """
    receipt = scan_source(source)
    if not receipt.clean and not allow_findings:
        raise ValueError(receipt.render())
    return receipt
