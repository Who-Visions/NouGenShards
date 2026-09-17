#!/usr/bin/env python3
r"""
mrsb_shard_bridge.py - NouGenMorph Dynamic Shard Recall & Lineage Bridge
for "Learn With Mrs. B: ESOL Coloring & Activity Masterclass".

Provides direct, high-speed SQLite and FTS5 dynamic queries into:
- Canonical Shard Grid (~\.nougen\shards)
- Canonical Character DNA & Lineage Locks (Tedley = Dad, Kendall R.I.P., Little Dave, etc.)
- Trilingual Vocabulary (English / Haitian Creole / Spanish)
- Wynn Capit Kinesthetic Color-Key Swatches
- Helen Elliston 54-Color Palette Matrix
- NouGenMorph Pedagogical Absorption Patterns
"""

import os
import sys
import glob
import json
import sqlite3

SHARD_DIR = r"~\.nougen\shards"
PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PILOT_DIR) if os.path.basename(PILOT_DIR) == "pilot" else PILOT_DIR

def recall_shards(query, tags=None, limit=5):
    """Dynamically queries the NouGenMorph Shard Grid for relevant memory shards."""
    dbs = sorted(glob.glob(os.path.join(SHARD_DIR, "nougen_shards_*.db")))
    results = []
    for db in dbs:
        try:
            conn = sqlite3.connect(db)
            cur = conn.cursor()
            cur.execute("""
                SELECT id, title, category, tags, content
                FROM shards
                WHERE content LIKE ? OR title LIKE ? OR tags LIKE ?
                ORDER BY id DESC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", limit))
            for row in cur.fetchall():
                results.append({
                    "db": os.path.basename(db),
                    "id": row[0],
                    "title": row[1],
                    "category": row[2],
                    "tags": row[3],
                    "content": row[4]
                })
            conn.close()
            if len(results) >= limit:
                break
        except Exception:
            pass
    return results[:limit]

def get_lineage_lock():
    """Returns the canonical Meralus lineage lock (Tedley = Dad)."""
    manifest_path = os.path.join(PROJECT_DIR, "mrs_b_character_lineage_manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "lineup": [
            "1. Mrs. B (Matriarch & Educator with afro bun & cardigan)",
            "2. Dad Tedley ('Tech Dad Teddy' / Twin 1 / Locs updo / Honors graduate)",
            "3. Kendall Meralus (Twin 2 — April 12, 2020, R.I.P. Guardian Angel with wings)",
            "4. Dave / Dav3 (Young Visionary in tailored suit with blueprints)",
            "5. Kendall Amelia Meralus ('Curious' Niece/Daughter in space buns & Crocs)"
        ]
    }

def get_character_dna(char_key="mrs_b"):
    """Returns specific character visual DNA from the lineage manifest."""
    manifest = get_lineage_lock()
    return manifest.get("characters", {}).get(char_key, {})

def get_unit_spec(unit_num):
    """Returns the comprehensive 88-page master specification for a given unit."""
    spec_path = os.path.join(PROJECT_DIR, "mrs_b_88_page_kdp_master_spec.json")
    if os.path.exists(spec_path):
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = json.load(f)
            plates = [p for p in spec.get("recto_master_manifest", []) if p.get("unit") == unit_num]
            return plates
    return []

def get_plate_spec(recto_index):
    """Returns the exact plate specification by recto index (1 to 44)."""
    spec_path = os.path.join(PROJECT_DIR, "mrs_b_88_page_kdp_master_spec.json")
    if os.path.exists(spec_path):
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = json.load(f)
            for p in spec.get("recto_master_manifest", []):
                if p.get("recto_index") == recto_index:
                    return p
    return {}

if __name__ == "__main__":
    print("✨ NouGenMorph Shard Bridge Test ✨")
    lineage = get_lineage_lock()
    print("Canonical Lineage Characters:", list(lineage.get("characters", {}).keys()))
    plate13 = get_plate_spec(13)
    print("Plate 13 Title:", plate13.get("title"))
    print("Plate 13 Lineup:", plate13.get("exact_lineup_left_to_right"))
