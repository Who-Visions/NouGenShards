"""Graded rhyme engine.

Rhyme is scored as a phonetic distance from 0.0 (identical) to 1.0
(unrelated), then labeled with a kind. Kinds, strictest first:

- ``identity``: the same sounds including the onset of the stressed syllable
  (same word, homophone, or rich rhyme like light / delight). Fine in small
  doses, penalized by the scorer when overused.
- ``exact``: rhyme tails (stressed vowel to end of word) match phone for
  phone, onsets differ (cat / hat).
- ``perfect``: stressed vowel and every tail consonant match; unstressed
  vowels may differ a little (common between dictionary variants).
- ``slant``: close but not identical, within ``rhyme.slant_max_distance``.
- ``assonance``: stressed vowels match, consonants do not.
- ``consonance``: final consonants match, vowels do not.
- ``none``.

Phrase-level matching counts matching vowel runs from the end of two phrases.
Two or more syllables is a multisyllabic rhyme. When both sides span a word
boundary it is labeled ``compound``; when one side is a single word and the
other spans several words it is labeled ``mosaic``.

All cutoffs come from the ``rhyme`` config section. They are heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .config import Config, load_data_json, load_data_lines, resolve_config
from .phonetics import (
    PhoneticDictionary,
    PhraseSyllable,
    Pronunciation,
    Syllable,
    get_dictionary,
    phrase_syllables,
    strip_stress,
    token_pronunciations,
    tokenize,
)

RHYME_KINDS = ("identity", "exact", "perfect", "slant", "assonance", "consonance", "none")
KIND_RANK = {k: i for i, k in enumerate(RHYME_KINDS)}


@dataclass
class RhymeMatch:
    a: str
    b: str
    kind: str
    distance: float
    vowel_distance: float
    coda_distance: float
    syllables_compared: int
    confidence: float

    @property
    def is_rhyme(self) -> bool:
        return self.kind in ("identity", "exact", "perfect", "slant")

    def to_dict(self) -> dict:
        return {
            "a": self.a, "b": self.b, "kind": self.kind, "distance": round(self.distance, 4),
            "vowel_distance": round(self.vowel_distance, 4), "coda_distance": round(self.coda_distance, 4),
            "syllables_compared": self.syllables_compared, "confidence": round(self.confidence, 3),
        }


@dataclass
class MultiMatch:
    syllables: int
    distance: float
    kind: str
    spans_boundary_a: bool
    spans_boundary_b: bool
    vowels_a: list[str] = field(default_factory=list)
    vowels_b: list[str] = field(default_factory=list)
    words_a: list[str] = field(default_factory=list)
    words_b: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "syllables": self.syllables, "distance": round(self.distance, 4), "kind": self.kind,
            "spans_boundary_a": self.spans_boundary_a, "spans_boundary_b": self.spans_boundary_b,
            "vowels_a": self.vowels_a, "vowels_b": self.vowels_b, "words_a": self.words_a, "words_b": self.words_b,
            "confidence": round(self.confidence, 3),
        }


@dataclass
class RhymeCandidate:
    word: str
    kind: str
    distance: float
    syllables_matched: int
    confidence: float
    source: str

    def to_dict(self) -> dict:
        return {
            "word": self.word, "kind": self.kind, "distance": round(self.distance, 4),
            "syllables_matched": self.syllables_matched, "confidence": round(self.confidence, 3), "source": self.source,
        }


class RhymeScorer:
    """Feature-based phonetic distances with config-driven weights and cutoffs."""

    def __init__(self, config: Config | dict | None = None):
        cfg = resolve_config(config)
        self.config = cfg
        self.r = cfg.rhyme
        feats = load_data_json("phonetic_features.json")
        self._vowels = feats["vowels"]
        self._cons = feats["consonants"]
        self._places = {name: i for i, name in enumerate(feats["consonant_places"])}
        self._place_span = max(1, len(feats["consonant_places"]) - 1)
        self._near = {frozenset(p) for p in feats["manner_near_pairs"]}
        self._near_d = float(feats["manner_near_distance"])
        self._share = float(feats["diphthong_nucleus_share"])
        self._vcache: dict[tuple[str, str], float] = {}
        self._ccache: dict[tuple[str, str], float] = {}

    # -- segment distances ---------------------------------------------------
    def _mono(self, f1: dict, f2: dict) -> float:
        w = self.r["vowel_feature_weights"]
        return (w["height"] * abs(f1["height"] - f2["height"]) + w["backness"] * abs(f1["backness"] - f2["backness"])
                + w["round"] * abs(f1["round"] - f2["round"]) + w["rhotic"] * abs(f1["rhotic"] - f2["rhotic"]))

    def vowel_distance(self, a: str, b: str) -> float:
        a, b = strip_stress(a), strip_stress(b)
        if a == b:
            return 0.0
        key = (a, b) if a < b else (b, a)
        if key in self._vcache:
            return self._vcache[key]
        fa, fb = self._vowels[a], self._vowels[b]
        ga, gb = fa.get("glide_to"), fb.get("glide_to")
        if ga and gb:
            d = self._share * self._mono(fa, fb) + (1 - self._share) * self._mono(self._vowels[ga], self._vowels[gb])
        elif ga or gb:
            d = self._mono(fa, fb) + float(self.r["diphthong_glide_penalty"])
        else:
            d = self._mono(fa, fb)
        d = min(1.0, d)
        self._vcache[key] = d
        return d

    def consonant_distance(self, a: str, b: str) -> float:
        if a == b:
            return 0.0
        key = (a, b) if a < b else (b, a)
        if key in self._ccache:
            return self._ccache[key]
        fa, fb = self._cons[a], self._cons[b]
        w = self.r["consonant_feature_weights"]
        place = abs(self._places[fa["place"]] - self._places[fb["place"]]) / self._place_span
        if fa["manner"] == fb["manner"]:
            manner = 0.0
        elif frozenset((fa["manner"], fb["manner"])) in self._near:
            manner = self._near_d
        else:
            manner = 1.0
        voice = abs(fa["voiced"] - fb["voiced"])
        d = min(1.0, w["place"] * place + w["manner"] * manner + w["voice"] * voice)
        self._ccache[key] = d
        return d

    def cluster_distance(self, a: Sequence[str], b: Sequence[str]) -> float:
        """Normalized edit distance between consonant sequences using feature substitution costs."""
        if not a and not b:
            return 0.0
        indel = float(self.r["consonant_indel_cost"])
        rows, cols = len(a) + 1, len(b) + 1
        dp = [[0.0] * cols for _ in range(rows)]
        for i in range(1, rows):
            dp[i][0] = i * indel
        for j in range(1, cols):
            dp[0][j] = j * indel
        for i in range(1, rows):
            for j in range(1, cols):
                dp[i][j] = min(
                    dp[i - 1][j] + indel,
                    dp[i][j - 1] + indel,
                    dp[i - 1][j - 1] + self.consonant_distance(a[i - 1], b[j - 1]),
                )
        return min(1.0, dp[-1][-1] / max(len(a), len(b)))

    def syllable_distance(self, a: Syllable, b: Syllable) -> tuple[float, float, float]:
        vd = self.vowel_distance(a.nucleus, b.nucleus)
        cd = self.cluster_distance(a.coda, b.coda)
        return vd, cd, self.r["vowel_weight"] * vd + self.r["coda_weight"] * cd

    # -- word level ------------------------------------------------------------
    def compare(self, p1: Pronunciation, p2: Pronunciation) -> RhymeMatch:
        conf = min(p1.confidence, p2.confidence)
        t1, t2 = p1.tail_syllables(), p2.tail_syllables()
        if not t1 or not t2:
            return RhymeMatch(p1.word, p2.word, "none", 1.0, 1.0, 1.0, 0, conf)
        if [strip_stress(p) for p in p1.phones] == [strip_stress(p) for p in p2.phones]:
            return RhymeMatch(p1.word, p2.word, "identity", 0.0, 0.0, 0.0, len(t1), conf)
        pairs = list(zip(t1, t2))
        extra = abs(len(t1) - len(t2))
        ws = float(self.r["stressed_syllable_weight"])
        wu = float(self.r["unstressed_syllable_weight"])
        total = 0.0
        weight = 0.0
        vds, cds = [], []
        for k, (s1, s2) in enumerate(pairs):
            vd, cd, d = self.syllable_distance(s1, s2)
            w = ws if k == 0 else wu
            total += w * d
            weight += w
            vds.append(vd)
            cds.append(cd)
        total += extra * float(self.r["syllable_mismatch_penalty"]) * wu
        weight += extra * wu
        distance = min(1.0, total / weight if weight else 1.0)
        v0, c0 = vds[0], cds[0]
        codas_same = all(s1.coda == s2.coda for s1, s2 in pairs)
        nuclei_same = all(s1.nucleus == s2.nucleus for s1, s2 in pairs)
        if extra == 0 and nuclei_same and codas_same:
            kind = "identity" if t1[0].onset == t2[0].onset else "exact"
            distance = 0.0
        elif extra == 0 and v0 == 0.0 and codas_same and all(v <= self.r["perfect_unstressed_vowel_max"] for v in vds[1:]):
            kind = "perfect"
        elif distance <= self.r["slant_max_distance"] and v0 <= self.r["slant_vowel_max"]:
            kind = "slant"
        elif v0 <= self.r["assonance_vowel_max"]:
            kind = "assonance"
        elif (t1[-1].coda or t2[-1].coda) and self.cluster_distance(t1[-1].coda, t2[-1].coda) <= self.r["consonance_coda_max"]:
            kind = "consonance"
        else:
            kind = "none"
        return RhymeMatch(p1.word, p2.word, kind, distance, v0, c0, len(pairs), conf)

    def compare_words(self, w1: str, w2: str, dictionary: PhoneticDictionary | None = None) -> RhymeMatch:
        d = dictionary or get_dictionary(self.config)
        best: RhymeMatch | None = None
        for p1 in d.pronounce_all(w1):
            for p2 in d.pronounce_all(w2):
                m = self.compare(p1, p2)
                if best is None or (m.distance, KIND_RANK[m.kind]) < (best.distance, KIND_RANK[best.kind]):
                    best = m
        assert best is not None
        return best

    # -- phrase level ----------------------------------------------------------
    def multisyllabic(self, a: Sequence[PhraseSyllable], b: Sequence[PhraseSyllable]) -> MultiMatch:
        """Longest run of matching vowels counted back from the end of both phrases."""
        limit_s = float(self.r["multi_vowel_max"])
        limit_u = float(self.r["multi_unstressed_vowel_max"])
        max_k = int(self.r["multi_max_syllables"])
        k = 0
        ds: list[float] = []
        stressed_pair = False
        for i in range(1, min(len(a), len(b)) + 1):
            sa, sb = a[-i], b[-i]
            vd = self.vowel_distance(sa.syllable.nucleus, sb.syllable.nucleus)
            both_unstressed = not sa.stressed and not sb.stressed
            if vd > (limit_u if both_unstressed else limit_s):
                break
            if sa.stressed and sb.stressed:
                stressed_pair = True
            k = i
            ds.append(vd)
            if k >= max_k:
                break
        if not stressed_pair:
            k = 0
        run_a, run_b = list(a[len(a) - k:]) if k else [], list(b[len(b) - k:]) if k else []
        words_a = sorted({s.word_index for s in run_a})
        words_b = sorted({s.word_index for s in run_b})
        span_a, span_b = len(words_a) > 1, len(words_b) > 1
        if k < int(self.r["multi_min_syllables"]):
            kind = "none"
        elif span_a and span_b:
            kind = "compound"
        elif span_a or span_b:
            kind = "mosaic"
        else:
            kind = "multisyllabic"
        conf = min([s.confidence for s in run_a + run_b], default=0.0)
        return MultiMatch(
            k, sum(ds) / len(ds) if ds else 1.0, kind, span_a, span_b,
            [s.syllable.nucleus for s in run_a], [s.syllable.nucleus for s in run_b],
            _ordered_words(run_a), _ordered_words(run_b), conf,
        )


def _ordered_words(run: Sequence[PhraseSyllable]) -> list[str]:
    out: list[str] = []
    seen = set()
    for s in run:
        if s.word_index not in seen:
            seen.add(s.word_index)
            out.append(s.word)
    return out


def stopwords() -> set[str]:
    return set(load_data_json("lexicons.json")["stopwords"])


def phrase_to_syllables(text: str, dictionary: PhoneticDictionary | None = None, config: Config | None = None) -> list[PhraseSyllable]:
    d = dictionary or get_dictionary(config)
    toks = tokenize(text)
    prons = token_pronunciations(toks, d)
    demote = stopwords() if d.config.phonetics.get("demote_function_words", True) else set()
    return phrase_syllables(toks, prons, demote)


def compare_words(w1: str, w2: str, dictionary: PhoneticDictionary | None = None, config: Config | dict | None = None) -> RhymeMatch:
    return RhymeScorer(config if config is not None else (dictionary.config if dictionary else None)).compare_words(w1, w2, dictionary)


def compare_phrases(a: str, b: str, dictionary: PhoneticDictionary | None = None, config: Config | dict | None = None) -> MultiMatch:
    cfg = resolve_config(config if config is not None else (dictionary.config if dictionary else None))
    d = dictionary or get_dictionary(cfg)
    scorer = RhymeScorer(cfg)
    return scorer.multisyllabic(phrase_to_syllables(a, d, cfg), phrase_to_syllables(b, d, cfg))


def family_label(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    label = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        label = chr(ord("A") + rem) + label
    return label


def _vocabulary(dictionary: PhoneticDictionary, extra: Iterable[str] | None) -> list[tuple[str, str]]:
    words: dict[str, str] = {}
    for w in load_data_lines("vocab.txt"):
        words.setdefault(w, "vocab")
    for w in load_data_json("seed_lexicon.json")["words"]:
        if w.isalpha():
            words.setdefault(w, "seed")
    if dictionary._backend is not None:  # optional dictionary adds the long tail
        for w in dictionary._backend:
            if w.isalpha() and len(w) > 1:
                words.setdefault(w, "dictionary")
    for w in extra or ():
        words[w.lower()] = "user"
    return sorted(words.items())


def find_rhymes(
    phrase: str,
    constraints: dict | None = None,
    dictionary: PhoneticDictionary | None = None,
    config: Config | dict | None = None,
) -> list[RhymeCandidate]:
    """Rank candidate rhymes for the end of ``phrase``.

    constraints keys (all optional):
      kinds: rhyme kinds to accept (default exact, perfect; slant=True adds slant and assonance)
      slant: bool shortcut to include slant and assonance
      syllables: minimum matched syllables counted back from the end (multisyllabic depth)
      max_results: cap (default rhyme.find_max_results)
      vocabulary: extra or replacement words to search (list)
      vocabulary_only: search only the supplied vocabulary
    """
    cfg = resolve_config(config if config is not None else (dictionary.config if dictionary else None))
    c = dict(constraints or {})
    d = dictionary or get_dictionary(cfg)
    scorer = RhymeScorer(cfg)
    kinds = set(c.get("kinds") or ("exact", "perfect"))
    if c.get("slant"):
        kinds |= {"slant", "assonance"}
    min_syll = int(c.get("syllables") or 0)
    limit = int(c.get("max_results") or cfg.rhyme["find_max_results"])
    target_sylls = phrase_to_syllables(phrase, d, cfg)
    toks = tokenize(phrase)
    if not toks or not target_sylls:
        return []
    target_word = toks[-1].norm
    target_pron = token_pronunciations(toks[-1:], d)[0]
    if c.get("vocabulary_only"):
        vocab = [(w.lower(), "user") for w in c.get("vocabulary") or []]
    else:
        vocab = _vocabulary(d, c.get("vocabulary"))
    target_nucleus = target_pron.tail_syllables()[0].nucleus if target_pron.tail_syllables() else None
    loose = bool(kinds - {"exact", "perfect", "identity"}) or bool(min_syll)
    vowel_gate = max(float(cfg.rhyme["slant_vowel_max"]), float(cfg.rhyme["multi_vowel_max"])) if loose else 0.0
    stop = stopwords()
    out: list[RhymeCandidate] = []
    for word, source in vocab:
        if word == target_word:
            continue
        pr = d.pronounce(word)
        tail = pr.tail_syllables()
        if not tail:
            continue
        if target_nucleus and scorer.vowel_distance(target_nucleus, tail[0].nucleus) > vowel_gate:
            continue
        m = scorer.compare(target_pron, pr)
        if m.kind == "identity":
            continue
        word_sylls = [PhraseSyllable(s, 0, word, k, pr.confidence, k == pr.syllable_count - 1, word in stop and pr.syllable_count == 1)
                      for k, s in enumerate(pr.syllables)]
        multi = scorer.multisyllabic(target_sylls, word_sylls)
        matched = max(multi.syllables, 1 if m.kind in ("exact", "perfect", "slant") else 0)
        if min_syll:
            if matched < min_syll:
                continue
        elif m.kind not in kinds:
            continue
        kind = m.kind if m.kind in kinds or not min_syll else ("multisyllabic" if multi.kind != "none" else m.kind)
        out.append(RhymeCandidate(word, kind, m.distance if not min_syll else multi.distance, matched, m.confidence, source))
    # common words (bundled vocabulary, seed lexicon, user words) come before the dictionary's long tail
    out.sort(key=lambda r: (-r.syllables_matched if min_syll else 0, 0 if r.source in ("vocab", "seed", "user") else 1, round(r.distance, 6), r.word))
    return out[:limit]
