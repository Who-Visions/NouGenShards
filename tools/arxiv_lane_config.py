"""Single source of truth for the arXiv lane's runtime configuration.

Rule 0.2 says every environment-, path-, count-, threshold-, or model-shaped
value resolves env -> config -> probe, with a constant only as a LOGGED
fallback. Before this module each tool in the lane carried its own copy of
`_resolve_vault_root()` and its own ad-hoc `os.environ.get(...)` casts, which is
how three copies silently drift apart — and a writer drifting from its monitor
is exactly the failure that makes a healthy lane report EMPTY forever.

Every resolver here returns the value AND where it came from, so a run can print
its own configuration instead of an operator guessing which of three layers won.
Call `describe()` (or any tool's --print-config) to see the whole resolved set.
"""
import json
import os

_CONFIG_CACHE = None


def _user_config():
    """~/.nougen/config.json, read once. Missing/broken file is not fatal."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        try:
            path = os.path.join(os.path.expanduser("~"), ".nougen", "config.json")
            with open(path, encoding="utf-8") as f:
                _CONFIG_CACHE = json.load(f)
        except Exception:
            _CONFIG_CACHE = {}
    return _CONFIG_CACHE


def resolve(env_name, config_key, fallback, cast=str):
    """env -> ~/.nougen/config.json -> fallback. Returns (value, source).

    `source` is the whole point: "fallback-constant" in a log is a prompt to go
    set the value properly, and it distinguishes "configured to X" from
    "defaulted to X" when a run misbehaves.
    """
    raw, source = os.environ.get(env_name), "env:" + env_name
    if raw in (None, ""):
        cfg = _user_config().get(config_key) if config_key else None
        if cfg not in (None, ""):
            raw, source = cfg, "config:" + str(config_key)
    if raw in (None, ""):
        raw, source = fallback, "fallback-constant"
    try:
        return cast(raw), source
    except (TypeError, ValueError):
        # A malformed override must not take the lane down, but it must be loud.
        return cast(fallback), source + "(bad-value->fallback)"


def resolve_value(env_name, config_key, fallback, cast=str):
    return resolve(env_name, config_key, fallback, cast)[0]


def resolve_list(env_name, config_key, fallback, sep=";"):
    """Split on `sep` (or comma), tolerating a JSON list in config.json."""
    raw, source = resolve(env_name, config_key, fallback)
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace(",", sep).split(sep) if p.strip()]
    else:
        parts = [str(p).strip() for p in raw if str(p).strip()]
    return parts, source


def resolve_vault_root(artifact_prefixes=None):
    """Vault dir: NOUGEN_ARXIV_VAULT_DIR -> config arxiv_vault_dir ->
    NOUGEN_VAULT_DIR -> config vault_dir -> WATCHTOWER_ROOT/vault.

    `artifact_prefixes` is what this caller's corpus LOOKS like, used to rank
    candidates by evidence (see below). Default: both of the lane's families.
    A caller that consumes only one should pass only that one -- the lane holds
    two artifact families side by side in the same directory, written by
    different tools on different date keys (daily docs key on SUBMISSION date,
    shards on ANNOUNCE date; never derive one from the other), and a vault
    holding only shards is the CORRECT vault for the shard lane. Ranking every
    caller against the daily-doc prefix alone would trade "wrong-but-real
    directory silently wins" for "right directory for THIS caller silently
    loses" -- a narrower failure, equally silent. Raised by node-a's
    arxiv-daily-scan lane, 2026-09-04, against node-a's live 85,298 docs +
    88,204 shards in one directory.

    The lane-specific override exists because the general vault config can
    legitimately point at the shard DB store while this lane's markdown corpus
    (79k+ daily docs) lives elsewhere — GM decision 2026-08-16 (option b of
    shard 17882): the arXiv lane gets its own vault knob rather than migrating
    the corpus or baking a machine path into the scheduled task.

    The final fallback is derived, never a baked absolute path: a hardcoded
    "C:\\Users\\<someone>\\..." silently writes to the wrong place on any other
    machine or account instead of failing loudly.
    """
    # Fallback is "" not None: resolve() casts the fallback through `cast`,
    # and str(None) is the truthy string "None" — which made this function
    # return a literal "None" vault dir (a cwd-relative folder!) whenever
    # neither env nor config was set, and left the derived fallback below dead.
    candidates = []
    v, source = resolve("NOUGEN_ARXIV_VAULT_DIR", "arxiv_vault_dir", "")
    if v:
        candidates.append((v, source))
    v, source = resolve("NOUGEN_VAULT_DIR", "vault_dir", "")
    if v:
        candidates.append((v, source))
    root = os.environ.get("WATCHTOWER_ROOT") or os.path.expanduser("~/Watchtower")
    # normpath: expanduser("~/Watchtower") yields "<home>/Watchtower" with a
    # FORWARD slash on Windows, so the joined path goes out with mixed
    # separators in every log line and warning that quotes it.
    candidates.append((os.path.normpath(os.path.join(root, "vault")), (
        "derived:WATCHTOWER_ROOT" if os.environ.get("WATCHTOWER_ROOT")
        else "derived:~/Watchtower")))

    # A CONFIGURED path is not a path that EXISTS, and an existing path is not a
    # path that holds this lane's CORPUS. Both halves have been measured:
    #
    #   node-c 2026-09-04 — NOUGEN_ARXIV_VAULT_DIR pinned a Watchtower path that
    #     does not exist on the machine at all. The chain returned it anyway,
    #     with a clean provenance string.
    #   node-a  2026-09-04 — the same pin names a Watchtower dir that DOES exist,
    #     with 300+ entries and zero arXiv daily docs, while the real corpus
    #     (85k docs) sits under the next candidate down.
    #
    # So an is_dir() gate alone is not enough: it would hand back node-a's
    # populated-but-wrong directory and merely sound more confident about it.
    # Rank candidates by evidence instead, and keep chain order within a rank:
    #
    #   0  live directory, lane artifacts found       <- take this
    #   1  live directory, probe inconclusive (capped)
    #   2  live directory, confirmed zero artifacts
    #   -  not a directory: never selectable
    #
    # Rank 1 exists so a huge corpus whose first N entries happen not to match
    # is not demoted below a confirmed-empty directory. Absence of proof is not
    # proof of absence, and this function must not invent either.
    if artifact_prefixes is None:
        artifact_prefixes = [
            resolve("NOUGEN_ARXIV_DOC_PREFIX", "arxiv_doc_prefix",
                    "arxiv_cs_AI_")[0],
            resolve("NOUGEN_ARXIV_SHARD_PREFIX", "arxiv_shard_prefix",
                    "intelligence_shard_arxiv_")[0],
        ]
    elif isinstance(artifact_prefixes, str):
        artifact_prefixes = [artifact_prefixes]
    artifact_prefixes = [p for p in artifact_prefixes if p]

    ranked, dead = [], []
    for value, src in candidates:
        rank, note = _probe_candidate(value, artifact_prefixes)
        if rank is None:
            dead.append(src)
            continue
        ranked.append((rank, len(ranked), value, src, note))

    if ranked:
        # key=r[:2], not a bare min(ranked): `index` is len(ranked) at append
        # time and therefore unique, so (rank, index) alone always breaks the
        # tie -- but a bare min() would fall through to comparing `value` and
        # then `note` (a list) if that ever stopped being true, which is a
        # TypeError or a meaningless ordering waiting for a refactor to trip
        # it. Pinned by test_min_never_compares_past_rank_and_index. Raised by
        # an adversarial review panel, 2026-09-04.
        rank, _, value, src, note = min(ranked, key=lambda r: r[:2])
        detail = list(note)
        if dead:
            detail.append("skipped dead: " + ", ".join(dead))
        # Name every live candidate this one outranked, so a wrong-but-real
        # layer losing is visible rather than merely absent from the output.
        outranked = [s for r, _, _, s, _ in ranked if (r, s) != (rank, src)]
        if outranked and rank == 0:
            detail.append("outranked: " + ", ".join(outranked))
        if detail:
            src += " (" + "; ".join(detail) + ")"
        return value, src

    # Nothing on the chain is even a directory. Return the highest-priority
    # CONFIGURED value rather than a lower one: a first run that legitimately
    # creates its vault must still honour explicit configuration. But say
    # plainly that it is not there, so "0 documents" reads as a broken path
    # instead of a quiet lane.
    value, src = candidates[0]
    return value, src + " (MISSING: no candidate directory exists)"


#: How many directory entries a corpus probe will look at before giving up.
#: Bounded on purpose: the real store has ~85k files and globbing it has been
#: measured at 3-30s, which is far past any caller's budget. The probe stops at
#: the first match, so a healthy vault costs almost nothing; only a directory
#: with no artifacts near the top pays the full cap.
_PROBE_ENTRY_CAP = int(os.environ.get("NOUGEN_ARXIV_PROBE_CAP", "4000"))


def _probe_candidate(path, artifact_prefixes):
    """Rank one candidate by evidence. Returns (rank, notes) or (None, notes).

    rank 0 = artifacts found, 1 = inconclusive, 2 = confirmed empty of them,
    None = not a usable directory. A hit on ANY prefix is a hit -- and the note
    says WHICH family was found, because "this vault has shards but no daily
    docs" is a materially different fact from "this vault has the corpus", and a
    caller reading the provenance should be able to tell them apart.
    """
    try:
        if not os.path.isdir(path):
            return None, []
    except OSError:
        # An unreachable network path (a dead SMB mount has been measured on
        # this fleet) is dead for our purposes, not a crash.
        return None, []
    wanted = tuple(artifact_prefixes)
    if not wanted:
        # No predicate to rank on. Every live directory is equally unproven --
        # say so rather than silently ranking them all "empty".
        return 1, ["corpus probe skipped: no artifact prefix given"]
    # Case-insensitive: NTFS is case-preserving but case-INsensitive for
    # lookups, and this is a plain string compare that does not know that. A
    # writer that ever emits mixed case (a rename, a sync tool, a manual copy)
    # would otherwise probe as empty on a directory that plainly holds the
    # corpus. Raised independently by two routes in an adversarial review
    # panel, 2026-09-04. Cheap and has no real downside: the prefixes are
    # namespace tags, not case-sensitive-by-design identifiers.
    wanted_lower = tuple(p.lower() for p in wanted)
    try:
        seen = 0
        with os.scandir(path) as entries:
            for entry in entries:
                name_lower = entry.name.lower()
                for prefix, prefix_lower in zip(wanted, wanted_lower):
                    if name_lower.startswith(prefix_lower):
                        return 0, ["artifacts: %s*" % prefix]
                seen += 1
                if seen >= _PROBE_ENTRY_CAP:
                    return 1, ["corpus probe inconclusive: none of %s in first %d entries"
                               % ("/".join(wanted), _PROBE_ENTRY_CAP)]
    except OSError:
        # Readable enough to be a directory, not readable enough to enumerate.
        # Do not demote it on that basis; say so and let it win on chain order.
        return 1, ["corpus probe failed: directory not enumerable"]
    return 2, ["no %s artifacts present" % "/".join(p + "*" for p in wanted)]


# --- lane-wide names ---------------------------------------------------------
# Artifact prefixes are the lane's NAMESPACE, not a category claim. The writers
# (arxiv_gap_backfill, arxiv_rss_scanner) and the monitor (lane_freshness) must
# resolve these from the SAME place or gap detection and freshness silently
# disagree about which files count.
DOC_PREFIX, DOC_PREFIX_SRC = resolve(
    "NOUGEN_ARXIV_DOC_PREFIX", "arxiv_doc_prefix", "arxiv_cs_AI_")
SHARD_PREFIX, SHARD_PREFIX_SRC = resolve(
    "NOUGEN_ARXIV_SHARD_PREFIX", "arxiv_shard_prefix", "intelligence_shard_arxiv_")
TOPIC_PREFIX, TOPIC_PREFIX_SRC = resolve(
    "NOUGEN_ARXIV_TOPIC_PREFIX", "arxiv_topic_prefix", "arxiv_cs_ai_")

# Shard-store layout. The DB filename pattern and table name are structural, but
# a tool that greps the store should still not bake them into a literal.
SHARD_DB_GLOB, SHARD_DB_GLOB_SRC = resolve(
    "NOUGEN_SHARD_DB_GLOB", "shard_db_glob", "nougen_shards_*.db")
SHARD_TABLE, SHARD_TABLE_SRC = resolve(
    "NOUGEN_SHARD_TABLE", "shard_table", "shards")

CATEGORIES, CATEGORIES_SRC = resolve_list(
    "NOUGEN_ARXIV_CATEGORIES", "arxiv_categories", "cs.AI,cs.CL,cs.LG,cs.CV")


def describe(extra=None):
    """Every resolved value with its provenance, for --print-config."""
    vault, vault_src = resolve_vault_root()
    rows = [
        ("vault_dir", vault, vault_src),
        ("categories", ",".join(CATEGORIES), CATEGORIES_SRC),
        ("doc_prefix", DOC_PREFIX, DOC_PREFIX_SRC),
        ("shard_prefix", SHARD_PREFIX, SHARD_PREFIX_SRC),
        ("topic_prefix", TOPIC_PREFIX, TOPIC_PREFIX_SRC),
        ("shard_db_glob", SHARD_DB_GLOB, SHARD_DB_GLOB_SRC),
        ("shard_table", SHARD_TABLE, SHARD_TABLE_SRC),
    ]
    rows.extend(extra or [])
    width = max(len(r[0]) for r in rows)
    lines = ["=== arXiv lane resolved config ==="]
    for name, value, source in rows:
        lines.append("  {:<{w}}  {:<44}  [{}]".format(name, str(value), source, w=width))
    # Per-row provenance already says which values fell back, and for names like
    # the artifact prefixes the constant IS the intended state — a blanket
    # "still on fallback" warning would cry wolf on correct configuration.
    # Only a value that was overridden BADLY deserves to be called out.
    bad = [r[0] for r in rows if "bad-value" in str(r[2])]
    if bad:
        lines.append("  WARNING: malformed override ignored for: " + ", ".join(bad))
    # A resolved path that is not on disk is the exact failure this module
    # exists to prevent, so it gets its own line rather than hiding inside the
    # source column of one row.
    missing = [r[0] for r in rows if "MISSING" in str(r[2])]
    if missing:
        lines.append("  WARNING: resolved path does not exist for: " + ", ".join(missing)
                     + " - the lane reads an empty corpus until this is fixed")
    # A directory that exists but holds none of this lane's artifacts is the
    # node-a shape of the same failure: it looks configured, it looks alive, and
    # it reads empty. It only reaches here when NO candidate had artifacts, so
    # it is worth a warning of its own rather than a silent selection.
    barren = [r[0] for r in rows if "artifacts present" in str(r[2])]
    if barren:
        lines.append("  WARNING: resolved path holds no lane artifacts for: "
                     + ", ".join(barren)
                     + " - it exists, but the corpus is somewhere else")
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())
