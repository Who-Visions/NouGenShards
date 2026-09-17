"""NouGen Mrs. B Project Engine — CLI + MCP-callable functions.

Provides:
    - Asset audit (SVGs, plates, PDFs, character refs)
    - Shard bridge (recall character DNA, unit specs, lineage)
    - KDP build orchestration (rebuild PDFs from SVGs)
    - Project status dashboard
"""

import os
import json
import glob
import sqlite3
from pathlib import Path
from typing import Optional

# Canonical project paths
PROJECT_DIR = Path(r"C:\Users\super\Outpost\NouGen\projects\learn-with-mrs-b")
PILOT_DIR = PROJECT_DIR / "pilot"
ASSETS_DIR = PROJECT_DIR / "assets"
SHARD_DIR = Path(r"C:\Users\super\.nougen\shards")

# Spec files
LINEAGE_MANIFEST = PROJECT_DIR / "mrs_b_character_lineage_manifest.json"
KDP_METADATA = PROJECT_DIR / "mrs_b_kdp_print_metadata.json"
MASTER_SPEC_88 = PROJECT_DIR / "mrs_b_88_page_kdp_master_spec.json"
MASTER_SPEC_40 = PROJECT_DIR / "mrs_b_40_page_master_spec.json"
ACTIVITY_MANIFEST = PROJECT_DIR / "nougenmorph_activity_mechanics_manifest.json"
ARCHITECTURE_DOC = PROJECT_DIR / "esol-coloring-book-40-page-architecture.md"

# All 26 letters we need tracing plates for
ALPHABET = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

# 8 units × 5 steps = 40 content SVGs
UNIT_STEPS = ["see", "say", "color", "trace", "use"]
FRONT_BACK_SVGS = [
    "00_cover.svg", "00_dedication.svg", "00_swatch_grid.svg",
    "00_blank_bleed_guard.svg", "41_certificate.svg", "42_backmatter_guide.svg"
]


def _load_json(path: Path) -> dict:
    """Safe JSON loader."""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------------------------
# 1. ASSET AUDIT
# ---------------------------------------------------------------------------

def audit_assets() -> dict:
    """Full production audit of all Learn With Mrs. B assets."""
    result = {
        "project_dir": str(PROJECT_DIR),
        "svgs": {"total": 0, "content_pages": 0, "front_back": 0, "files": []},
        "alphabet_plates": {"total": 0, "found_letters": [], "missing_letters": []},
        "unit_see_plates": {"total": 0, "present": [], "missing": []},
        "pdfs": [],
        "kam_assets": [],
        "character_refs": [],
        "manifests": {},
    }

    # SVGs in pilot/
    if PILOT_DIR.exists():
        svgs = sorted(f.name for f in PILOT_DIR.glob("*.svg"))
        result["svgs"]["files"] = svgs
        result["svgs"]["total"] = len(svgs)
        result["svgs"]["front_back"] = sum(1 for s in svgs if s in FRONT_BACK_SVGS)
        result["svgs"]["content_pages"] = len(svgs) - result["svgs"]["front_back"]

    # Alphabet tracing plates
    if PILOT_DIR.exists():
        trace_files = [f.name for f in PILOT_DIR.glob("*trace_*_is_for*.jpg")]
        found = set()
        for tf in trace_files:
            # Extract letter from pattern like "u1_trace_a_is_for_astronaut_apple.jpg"
            parts = tf.split("trace_")
            if len(parts) > 1:
                letter = parts[1][0].upper()
                if letter in ALPHABET:
                    found.add(letter)
        result["alphabet_plates"]["total"] = len(trace_files)
        result["alphabet_plates"]["found_letters"] = sorted(found)
        result["alphabet_plates"]["missing_letters"] = [
            letter_item for letter_item in ALPHABET if letter_item not in found
        ]

    # Unit SEE master plates
    see_plates = [
        "u1_p01_see_classroom_welcome.jpg",
        "u2_p06_see_family_photo_wall.jpg",
        "u3_p11_see_mrs_b_classroom.jpg",
        "u4_p16_see_read_together.jpg",
        "u5_p21_see_kind_animals_pony.jpg",
        "u6_p26_see_good_food_market.jpg",
        "u7_p31_see_color_our_world.jpg",
        "u8_p36_see_big_dreams_together.jpg",
    ]
    for sp in see_plates:
        exists = (PILOT_DIR / sp).exists() or (ASSETS_DIR / sp).exists()
        if exists:
            result["unit_see_plates"]["present"].append(sp)
        else:
            result["unit_see_plates"]["missing"].append(sp)
    result["unit_see_plates"]["total"] = len(result["unit_see_plates"]["present"])

    # PDFs
    for d in [PILOT_DIR, PROJECT_DIR]:
        if d.exists():
            for pdf in sorted(d.glob("*.pdf")):
                result["pdfs"].append({
                    "name": pdf.name,
                    "size_mb": round(pdf.stat().st_size / (1024 * 1024), 1),
                    "path": str(pdf),
                })

    # KAM assets
    if ASSETS_DIR.exists():
        result["kam_assets"] = [
            f.name for f in ASSETS_DIR.iterdir()
            if "kam" in f.name.lower()
        ]

    # Character references
    if ASSETS_DIR.exists():
        result["character_refs"] = [
            f.name for f in ASSETS_DIR.iterdir()
            if any(k in f.name.lower() for k in [
                "mrs_b_character", "little_dave", "curious_granddaughter",
                "parents_canonical", "meralus_family", "mrs_b_granddaughter",
                "mrs_b_teacher", "mrs_b_kdp"
            ])
        ]

    # Manifests
    for name, path in [
        ("lineage", LINEAGE_MANIFEST),
        ("kdp_metadata", KDP_METADATA),
        ("spec_88", MASTER_SPEC_88),
        ("spec_40", MASTER_SPEC_40),
        ("activity_mechanics", ACTIVITY_MANIFEST),
        ("architecture", ARCHITECTURE_DOC),
    ]:
        result["manifests"][name] = {
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "path": str(path),
        }

    return result


def audit_summary() -> str:
    """Human-readable audit summary."""
    a = audit_assets()
    lines = [
        "═══ Learn With Mrs. B — Production Audit ═══",
        "",
        f"  SVGs:           {a['svgs']['total']} total ({a['svgs']['content_pages']} content + {a['svgs']['front_back']} front/back)",
        f"  Alphabet:       {len(a['alphabet_plates']['found_letters'])}/26 letters",
    ]
    if a["alphabet_plates"]["missing_letters"]:
        lines.append(f"    ⚠ Missing:    {', '.join(a['alphabet_plates']['missing_letters'])}")
    else:
        lines.append("    ✓ ALL 26 COMPLETE")

    lines.append(f"  Unit SEE:       {a['unit_see_plates']['total']}/8 master plates")
    lines.append(f"  KAM assets:     {len(a['kam_assets'])} files")
    lines.append(f"  Character refs: {len(a['character_refs'])} sheets")
    lines.append(f"  PDFs built:     {len(a['pdfs'])}")
    for p in a["pdfs"]:
        lines.append(f"    • {p['name']}: {p['size_mb']} MB")

    lines.append("")
    lines.append("  Manifests:")
    for k, v in a["manifests"].items():
        icon = "✓" if v["exists"] else "✗"
        lines.append(f"    {icon} {k}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. SHARD BRIDGE — Character DNA, Lineage, Specs
# ---------------------------------------------------------------------------

def recall_shards(query: str, limit: int = 5) -> list:
    """Query the NouGen shard grid for Mrs. B project-relevant memories."""
    dbs = sorted(glob.glob(str(SHARD_DIR / "nougen_shards_*.db")))
    results = []
    # Tokenize query for flexible matching
    terms = [t.strip().strip("'\"") for t in query.split() if t.strip().strip("'\"")]
    for db_path in dbs:
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            # Try FTS5 first if available
            fts_matched = False
            try:
                cur.execute("""
                    SELECT s.id, s.title, s.domain_key, s.tags, s.content
                    FROM shards_fts f JOIN shards s ON s.id = f.rowid
                    WHERE shards_fts MATCH ?
                    LIMIT ?
                """, (query, limit))
                rows = cur.fetchall()
                if rows:
                    fts_matched = True
                    for row in rows:
                        results.append({
                            "db": os.path.basename(db_path),
                            "id": row[0],
                            "title": row[1],
                            "domain_key": row[2],
                            "tags": row[3],
                            "snippet": (row[4] or "")[:300],
                        })
            except Exception:
                fts_matched = False

            if not fts_matched:
                # Fallback to LIKE with domain_key, title, tags, content
                conditions = []
                params = []
                for term in terms:
                    conditions.append("(content LIKE ? OR title LIKE ? OR tags LIKE ? OR domain_key LIKE ?)")
                    p = f"%{term}%"
                    params.extend([p, p, p, p])
                where_clause = " AND ".join(conditions) if conditions else "1=1"
                params.append(limit)
                cur.execute(f"""
                    SELECT id, title, domain_key, tags, content
                    FROM shards
                    WHERE {where_clause}
                    ORDER BY id DESC LIMIT ?
                """, params)
                for row in cur.fetchall():
                    results.append({
                        "db": os.path.basename(db_path),
                        "id": row[0],
                        "title": row[1],
                        "domain_key": row[2],
                        "tags": row[3],
                        "snippet": (row[4] or "")[:300],
                    })

            conn.close()
        except Exception:
            pass
    # Sort all results across cluster DBs by recency (highest ID first)
    results.sort(key=lambda r: r.get("id", 0), reverse=True)
    return results[:limit]


def get_lineage() -> dict:
    """Return the canonical Meralus family lineage manifest."""
    return _load_json(LINEAGE_MANIFEST)


def get_character_dna(char_key: str = "mrs_b") -> dict:
    """Return visual DNA for a specific character."""
    manifest = get_lineage()
    # Check both top-level characters and community_helpers_lineage
    char = manifest.get("characters", {}).get(char_key, {})
    if not char:
        helpers = manifest.get("community_helpers_lineage", {}).get("characters", {})
        char = helpers.get(char_key, {})
    return char


def get_unit_spec(unit_num: int) -> list:
    """Return plate specs for a given unit from the 88-page master spec."""
    spec = _load_json(MASTER_SPEC_88)
    plates = [
        p for p in spec.get("recto_master_manifest", [])
        if p.get("unit") == unit_num
    ]
    return plates


def get_plate_spec(recto_index: int) -> dict:
    """Return the exact plate specification by recto index (1 to 44)."""
    spec = _load_json(MASTER_SPEC_88)
    for p in spec.get("recto_master_manifest", []):
        if p.get("recto_index") == recto_index:
            return p
    return {}


def get_kdp_metadata() -> dict:
    """Return KDP print metadata (pricing, BISAC, keywords)."""
    return _load_json(KDP_METADATA)


def get_activity_mechanics() -> dict:
    """Return the NouGenMorph pedagogical modules manifest."""
    return _load_json(ACTIVITY_MANIFEST)


def list_characters() -> list:
    """List all character keys in the lineage manifest."""
    manifest = get_lineage()
    chars = list(manifest.get("characters", {}).keys())
    helpers = manifest.get("community_helpers_lineage", {}).get("characters", {})
    chars.extend(helpers.keys())
    return chars


# ---------------------------------------------------------------------------
# 2.5 RECURSION PROTOCOL: 4-STAGE RECURSIVE LESSON LEDGER
# ---------------------------------------------------------------------------

RECURSION_MAP = {
    1: {
        "unit": 1,
        "title": "Welcome to School / Byenvini nan Lekòl",
        "theme": "Classroom items, greetings, emotional safety",
        "setup": "Mrs. B welcomes learners in classroom with peacock chair and warm smile. Focus words: Backpack, Pencil, Book.",
        "first_echo": "Tracing letters A, B, C; repeating 'Good Morning / Bonjou / Buenos Días' with phonetic guides.",
        "inversion": "Rebus matching: connect the school tool to its classroom action; decode pencil-maze.",
        "final_payoff": "First Day Hero badge; coloring Mrs. B's classroom helper sticker."
    },
    2: {
        "unit": 2,
        "title": "Colors & Shapes / Koulè ak Fòm",
        "theme": "Visual vocabulary, primary colors, geometric forms",
        "setup": "Kid Dave explores colorful art palette with brushes. Focus words: Red/Wouj/Rojo, Circle/Sèk/Círculo.",
        "first_echo": "Tracing D, E, F; saying and coloring the 54-circle swatch grid.",
        "inversion": "Color-by-number pattern; finding hidden circles and squares in Kid Dave's studio.",
        "final_payoff": "Master Artist Certificate stamp; create your own family flag."
    },
    3: {
        "unit": 3,
        "title": "Family & Home / Fanmi ak Kay",
        "theme": "Sacred family provenance, community foundation",
        "setup": "Meralus family porch scene with Grandma Mrs. B, Tech Dad Teddy, and curious grandchildren.",
        "first_echo": "Tracing G, H, I; family member vocabulary (Mother, Father, Sister, Brother).",
        "inversion": "Family tree connection puzzle; drawing who lives in your home with bilingual prompt.",
        "final_payoff": "Family Foundation award; share story with caregiver."
    },
    4: {
        "unit": 4,
        "title": "Community Helpers / Moun K ap Ede Nou",
        "theme": "Safety, service, neighborhood protectors",
        "setup": "Officer Kam (Police Badge #516) and Firefighter intro at the community center.",
        "first_echo": "Tracing J, K, L; community helper vehicle call-and-response.",
        "inversion": "Crosswalk safety maze; identifying safe adults and dialing 911 when needed.",
        "final_payoff": "Official Junior Community Safety Officer badge signed by Officer Kam."
    },
    5: {
        "unit": 5,
        "title": "Food & Sharing / Manje ak Pataje",
        "theme": "Nutrition, cultural dishes, kindness",
        "setup": "Marketplace fruit stand with mangoes, plantains, rice, and beans.",
        "first_echo": "Tracing M, N, O; food words in 3 languages.",
        "inversion": "Plate balance puzzle; sorting healthy foods and counting recipe ingredients.",
        "final_payoff": "Kindness Kitchen certificate; recipe sharing card."
    },
    6: {
        "unit": 6,
        "title": "Animals & Nature / Bèt ak Lanati",
        "theme": "Living things, habitats, stewardship",
        "setup": "Curious Granddaughter meets farm animals and garden creatures.",
        "first_echo": "Tracing P, Q, R, S; animal sounds and names across English/Kreyòl/Spanish.",
        "inversion": "Habitat matching (pond, farm, forest); animal footprint tracker.",
        "final_payoff": "Junior Park Ranger badge."
    },
    7: {
        "unit": 7,
        "title": "Feelings & Friendship / Santiman ak Zanmitay",
        "theme": "Social-emotional learning, empathy, conflict resolution",
        "setup": "Two friends solving a playground misunderstanding with Mrs. B guiding.",
        "first_echo": "Tracing T, U, V; emotion facial expressions (Happy, Sad, Calm, Brave).",
        "inversion": "Calm-down breathing maze; choosing kind words in tricky situations.",
        "final_payoff": "Peacemaker Medal & Friendship pledge."
    },
    8: {
        "unit": 8,
        "title": "Big Dreams & Graduation / Gwo Rèv ak Graduasyon",
        "theme": "Ambition, education milestone, future vision",
        "setup": "Lake Worth High School graduation stage with Mrs. B conferring awards to little dreamers.",
        "first_echo": "Tracing W, X, Y, Z; dream profession words (Doctor, Pilot, Engineer, Artist).",
        "inversion": "Future-self self-portrait plate; milestone checklist.",
        "final_payoff": "Master Completion Diploma (Plate 41) signed by Mrs. B."
    }
}


def get_recursion_map(unit_id: Optional[int] = None) -> dict:
    """Return the 4-stage recursive lesson ledger (setup, echo, inversion, payoff)."""
    if unit_id is not None:
        return RECURSION_MAP.get(unit_id, {})
    return RECURSION_MAP


# ---------------------------------------------------------------------------
# 3. PROJECT STATUS DASHBOARD
# ---------------------------------------------------------------------------

def project_status() -> dict:
    """Comprehensive project status for CLI and MCP."""
    audit = audit_assets()
    lineage = get_lineage()
    kdp = get_kdp_metadata()

    return {
        "project": "Learn With Mrs. B: ESOL Coloring & Activity Masterclass",
        "publisher": kdp.get("publisher", "Who Visions / NouGen Publishing"),
        "author": kdp.get("primary_author", {}).get("name", "Mrs. B"),
        "lineage": lineage,
        "status": {
            "svgs_complete": audit["svgs"]["content_pages"] >= 40,
            "alphabet_complete": len(audit["alphabet_plates"]["missing_letters"]) == 0,
            "all_see_plates": audit["unit_see_plates"]["total"] == 8,
            "pdfs_built": len(audit["pdfs"]),
            "kdp_ready": audit["svgs"]["content_pages"] >= 40 and len(audit["alphabet_plates"]["missing_letters"]) == 0,
        },
        "characters": list_characters(),
        "dimensions": kdp.get("dimensions", {}),
        "pricing": kdp.get("pricing", {}),
        "isbn": kdp.get("isbn_13_kdp_assigned", "Pending"),
        "svgs": audit["svgs"]["total"],
        "pdfs": [p["name"] for p in audit["pdfs"]],
    }


# ---------------------------------------------------------------------------
# 4. CLI ENTRYPOINT
# ---------------------------------------------------------------------------

def cli_handler(args):
    """Handle `nougen mrsb <action>` commands."""
    action = getattr(args, "mrsb_action", None) or "status"

    if action == "audit":
        if getattr(args, "json", False):
            print(json.dumps(audit_assets(), indent=2))
        else:
            print(audit_summary())

    elif action == "status":
        status = project_status()
        if getattr(args, "json", False):
            print(json.dumps(status, indent=2, default=str))
        else:
            s = status["status"]
            print("═══ Learn With Mrs. B — Project Status ═══")
            print(f"  Publisher:  {status['publisher']}")
            print(f"  Author:    {status['author']}")
            print(f"  ISBN:      {status['isbn']}")
            print(f"  SVGs:      {status['svgs']} | PDFs: {s['pdfs_built']}")
            print(f"  Alphabet:  {'✓ COMPLETE' if s['alphabet_complete'] else '⚠ INCOMPLETE'}")
            print(f"  KDP Ready: {'✓ YES' if s['kdp_ready'] else '⚠ NOT YET'}")
            print(f"  Characters: {', '.join(status['characters'])}")
            if status["pricing"]:
                print(f"  Price:     ${status['pricing'].get('usd', '?')} USD")

    elif action == "lineage":
        manifest = get_lineage()
        char_key = getattr(args, "character", None)
        if char_key:
            dna = get_character_dna(char_key)
            if dna:
                print(json.dumps(dna, indent=2, ensure_ascii=False))
            else:
                print(f"Character '{char_key}' not found. Available: {', '.join(list_characters())}")
        else:
            if getattr(args, "json", False):
                print(json.dumps(manifest, indent=2, ensure_ascii=False))
            else:
                print("═══ Meralus Family Lineage ═══")
                for key, char in manifest.get("characters", {}).items():
                    name = char.get("name", key)
                    role = char.get("role", "")
                    print(f"  • {name} [{key}]")
                    print(f"    {role}")
                helpers = manifest.get("community_helpers_lineage", {}).get("characters", {})
                if helpers:
                    print("\n  Community Helpers:")
                    for key, char in helpers.items():
                        print(f"    • {char.get('name', key)} [{key}]")
                        print(f"      {char.get('motto', '')}")

    elif action == "recall":
        query = getattr(args, "query", "Mrs. B")
        limit = getattr(args, "limit", 5)
        results = recall_shards(query, limit)
        if getattr(args, "json", False):
            print(json.dumps(results, indent=2))
        else:
            if not results:
                print(f"No shards found for: {query}")
            else:
                print(f"═══ Shard Recall: '{query}' ({len(results)} results) ═══")
                for r in results:
                    print(f"\n  [{r['db']}] #{r['id']}: {r['title']}")
                    print(f"    {r.get('domain_key', '')} | {r.get('tags', '')}")
                    print(f"    {r['snippet'][:200]}...")

    elif action == "recurse":
        unit_arg = getattr(args, "unit", None)
        rec_data = get_recursion_map(unit_arg)
        if getattr(args, "json", False):
            print(json.dumps(rec_data, indent=2, ensure_ascii=False))
        else:
            if unit_arg and isinstance(rec_data, dict) and rec_data:
                u = rec_data
                print(f"═══ Unit {u['unit']} Recursive Ledger: {u['title']} ═══")
                print(f"  Theme:         {u['theme']}")
                print(f"  1. SETUP:      {u['setup']}")
                print(f"  2. FIRST ECHO: {u['first_echo']}")
                print(f"  3. INVERSION:  {u['inversion']}")
                print(f"  4. PAYOFF:     {u['final_payoff']}")
            else:
                print("═══ NouGen 4-Stage Recursive Lesson Ledger (Units 1-8) ═══")
                for uid, u in sorted(rec_data.items()):
                    print(f"\n  [Unit {uid}] {u['title']}")
                    print(f"    Theme:    {u['theme']}")
                    print(f"    Setup:    {u['setup'][:80]}...")
                    print(f"    Echo:     {u['first_echo'][:80]}...")
                    print(f"    Invert:   {u['inversion'][:80]}...")
                    print(f"    Payoff:   {u['final_payoff'][:80]}...")

    elif action == "build":
        print("Triggering KDP 88-page interior rebuild...")
        import subprocess, sys
        build_script = PILOT_DIR / "build_kdp_88page_interior.py"
        if build_script.exists():
            subprocess.run([sys.executable, str(build_script)], cwd=str(PILOT_DIR))
        else:
            print(f"Build script not found: {build_script}")

    elif action == "kdp":
        meta = get_kdp_metadata()
        if getattr(args, "json", False):
            print(json.dumps(meta, indent=2, ensure_ascii=False))
        else:
            print("═══ KDP Print Metadata ═══")
            print(f"  Title:    {meta.get('book_title', '?')}")
            print(f"  Subtitle: {meta.get('subtitle', '?')}")
            print(f"  Author:   {meta.get('primary_author', {}).get('name', '?')}")
            dims = meta.get("dimensions", {})
            print(f"  Trim:     {dims.get('trim_size', '?')}")
            print(f"  Pages:    {dims.get('page_count', '?')}")
            print(f"  Binding:  {dims.get('binding', '?')}")
            print(f"  Interior: {dims.get('interior_color_type', '?')}")
            pricing = meta.get("pricing", {})
            if pricing:
                print(f"  Price:    ${pricing.get('usd', '?')} USD / £{pricing.get('gbp', '?')} / €{pricing.get('eur', '?')}")
            keywords = meta.get("amazon_7_search_keywords", [])
            if keywords:
                print("  Keywords:")
                for kw in keywords:
                    print(f"    • {kw}")

    else:
        print(f"Unknown action: {action}")
        print("Available: status, audit, lineage, recall, recurse, build, kdp")
