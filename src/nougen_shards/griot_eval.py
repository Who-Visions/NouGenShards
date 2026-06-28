"""
Griot evaluation harness — measure, don't vibe.

A deterministic, model-free regression suite for Griot's quality-critical
pure functions, so every future change to the agent is scored against a golden
set instead of judged by feel. Three axes:

    1. Extraction precision/recall — does the deterministic fallback parser
       pull the right {subject, predicate} invariants out of raw logs?
    2. Verdict robustness — does the adversarial-verifier output parser
       (_parse_verdict) classify accept/reject correctly, defaulting to reject?
    3. Groundedness — does an answer stay within the subjects the vault
       actually recalled (a cheap hallucination proxy)?

Everything here runs without Ollama or any cloud key, so it belongs in CI.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .griot import Griot


# -- Golden sets --------------------------------------------------------

# (raw content, expected {subject, predicate} invariants the parser should find)
GOLDEN_PARSE_CASES: List[Tuple[str, List[Dict[str, str]]]] = [
    (
        "rule - SQLite: timeout must be set to 10.0 seconds to prevent WAL locks\n"
        "Rule: Next.js dev server must run on port 3000\n"
        "Some general comment that is not a rule\n"
        "GitHub: Always pull remote updates before push",
        [
            {"subject": "SQLite", "predicate": "timeout must be set to 10.0 seconds to prevent WAL locks"},
            {"subject": "Next.js dev server", "predicate": "must run on port 3000"},
            {"subject": "GitHub", "predicate": "Always pull remote updates before push"},
        ],
    ),
    (
        "Docker: containers must use read-only root filesystems\n"
        "just chatting here, nothing to see",
        [
            {"subject": "Docker", "predicate": "containers must use read-only root filesystems"},
        ],
    ),
    (
        "nothing structured at all, only prose without any rule shape",
        [],
    ),
]

# (raw verifier response, expected verdict) — note default-to-reject on garbage.
GOLDEN_VERDICT_CASES: List[Tuple[str, str]] = [
    ('{"verdict": "accept", "reason": "supported"}', "accept"),
    ('{"verdict": "reject", "reason": "speculative"}', "reject"),
    ("After review I accept this rule.", "accept"),
    ("This should be rejected as unsupported.", "reject"),
    ("accept... but also reject parts", "reject"),  # ambiguous -> reject
    ("garbage non-answer", "reject"),
]


@dataclass
class EvalResult:
    name: str
    score: float            # 0.0–1.0
    passed: bool
    threshold: float
    detail: Dict[str, Any] = field(default_factory=dict)


def _prf(expected: List[Dict[str, str]],
         got: List[Dict[str, str]]) -> Tuple[float, float, float]:
    """Precision, recall, F1 over (subject, predicate) pairs, case-insensitive."""
    def norm(rules):
        return {(r.get("subject", "").strip().lower(),
                 r.get("predicate", "").strip().lower()) for r in rules}
    exp, gt = norm(expected), norm(got)
    if not exp and not gt:
        return 1.0, 1.0, 1.0
    tp = len(exp & gt)
    precision = tp / len(gt) if gt else 0.0
    recall = tp / len(exp) if exp else (1.0 if not gt else 0.0)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def eval_parse(parser: Optional[Callable[[str], List[Dict[str, str]]]] = None,
               threshold: float = 0.95) -> EvalResult:
    """Score invariant extraction against the golden parse set (mean F1)."""
    parse = parser or Griot.fallback_parse
    f1s, cases = [], []
    for content, expected in GOLDEN_PARSE_CASES:
        _, _, f1 = _prf(expected, parse(content))
        f1s.append(f1)
        cases.append({"f1": round(f1, 3), "expected": len(expected)})
    mean_f1 = sum(f1s) / len(f1s) if f1s else 0.0
    return EvalResult("parse_precision", round(mean_f1, 4), mean_f1 >= threshold,
                      threshold, {"cases": cases})


def eval_verdicts(threshold: float = 1.0) -> EvalResult:
    """Score verifier-output classification against the golden verdict set."""
    correct = sum(1 for raw, want in GOLDEN_VERDICT_CASES
                  if Griot._parse_verdict(raw).get("verdict") == want)
    acc = correct / len(GOLDEN_VERDICT_CASES) if GOLDEN_VERDICT_CASES else 0.0
    return EvalResult("verdict_accuracy", round(acc, 4), acc >= threshold,
                      threshold, {"correct": correct, "total": len(GOLDEN_VERDICT_CASES)})


def groundedness(answer: str, recalled_subjects: List[str]) -> float:
    """Fraction of recalled subjects the answer actually references (0–1).

    A cheap proxy: an answer that ignores every recalled rule is likely
    ungrounded. Returns 1.0 when there is nothing to ground against.
    """
    if not recalled_subjects:
        return 1.0
    low = answer.lower()
    hit = sum(1 for s in recalled_subjects if s and s.lower() in low)
    return hit / len(recalled_subjects)


def run_all(verbose: bool = False) -> Dict[str, Any]:
    """Run every deterministic eval; return a summary with overall pass/fail."""
    results = [eval_parse(), eval_verdicts()]
    summary = {
        "passed": all(r.passed for r in results),
        "evals": [
            {"name": r.name, "score": r.score, "passed": r.passed,
             "threshold": r.threshold, **({"detail": r.detail} if verbose else {})}
            for r in results
        ],
    }
    return summary
