"""Deterministic phonetic layer.

Lookup order for a word:

1. manual overrides (names, slang, persona pronunciations),
2. the optional CMU dictionary backend (``cmudict`` package, never required),
3. a small hand-written seed lexicon for irregular common words,
4. suffix splitting (stem looked up through 1 to 3, suffix added by rule),
5. a heuristic grapheme-to-phoneme parser.

Every :class:`Pronunciation` says which source produced it and carries a
confidence value. Heuristic parses are guesses and are labeled that way.
Dialect profiles are optional substitution hooks; none of them is treated as
the correct way to say a word.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Sequence

from .config import ENV_DICTIONARY, Config, load_data_json, resolve_config

log = logging.getLogger("nougen_verse.phonetics")

VOWELS = frozenset("AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW".split())
LETTER_VOWELS = set("aeiou")
LONG_VOWEL = {"a": "EY", "e": "IY", "i": "AY", "o": "OW", "u": "UW", "y": "AY"}
SHORT_VOWEL = {"a": "AE", "e": "EH", "i": "IH", "o": "AA", "u": "AH", "y": "IH"}
SIMPLE_CONSONANTS = {
    "b": "B", "d": "D", "f": "F", "k": "K", "l": "L", "m": "M", "n": "N",
    "p": "P", "r": "R", "t": "T", "v": "V", "z": "Z", "j": "JH",
}
REDUCIBLE = {"AE", "AA", "AO", "EH", "AH"}
APOSTROPHE_CHARS = "".join(chr(c) for c in (0x2019, 0x2018, 0x02BC, 0x0060, 0x00B4, 0x2032))
DASH_CHARS = "".join(chr(c) for c in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015))
LEADING_ELISIONS = {"'cause", "'em", "'til", "'bout", "'round", "'fore", "'nuff", "'cuz"}
UNSTRESSED_PREFIXES = ("be", "de", "re", "un", "dis", "mis", "with", "for", "con", "com", "ex", "pre", "a")
# Suffix -> number of vowel nuclei the suffix contributes; stress falls just before it.
STRESS_SHIFT_SUFFIXES = (
    ("ical", 2), ("ity", 2), ("ious", 2), ("eous", 2), ("ial", 2), ("ian", 2), ("ient", 2),
    ("tion", 1), ("sion", 1), ("cian", 1), ("ic", 1),
)


def strip_stress(phone: str) -> str:
    return phone.rstrip("012")


def is_vowel(phone: str) -> bool:
    return strip_stress(phone) in VOWELS


def stress_of(phone: str) -> int | None:
    return int(phone[-1]) if phone and phone[-1] in "012" else None


def parse_phones(spec: str | Sequence[str]) -> tuple[str, ...]:
    """Parse ``"M EH1 M ER0 IY0"`` or a list into validated phones."""
    phones = spec.split() if isinstance(spec, str) else list(spec)
    feats = load_data_json("phonetic_features.json")
    out = []
    for p in phones:
        p = p.strip().upper()
        base = strip_stress(p)
        if base not in VOWELS and base not in feats["consonants"]:
            raise ValueError(f"unknown ARPAbet phone {p!r}")
        if base in VOWELS and stress_of(p) is None:
            p = base + "1"
        out.append(p)
    return tuple(out)


@dataclass(frozen=True)
class Syllable:
    onset: tuple[str, ...]
    nucleus: str
    coda: tuple[str, ...]
    stress: int

    def to_dict(self) -> dict:
        return {"onset": list(self.onset), "nucleus": self.nucleus, "coda": list(self.coda), "stress": self.stress}


def syllabify(phones: Sequence[str]) -> list[Syllable]:
    """Split phones into syllables (vowel nuclei; one intervocalic consonant goes to the onset)."""
    vowel_idx = [i for i, p in enumerate(phones) if is_vowel(p)]
    if not vowel_idx:
        return []
    sylls: list[Syllable] = []
    bounds = []
    for k, vi in enumerate(vowel_idx):
        if k == 0:
            onset_start = 0
        else:
            prev = vowel_idx[k - 1]
            cons = vi - prev - 1
            onset_start = prev + 1 + (0 if cons <= 1 else 1)
        bounds.append(onset_start)
    for k, vi in enumerate(vowel_idx):
        end = bounds[k + 1] if k + 1 < len(vowel_idx) else len(phones)
        onset = tuple(phones[bounds[k]:vi])
        coda = tuple(phones[vi + 1:end])
        stress = stress_of(phones[vi]) or 0
        sylls.append(Syllable(onset, strip_stress(phones[vi]), coda, stress))
    return sylls


@dataclass(frozen=True)
class Pronunciation:
    word: str
    phones: tuple[str, ...]
    source: str
    confidence: float
    notes: tuple[str, ...] = ()

    @property
    def syllables(self) -> list[Syllable]:
        return syllabify(self.phones)

    @property
    def syllable_count(self) -> int:
        return sum(1 for p in self.phones if is_vowel(p))

    @property
    def stress_pattern(self) -> str:
        return "".join(str(stress_of(p) or 0) for p in self.phones if is_vowel(p))

    def stressed_index(self) -> int:
        """Index (in syllables) of the rhyme-bearing stress: last primary, else last secondary, else last."""
        pattern = self.stress_pattern
        if not pattern:
            return -1
        for target in ("1", "2"):
            if target in pattern:
                return pattern.rindex(target)
        return len(pattern) - 1

    def tail_syllables(self) -> list[Syllable]:
        sylls = self.syllables
        idx = self.stressed_index()
        return sylls[idx:] if idx >= 0 else []

    def to_dict(self) -> dict:
        return {
            "word": self.word,
            "phones": " ".join(self.phones),
            "source": self.source,
            "confidence": round(self.confidence, 3),
            "syllables": self.syllable_count,
            "stress": self.stress_pattern,
            "notes": list(self.notes),
        }


# ----------------------------------------------------------------------------
# text normalization and tokens


def normalize_text(text: str) -> str:
    """NFKC normalize, unify apostrophes, turn unicode dashes into ASCII hyphen spacing."""
    text = unicodedata.normalize("NFKC", text or "")
    for ch in APOSTROPHE_CHARS:
        text = text.replace(ch, "'")
    for ch in DASH_CHARS:
        text = text.replace(ch, " - ")
    return text


def fold_accents(word: str) -> str:
    decomposed = unicodedata.normalize("NFKD", word)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@dataclass
class Token:
    surface: str
    norm: str
    start: int
    end: int
    punct_after: str = ""
    markers: tuple[str, ...] = ()
    stutter: int = 0
    g_dropped: bool = False
    is_number: bool = False
    spoken: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "surface": self.surface, "norm": self.norm, "start": self.start, "end": self.end,
            "punct_after": self.punct_after, "markers": list(self.markers), "stutter": self.stutter,
            "g_dropped": self.g_dropped, "is_number": self.is_number, "spoken": list(self.spoken),
        }


_TOKEN_RE = re.compile(r"[>]?'?[^\W_]+(?:['\-][^\W_]+)*'?~?", re.UNICODE)
_PUNCT_RE = re.compile(r"\s*([,;:.!?]|-\s)")

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def number_to_words(n: int) -> list[str]:
    """Spell 0 to 9999 the way a rapper would usually say it (years as pairs)."""
    if n < 20:
        return [_ONES[n]]
    if n < 100:
        tens, ones = divmod(n, 10)
        return [_TENS[tens]] + ([_ONES[ones]] if ones else [])
    if 1100 <= n <= 9999 and n % 100 != 0 and not (2000 <= n < 2010):
        hi, lo = divmod(n, 100)
        lo_words = number_to_words(lo) if lo >= 10 else ["oh", _ONES[lo]]
        return number_to_words(hi) + lo_words
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return [_ONES[hundreds], "hundred"] + (number_to_words(rest) if rest else [])
    thousands, rest = divmod(n, 1000)
    return number_to_words(thousands) + ["thousand"] + (number_to_words(rest) if rest else [])


def tokenize(line: str) -> list[Token]:
    """Split a line into word tokens with offsets, punctuation, markers and stutters.

    Markers: a trailing ``~`` marks elongation or a lazy tail; a leading ``>``
    marks emphasis. ``b-b-back`` is read as a stutter on ``back``; other
    hyphenated words are split into their parts.
    """
    text = normalize_text(line)
    tokens: list[Token] = []
    for m in _TOKEN_RE.finditer(text):
        raw = m.group(0)
        start, end = m.start(), m.end()
        markers = []
        if raw.startswith(">"):
            markers.append("emphasis")
            raw = raw[1:]
        if raw.endswith("~"):
            markers.append("elongate")
            raw = raw[:-1]
        punct = ""
        pm = _PUNCT_RE.match(text, end)
        if pm:
            punct = pm.group(1).strip() or "-"
        parts = raw.split("-")
        stutter = 0
        if len(parts) > 1:
            final = parts[-1].lower()
            if all(p and final.startswith(p.lower()) and len(p) < len(final) for p in parts[:-1]):
                stutter = len(parts) - 1
                parts = [parts[-1]]
        for k, part in enumerate(parts):
            tok = _make_token(part, start, end)
            if tok is None:
                continue
            tok.markers = tuple(markers)
            tok.stutter = stutter
            tok.punct_after = punct if k == len(parts) - 1 else ""
            tokens.append(tok)
    return tokens


def _make_token(part: str, start: int, end: int) -> Token | None:
    surface = part
    word = fold_accents(part).lower()
    g_dropped = False
    if word.startswith("'") and word not in LEADING_ELISIONS:
        word = word.lstrip("'")
    if word.endswith("'"):
        if word.endswith("in'"):
            g_dropped = True
        word = word.rstrip("'")
    if not word:
        return None
    if word.isdigit():
        return Token(surface, word, start, end, is_number=True, spoken=tuple(number_to_words(int(word) % 10000)))
    if re.fullmatch(r"\d+(st|nd|rd|th|s)", word):
        digits = re.match(r"\d+", word).group(0)
        return Token(surface, word, start, end, is_number=True, spoken=tuple(number_to_words(int(digits) % 10000)))
    return Token(surface, word, start, end, g_dropped=g_dropped, spoken=(word,))


# ----------------------------------------------------------------------------
# heuristic grapheme-to-phoneme


def _is_cons_letter(ch: str) -> bool:
    return ch.isalpha() and ch not in LETTER_VOWELS and ch != "y"


def _vowel_groups(word: str) -> int:
    return max(1, len(re.findall(r"[aeiouy]+", re.sub(r"e$", "", word)))) if word else 0


def heuristic_g2p(word: str) -> tuple[list[str], int]:
    """Rule-based letters-to-ARPAbet parse. Returns (phones without stress, ambiguity count)."""
    w = re.sub(r"[^a-z]", "", word.lower())
    n = len(w)
    out: list[str] = []
    amb = 0
    i = 0
    first_vowel_done = False
    if n == 1 and w not in LETTER_VOWELS:
        return _letter_name(w), 1

    def at(k: int) -> str:
        return w[k] if 0 <= k < n else ""

    while i < n:
        c = w[i]
        rest = w[i:]
        # ---- vowel letters (y counts as a vowel unless it starts a syllable)
        if c in LETTER_VOWELS or (c == "y" and i > 0 and not (at(i + 1) in LETTER_VOWELS)):
            is_first = not first_vowel_done
            first_vowel_done = True
            if rest.startswith("eau"):
                out.append("OW"); i += 3; continue
            if rest.startswith("igh"):
                out.append("AY"); i += 3; continue
            if rest.startswith("eigh"):
                out.append("EY"); i += 4; continue
            if rest.startswith("ough"):
                out.append("AO"); amb += 2; i += 4; continue
            if rest.startswith("augh"):
                out.append("AO"); i += 4; continue
            if rest.startswith("ious"):
                out += ["IY", "AH", "S"]; i += 4; continue
            if rest.startswith("ial") or rest.startswith("ian"):
                out += ["IY", "AH", "L" if rest[2] == "l" else "N"]; i += 3; continue
            if rest.startswith("air"):
                out += ["EH", "R"]; i += 3; continue
            if rest.startswith("ear"):
                if _is_cons_letter(at(i + 3)):
                    out.append("ER"); amb += 1
                else:
                    out += ["IH", "R"]; amb += 1
                i += 3; continue
            if rest.startswith("eer"):
                out += ["IH", "R"]; i += 3; continue
            if rest == "ier":
                out += ["IY", "ER"]; i += 3; continue
            if rest.startswith("our"):
                out += ["AW", "ER"]; amb += 1; i += 3; continue
            if rest.startswith("oor"):
                out += ["AO", "R"]; i += 3; continue
            if rest in ("are", "ire", "ore", "ure", "ere"):
                out += {"are": ["EH", "R"], "ire": ["AY", "ER"], "ore": ["AO", "R"],
                        "ure": ["Y", "UH", "R"], "ere": ["IH", "R"]}[rest]
                i += 3; continue
            if at(i + 1) == "r" and at(i + 2) not in LETTER_VOWELS and at(i + 2) != "y" or (at(i + 1) == "r" and i + 2 == n):
                if at(i + 2) != "r":
                    prev = at(i - 1)
                    if c == "o" and prev == "w":
                        out.append("ER")
                    elif c == "a" and prev == "w":
                        out += ["AO", "R"]
                    elif c == "a":
                        out += ["AA", "R"]
                    elif c == "o":
                        out += ["AO", "R"]
                    else:
                        out.append("ER")
                    i += 2; continue
            pair = rest[:2]
            if pair in ("ai", "ay"):
                out.append("EY"); i += 2; continue
            if pair == "ei":
                out.append("EY"); amb += 1; i += 2; continue
            if pair == "ey":
                out.append("IY" if i + 2 == n and _vowel_groups(w) > 1 else "EY"); i += 2; continue
            if pair == "ie":
                if i + 2 == n:
                    out.append("AY" if _vowel_groups(w[:i]) == 0 else "IY")
                else:
                    out.append("IY")
                i += 2; continue
            if pair == "ee":
                out.append("IY"); i += 2; continue
            if pair == "ea":
                out.append("IY"); amb += 1; i += 2; continue
            if pair == "oa":
                out.append("OW"); i += 2; continue
            if pair == "oe" and i + 2 == n:
                out.append("OW"); i += 2; continue
            if pair == "oo":
                out.append("UH" if at(i + 2) == "k" else "UW"); i += 2; continue
            if pair == "ou":
                out.append("AW"); amb += 1; i += 2; continue
            if pair == "ow":
                if i + 2 == n or w[i + 2:] in ("n", "ns"):
                    out.append("OW")
                else:
                    out.append("AW")
                amb += 1; i += 2; continue
            if pair in ("oi", "oy"):
                out.append("OY"); i += 2; continue
            if pair in ("au", "aw"):
                out.append("AO"); i += 2; continue
            if pair in ("ew", "ue", "ui"):
                out.append("UW"); amb += 1 if pair == "ui" else 0; i += 2; continue
            if pair == "uy":
                out.append("AY"); i += 2; continue
            # single vowel letter
            if c == "e" and i == n - 1:
                if _vowel_groups(w[:i]) == 0:
                    out.append("IY")
                i += 1; continue
            if c == "y":
                if i == n - 1:
                    out.append("AY" if _vowel_groups(w[:i]) == 0 else "IY")
                elif at(i + 1) and _is_cons_letter(at(i + 1)) and at(i + 2) == "e" and i + 3 == n:
                    out.append("AY")
                else:
                    out.append("IH")
                i += 1; continue
            nxt, nxt2 = at(i + 1), at(i + 2)
            magic_e = _is_cons_letter(nxt) and nxt not in "wx" and nxt2 == "e" and i + 3 == n
            if magic_e:
                out.append(LONG_VOWEL[c]); i += 1; continue
            if c == "a" and nxt == "l" and nxt2 in ("k", "m"):
                out.append("AO" if nxt2 == "k" else "AA"); i += 2; continue  # walk, chalk, calm, palm: the l is silent
            if c == "a" and nxt == "l" and nxt2 in ("l", "t"):
                out.append("AO"); i += 1; continue
            if c == "a" and w[i + 1:] in ("nge", "nges", "nged"):
                out.append("EY"); i += 1; continue  # change, range, strange
            if c == "o" and nxt == "a" and nxt2 == "r":
                out += ["AO", "R"]; i += 3; continue  # board, roar
            if c == "a" and at(i - 1) == "w":
                out.append("AA"); amb += 1; i += 1; continue
            if c == "a" and i == n - 1:
                out.append("AH"); i += 1; continue
            if c == "o" and nxt == "l" and nxt2 in ("d", "t", "l") and (i + 3 >= n or w[i + 3:] == "s"):
                out.append("OW"); i += 1; continue
            if c == "o" and i == n - 1:
                out.append("OW"); i += 1; continue
            if c == "o" and nxt == "n" and nxt2 == "g":
                out.append("AO"); i += 1; continue
            if c == "i" and w[i + 1:] in ("nd", "ld", "gn", "nds", "lds"):
                out.append("AY"); i += 1; continue
            vcv = (
                is_first and c in "aiou" and _is_cons_letter(nxt) and nxt != "x"
                and (nxt2 in LETTER_VOWELS or nxt2 == "y" or w[i + 2:] == "le")
                and not (nxt2 == "e" and i + 3 == n)
            )
            if vcv:
                out.append(LONG_VOWEL[c]); amb += 1; i += 1; continue
            out.append(SHORT_VOWEL[c]); i += 1; continue

        # ---- consonants
        if c == at(i + 1) and c not in "aeiouy":
            i += 1  # doubled consonant: skip the first letter, the second is parsed normally
            continue
        if rest.startswith("tch"):
            out.append("CH"); i += 3; continue
        if rest.startswith("dge"):
            out.append("JH"); i += 3 if i + 3 == n else 2; continue
        if rest.startswith("tion"):
            out += ["SH", "AH", "N"]; i += 4; continue
        if rest.startswith("sion"):
            out += ["ZH" if at(i - 1) in LETTER_VOWELS else "SH", "AH", "N"]; i += 4; continue
        if rest.startswith("cian"):
            out += ["SH", "AH", "N"]; i += 4; continue
        if rest.startswith("cious") or rest.startswith("tious"):
            out += ["SH", "AH", "S"]; i += 5; continue
        if rest.startswith("ture") and i > 0:
            out += ["CH", "ER"]; i += 4; continue
        if rest.endswith("le") and len(rest) == 3 and _is_cons_letter(c) and i > 0:
            out += [SIMPLE_CONSONANTS.get(c, c.upper()), "AH", "L"]; i += 3; continue
        if rest.startswith("sch"):
            out += ["S", "K"]; i += 3; continue
        if rest.startswith("chr"):
            out.append("K"); i += 2; continue
        if rest.startswith("ch"):
            out.append("CH"); i += 2; continue
        if rest.startswith("sh"):
            out.append("SH"); i += 2; continue
        if rest.startswith("th"):
            voiced = i > 0 and at(i - 1) in LETTER_VOWELS and w[i + 2:i + 4] == "er"
            out.append("DH" if voiced else "TH"); i += 2; continue
        if rest.startswith("ph"):
            out.append("F"); i += 2; continue
        if rest.startswith("wh"):
            out.append("W"); i += 2; continue
        if rest.startswith("ck"):
            out.append("K"); i += 2; continue
        if rest.startswith("ng"):
            after = at(i + 2)
            if w[i:] in ("nge", "nges", "nged") and i > 0:
                out += ["N", "JH"]; amb += 1  # change, hinge, orange
            elif after in LETTER_VOWELS or after in ("l", "r"):
                out += ["NG", "G"]  # anger, finger, single
            else:
                out.append("NG")
            i += 2; continue
        if rest.startswith("nk"):
            out += ["NG", "K"]; i += 2; continue
        if i == 0 and rest.startswith("kn"):
            out.append("N"); i += 2; continue
        if i == 0 and rest.startswith("wr"):
            out.append("R"); i += 2; continue
        if rest == "gn":
            out.append("N"); i += 2; continue
        if rest == "mb":
            out.append("M"); i += 2; continue
        if rest.startswith("gh"):
            if i == 0:
                out.append("G")
            i += 2; continue
        if rest.startswith("qu"):
            out += ["K", "W"]; i += 2; continue
        if c == "x":
            out += ["Z"] if i == 0 else ["K", "S"]; i += 1; continue
        if c == "c":
            out.append("S" if at(i + 1) in ("e", "i", "y") else "K"); i += 1; continue
        if c == "g":
            if at(i + 1) in ("e", "i", "y"):
                out.append("JH"); amb += 1
            else:
                out.append("G")
            i += 1; continue
        if c == "s":
            between = at(i - 1) in LETTER_VOWELS and (at(i + 1) in LETTER_VOWELS or at(i + 1) == "y")
            out.append("Z" if between else "S"); i += 1; continue
        if c == "y":
            out.append("Y"); i += 1; continue
        if c == "w":
            out.append("W"); i += 1; continue
        if c == "h":
            if i == 0 or at(i + 1) in LETTER_VOWELS:
                out.append("HH")
            i += 1; continue
        if c in SIMPLE_CONSONANTS:
            out.append(SIMPLE_CONSONANTS[c]); i += 1; continue
        i += 1  # unknown symbol, skip
    if not any(p in VOWELS for p in out):
        if out:
            out.insert(1 if len(out) > 1 else 0, "AH")
            amb += 2
    return out, amb


def _letter_name(ch: str) -> list[str]:
    names = {
        "b": "B IY", "c": "S IY", "d": "D IY", "f": "EH F", "g": "JH IY", "h": "EY CH", "j": "JH EY",
        "k": "K EY", "l": "EH L", "m": "EH M", "n": "EH N", "p": "P IY", "q": "K Y UW", "r": "AA R",
        "s": "EH S", "t": "T IY", "v": "V IY", "w": "D AH B AH L Y UW", "x": "EH K S", "y": "W AY", "z": "Z IY",
    }
    return names.get(ch, "AH").split()


def assign_stress(word: str, phones: list[str]) -> tuple[list[str], int]:
    """Add stress digits to a heuristic parse; returns (phones, extra ambiguity)."""
    vowel_pos = [i for i, p in enumerate(phones) if p in VOWELS]
    amb = 0
    if not vowel_pos:
        return phones, amb
    count = len(vowel_pos)
    stressed = 0
    if count > 1:
        w = word.lower()
        shifted = False
        for suffix, nuclei in STRESS_SHIFT_SUFFIXES:
            if w.endswith(suffix) and count > nuclei:
                stressed = count - nuclei - 1
                shifted = True
                break
        if not shifted and count == 2:
            for prefix in UNSTRESSED_PREFIXES:
                if w.startswith(prefix) and len(w) > len(prefix) + 2:
                    after = w[len(prefix):]
                    # the prefix must be followed by one consonant, or a consonant plus l or r (a-way, con-trol),
                    # so words like after, anger and better keep first-syllable stress
                    single = after[0] not in LETTER_VOWELS and len(after) > 1 and (after[1] in LETTER_VOWELS or after[1] in "lr")
                    if single and after[0] != after[1]:
                        stressed = 1
                        amb += 1
                        break
    out = list(phones)
    drop_r = set()
    for k, pos in enumerate(vowel_pos):
        base = out[pos]
        if k == stressed:
            out[pos] = base + "1"
        else:
            followed_by_r = pos + 1 < len(out) and out[pos + 1] == "R"
            if base in ("AA", "AO") and followed_by_r and not (pos + 2 < len(out) and out[pos + 2] in VOWELS):
                base = "ER"  # unstressed -ar / -or reduce: dollar, doctor
                drop_r.add(pos + 1)
            elif base in REDUCIBLE and not followed_by_r:
                base = "AH"
            out[pos] = base + "0"
    return [p for i, p in enumerate(out) if i not in drop_r], amb


# ----------------------------------------------------------------------------
# dictionary backend (optional)


@lru_cache(maxsize=1)
def _load_cmudict() -> dict | None:
    try:
        import cmudict  # type: ignore
    except ImportError:
        return None
    try:
        return cmudict.dict()
    except Exception as exc:  # pragma: no cover - depends on package internals
        log.warning("cmudict import worked but loading failed: %s", exc)
        return None


def dictionary_mode(config: Config | None = None) -> str:
    cfg = resolve_config(config)
    mode = os.environ.get(ENV_DICTIONARY) or cfg.phonetics.get("use_dictionary", "auto")
    mode = str(mode).strip().lower()
    return {"0": "off", "false": "off", "no": "off", "1": "on", "true": "on", "yes": "on"}.get(mode, mode)


def dictionary_available() -> bool:
    return _load_cmudict() is not None


# ----------------------------------------------------------------------------
# dialect hooks


def _dialect_profiles(names: str | Sequence[str] | None) -> list[tuple[str, dict]]:
    if not names:
        return []
    if isinstance(names, str):
        names = [names]
    table = load_data_json("dialects.json")
    out = []
    for name in names:
        if name == "none":
            continue
        if name not in table:
            raise ValueError(f"unknown dialect profile {name!r}; known: {sorted(k for k in table if not k.startswith('_'))}")
        out.append((name, table[name]))
    return out


def apply_dialect(phones: Sequence[str], profiles: list[tuple[str, dict]]) -> tuple[tuple[str, ...], list[str]]:
    result = list(phones)
    notes = []
    for name, prof in profiles:
        before = list(result)
        vmap = prof.get("vowel_map", {})
        cmap = prof.get("consonant_map", {})
        new = []
        for i, p in enumerate(result):
            base, st = strip_stress(p), p[len(strip_stress(p)):]
            if base in vmap:
                p = vmap[base] + st
            elif base in cmap:
                p = cmap[base]
            for rule in prof.get("vowel_before", []):
                if base == rule["vowel"] and i + 1 < len(result) and strip_stress(result[i + 1]) in rule["before"]:
                    p = rule["to"] + st
            new.append(p)
        result = new
        if prof.get("drop_postvocalic_r"):
            result = [p for i, p in enumerate(result) if not (p == "R" and i > 0 and is_vowel(result[i - 1]) and not (i + 1 < len(result) and is_vowel(result[i + 1])))]
        if prof.get("final_ing_to_in") and len(result) >= 2 and result[-1] == "NG" and strip_stress(result[-2]) == "IH" and result[-2].endswith("0"):
            result[-1] = "N"
        if result != before:
            notes.append(f"dialect:{name}")
    return tuple(result), notes


# ----------------------------------------------------------------------------
# the dictionary object


class PhoneticDictionary:
    """Pronunciation lookup with overrides, optional CMU backend, seed lexicon and heuristics."""

    def __init__(
        self,
        config: Config | dict | None = None,
        overrides: dict[str, str | Sequence[str] | Sequence[Sequence[str]]] | None = None,
        use_dictionary: str | None = None,
        dialect: str | Sequence[str] | None = None,
    ):
        self.config = resolve_config(config)
        self._conf = self.config.phonetics["confidence"]
        mode = (use_dictionary or dictionary_mode(self.config)).lower()
        self.mode = mode
        self._backend = None
        if mode in ("auto", "on"):
            self._backend = _load_cmudict()
            if self._backend is None and mode == "on":
                raise RuntimeError("dictionary mode is 'on' but the optional cmudict package is not installed (pip install 'nougen-verse[cmu]')")
        self._seed = {k: [parse_phones(v) for v in vs] for k, vs in load_data_json("seed_lexicon.json")["words"].items()}
        self._overrides: dict[str, list[tuple[str, ...]]] = {}
        self.dialect = dialect if dialect is not None else self.config.phonetics.get("dialect", "none")
        self._profiles = _dialect_profiles(self.dialect)
        self._cache: dict[str, list[Pronunciation]] = {}
        for word, spec in (overrides or {}).items():
            self.register(word, spec)

    @property
    def backend_name(self) -> str:
        return "cmudict" if self._backend is not None else "none"

    # -- overrides -----------------------------------------------------------
    def register(self, word: str, phones: str | Sequence[str] | Sequence[Sequence[str]]) -> None:
        """Register one or more pronunciations for a word (names, slang, your own accent)."""
        key = self._key(word)
        if isinstance(phones, str):
            variants = [parse_phones(phones)]
        elif phones and not isinstance(phones[0], str):
            variants = [parse_phones(v) for v in phones]  # type: ignore[arg-type]
        elif phones and all(" " in p for p in phones):  # list of full pronunciation strings
            variants = [parse_phones(v) for v in phones]  # type: ignore[arg-type]
        else:
            variants = [parse_phones(phones)]  # type: ignore[arg-type]
        self._overrides[key] = variants
        self._cache.clear()

    def set_stress(self, word: str, syllable_index: int) -> Pronunciation:
        """Move primary stress of a word's first pronunciation to ``syllable_index`` (0-based)."""
        base = self.pronounce(word)
        vowels = [i for i, p in enumerate(base.phones) if is_vowel(p)]
        if not 0 <= syllable_index < len(vowels):
            raise ValueError(f"{word!r} has {len(vowels)} syllables; cannot stress index {syllable_index}")
        phones = []
        for i, p in enumerate(base.phones):
            if is_vowel(p):
                p = strip_stress(p) + ("1" if i == vowels[syllable_index] else "0")
            phones.append(p)
        self.register(word, phones)
        return self.pronounce(word)

    # -- lookup ----------------------------------------------------------------
    @staticmethod
    def _key(word: str) -> str:
        return fold_accents(normalize_text(word)).strip().lower()

    def pronounce(self, word: str) -> Pronunciation:
        return self.pronounce_all(word)[0]

    def pronounce_all(self, word: str) -> list[Pronunciation]:
        key = self._key(word)
        if key in self._cache:
            return self._cache[key]
        result = self._lookup(key)
        if self._profiles:
            adjusted = []
            for pr in result:
                phones, notes = apply_dialect(pr.phones, self._profiles)
                adjusted.append(Pronunciation(pr.word, phones, pr.source, pr.confidence, pr.notes + tuple(notes)))
            result = adjusted
        self._cache[key] = result
        return result

    def _direct(self, key: str) -> tuple[list[tuple[str, ...]], str] | None:
        if key in self._overrides:
            return self._overrides[key], "override"
        if self._backend is not None:
            found = self._backend.get(key)
            if found:
                return [tuple(v) for v in found], "dictionary"
        if key in self._seed:
            return self._seed[key], "seed"
        return None

    def _conf_for(self, source: str) -> float:
        return float(self._conf.get(source, self._conf["heuristic_base"]))

    def _lookup(self, key: str) -> list[Pronunciation]:
        if not key:
            return [Pronunciation(key, (), "empty", 0.0, ("empty token",))]
        direct = self._direct(key)
        if direct:
            variants, source = direct
            return [Pronunciation(key, v, source, self._conf_for(source)) for v in variants]
        # g-dropped forms like runnin -> running
        if self.config.phonetics.get("g_drop_expansion", True) and key.endswith("in") and len(key) > 3:
            full = self._direct(key + "g")
            if full:
                variants, source = full
                out = []
                for v in variants:
                    v = tuple(v[:-1]) + ("N",) if v and v[-1] == "NG" else tuple(v)
                    out.append(Pronunciation(key, v, source, self._conf_for(source) - self._conf["g_drop_penalty"], ("g-dropped form of " + key + "g",)))
                return out
        # contractions: stem + clitic
        if "'" in key:
            stem, _, clitic = key.rpartition("'")
            clitic_phones = {"s": None, "re": ("ER0",), "ll": ("L",), "ve": ("V",), "d": ("D",), "m": ("M",), "t": ("T",)}
            if stem and clitic in clitic_phones:
                if clitic == "t" and stem.endswith("n"):
                    base = self.pronounce(stem[:-1])
                    phones = base.phones + ("AH0", "N", "T")
                else:
                    base = self.pronounce(stem)
                    add = clitic_phones[clitic]
                    if add is None:
                        last = strip_stress(base.phones[-1]) if base.phones else ""
                        voiceless = set(load_data_json("phonetic_features.json")["voiceless_consonants"])
                        add = ("IH0", "Z") if last in ("S", "Z", "SH", "ZH", "CH", "JH") else (("S",) if last in voiceless else ("Z",))
                    phones = base.phones + tuple(add)
                return [Pronunciation(key, phones, base.source, base.confidence - self._conf["contraction_penalty"], ("contraction",))]
            key = key.replace("'", "")
            direct = self._direct(key)
            if direct:
                variants, source = direct
                return [Pronunciation(key, v, source, self._conf_for(source)) for v in variants]
        suffixed = self._suffix_split(key)
        if suffixed:
            return [suffixed]
        return [self._heuristic(key)]

    @staticmethod
    def _suffix_candidates(key: str) -> list[tuple[str, object, bool]]:
        """(stem, suffix spec, usable_with_heuristic_stem) in priority order."""
        ing = ("IH0", "NG")
        out: list[tuple[str, object, bool]] = []

        def vc_end(s: str) -> bool:
            return (len(s) >= 2 and _is_cons_letter(s[-1]) and s[-1] not in "wx" and s[-2] in LETTER_VOWELS
                    and (len(s) < 3 or s[-3] not in LETTER_VOWELS) and _vowel_groups(s) == 1)

        if key.endswith("ies") and len(key) > 4:
            out.append((key[:-3] + "y", ("Z",), True))
        if key.endswith("ied") and len(key) > 4:
            out.append((key[:-3] + "y", ("D",), True))
        if key.endswith("ing") and len(key) > 4:
            stem = key[:-3]
            if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in "ls":
                out.append((stem[:-1], ing, True))
            if vc_end(stem):
                out.append((stem + "e", ing, True))
            out.append((stem, ing, True))
            out.append((stem + "e", ing, False))
        if key.endswith("ed") and len(key) > 3:
            stem = key[:-2]
            if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in "ls":
                out.append((stem[:-1], "ED", True))
            if vc_end(stem) or re.search(r"[bcdfgkptvz]l$", stem):
                out.append((key[:-1], "ED", True))
            out.append((stem, "ED", True))
            out.append((key[:-1], "ED", False))
        if key.endswith("es") and len(key) > 3:
            stem = key[:-2]
            if re.search(r"(s|x|z|ch|sh)$", stem):
                out.append((stem, "ES", True))
            out.append((key[:-1], "S", True))
        elif key.endswith("s") and not key.endswith(("ss", "us", "is")) and len(key) > 2:
            out.append((key[:-1], "S", True))
        if key.endswith("ly") and len(key) > 4:
            out.append((key[:-2], ("L", "IY0"), True))
        for suffix, phones in (("ness", ("N", "AH0", "S")), ("ment", ("M", "AH0", "N", "T")),
                               ("ful", ("F", "AH0", "L")), ("less", ("L", "AH0", "S"))):
            if key.endswith(suffix) and len(key) > len(suffix) + 2:
                out.append((key[:-len(suffix)], phones, True))
        if key.endswith("er") and len(key) > 4:
            out.append((key[:-2], ("ER0",), False))
        return out

    @staticmethod
    def _finish_suffix(base: Sequence[str], add: object) -> tuple[str, ...] | None:
        voiceless = set(load_data_json("phonetic_features.json")["voiceless_consonants"])
        last = strip_stress(base[-1]) if base else ""
        sibilant = last in ("S", "Z", "SH", "ZH", "CH", "JH")
        if add == "ED":
            add = ("IH0", "D") if last in ("T", "D") else (("T",) if last in voiceless else ("D",))
        elif add == "ES":
            if not sibilant:
                return None
            add = ("IH0", "Z")
        elif add == "S":
            add = ("IH0", "Z") if sibilant else (("S",) if last in voiceless else ("Z",))
        return tuple(base) + tuple(add)  # type: ignore[arg-type]

    def _suffix_split(self, key: str) -> Pronunciation | None:
        candidates = self._suffix_candidates(key)
        for stem, add, _ in candidates:
            direct = self._direct(stem)
            if not direct:
                continue
            variants, source = direct
            phones = self._finish_suffix(variants[0], add)
            if phones is None:
                continue
            conf = self._conf_for(source) - self._conf["heuristic_ambiguity_penalty"] / 2
            return Pronunciation(key, phones, source, conf, (f"suffix split: {stem}",))
        for stem, add, heuristic_ok in candidates:
            if not heuristic_ok or len(stem) < 3 or not re.search(r"[aeiouy]", stem):
                continue
            stem_pr = self._heuristic(stem)
            phones = self._finish_suffix(stem_pr.phones, add)
            if phones is None:
                continue
            return Pronunciation(key, phones, "heuristic", stem_pr.confidence, ("spelling-based guess", f"suffix split: {stem}"))
        return None

    def _heuristic(self, key: str) -> Pronunciation:
        raw, amb = heuristic_g2p(key)
        phones, amb2 = assign_stress(key, raw)
        sylls = sum(1 for p in phones if is_vowel(p))
        conf = (self._conf["heuristic_base"]
                - (amb + amb2) * self._conf["heuristic_ambiguity_penalty"]
                - max(0, sylls - 2) * self._conf["heuristic_length_penalty_per_syllable_over_two"])
        conf = max(self._conf["heuristic_min"], conf)
        return Pronunciation(key, tuple(phones), "heuristic", conf, ("spelling-based guess",))


_DEFAULT_DICTS: dict[tuple, PhoneticDictionary] = {}


def get_dictionary(config: Config | dict | None = None) -> PhoneticDictionary:
    """Shared dictionary for a config (no overrides). Build your own for overrides."""
    cfg = resolve_config(config)
    key = (dictionary_mode(cfg), str(cfg.phonetics.get("dialect")), id(cfg))
    if key not in _DEFAULT_DICTS:
        _DEFAULT_DICTS[key] = PhoneticDictionary(cfg)
    return _DEFAULT_DICTS[key]


def clear_dictionary_cache() -> None:
    _DEFAULT_DICTS.clear()


# ----------------------------------------------------------------------------
# phrase level


@dataclass
class PhraseSyllable:
    """One syllable in a phrase, with the word it came from."""

    syllable: Syllable
    word_index: int
    word: str
    syllable_in_word: int
    confidence: float
    is_word_final: bool = False
    demoted: bool = False

    @property
    def stressed(self) -> bool:
        return self.syllable.stress in (1, 2) and not self.demoted


def token_pronunciations(tokens: Sequence[Token], dictionary: PhoneticDictionary) -> list[Pronunciation]:
    """One pronunciation per token (numbers are spelled out and joined)."""
    prons = []
    for tok in tokens:
        if len(tok.spoken) == 1:
            prons.append(dictionary.pronounce(tok.spoken[0]))
            continue
        parts = [dictionary.pronounce(w) for w in tok.spoken]
        phones = tuple(p for pr in parts for p in pr.phones)
        conf = min(pr.confidence for pr in parts) if parts else 0.0
        prons.append(Pronunciation(tok.norm, phones, "number", conf, ("spelled out: " + " ".join(tok.spoken),)))
    return prons


def phrase_syllables(tokens: Sequence[Token], prons: Sequence[Pronunciation], function_words: Iterable[str] = ()) -> list[PhraseSyllable]:
    fw = set(function_words)
    out: list[PhraseSyllable] = []
    for wi, (tok, pr) in enumerate(zip(tokens, prons)):
        sylls = pr.syllables
        demote = tok.norm in fw and len(sylls) == 1
        for si, s in enumerate(sylls):
            out.append(PhraseSyllable(s, wi, tok.norm, si, pr.confidence, si == len(sylls) - 1, demote))
    return out
