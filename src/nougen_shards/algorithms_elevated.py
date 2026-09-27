"""
Elevated Mathematical Algorithms & String Similarity Subsystem.
Extends algorithms.py with Damerau-Levenshtein, Jaro-Winkler similarity, and fast vectorized metric matrices.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple, Any, Optional


def damerau_levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculates Damerau-Levenshtein edit distance between two strings,
    accounting for insertions, deletions, substitutions, and adjacent transpositions.
    """
    if s1 == s2:
        return 0
    len1, len2 = len(s1), len(s2)
    if not len1:
        return len2
    if not len2:
        return len1

    # Matrix allocation
    d: Dict[Tuple[int, int], int] = {}
    for i in range(-1, len1 + 1):
        d[(i, -1)] = i + 1
    for j in range(-1, len2 + 1):
        d[(-1, j)] = j + 1

    for i in range(len1):
        for j in range(len2):
            cost = 0 if s1[i] == s2[j] else 1
            d[(i, j)] = min(
                d[(i - 1, j)] + 1,        # Deletion
                d[(i, j - 1)] + 1,        # Insertion
                d[(i - 1, j - 1)] + cost   # Substitution
            )
            if i > 0 and j > 0 and s1[i] == s2[j - 1] and s1[i - 1] == s2[j]:
                d[(i, j)] = min(d[(i, j)], d[(i - 2, j - 2)] + cost) # Transposition

    return d[(len1 - 1, len2 - 1)]


def jaro_winkler_similarity(s1: str, s2: str, p: float = 0.1) -> float:
    """
    Computes Jaro-Winkler Similarity score SIM_jw in range [0.0, 1.0].
    """
    if s1 == s2:
        return 1.0

    len1, len2 = len(s1), len(s2)
    if not len1 or not len2:
        return 0.0

    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2

    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)

        for j in range(start, end):
            if s2_matches[j]:
                continue
            if s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (
        (matches / len1) +
        (matches / len2) +
        ((matches - (transpositions / 2.0)) / matches)
    ) / 3.0

    # Prefix scale
    prefix = 0
    for i in range(min(4, min(len1, len2))):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    jw = jaro + (prefix * p * (1.0 - jaro))
    return round(jw, 4)
