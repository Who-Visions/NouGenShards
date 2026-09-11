from __future__ import annotations

import hashlib
import json
from typing import Any


def logical_hash(hit: dict[str, Any]) -> str:
    if hit.get("content_hash"):
        return str(hit["content_hash"])
    if hit.get("uuid"):
        return str(hit["uuid"])

    stable = {
        "title": hit.get("title"),
        "content": hit.get("content"),
        "event_type": hit.get("event_type"),
        "created_at": hit.get("created_at") or hit.get("timestamp"),
    }
    raw = json.dumps(stable, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def dedupe_federated_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for hit in hits:
        key = logical_hash(hit)
        replica = {
            "vault": hit.get("source_vault"),
            "machine": hit.get("source_machine"),
            "db_index": hit.get("db_index") or hit.get("_db_index"),
            "id": hit.get("id"),
        }

        if key not in merged:
            item = dict(hit)
            item["logical_hash"] = key
            item["replicas"] = [replica]
            merged[key] = item
            continue

        existing = merged[key]
        existing.setdefault("replicas", []).append(replica)
        if float(hit.get("score") or 0) > float(existing.get("score") or 0):
            keep_replicas = existing["replicas"]
            existing.clear()
            existing.update(hit)
            existing["logical_hash"] = key
            existing["replicas"] = keep_replicas

    return list(merged.values())
