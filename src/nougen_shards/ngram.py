"""N-gram primitives for fuzzy recall and information-density scoring.

Implements the applied portions of docs/theory/n-gram-topologies.md:

- fastText-style character n-grams with boundary markers (§8.2) and Dice set
  similarity, giving typo/morphology-robust matching that neither exact-token
  FTS nor substring LIKE/trigram-FTS provides (§7.2's "synonymy deficit" -
  the morphological half of it).
Everything here is stdlib-only and deterministic. (A §9-style Lidstone
self-perplexity density scorer was prototyped and rejected: without a
reference corpus the metric is degenerate - see the note in
core.calculate_contrastive_perplexity.)
"""
import re
from typing import List, Set

# Admission threshold for fuzzy matches: at least half of the QUERY's
# char-trigrams must appear in the candidate (overlap coefficient). Dice is
# the wrong gate for query-vs-document matching - its denominator counts the
# document's grams too, so a short query against a long shard dilutes toward
# zero even when every query gram is present.
FUZZY_MIN_OVERLAP = 0.5


def tokenize(text: str) -> List[str]:
    """Sanitize a raw stream into atomic word symbols (doc §9)."""
    return re.findall(r"\b\w+\b", text.lower())


def char_ngrams(text: str, n: int = 3) -> Set[str]:
    """fastText-style character n-grams with boundary markers (doc §8.2).

    `where` -> {"<wh", "whe", "her", "ere", "re>"}. Short tokens contribute
    their whole marked form, so 1-2 character words still participate.
    """
    grams: Set[str] = set()
    for tok in tokenize(text):
        marked = f"<{tok}>"
        if len(marked) <= n:
            grams.add(marked)
            continue
        for i in range(len(marked) - n + 1):
            grams.add(marked[i:i + n])
    return grams


def dice_similarity(a: Set[str], b: Set[str]) -> float:
    """Sørensen–Dice coefficient over two n-gram sets, in [0, 1].

    Symmetric: right for comparing two strings of similar length."""
    if not a or not b:
        return 0.0
    return 2.0 * len(a & b) / (len(a) + len(b))


def overlap_coefficient(a: Set[str], b: Set[str]) -> float:
    """Szymkiewicz–Simpson overlap coefficient, in [0, 1].

    Asymmetry-tolerant: |A∩B| / min(|A|,|B|) measures how fully the SMALLER
    set (the query) is covered by the larger (the shard), which is the right
    semantics for query-in-document fuzzy recall."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))
