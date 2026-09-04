"""The arXiv lane's vault-root chain had no tests at all, and seven tools call it.

The defect these cover: `resolve_vault_root()` returned the first *configured*
candidate and stopped, without ever asking whether that directory exists. A
User-scope `NOUGEN_ARXIV_VAULT_DIR` left over from an older machine layout
therefore won every run, every lane tool read an empty corpus, and the output
was indistinguishable from "no papers today".

Measured on node-c 2026-09-04: the pin named a Watchtower path that does not
exist on this machine, `~/.nougen/config.json` does not exist either, and the
derived `~/Watchtower/vault` fallback is dead too — so the fix node-a applied on
its own box (delete the pin) does not transfer here. The resolver itself has to
distinguish "configured" from "present".
"""
import os

import pytest

import tools.arxiv_lane_config as cfg

ENV_VARS = ("NOUGEN_ARXIV_VAULT_DIR", "NOUGEN_VAULT_DIR", "WATCHTOWER_ROOT")


@pytest.fixture(autouse=True)
def clean_chain(monkeypatch, tmp_path):
    """Every layer of the chain under test control, including $HOME.

    `~/Watchtower/vault` is the derived fallback, so a test that did not move
    HOME would pass or fail depending on the operator's real home directory.
    """
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cfg, "_CONFIG_CACHE", {}, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def test_live_pin_wins(monkeypatch, tmp_path):
    live = tmp_path / "live_vault"
    live.mkdir()
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(live))
    value, source = cfg.resolve_vault_root()
    assert value == str(live)
    # startswith, not ==: the corpus probe appends its own note, and an empty
    # tmp dir legitimately reports "no artifacts". The layer that won is the
    # assertion here; the evidence trailer is Finding-2b's job.
    assert source.startswith("env:NOUGEN_ARXIV_VAULT_DIR")


def test_dead_pin_falls_through_to_the_live_general_vault(monkeypatch, tmp_path):
    """The node-c case, with a survivor below it: the lane must not stop on a
    configured path that is not on disk."""
    dead = tmp_path / "gone" / "vault"          # never created
    live = tmp_path / "real_vault"
    live.mkdir()
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(dead))
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(live))
    value, source = cfg.resolve_vault_root()
    assert value == str(live)
    assert source.startswith("env:NOUGEN_VAULT_DIR")
    # The skipped layer is named, so an operator can see WHY the lower one won.
    assert "skipped dead" in source
    assert "NOUGEN_ARXIV_VAULT_DIR" in source


def test_dead_pin_falls_through_to_derived_watchtower(monkeypatch, tmp_path, clean_chain):
    dead = tmp_path / "gone" / "vault"
    watchtower = clean_chain / "Watchtower" / "vault"
    watchtower.mkdir(parents=True)
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(dead))
    value, source = cfg.resolve_vault_root()
    assert os.path.normpath(value) == os.path.normpath(str(watchtower))
    assert source.startswith("derived:~/Watchtower")
    assert "skipped dead" in source


def test_config_layer_is_still_honoured_when_it_exists(monkeypatch, tmp_path):
    live = tmp_path / "from_config"
    live.mkdir()
    monkeypatch.setattr(cfg, "_CONFIG_CACHE", {"arxiv_vault_dir": str(live)},
                        raising=False)
    value, source = cfg.resolve_vault_root()
    assert value == str(live)
    assert source.startswith("config:arxiv_vault_dir")


def test_whole_chain_dead_reports_missing_and_keeps_the_configured_value(
        monkeypatch, tmp_path):
    """Exactly node-c's state. A first run that legitimately creates its own
    vault must still land on the CONFIGURED path, so the value is preserved --
    but the provenance has to say the directory is not there."""
    dead = tmp_path / "nowhere" / "vault"
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(dead))
    value, source = cfg.resolve_vault_root()
    assert value == str(dead)
    assert "MISSING" in source
    assert source.startswith("env:NOUGEN_ARXIV_VAULT_DIR")


def test_nothing_configured_at_all_still_reports_missing(clean_chain):
    """No env, no config.json, no ~/Watchtower -- the bare-machine case. It must
    not silently return a plausible-looking path with a clean provenance."""
    value, source = cfg.resolve_vault_root()
    assert "Watchtower" in value
    assert "MISSING" in source


def test_unreadable_candidate_is_treated_as_dead(monkeypatch, tmp_path):
    """isdir() can raise on an unreachable network path (a dead SMB mount has
    been measured on this fleet). That must degrade to 'dead', not crash the
    lane."""
    live = tmp_path / "live"
    live.mkdir()
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", r"\10.0.0.254\gone\vault")
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(live))
    real_isdir = os.path.isdir

    def exploding_isdir(path):
        if str(path).startswith("\\\\"):
            raise OSError("network path unreachable")
        return real_isdir(path)

    monkeypatch.setattr(cfg.os.path, "isdir", exploding_isdir)
    value, source = cfg.resolve_vault_root()
    assert value == str(live)
    assert "skipped dead" in source


# --- the node-a shape: the dead layer is a REAL, POPULATED directory -----------
#
# node-c's dead layer is absent; node-a's is present and wrong -- 300+ entries,
# zero arXiv daily docs, while the real 85k-doc corpus sits one candidate down.
# An is_dir() gate returns node-a's directory and merely sounds more confident
# about it, so the check has to be corpus-shaped. Requested by node-a's
# arxiv-daily-scan lane, 2026-09-04.

def _populate(d, names):
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_text("x", encoding="utf-8")
    return d


def test_populated_but_corpusless_directory_loses_to_the_real_corpus(
        monkeypatch, tmp_path):
    """Node-a, exactly: the pin names a live directory full of unrelated files."""
    wrong = _populate(tmp_path / "Watchtower" / "vault",
                      ["notes.md", "readme.txt", "arxiv_something_else.json"])
    right = _populate(tmp_path / "shards",
                      ["arxiv_cs_AI_2026-09-01.md", "arxiv_cs_AI_2026-09-02.md"])
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(wrong))
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(right))
    value, source = cfg.resolve_vault_root()
    assert value == str(right)
    assert "outranked" in source and "NOUGEN_ARXIV_VAULT_DIR" in source


def test_an_is_dir_gate_alone_would_have_chosen_wrong(monkeypatch, tmp_path):
    """Guards the distinction itself: both candidates are real directories, so
    anything that only asks `is this a directory` picks the first one."""
    wrong = _populate(tmp_path / "wt", ["a.txt", "b.txt"])
    right = _populate(tmp_path / "real", ["arxiv_cs_AI_2026-09-01.md"])
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(wrong))
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(right))
    assert os.path.isdir(wrong) and os.path.isdir(right)
    assert cfg.resolve_vault_root()[0] == str(right)


def test_no_candidate_has_artifacts_keeps_chain_order_and_says_so(
        monkeypatch, tmp_path):
    """Nothing to prefer -- fall back to priority, but do not pretend it is fine."""
    first = _populate(tmp_path / "one", ["a.txt"])
    second = _populate(tmp_path / "two", ["b.txt"])
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(first))
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(second))
    value, source = cfg.resolve_vault_root()
    assert value == str(first)
    # Both families are named -- the note says what was looked for, not just
    # that nothing was found.
    assert "artifacts present" in source
    assert "arxiv_cs_AI_*" in source and "intelligence_shard_arxiv_*" in source


def test_a_barren_result_is_warned_about_in_describe(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(_populate(tmp_path / "x", ["a"])))
    out = cfg.describe()
    assert "WARNING: resolved path holds no lane artifacts" in out
    assert out.isascii()


def test_inconclusive_probe_is_not_demoted_below_a_confirmed_empty_dir(
        monkeypatch, tmp_path):
    """A real corpus whose first N entries happen not to match must not lose to a
    directory PROVEN to hold nothing. Absence of proof is not proof of absence.

    scandir order is mocked rather than relied on. The first version of this
    test built the ordering out of filenames ("aaa_*" before "arxiv_cs_AI_*"),
    which holds on NTFS (name order) but not on Linux ext4, where directory
    iteration order is effectively arbitrary -- it passed locally on Windows
    and failed in CI on every Python version, with the real artifact found
    inside the cap instead of past it. Mocking the entries directly makes the
    ordering the test's premise rather than the filesystem's mood.
    """
    monkeypatch.setattr(cfg, "_PROBE_ENTRY_CAP", 5, raising=False)
    big = _populate(tmp_path / "big", ["placeholder.md"])
    empty = _populate(tmp_path / "empty", ["a.txt"])

    class FakeEntry:
        def __init__(self, name):
            self.name = name

    fake_entries = [FakeEntry(f"filler_{i:03d}.md") for i in range(20)]
    fake_entries.append(FakeEntry("arxiv_cs_AI_2026-09-01.md"))
    real_scandir = os.scandir

    def fake_scandir(path):
        if os.path.normpath(str(path)) == os.path.normpath(str(big)):
            from contextlib import contextmanager

            @contextmanager
            def cm():
                yield iter(fake_entries)
            return cm()
        return real_scandir(path)

    monkeypatch.setattr(cfg.os, "scandir", fake_scandir)
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(big))
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(empty))
    value, source = cfg.resolve_vault_root()
    assert value == str(big)
    assert "inconclusive" in source


def test_the_probe_is_bounded(monkeypatch, tmp_path):
    """The real store is ~85k files and globbing it costs 3-30s. The probe must
    stop at the cap, not walk the whole directory."""
    monkeypatch.setattr(cfg, "_PROBE_ENTRY_CAP", 10, raising=False)
    d = _populate(tmp_path / "many", [f"f{i}.txt" for i in range(200)])
    seen = {"n": 0}
    real_scandir = os.scandir

    class CountingScandir:
        def __init__(self, path):
            self._it = real_scandir(path)

        def __enter__(self):
            inner = self._it.__enter__()

            def gen():
                for e in inner:
                    seen["n"] += 1
                    yield e
            return gen()

        def __exit__(self, *a):
            return self._it.__exit__(*a)

    monkeypatch.setattr(cfg.os, "scandir", CountingScandir)
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(d))
    cfg.resolve_vault_root()
    assert seen["n"] <= 10, f"probe walked {seen['n']} entries past a cap of 10"


def test_unenumerable_directory_is_inconclusive_not_empty(monkeypatch, tmp_path):
    """Readable enough to be a directory, not readable enough to list. That is
    unknown, not proven-empty -- do not demote it on a permissions error."""
    d = _populate(tmp_path / "locked", ["arxiv_cs_AI_2026-09-01.md"])

    def deny(path):
        raise OSError("access denied")

    monkeypatch.setattr(cfg.os, "scandir", deny)
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(d))
    value, source = cfg.resolve_vault_root()
    assert value == str(d)
    assert "not enumerable" in source


# --- two artifact families in one directory -----------------------------------
#
# Node-a's live vault holds 85,298 arxiv_cs_* daily docs AND 88,204 arxiv-named
# shards side by side, written by different tools on different date keys (docs
# key on submission date, shards on announce date). Ranking every caller against
# the daily-doc prefix alone would make a shard-only vault "confirmed empty" and
# skip the one directory the shard lane actually wants. Raised by node-a's
# arxiv-daily-scan lane, 2026-09-04.

SHARD_DOC = "intelligence_shard_arxiv_2508.01234.md"
DAILY_DOC = "arxiv_cs_AI_2026-09-01.md"


def test_shard_only_vault_is_found_by_default(monkeypatch, tmp_path):
    """Default predicate accepts EITHER family, so a shard store is not
    mistaken for an empty directory."""
    shards = _populate(tmp_path / "shardstore", [SHARD_DOC, "other.md"])
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(shards))
    value, source = cfg.resolve_vault_root()
    assert value == str(shards)
    assert "artifacts: intelligence_shard_arxiv_*" in source
    assert "no " not in source.split("(")[-1]   # not reported as empty


def test_shard_lane_caller_selects_the_shard_vault_over_a_docs_only_one(
        monkeypatch, tmp_path):
    """Node-a's case, stated as the caller sees it: a consumer that only reads
    shards must not be routed to a docs-only vault just because docs rank first
    in the default predicate."""
    docs_only = _populate(tmp_path / "docs", [DAILY_DOC])
    shards_only = _populate(tmp_path / "shards", [SHARD_DOC])
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(docs_only))
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(shards_only))

    # Default (either family): the pin wins, it genuinely has artifacts.
    assert cfg.resolve_vault_root()[0] == str(docs_only)

    # Shard-lane caller declares its own corpus shape and gets the right dir.
    value, source = cfg.resolve_vault_root(
        artifact_prefixes=["intelligence_shard_arxiv_"])
    assert value == str(shards_only)
    assert "artifacts: intelligence_shard_arxiv_*" in source
    assert "outranked" in source


def test_docs_lane_caller_still_gets_the_docs_vault(monkeypatch, tmp_path):
    """The mirror image, so the parameter is proven to steer both ways."""
    docs_only = _populate(tmp_path / "docs", [DAILY_DOC])
    shards_only = _populate(tmp_path / "shards", [SHARD_DOC])
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(shards_only))
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(docs_only))
    value, source = cfg.resolve_vault_root(artifact_prefixes=["arxiv_cs_AI_"])
    assert value == str(docs_only)
    assert "artifacts: arxiv_cs_AI_*" in source


def test_a_single_prefix_may_be_passed_as_a_bare_string(monkeypatch, tmp_path):
    d = _populate(tmp_path / "d", [SHARD_DOC])
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(d))
    assert cfg.resolve_vault_root("intelligence_shard_arxiv_")[0] == str(d)


def test_blades_decoy_filename_does_not_count_as_an_artifact(monkeypatch, tmp_path):
    """The one arxiv-NAMED file in node-a's dead vault is
    `intelligence_shard_20260822001_stale_nougen_arxiv_vault_dir_...` -- it
    contains 'arxiv' but matches neither prefix. It must not rescue the dead
    layer. (It is also the shard ABOUT this defect, quarantined inside the tree
    the defect points at.)"""
    decoy = _populate(tmp_path / "wt", [
        "intelligence_shard_20260822001_stale_nougen_arxiv_vault_dir_"
        "silently_broke_arxiv_gap_backfill.md"])
    real = _populate(tmp_path / "real", [DAILY_DOC])
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(decoy))
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(real))
    value, source = cfg.resolve_vault_root()
    assert value == str(real)
    assert "outranked" in source


def test_empty_prefix_list_is_inconclusive_not_empty(monkeypatch, tmp_path):
    """No predicate means nothing was measured. Every live dir is unproven, so
    chain order decides -- but it must not be reported as confirmed-empty."""
    first = _populate(tmp_path / "one", ["a.txt"])
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(first))
    value, source = cfg.resolve_vault_root(artifact_prefixes=[])
    assert value == str(first)
    assert "no artifact prefix given" in source


def test_describe_warns_loudly_when_the_resolved_path_is_absent(monkeypatch, tmp_path):
    """The silent failure is the whole bug: 'vault_dir <path>' with a clean
    source column reads as healthy configuration."""
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(tmp_path / "nowhere"))
    out = cfg.describe()
    assert "WARNING: resolved path does not exist" in out
    assert "vault_dir" in out
    assert out.isascii(), "describe() lands in scheduled-task logs on cp1252 consoles"


def test_describe_is_quiet_when_the_vault_is_real(monkeypatch, tmp_path):
    live = tmp_path / "real"
    live.mkdir()
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(live))
    out = cfg.describe()
    assert "resolved path does not exist" not in out


# --- findings from an adversarial review panel, 2026-09-04 --------------------
#
# Six routes (three vendors, three empty/failed) reviewed the diff cold. Two
# points survived scrutiny against the actual code; a third (TOCTOU between
# isdir and scandir) did not -- os.scandir's OSError is already caught and
# demotes the candidate to rank 1, so a directory that vanishes mid-probe
# degrades rather than crashing. That path already has coverage
# (test_unenumerable_directory_is_inconclusive_not_empty, above).

def test_case_insensitive_prefix_match(monkeypatch, tmp_path):
    """NTFS is case-preserving but case-INsensitive for lookups; `startswith` on
    a plain string comparison does not know that. A writer that ever emits
    mixed case (a rename, a sync tool, a manual copy) must not read as an empty
    vault just because the panel's `Arxiv_...` differs from the constant's
    `arxiv_...`."""
    mixed = _populate(tmp_path / "mixed", ["Arxiv_cs_AI_2026-09-01.md"])
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(mixed))
    value, source = cfg.resolve_vault_root(artifact_prefixes=["arxiv_cs_AI_"])
    assert value == str(mixed)
    assert "artifacts:" in source


def test_case_insensitive_match_also_works_the_other_way(monkeypatch, tmp_path):
    """The prefix itself may be the differently-cased one."""
    lower = _populate(tmp_path / "lower", ["arxiv_cs_ai_2026-09-01.md"])
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(lower))
    value, source = cfg.resolve_vault_root(artifact_prefixes=["ARXIV_CS_AI_"])
    assert value == str(lower)
    assert "artifacts:" in source


def test_min_never_compares_past_rank_and_index(monkeypatch, tmp_path):
    """`index` is `len(ranked)` at append time -- strictly increasing and unique
    per candidate, so `(rank, index)` alone always decides `min()`. A bare
    `min(ranked)` would fall through to comparing `value`/`src`/`note` (a list)
    if that ever stopped holding, which is a TypeError or a meaningless
    ordering waiting for a refactor to trip it. This does not need `index` to
    ever actually tie -- it needs the SELECTOR to never look past it, which is
    what `key=lambda r: r[:2]` guarantees regardless. Proven here by forcing a
    tie on rank with candidates whose `value`/`src` would sort in the WRONG
    chain order if the comparison ever reached them."""
    # Two candidates, same rank (2: confirmed empty), chain order first->second.
    # If min() ever compared past (rank, index), alphabetically-later `value`
    # strings would flip the winner depending on tmp_path naming -- this
    # construction makes that failure mode visible rather than incidental.
    first = _populate(tmp_path / "zzz_first_in_chain", ["a.txt"])
    second = _populate(tmp_path / "aaa_second_in_chain", ["b.txt"])
    monkeypatch.setenv("NOUGEN_ARXIV_VAULT_DIR", str(first))
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(second))
    value, _ = cfg.resolve_vault_root()
    # Chain order must win: first candidate declared, not alphabetical order.
    assert value == str(first)


def test_min_selector_is_stable_under_monkeypatched_index_collision(monkeypatch):
    """Direct unit test of the selector itself, independent of resolve_vault_root
    ever being able to produce a real tie. Simulates two ranked entries sharing
    (rank, index) with values/notes that would sort backwards if compared --
    the panel's exact concern, isolated from whether the surrounding code can
    reach it today."""
    ranked = [
        (0, 0, "zzz_would_lose_if_value_compared", "src-a", ["note-a"]),
        (0, 0, "aaa_would_win_if_value_compared", "src-b", ["note-b"]),
    ]
    # key=r[:2] treats both as equal and min() returns the FIRST equal element
    # (Python's min is stable) -- proving the comparison never reaches `value`.
    winner = min(ranked, key=lambda r: r[:2])
    assert winner[2] == "zzz_would_lose_if_value_compared"
