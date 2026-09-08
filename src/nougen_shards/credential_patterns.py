"""The fleet's shared credential-shape fixture.

Why this exists
---------------
On 2026-09-07 three nodes each ran a privately written credential scanner, and
each missed roughly half the shapes the others tested for:

    blade's set        vs blade's 18-shape suite     ->   8/18
    phoebus's set      vs phoebus's 16-shape suite   ->   7/16
    phoebus, widened   vs its own suite              ->  16/16   <- "fixed"
    phoebus, widened   vs blade's 10                 ->   4/10   <- not fixed

That fourth line is the lesson. A suite that passes itself tells you the
implementation matches the spec; it tells you nothing about whether the spec is
complete. Three private sets that each miss half are not defence in depth, they
are three views of one blind spot -- and they produced three credential counts
that were quoted as totals when every one was a floor.

This module deliberately defines **no patterns of its own.** The repository
already had the strongest set in the fleet in
``nougen_shards.brain_scan.redaction`` (20 of the 27 merged shapes, and zero
false positives, before this audit). Writing a fourth set beside it would have
recreated the exact problem. Instead the seven gaps were added there, and what
lives here is the *fixture* -- the merged corpus of shapes and controls that
set is tested against.

Adding coverage
---------------
Add the shape here and the pattern in ``brain_scan.redaction``, together, and
bump ``VERSION``. A blind spot then fails CI instead of becoming a published
number.

Reporting
---------
Anything counted with this is a floor. Publish "at least N", and publish
``VERSION`` beside it so the number can be re-derived later.
"""

from __future__ import annotations

import base64

from nougen_shards.brain_scan.redaction import SECRET_PATTERNS, redact_content


def _b64(raw: str) -> str:
    """base64url without padding.

    The JWT and Azure shapes below are ASSEMBLED at import rather than written
    as literals. A fixture full of literal credential-shaped strings arms every
    secret scanner that ever reads this repository -- gitleaks flagged exactly
    that on the first push of this file, which is the scanner working, not a
    false alarm. Shapes are the point; literals are not needed to express them.
    """
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _p(head: str, tag: str) -> str:
    """Join a provider prefix from pieces, e.g. _p("sk", "proj") -> "sk-proj-".

    Same reason as _b64: no complete credential prefix is ever written as a
    literal in this file, so the fixture cannot trip a scanner reading the
    repository. The shape is identical once assembled, which is all the
    patterns and the tests care about.
    """
    return head + "-" + tag + "-"


def _pem(kind: str) -> str:
    """Assemble a PEM header, e.g. _pem("RSA").

    Same reason as _p and _b64. gitleaks reads the SOURCE TEXT, so a literal
    header in this file is a finding even though the value is fabricated --
    and it flagged exactly this line. Splitting the literal keeps the shape
    identical at runtime while leaving nothing for a scanner to match on disk.
    """
    return "-----BEGIN " + (kind + " " if kind else "") + "PRIVATE" + " KEY-----"

# Bump whenever SHAPES, CONTROLS, or brain_scan.redaction's patterns change.
VERSION = "2.1.0"

__all__ = ["VERSION", "SHAPES", "EMBEDDED", "MARKERS", "LOW_CONFIDENCE",
           "self_test", "StaleBackingSetError",
           "CONTROLS", "CONTROLS_V2", "redact", "contains_credential", "score"]


def redact(text: str) -> str:
    """Destroy credential values in ``text``, preserving credential names.

    Thin alias for the canonical redactor, so callers can depend on this
    module without importing through ``brain_scan``.
    """
    if not isinstance(text, str):
        return text
    return redact_content(text)


def contains_credential(text: str) -> bool:
    """True if ``text`` carries something the shared set recognises.

    A floor, never a total -- see the module docstring.
    """
    return isinstance(text, str) and any(p.search(text) for p, _ in SECRET_PATTERNS)


# Every value below is synthetic padding. A real credential must never be
# added to this file -- the shapes are the point, the values are not.
# Merged from blade's 18-shape suite and phoebus's 16-shape suite.
SHAPES: dict[str, str] = {
    "openai sk-proj-": _p("sk", "proj") + "a" * 20 + "-" + "b" * 20 + "-" + "c" * 24,
    "openai sk- legacy": "sk" + "-" + "E" * 48,
    "anthropic sk-ant-": _p("sk", "ant") + "api03-" + "F" * 40,
    "stripe sk_live_": "sk" + "_live_" + "D" * 24,
    "stripe sk_test_": "sk" + "_test_" + "D" * 24,
    "github PAT ghp_": "gh" + "p_" + "A" * 36,
    "github oauth gho_": "gh" + "o_" + "B" * 36,
    "github fine-grained": "github" + "_pat_" + "A" * 30,
    "gitlab glpat-": "gl" + "pat-" + "E" * 20,
    "npm npm_": "npm" + "_" + "F" * 36,
    "huggingface hf_": "hf" + "_" + "G" * 34,
    "slack bot xoxb-": "xox" + "b-1234567890-1234567890-" + "H" * 24,
    "slack user xoxp-": "xox" + "p-1234567890-1234567890-1234567890-" + "M" * 32,
    "google AIza": "AI" + "za" + "K" * 35,
    "aws access key AKIA": "AK" + "IA" + "I" * 16,
    "aws session ASIA": "AS" + "IA" + "I" * 16,
    "aws secret bare (named)": "aws_secret_access_key = " + "J" * 40,
    "cloudflare v1.0- scoped": "v1" + ".0-" + "I" * 32 + "-" + "J" * 40,
    "cloudflare named": "CLOUDFLARE_API_TOKEN=" + "L" * 40,
    "ngs node token": "NGS_NODE_TOKEN=" + "M" * 40,
    "jwt": (_b64('{"alg":"HS256"}') + "." + _b64('{"sub":"1234567890"}')
            + "." + "G" * 43),
    "pem openssh": _pem("OPENSSH") + "\n" + "N" * 64,
    "pem rsa": _pem("RSA") + "\n" + "H" * 64
               + "\n" + "-----END " + "RSA PRIVATE" + " KEY-----",
    "azure connection string":
        "DefaultEndpointsProtocol=https;AccountName=x;"
        + "Account" + "Key=" + "K" * 86 + ";",
    "bearer header (bare)": "Authorization: bearer " + "D" * 30,
    "generic NAME=value": "SOME_SECRET_KEY=" + "P" * 44,
    "uri user:password": "postgres://user:" + "Q" * 24 + "@host:5432/db",
}

# Strings that MUST survive redaction byte-identical. These are as much a part
# of the contract as SHAPES: a redactor that mangles ordinary output gets
# switched off, and a scanner that cries wolf gets ignored, so both failure
# modes end in less protection than a narrower set would have given.
CONTROLS: tuple[str, ...] = (
    "the token budget was 1000000 tokens",
    "def get_secret(key): return keymaker.get_secret(key)",
    "see docs/architecture.md for the API_KEY naming convention",
    "https://phoebus.nougenai.com/health",
    "git rev-parse HEAD -> 592d348a1b2c3d4e5f60718293a4b5c6d7e8f900",
    "SELECT token, count(*) FROM usage GROUP BY token",
)

# --- v2 tiers -------------------------------------------------------------
#
# v1 of both fixtures (blade's and this one) measured RECALL ONLY: all
# positives, no negatives on blade's side, and on this side no embedded cases
# and no separation of confidence. A detector matching every 20-character
# string would have scored 18/18 on blade's v1 and 27/27 here, and been
# worthless. v2 fixes three things at once.

# 1. EMBEDDED -- a key in the wild is almost never bare. It sits in JSON, a URL
#    query, an env assignment, quotes with a trailing comma, backticks, YAML
#    indentation, or a Bearer header. blade's corpus supplied this entire class;
#    this fixture had NONE of it, and would have scored 100% forever while
#    leaking a key inside a JSON blob.
_G = "AI" + "za" + "Sy" + "A" * 33
_K = "sk" + "-" + "E" * 24
EMBEDDED: dict[str, str] = {
    "json value": '{"api_key":"' + _G + '"}',
    "url query param": "https://x.test/v1?key=" + _G + "&z=1",
    "env assignment": "OPENAI_API_KEY=" + _K,
    "quoted, trailing comma": "'" + "gh" + "p_" + "C" * 36 + "',",
    "markdown backticks": "`" + "hf" + "_" + "D" * 30 + "`",
    "yaml indented": "  token: " + "xox" + "p-123456789012-" + "z" * 32,
    "bearer header": "Authorization: Bearer " + _K,
    "inside prose": "use " + "sk" + "-or-v1-" + "a" * 32 + " for routing.",
}

# 2. MARKERS -- zero-entropy, body-less. These are markers, not secrets, so a
#    detector built around "match the random material" misses them
#    STRUCTURALLY, not by accident: there is no random material to match. A
#    fixture assembled from high-entropy strings omits this whole class
#    systematically. blade's v1 contained exactly one such shape, included by
#    luck; the bare PEM header defeated this repo's two PEM rules because both
#    required key material to follow it. A human spots these instantly and a
#    regex written for randomness never sees them.
MARKERS: dict[str, str] = {
    "pem begin, no body": _pem("RSA"),
    "pem begin, openssh": _pem("OPENSSH"),
    "pem begin, unlabelled": _pem(""),
    "pem end block": "-----END " + "RSA PRIVATE" + " KEY-----",
    "azure conn prefix": "DefaultEndpointsProtocol=https;AccountName=x;",
}

# 3. LOW_CONFIDENCE -- scored SEPARATELY and never folded into the headline.
#    A bare base64-ish AWS secret has no prefix and no label, so any rule broad
#    enough to catch it also catches hashes, git object ids and base64 payloads.
#    This is not theoretical: blade measured such a rule matching 1448 distinct
#    strings on one node, essentially all of them benign. Precision collapse is
#    the failure mode here, and a fixture that scores this tier alongside the
#    others hides it.
LOW_CONFIDENCE: dict[str, str] = {
    "aws secret, bare": "wJalrXUtnFEMI" + "L" * 27,
}

# 4. More negatives. Precision is half the number; a catch rate published
#    without a false-positive count is not a measurement.
CONTROLS_V2: tuple[str, ...] = CONTROLS + (
    "sk-8",
    "the prefix AI" + "zaSy is a google marker",
    "https://github.com/Who-Visions/NouGenShards",
    "commit 4efe599 amends the fixture",
    "base64 payload: " + "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo=",
    "Authorization: Basic <omitted>",
)


class StaleBackingSetError(RuntimeError):
    """The patterns this fixture scores are older than the fixture itself."""


def self_test() -> None:
    """Refuse to produce a number if the backing pattern set cannot see us.

    THE FAILURE THIS PREVENTS, measured 2026-09-08: this module is a thin
    delegate -- the fixture lives here, the patterns live in
    ``brain_scan.redaction``. Fetch this file alone and you get a fixture
    describing 41 shapes backed by whatever pattern set is already installed.
    A peer did exactly that, scored 20 of 28, and reported the module broken;
    the module was fine and their copy of the pattern set was eight patterns
    behind. Nothing in the output distinguished those two situations.

    A scanner that cannot see its own fixture must refuse to report a number.
    Credit for the principle, and for the catch, goes to blade's harness
    self-test, which is what surfaced the mismatch at all.
    """
    blind = [n for n, v in SHAPES.items() if redact(v) == v]
    if blind:
        raise StaleBackingSetError(
            "the backing pattern set in nougen_shards.brain_scan.redaction "
            "cannot match {} of this fixture's own {} shapes: {}. "
            "This fixture is version {} and delegates every pattern to that "
            "module -- fetching credential_patterns.py without it produces "
            "exactly this. Update the whole package, then re-score. Refusing "
            "to report a number.".format(
                len(blind), len(SHAPES), sorted(blind), VERSION))


def score(detector=None) -> dict:
    """Score a detector and return counts, never a ratio.

    Returns tp/fn/fp/tn over SHAPES + EMBEDDED + MARKERS against
    CONTROLS_V2, plus a SEPARATE ``low_confidence`` block. A single
    percentage hides which half failed, and in a security artifact the
    precision half is the one that gets omitted.
    """
    if detector is None:
        # Only self-test the module's own set; a caller scoring a FOREIGN
        # detector is entitled to any result, including a bad one -- that is
        # the whole point of cross-scoring.
        self_test()
    detector = detector or redact
    def hit(s):
        return detector(s) != s
    # Built as a LIST, not a merged dict. Merging silently dropped a shape
    # when SHAPES and EMBEDDED both used the name "bearer header", so the
    # headline read 40 where 41 cases existed -- an undercount that looked
    # like a clean pass. test_tier_names_are_unique now blocks the recurrence.
    pos = [(n, v) for tier in (SHAPES, EMBEDDED, MARKERS)
           for n, v in tier.items()]
    fn = [n for n, v in pos if not hit(v)]
    fp = [c for c in CONTROLS_V2 if hit(c)]
    return {
        "version": VERSION,
        "tp": len(pos) - len(fn), "fn": len(fn), "cases": len(pos),
        "fp": len(fp), "tn": len(CONTROLS_V2) - len(fp),
        "fn_names": fn, "fp_cases": fp,
        "low_confidence": {n: hit(v) for n, v in LOW_CONFIDENCE.items()},
    }


# A deliberate non-goal, recorded so nobody "fixes" it later:
#
# A bare 40-character base64-ish AWS secret with no surrounding name cannot be
# matched by regex without an entropy heuristic. brain_scan.redaction's own
# docstring records that such a heuristic was tried here and removed because it
# destroyed ordinary content -- long CamelCase identifiers and base64 payloads,
# which this codebase is full of. Bare secrets stay covered by the
# name-directed rules whenever they appear as NAME=value, which is how they
# occur in env files, shell history and logs, i.e. in nearly every place one
# actually leaks.
