"""
NouGen Autonomous Maintenance & Shard Optimizer.

Executes autonomous compaction, vacuuming, and deduplication sweeps across the 9 shard databases.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ShardCompactor:
    """
    Autonomous database optimizer:
    - Analyzes fragmentation and unallocated SQLite pages.
    - Runs PRAGMA incremental_vacuum / VACUUM when fragmentation threshold is exceeded.
    - Runs PRAGMA optimize to refresh query planner statistics.
    """

    def __init__(self, db_paths: Optional[List[Path]] = None):
        self.db_paths = db_paths or self._discover_default_shard_dbs()

    @staticmethod
    def _discover_default_shard_dbs() -> List[Path]:
        vault = Path.home() / ".nougen" / "shards"
        if not vault.exists():
            return []
        return sorted(vault.glob("nougen_shards_*.db"))

    @staticmethod
    def inspect_fragmentation(db_path: Path) -> Dict[str, Any]:
        """Inspects page count, freelist count, and calculates fragmentation percentage."""
        if not db_path.exists():
            return {"exists": False, "fragmentation_pct": 0.0}

        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            cur = conn.cursor()
            cur.execute("PRAGMA page_count;")
            page_count = cur.fetchone()[0] or 0

            cur.execute("PRAGMA freelist_count;")
            freelist_count = cur.fetchone()[0] or 0

            cur.execute("PRAGMA page_size;")
            page_size = cur.fetchone()[0] or 4096
            conn.close()

            frag_pct = (freelist_count / max(1, page_count)) * 100.0
            reclaimable_bytes = freelist_count * page_size

            return {
                "exists": True,
                "path": str(db_path),
                "page_count": page_count,
                "freelist_count": freelist_count,
                "fragmentation_pct": round(frag_pct, 2),
                "reclaimable_bytes": reclaimable_bytes,
                "reclaimable_mb": round(reclaimable_bytes / (1024 * 1024), 2),
            }
        except Exception as e:
            return {"exists": True, "path": str(db_path), "error": str(e), "fragmentation_pct": 0.0}

    def compact_database(self, db_path: Path, force: bool = False, min_frag_pct: float = 10.0) -> Dict[str, Any]:
        """Runs VACUUM and PRAGMA optimize if fragmentation exceeds threshold."""
        info = self.inspect_fragmentation(db_path)
        frag_pct = info.get("fragmentation_pct", 0.0)

        if not force and frag_pct < min_frag_pct:
            return {
                "path": str(db_path),
                "optimized": False,
                "reason": f"Fragmentation ({frag_pct}%) below threshold ({min_frag_pct}%)",
            }

        start_time = time.time()
        try:
            conn = sqlite3.connect(str(db_path), timeout=30.0)
            conn.execute("PRAGMA optimize;")
            conn.execute("VACUUM;")
            conn.close()

            post_info = self.inspect_fragmentation(db_path)
            elapsed = time.time() - start_time

            return {
                "path": str(db_path),
                "optimized": True,
                "duration_s": round(elapsed, 2),
                "prior_fragmentation_pct": frag_pct,
                "new_fragmentation_pct": post_info.get("fragmentation_pct", 0.0),
                "freed_mb": info.get("reclaimable_mb", 0.0),
            }
        except Exception as e:
            return {"path": str(db_path), "optimized": False, "error": str(e)}

    def run_fleet_compaction(self, force: bool = False, min_frag_pct: float = 10.0) -> Dict[str, Any]:
        """Runs compaction sweep across all discovered shard databases."""
        results = []
        total_freed_mb = 0.0
        for db in self.db_paths:
            res = self.compact_database(db, force=force, min_frag_pct=min_frag_pct)
            if res.get("optimized"):
                total_freed_mb += res.get("freed_mb", 0.0)
            results.append(res)

        return {
            "timestamp": time.time(),
            "databases_processed": len(self.db_paths),
            "total_freed_mb": round(total_freed_mb, 2),
            "details": results,
        }
