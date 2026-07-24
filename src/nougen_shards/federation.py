"""Federated Retrieval Engine. Merges local substrate, sibling vaults, external DBs, and cloud nodes."""
import logging
import os
import threading
from pathlib import Path
from . import core
from . import provenance
from .connectors.sql import query_external_dbs
from .connectors.cloud import query_cloud_shards
from . import keymaker
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Auto-embed queries so the vector lane works for callers that don't compute an
# embedding themselves (the MCP recall path passed None, leaving semantic
# scoring, the ANN index, and MMR similarity dead for agents). Must be the same
# model family the backfill wrote with, or the vector space won't line up.
AUTO_EMBED = os.environ.get("NOUGEN_AUTO_EMBED", "1") == "1"
EMBED_MODEL = os.environ.get("NOUGEN_EMBED_MODEL", "nomic-embed-text")
_EMBED_CLIENT = None  # process-cached; False once probed dead


def _auto_query_embedding(query: str) -> Optional[List[float]]:
    """Best-effort local embedding for the query. Never raises; None on any miss."""
    global _EMBED_CLIENT  # pylint: disable=global-statement
    if not AUTO_EMBED:
        return None
    if _EMBED_CLIENT is None:
        try:
            from .models_client import OllamaClient  # pylint: disable=import-outside-toplevel
            client = OllamaClient()
            _EMBED_CLIENT = client if client.is_alive() else False
        except Exception:  # noqa: BLE001 - degrade to keyword-only retrieval
            _EMBED_CLIENT = False
    if not _EMBED_CLIENT:
        return None
    try:
        vec = _EMBED_CLIENT.embed(EMBED_MODEL, query)
        return vec or None
    except Exception:  # noqa: BLE001
        return None


# --- Sibling-vault lane (Rule 0.2: env -> probe, constants as logged fallback) ---
#
# The SQL connector deliberately refuses sqlite:/// URIs (local-file/SSRF
# hardening), so a sibling NouGen vault cannot ride the external-DB lane without
# weakening that control. Sibling vaults already speak THIS engine's schema, so
# they get a native lane instead: core is briefly repointed at the sibling grid
# and the full retrieval stack (FTS5/BM25 + vector + RRF) runs against it in
# place. Nothing is copied, merged, or migrated -- each store stays where it is,
# and secondary stores are read under a read-only guard.
#
#   NOUGEN_VAULT_DIR             -> PRIMARY store (curated Memory Vault)
#   NOUGEN_SECONDARY_VAULT_DIRS  -> os.pathsep-separated SECONDARY stores,
#                                   each optionally "label=path"
_STORE_SEP = os.environ.get("NOUGEN_VAULT_PATH_SEP", os.pathsep)

# Cross-store RRF ties are broken by the utility prior, so a bulk-ingested shard
# with an inflated utility_score can outrank another store's exact-term match.
# Measured 2026-07-24: query "logfire" (0 lexical hits in the curated vault, 198
# in the sibling store) surfaced three unrelated high-utility arXiv shards from
# the vault's semantic lane and buried every exact match from the sibling. When
# ANY store produced real lexical evidence, semantic-only near-neighbours must
# not outrank it. Purely semantic queries are unaffected (guard below).
LEXICAL_FIRST = os.environ.get("NOUGEN_FED_LEXICAL_FIRST", "1") == "1"


def _has_lexical_evidence(item: dict) -> bool:
    """True when the hit came through an FTS/BM25 (or LIKE) lane, not vectors only."""
    return item.get("bm25_score") is not None

# core.GLOBAL_DIR is a module global read by get_db_path(); swapping it is only
# safe if every store query serialises, so primary and secondary share one lock.
_VAULT_LOCK = threading.RLock()


def _store_label(path) -> str:
    """Readable store name. A dotted dir ('.vault') takes its parent's name."""
    p = Path(path)
    if p.name.startswith(".") and p.parent.name:
        return p.parent.name
    return p.name or str(p)


def primary_store_label() -> str:
    return os.environ.get("NOUGEN_PRIMARY_STORE_LABEL") or _store_label(core.GLOBAL_DIR)


def _parse_store_entry(entry: str) -> Optional[Tuple[str, Path]]:
    """Parse 'path' or 'label=path'. Only a separator-free prefix counts as a label."""
    entry = entry.strip().strip('"').strip("'")
    if not entry:
        return None
    label = None
    head, sep, tail = entry.partition("=")
    if sep and tail.strip() and not any(c in head for c in "\\/:"):
        label, entry = head.strip(), tail.strip()
    path = Path(os.path.expandvars(os.path.expanduser(entry)))
    return (label or _store_label(path), path)


def secondary_stores() -> List[Tuple[str, Path]]:
    """Resolve SECONDARY stores from env, probing each before trusting it (Rule 0.2)."""
    raw = os.environ.get("NOUGEN_SECONDARY_VAULT_DIRS", "").strip()
    if not raw:
        return []
    try:
        primary_key = str(Path(core.GLOBAL_DIR).resolve()).lower()
    except OSError:
        primary_key = str(core.GLOBAL_DIR).lower()

    stores, seen = [], set()
    for entry in raw.split(_STORE_SEP):
        parsed = _parse_store_entry(entry)
        if not parsed:
            continue
        label, path = parsed
        try:
            key = str(path.resolve()).lower()
        except OSError:
            key = str(path).lower()
        if key == primary_key or key in seen:
            continue  # never double-count the primary store
        if not path.is_dir():
            logger.warning("secondary vault skipped (not a directory): %s -> %s", label, path)
            continue
        seen.add(key)
        stores.append((label, path))
    return stores


def _tag_store(results: list, label: str, vault_dir, is_primary: bool) -> list:
    """Stamp provenance so every hit says which store it came from."""
    for item in results:
        item["_store"] = label
        item["_store_dir"] = str(vault_dir)
        item["_store_primary"] = is_primary
        if not is_primary:
            idx = item.get("_db_index")
            # Namespace the grid index for non-primary hits. A bare int would let
            # a follow-up shard_get/mark_utility resolve this id against the
            # PRIMARY grid and silently return/modify a different shard.
            if idx is not None and not isinstance(idx, str):
                item["_db_index"] = f"{label}:{idx}"
    return results


def _retrieve_from_store(label: str, vault_dir, query: str, limit: int,
                         query_embedding, domain_key, is_primary: bool) -> list:
    """Run the full local retrieval stack against one store, then restore state."""
    with _VAULT_LOCK:
        prev_dir, prev_ro = core.GLOBAL_DIR, core.VAULT_READONLY
        try:
            core.GLOBAL_DIR = Path(vault_dir)
            core.VAULT_READONLY = not is_primary
            results = core.retrieve(query, limit=limit,
                                    query_embedding=query_embedding, domain_key=domain_key)
        finally:
            core.GLOBAL_DIR, core.VAULT_READONLY = prev_dir, prev_ro
    return _tag_store(results, label, vault_dir, is_primary)


def federated_retrieve(query: str, limit: int = 3, query_embedding: Optional[List[float]] = None,
                       domain_key: Optional[str] = None) -> list:
    """
    Module 8: Combine Compatible Systems.
    Polls the primary Shard substrate, secondary sibling vaults, external DBs,
    and remote cloud nodes.
    """
    if query_embedding is None:
        query_embedding = _auto_query_embedding(query)

    # 1. PRIMARY store (weighted relevance blend)
    local_results = _retrieve_from_store(primary_store_label(), core.GLOBAL_DIR, query,
                                         limit, query_embedding, domain_key, True)

    # 1b. SECONDARY sibling vaults, read in place and read-only. One unreadable
    # sibling must never take down recall from the primary store.
    secondary_lanes = []
    for label, path in secondary_stores():
        try:
            secondary_lanes.append(
                _retrieve_from_store(label, path, query, limit,
                                     query_embedding, domain_key, False))
        except Exception as exc:  # noqa: BLE001 - degrade, don't crash federation
            logger.warning("secondary vault skipped (federation continues) %s: %s: %s",
                           label, type(exc).__name__, exc)

    # 2. Get Configs from Keymaker
    external_configs = keymaker.list_external_dbs()
    cloud_configs = keymaker.list_cloud_nodes()

    # 3. Query External DBs if configured.
    # Remote sources must never abort federation: a raising external/cloud
    # source is logged and skipped so local_results always survive.
    # (Module 10: Graceful Degradation)
    external_results = []
    if external_configs:
        try:
            external_results = query_external_dbs(query, external_configs, limit=limit)
        except Exception as exc:  # noqa: BLE001 - degrade, don't crash federation
            logger.warning("external DBs skipped (federation continues): %s: %s",
                           type(exc).__name__, exc)
            external_results = []

    # 4. Query Cloud Nodes if configured
    cloud_results = []
    if cloud_configs:
        try:
            cloud_results = query_cloud_shards(query, cloud_configs, limit=limit)
        except Exception as exc:  # noqa: BLE001 - degrade, don't crash federation
            logger.warning("cloud nodes skipped (federation continues): %s: %s",
                           type(exc).__name__, exc)
            cloud_results = []

    # 5. Merge and re-rank via Reciprocal Rank Fusion (RRF)
    # (Module 21: Orchestrate Convergence)
    rrf_k = int(os.environ.get("NOUGEN_RRF_K", "60"))
    # PRIMARY first: RRF dedups by file_hash, and the first lane to present a
    # given hash owns the merged record's provenance — so a shard that exists in
    # both stores is attributed to the curated vault, not to a transcript import.
    combined = core.reciprocal_rank_fusion(
        [local_results, *secondary_lanes, external_results, cloud_results], k=rrf_k)

    # Keep lexically-grounded hits ahead of semantic-only ones, but only when
    # such evidence exists at all -- a purely semantic query keeps RRF order.
    # sort() is stable, so relative RRF ranking survives inside each group.
    if LEXICAL_FIRST and any(_has_lexical_evidence(i) for i in combined):
        combined.sort(key=lambda i: 0 if _has_lexical_evidence(i) else 1)

    # LEXICAL_FIRST is RETAINED, not superseded. It and the provenance tier fix
    # two different axes and compose cleanly:
    #   * LEXICAL_FIRST  -- evidence TYPE: lexical hits ahead of semantic-only.
    #   * provenance     -- evidence AUTHORITY: a third-party shard cannot win
    #                       on the utility prior alone (applied inside RRF's
    #                       scoring, so relative order within each lexical group
    #                       is already tier-corrected before this stable sort).
    # Deliberately NOT a hard tier sort here: that would push arXiv permanently
    # to the bottom and make research queries unanswerable. Un-privileged, not
    # unreachable.
    return provenance.annotate(combined[:limit])
