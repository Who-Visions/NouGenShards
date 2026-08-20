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


def resolve_vault_root():
    """Vault dir: NOUGEN_ARXIV_VAULT_DIR -> config arxiv_vault_dir ->
    NOUGEN_VAULT_DIR -> config vault_dir -> WATCHTOWER_ROOT/vault.

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
    v, source = resolve("NOUGEN_ARXIV_VAULT_DIR", "arxiv_vault_dir", "")
    if v:
        return v, source
    v, source = resolve("NOUGEN_VAULT_DIR", "vault_dir", "")
    if v:
        return v, source
    root = os.environ.get("WATCHTOWER_ROOT") or os.path.expanduser("~/Watchtower")
    return os.path.join(root, "vault"), (
        "derived:WATCHTOWER_ROOT" if os.environ.get("WATCHTOWER_ROOT")
        else "derived:~/Watchtower")


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
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())
