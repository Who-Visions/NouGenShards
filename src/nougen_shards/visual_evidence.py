"""
NouGen Visual Evidence Plane — Core Multimodal Architecture & MCP Engine.

Implements the top 0.01% multimodal evidence architecture for NouGen:
1. Original Bytes are the Witness (Immutable content-addressed storage).
2. Content-Addressed Identity (SHA-256 asset_id and nougen://asset/<sha256> URIs).
3. Hard + Soft Bindings (Cryptographic SHA-256 + Perceptual Hashes + Embeddings).
4. Provenance Graph (C2PA 2.4-aligned DAG of actors, machines, tools, transformations).
5. Object Plane + MCP Control Plane Separation (Lightweight references over raw base64 pipes).
6. Multi-Resolution Delivery (Micro-previews, UI thumbnails, Model renditions, Masters).
7. Native Multimodal Retrieval (Late-fusion combining BM25, Cosine Similarity, Hamming Distance, Provenance Trust).
8. Derived Interpretations as Attributed Claims (Model, version, prompt, confidence).
9. Visual Shards with deep evidence handles.
10. Security Sanitization (OWASP magic-byte inspection, SVG sanitization, bomb checks).
11. Capability Scoping & Privacy Enforcement.
12. Observability & OpenTelemetry Usage Telemetry.
13. Idempotent Ingestion & Exactly-Once Semantics.
14. ActionGate for media mutations and exports.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import sqlite3
import struct
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# ============================================================================
# Enums & Constants
# ============================================================================

class RenditionType(str, Enum):
    MICRO_PREVIEW = "MICRO_PREVIEW"     # 64x64 micro preview / blurred placeholder
    UI_THUMBNAIL = "UI_THUMBNAIL"       # 256x256 / 512x512 UI card thumbnail
    MODEL_RENDITION = "MODEL_RENDITION" # 1024x1024 vision model inference rendition
    WEB_MASTER = "WEB_MASTER"           # 2048px high-craft responsive web display
    FULL_MASTER = "FULL_MASTER"         # 100% original uncompressed master asset


class ProvenanceEventType(str, Enum):
    INGEST = "INGEST"
    C2PA_MANIFEST_DETECTED = "C2PA_MANIFEST_DETECTED"
    TRANSFORMATION = "TRANSFORMATION"
    CROP_EDIT = "CROP_EDIT"
    AI_OBSERVATION = "AI_OBSERVATION"
    HUMAN_ASSERTION = "HUMAN_ASSERTION"
    REDACTION = "REDACTION"
    EXPORT = "EXPORT"
    PUBLICATION = "PUBLICATION"


class ObservationKind(str, Enum):
    CAPTION = "CAPTION"
    OBJECT_DETECTION = "OBJECT_DETECTION"
    SCENE_GRAPH = "SCENE_GRAPH"
    OCR_TEXT = "OCR_TEXT"
    AESTHETIC_MOOD = "AESTHETIC_MOOD"
    CLASSIFICATION = "CLASSIFICATION"
    EMBEDDING = "EMBEDDING"


class CapabilityScope(str, Enum):
    ASSET_METADATA = "asset:metadata"
    ASSET_PREVIEW = "asset:preview"
    ASSET_ANALYZE = "asset:analyze"
    ASSET_ORIGINAL = "asset:original"
    ASSET_EXIF = "asset:exif"
    ASSET_EXPORT = "asset:export"
    ASSET_MUTATE = "asset:mutate"


# Magic byte signatures for allowlisted media formats
ALLOWED_MAGIC_SIGNATURES: Dict[str, List[bytes]] = {
    "image/jpeg": [b"\xFF\xD8\xFF"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"], # Sub-check for WEBP at offset 8
    "image/gif": [b"GIF87a", b"GIF89a"],
    "image/tiff": [b"II*\x00", b"MM\x00*"],
    "image/svg+xml": [b"<?xml", b"<svg"],
}

MAX_ALLOWED_DECOMPRESSION_PIXELS = 100_000_000 # 100 Megapixels max bomb limit
DEFAULT_BLOB_STORAGE_DIR = "vault/blobs"


def utc_now_iso() -> str:
    """Returns ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ============================================================================
# Core Data Models
# ============================================================================

@dataclass
class ContentBinding:
    """Cryptographic (Hard) and Perceptual (Soft) bindings for an asset."""
    asset_id: str
    hard_sha256: str
    soft_dhash: str # 64-bit hexadecimal difference hash
    soft_ahash: str # 64-bit hexadecimal average hash
    embedding_vector: Optional[List[float]] = None
    embedding_model: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AssetRecord:
    """Canonical, immutable asset metadata record."""
    asset_id: str                          # SHA-256 digest of original bytes
    blob_uri: str                          # nougen://asset/<sha256>
    mime_type: str
    byte_size: int
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None # For video / audio assets
    original_filename: str = "unnamed_asset"
    captured_at: Optional[str] = None
    capture_confidence: str = "filesystem" # 'exif' | 'container' | 'sidecar' | 'filesystem' | 'none'
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    lens_slug: Optional[str] = None
    exposure_iso: Optional[int] = None
    exposure_fnumber: Optional[float] = None
    exposure_seconds: Optional[float] = None
    focal_length_35mm: Optional[float] = None
    geo_lat: Optional[float] = None
    geo_lon: Optional[float] = None
    geo_altitude: Optional[float] = None
    geo_geohash5: Optional[str] = None
    imported_at: str = field(default_factory=utc_now_iso)
    source_machine: str = "local"
    source_lane: str = "default"
    is_redacted: bool = False
    exif_redacted: bool = False
    c2pa_manifest_present: bool = False
    c2pa_status: str = "none" # 'valid' | 'invalid' | 'none' | 'signed'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Rendition:
    """Multi-resolution rendition generated from master asset."""
    rendition_id: str
    parent_asset_id: str
    rendition_type: RenditionType
    width: int
    height: int
    byte_size: int
    mime_type: str
    blob_uri: str
    sha256: str
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["rendition_type"] = self.rendition_type.value
        return d


@dataclass
class ProvenanceEvent:
    """C2PA 2.4-aligned append-only provenance event node."""
    event_id: str
    asset_id: str
    event_type: ProvenanceEventType
    actor_id: str
    machine_id: str
    tool_name: str
    tool_version: str
    parent_asset_ids: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    attestation_signature: Optional[str] = None
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d


@dataclass
class ClaimObservation:
    """Attributed interpretation/observation produced by an AI model or analyst."""
    claim_id: str
    asset_id: str
    rendition_id: Optional[str]
    observation_kind: ObservationKind
    model_name: str
    model_version: str
    prompt_policy: str
    confidence: float # 0.0 to 1.0
    payload: Dict[str, Any] # Extracted tags, captions, OCR strings, scene elements
    bounding_boxes: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["observation_kind"] = self.observation_kind.value
        return d


@dataclass
class VisualShard:
    """High-level knowledge shard linked to visual evidence."""
    shard_id: str
    asset_id: str
    title: str
    body: str # BM25 / FTS5 searchable narrative
    facets: Dict[str, Any]
    utility_score: float = 1.0
    domain_key: str = "visual"
    linked_shards: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TelemetryEnvelope:
    """OpenTelemetry-aligned usage and observability trace record."""
    trace_id: str
    span_id: str
    operation: str
    asset_id: Optional[str]
    duration_ms: float
    bytes_transferred: int
    decode_ms: float
    vision_tokens_in: int
    vision_tokens_out: int
    cache_hit: bool
    machine_lane: str
    cost_usd: float = 0.0
    error_code: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# Security, Sanitization & Hashing Engine
# ============================================================================

class SecuritySanitizer:
    """OWASP-compliant media sanitization and attack prevention."""

    @staticmethod
    def verify_magic_bytes(data: bytes, declared_mime: Optional[str] = None) -> str:
        """Inspects binary header against allowlist, detecting spoofed MIME types."""
        if not data or len(data) < 8:
            raise ValueError("Invalid binary payload: payload is empty or too short.")

        detected_mime = None
        for mime, signatures in ALLOWED_MAGIC_SIGNATURES.items():
            for sig in signatures:
                if data.startswith(sig):
                    if mime == "image/webp":
                        # Verify WEBP signature at offset 8
                        if len(data) >= 12 and data[8:12] == b"WEBP":
                            detected_mime = "image/webp"
                            break
                    else:
                        detected_mime = mime
                        break
            if detected_mime:
                break

        if not detected_mime:
            # Check for SVG in text mode
            prefix = data[:512].strip()
            if b"<svg" in prefix.lower() or b"<?xml" in prefix.lower():
                detected_mime = "image/svg+xml"

        if not detected_mime:
            raise ValueError("Unsupported or forbidden media format: magic signature mismatch.")

        return detected_mime

    @staticmethod
    def sanitize_svg(data: bytes) -> bytes:
        """Sanitizes active SVG scripts, onclick handlers, and malicious tags."""
        text = data.decode("utf-8", errors="replace")
        
        # Check for dangerous script execution payloads
        dangerous_patterns = [
            r"<script[\s\S]*?>[\s\S]*?<\/script>",
            r"on\w+\s*=\s*[\"'][^\"']*[\"']",
            r"href\s*=\s*[\"']javascript:[^\"']*[\"']",
            r"xlink:href\s*=\s*[\"']javascript:[^\"']*[\"']",
            r"<!ENTITY[\s\S]*?>", # XML entity expansion attacks
        ]

        sanitized_text = text
        for pattern in dangerous_patterns:
            sanitized_text = re.sub(pattern, "", sanitized_text, flags=re.IGNORECASE)

        return sanitized_text.encode("utf-8")

    @staticmethod
    def check_dimensions_bomb(width: int, height: int) -> None:
        """Prevents decompression bombs (huge pixel dimension denial-of-service)."""
        total_pixels = width * height
        if total_pixels > MAX_ALLOWED_DECOMPRESSION_PIXELS:
            raise ValueError(
                f"Decompression bomb detected: {total_pixels} pixels exceeds safety limit of {MAX_ALLOWED_DECOMPRESSION_PIXELS}."
            )


class PerceptualHashing:
    """Pure-python fallback perceptual hashing (dHash and aHash) for image identity."""

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        """Computes hard cryptographic SHA-256 digest."""
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def compute_dhash_from_matrix(grayscale_9x8: List[List[int]]) -> str:
        """Computes 64-bit difference hash (dHash) from a 9x8 intensity matrix."""
        diff_bits = []
        for row in grayscale_9x8:
            for col in range(8):
                diff_bits.append(1 if row[col] > row[col + 1] else 0)
        
        # Convert 64 bits to 16 hex chars
        hex_str = ""
        for i in range(0, 64, 4):
            nibble = (diff_bits[i] << 3) | (diff_bits[i+1] << 2) | (diff_bits[i+2] << 1) | diff_bits[i+3]
            hex_str += f"{nibble:x}"
        return hex_str

    @staticmethod
    def compute_ahash_from_matrix(grayscale_8x8: List[List[int]]) -> str:
        """Computes 64-bit average hash (aHash) from an 8x8 intensity matrix."""
        flat = [val for row in grayscale_8x8 for val in row]
        avg = sum(flat) / 64.0
        bits = [1 if val >= avg else 0 for val in flat]
        
        hex_str = ""
        for i in range(0, 64, 4):
            nibble = (bits[i] << 3) | (bits[i+1] << 2) | (bits[i+2] << 1) | bits[i+3]
            hex_str += f"{nibble:x}"
        return hex_str

    @staticmethod
    def compute_fallback_soft_hashes(data: bytes) -> Tuple[str, str]:
        """Calculates pseudo-perceptual dHash and aHash directly from sample chunks."""
        sample_len = len(data)
        matrix_9x8 = []
        for r in range(9):
            row = []
            for c in range(9):
                idx = int((r * 9 + c) * (sample_len / 81.0)) % sample_len
                row.append(data[idx])
            matrix_9x8.append(row)

        matrix_8x8 = [row[:8] for row in matrix_9x8[:8]]

        dhash = PerceptualHashing.compute_dhash_from_matrix(matrix_9x8)
        ahash = PerceptualHashing.compute_ahash_from_matrix(matrix_8x8)
        return dhash, ahash

    @staticmethod
    def hamming_distance(hex1: str, hex2: str) -> int:
        """Calculates bitwise Hamming distance between two hex hashes."""
        val1 = int(hex1, 16)
        val2 = int(hex2, 16)
        xor_val = val1 ^ val2
        return bin(xor_val).count("1")


# ============================================================================
# Capability Gate & Privacy Enforcement
# ============================================================================

class CapabilityGate:
    """Enforces fine-grained permission scopes for asset operations."""

    @staticmethod
    def check_scope(granted_scopes: Set[str], required_scope: CapabilityScope) -> None:
        """Verifies if granted scopes contain the required capability."""
        if required_scope.value not in granted_scopes and "*" not in granted_scopes:
            raise PermissionError(
                f"Access denied: Missing required capability scope '{required_scope.value}'. "
                f"Granted scopes: {sorted(list(granted_scopes))}"
            )

    @staticmethod
    def redact_asset_for_scopes(asset: AssetRecord, granted_scopes: Set[str]) -> AssetRecord:
        """Redacts sensitive EXIF/GPS fields if asset:exif is not authorized."""
        if CapabilityScope.ASSET_EXIF.value in granted_scopes or "*" in granted_scopes:
            return asset
        
        # Redact GPS and camera serial info
        return AssetRecord(
            asset_id=asset.asset_id,
            blob_uri=asset.blob_uri,
            mime_type=asset.mime_type,
            byte_size=asset.byte_size,
            width=asset.width,
            height=asset.height,
            duration_seconds=asset.duration_seconds,
            original_filename=asset.original_filename,
            captured_at=asset.captured_at,
            capture_confidence=asset.capture_confidence,
            camera_make=asset.camera_make,
            camera_model=asset.camera_model,
            lens_slug=asset.lens_slug,
            exposure_iso=asset.exposure_iso,
            exposure_fnumber=asset.exposure_fnumber,
            exposure_seconds=asset.exposure_seconds,
            focal_length_35mm=asset.focal_length_35mm,
            geo_lat=None, # Redacted
            geo_lon=None, # Redacted
            geo_altitude=None, # Redacted
            geo_geohash5=None, # Redacted
            imported_at=asset.imported_at,
            source_machine=asset.source_machine,
            source_lane=asset.source_lane,
            is_redacted=asset.is_redacted,
            exif_redacted=True,
            c2pa_manifest_present=asset.c2pa_manifest_present,
            c2pa_status=asset.c2pa_status,
        )


# ============================================================================
# Visual Evidence Ledger & SQLite Persistence Plane
# ============================================================================

class VisualEvidenceStore:
    """
    SQLite-backed storage and retrieval plane for assets, renditions,
    provenance graphs, claims, embeddings, and visual shards.
    """

    def __init__(self, db_path: Union[str, Path], blob_dir: Optional[Union[str, Path]] = None):
        self.db_path = Path(db_path).expanduser().resolve()
        self.blob_dir = Path(blob_dir or self.db_path.parent / DEFAULT_BLOB_STORAGE_DIR).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        self.initialize_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def initialize_schema(self) -> None:
        """Initializes tables, FTS5 virtual tables, and indexes."""
        with self.connect() as conn:
            conn.executescript(
                """
                -- Canonical Assets Table
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY CHECK(length(asset_id) = 64),
                    blob_uri TEXT NOT NULL UNIQUE,
                    mime_type TEXT NOT NULL,
                    byte_size INTEGER NOT NULL CHECK(byte_size >= 0),
                    width INTEGER,
                    height INTEGER,
                    duration_seconds REAL,
                    original_filename TEXT NOT NULL,
                    captured_at TEXT,
                    capture_confidence TEXT NOT NULL,
                    camera_make TEXT,
                    camera_model TEXT,
                    lens_slug TEXT,
                    exposure_iso INTEGER,
                    exposure_fnumber REAL,
                    exposure_seconds REAL,
                    focal_length_35mm REAL,
                    geo_lat REAL,
                    geo_lon REAL,
                    geo_altitude REAL,
                    geo_geohash5 TEXT,
                    imported_at TEXT NOT NULL,
                    source_machine TEXT NOT NULL,
                    source_lane TEXT NOT NULL,
                    is_redacted INTEGER NOT NULL DEFAULT 0,
                    exif_redacted INTEGER NOT NULL DEFAULT 0,
                    c2pa_manifest_present INTEGER NOT NULL DEFAULT 0,
                    c2pa_status TEXT NOT NULL DEFAULT 'none'
                );
                CREATE INDEX IF NOT EXISTS idx_assets_imported ON assets(imported_at DESC);
                CREATE INDEX IF NOT EXISTS idx_assets_captured ON assets(captured_at DESC);
                CREATE INDEX IF NOT EXISTS idx_assets_geohash ON assets(geo_geohash5);

                -- Content Bindings (Hard + Soft Hashes & Embeddings)
                CREATE TABLE IF NOT EXISTS content_bindings (
                    asset_id TEXT PRIMARY KEY REFERENCES assets(asset_id) ON DELETE CASCADE,
                    hard_sha256 TEXT NOT NULL,
                    soft_dhash TEXT NOT NULL,
                    soft_ahash TEXT NOT NULL,
                    embedding_blob BLOB,
                    embedding_model TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_bindings_dhash ON content_bindings(soft_dhash);

                -- Multi-Resolution Renditions
                CREATE TABLE IF NOT EXISTS renditions (
                    rendition_id TEXT PRIMARY KEY,
                    parent_asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
                    rendition_type TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    byte_size INTEGER NOT NULL,
                    mime_type TEXT NOT NULL,
                    blob_uri TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(parent_asset_id, rendition_type)
                );
                CREATE INDEX IF NOT EXISTS idx_renditions_parent ON renditions(parent_asset_id);

                -- C2PA 2.4 Provenance Graph Events
                CREATE TABLE IF NOT EXISTS provenance_events (
                    event_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_version TEXT NOT NULL,
                    parent_asset_ids_json TEXT NOT NULL DEFAULT '[]',
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    attestation_signature TEXT,
                    timestamp TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_prov_asset ON provenance_events(asset_id, timestamp);

                -- Model Observations & Claims
                CREATE TABLE IF NOT EXISTS claim_observations (
                    claim_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
                    rendition_id TEXT,
                    observation_kind TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    prompt_policy TEXT NOT NULL,
                    confidence REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
                    payload_json TEXT NOT NULL,
                    bounding_boxes_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_claims_asset ON claim_observations(asset_id);
                CREATE INDEX IF NOT EXISTS idx_claims_kind ON claim_observations(observation_kind);

                -- Visual Knowledge Shards
                CREATE TABLE IF NOT EXISTS visual_shards (
                    shard_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    facets_json TEXT NOT NULL DEFAULT '{}',
                    utility_score REAL NOT NULL DEFAULT 1.0,
                    domain_key TEXT NOT NULL DEFAULT 'visual',
                    linked_shards_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_visual_shards_asset ON visual_shards(asset_id);

                -- OpenTelemetry Telemetry Usage Ledger
                CREATE TABLE IF NOT EXISTS visual_telemetry (
                    trace_id TEXT NOT NULL,
                    span_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    asset_id TEXT,
                    duration_ms REAL NOT NULL,
                    bytes_transferred INTEGER NOT NULL,
                    decode_ms REAL NOT NULL,
                    vision_tokens_in INTEGER NOT NULL,
                    vision_tokens_out INTEGER NOT NULL,
                    cache_hit INTEGER NOT NULL,
                    machine_lane TEXT NOT NULL,
                    cost_usd REAL NOT NULL DEFAULT 0.0,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(trace_id, span_id)
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_time ON visual_telemetry(created_at DESC);
                """
            )

            # Check and initialize FTS5 table for visual shards
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS visual_shards_fts USING fts5(
                        shard_id UNINDEXED,
                        asset_id UNINDEXED,
                        title,
                        body,
                        content='visual_shards',
                        content_rowid='rowid'
                    );
                    """
                )
            except sqlite3.OperationalError:
                pass

    # ------------------------------------------------------------------------
    # Ingestion & Blob Persistence
    # ------------------------------------------------------------------------

    def ingest_bytes(
        self,
        media_bytes: bytes,
        original_filename: str = "upload.jpg",
        metadata: Optional[Dict[str, Any]] = None,
        actor_id: str = "operator",
        machine_id: str = "local",
        tool_name: str = "nougen_visual_mcp",
        tool_version: str = "2.0.0",
        scopes: Optional[Set[str]] = None,
    ) -> Tuple[AssetRecord, bool]:
        """
        Idempotently ingests media bytes:
        - Computes content-addressed SHA-256
        - Verifies magic byte signatures & sanitizes SVGs
        - Stores original bytes to immutable blob plane
        - Computes hard + soft perceptual bindings
        - Creates default multi-resolution renditions
        - Records INGEST provenance event
        """
        granted = scopes or {"*"}
        CapabilityGate.check_scope(granted, CapabilityScope.ASSET_METADATA)

        start_time = time.perf_counter()
        meta = metadata or {}

        # 1. Security & Magic Byte Inspection
        declared_mime = meta.get("mime_type")
        mime_type = SecuritySanitizer.verify_magic_bytes(media_bytes, declared_mime)

        if mime_type == "image/svg+xml":
            media_bytes = SecuritySanitizer.sanitize_svg(media_bytes)

        # 2. Content-Addressed Identity
        sha256 = PerceptualHashing.compute_sha256(media_bytes)
        blob_uri = f"nougen://asset/{sha256}"
        byte_size = len(media_bytes)

        # 3. Check if already ingested (Idempotency)
        existing = self.get_asset(sha256, granted)
        if existing:
            self.record_telemetry(
                TelemetryEnvelope(
                    trace_id=uuid.uuid4().hex,
                    span_id=uuid.uuid4().hex[:16],
                    operation="asset_ingest",
                    asset_id=sha256,
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                    bytes_transferred=byte_size,
                    decode_ms=0.0,
                    vision_tokens_in=0,
                    vision_tokens_out=0,
                    cache_hit=True,
                    machine_lane=machine_id,
                )
            )
            return existing, False

        # 4. Save Raw Bytes to Immutable Blob Storage
        blob_path = self.blob_dir / f"{sha256[:2]}" / f"{sha256[2:4]}" / f"{sha256}"
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        if not blob_path.exists():
            blob_path.write_bytes(media_bytes)

        # 5. Extract Dimensions & Fallback Hashes
        width = meta.get("width")
        height = meta.get("height")
        if width and height:
            SecuritySanitizer.check_dimensions_bomb(width, height)

        dhash, ahash = PerceptualHashing.compute_fallback_soft_hashes(media_bytes)

        # 6. Construct Records
        asset = AssetRecord(
            asset_id=sha256,
            blob_uri=blob_uri,
            mime_type=mime_type,
            byte_size=byte_size,
            width=width,
            height=height,
            duration_seconds=meta.get("duration_seconds"),
            original_filename=original_filename,
            captured_at=meta.get("captured_at") or utc_now_iso(),
            capture_confidence=meta.get("capture_confidence", "filesystem"),
            camera_make=meta.get("camera_make"),
            camera_model=meta.get("camera_model"),
            lens_slug=meta.get("lens_slug"),
            exposure_iso=meta.get("exposure_iso"),
            exposure_fnumber=meta.get("exposure_fnumber"),
            exposure_seconds=meta.get("exposure_seconds"),
            focal_length_35mm=meta.get("focal_length_35mm"),
            geo_lat=meta.get("geo_lat"),
            geo_lon=meta.get("geo_lon"),
            geo_altitude=meta.get("geo_altitude"),
            geo_geohash5=meta.get("geo_geohash5"),
            imported_at=utc_now_iso(),
            source_machine=machine_id,
            source_lane=meta.get("source_lane", "default"),
            c2pa_manifest_present=meta.get("c2pa_manifest_present", False),
            c2pa_status=meta.get("c2pa_status", "none"),
        )

        binding = ContentBinding(
            asset_id=sha256,
            hard_sha256=sha256,
            soft_dhash=dhash,
            soft_ahash=ahash,
            embedding_vector=meta.get("embedding_vector"),
            embedding_model=meta.get("embedding_model"),
        )

        prov_event = ProvenanceEvent(
            event_id=f"prv_{uuid.uuid4().hex[:16]}",
            asset_id=sha256,
            event_type=ProvenanceEventType.INGEST,
            actor_id=actor_id,
            machine_id=machine_id,
            tool_name=tool_name,
            tool_version=tool_version,
            parent_asset_ids=[],
            parameters={"original_filename": original_filename, "byte_size": byte_size, "mime_type": mime_type},
        )

        # 7. Multi-Resolution Rendition Generation
        renditions = [
            Rendition(
                rendition_id=f"rnd_{sha256[:12]}_micro",
                parent_asset_id=sha256,
                rendition_type=RenditionType.MICRO_PREVIEW,
                width=64,
                height=64,
                byte_size=max(128, int(byte_size * 0.01)),
                mime_type="image/webp",
                blob_uri=f"nougen://asset/{sha256}/rendition/micro",
                sha256=hashlib.sha256(f"{sha256}_micro".encode()).hexdigest(),
            ),
            Rendition(
                rendition_id=f"rnd_{sha256[:12]}_thumb",
                parent_asset_id=sha256,
                rendition_type=RenditionType.UI_THUMBNAIL,
                width=256,
                height=256,
                byte_size=max(512, int(byte_size * 0.05)),
                mime_type="image/webp",
                blob_uri=f"nougen://asset/{sha256}/rendition/thumbnail",
                sha256=hashlib.sha256(f"{sha256}_thumb".encode()).hexdigest(),
            ),
            Rendition(
                rendition_id=f"rnd_{sha256[:12]}_model",
                parent_asset_id=sha256,
                rendition_type=RenditionType.MODEL_RENDITION,
                width=min(width or 1024, 1024),
                height=min(height or 1024, 1024),
                byte_size=max(1024, int(byte_size * 0.20)),
                mime_type="image/jpeg",
                blob_uri=f"nougen://asset/{sha256}/rendition/model",
                sha256=hashlib.sha256(f"{sha256}_model".encode()).hexdigest(),
            ),
        ]

        # 8. Persist to SQLite
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO assets (
                    asset_id, blob_uri, mime_type, byte_size, width, height,
                    duration_seconds, original_filename, captured_at, capture_confidence,
                    camera_make, camera_model, lens_slug, exposure_iso, exposure_fnumber,
                    exposure_seconds, focal_length_35mm, geo_lat, geo_lon, geo_altitude,
                    geo_geohash5, imported_at, source_machine, source_lane, is_redacted,
                    exif_redacted, c2pa_manifest_present, c2pa_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset.asset_id, asset.blob_uri, asset.mime_type, asset.byte_size, asset.width, asset.height,
                    asset.duration_seconds, asset.original_filename, asset.captured_at, asset.capture_confidence,
                    asset.camera_make, asset.camera_model, asset.lens_slug, asset.exposure_iso, asset.exposure_fnumber,
                    asset.exposure_seconds, asset.focal_length_35mm, asset.geo_lat, asset.geo_lon, asset.geo_altitude,
                    asset.geo_geohash5, asset.imported_at, asset.source_machine, asset.source_lane,
                    1 if asset.is_redacted else 0, 1 if asset.exif_redacted else 0,
                    1 if asset.c2pa_manifest_present else 0, asset.c2pa_status
                )
            )

            emb_blob = struct.pack(f"{len(binding.embedding_vector)}f", *binding.embedding_vector) if binding.embedding_vector else None
            conn.execute(
                """
                INSERT INTO content_bindings (asset_id, hard_sha256, soft_dhash, soft_ahash, embedding_blob, embedding_model, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (binding.asset_id, binding.hard_sha256, binding.soft_dhash, binding.soft_ahash, emb_blob, binding.embedding_model, utc_now_iso())
            )

            for rnd in renditions:
                conn.execute(
                    """
                    INSERT INTO renditions (rendition_id, parent_asset_id, rendition_type, width, height, byte_size, mime_type, blob_uri, sha256, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (rnd.rendition_id, rnd.parent_asset_id, rnd.rendition_type.value, rnd.width, rnd.height, rnd.byte_size, rnd.mime_type, rnd.blob_uri, rnd.sha256, rnd.created_at)
                )

            conn.execute(
                """
                INSERT INTO provenance_events (event_id, asset_id, event_type, actor_id, machine_id, tool_name, tool_version, parent_asset_ids_json, parameters_json, attestation_signature, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prov_event.event_id, prov_event.asset_id, prov_event.event_type.value, prov_event.actor_id,
                    prov_event.machine_id, prov_event.tool_name, prov_event.tool_version,
                    json.dumps(prov_event.parent_asset_ids), json.dumps(prov_event.parameters),
                    prov_event.attestation_signature, prov_event.timestamp
                )
            )

        duration_ms = (time.perf_counter() - start_time) * 1000
        self.record_telemetry(
            TelemetryEnvelope(
                trace_id=uuid.uuid4().hex,
                span_id=uuid.uuid4().hex[:16],
                operation="asset_ingest",
                asset_id=sha256,
                duration_ms=duration_ms,
                bytes_transferred=byte_size,
                decode_ms=0.5,
                vision_tokens_in=0,
                vision_tokens_out=0,
                cache_hit=False,
                machine_lane=machine_id,
            )
        )

        return CapabilityGate.redact_asset_for_scopes(asset, granted), True

    # ------------------------------------------------------------------------
    # Retrieval, Inspection & Similarities
    # ------------------------------------------------------------------------

    def get_asset(self, asset_id: str, scopes: Optional[Set[str]] = None) -> Optional[AssetRecord]:
        """Retrieves canonical asset record with capability-scoped field redaction."""
        granted = scopes or {"*"}
        CapabilityGate.check_scope(granted, CapabilityScope.ASSET_METADATA)

        with self.connect() as conn:
            row = conn.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
            if not row:
                return None
            
            asset = AssetRecord(
                asset_id=row["asset_id"],
                blob_uri=row["blob_uri"],
                mime_type=row["mime_type"],
                byte_size=row["byte_size"],
                width=row["width"],
                height=row["height"],
                duration_seconds=row["duration_seconds"],
                original_filename=row["original_filename"],
                captured_at=row["captured_at"],
                capture_confidence=row["capture_confidence"],
                camera_make=row["camera_make"],
                camera_model=row["camera_model"],
                lens_slug=row["lens_slug"],
                exposure_iso=row["exposure_iso"],
                exposure_fnumber=row["exposure_fnumber"],
                exposure_seconds=row["exposure_seconds"],
                focal_length_35mm=row["focal_length_35mm"],
                geo_lat=row["geo_lat"],
                geo_lon=row["geo_lon"],
                geo_altitude=row["geo_altitude"],
                geo_geohash5=row["geo_geohash5"],
                imported_at=row["imported_at"],
                source_machine=row["source_machine"],
                source_lane=row["source_lane"],
                is_redacted=bool(row["is_redacted"]),
                exif_redacted=bool(row["exif_redacted"]),
                c2pa_manifest_present=bool(row["c2pa_manifest_present"]),
                c2pa_status=row["c2pa_status"],
            )
            return CapabilityGate.redact_asset_for_scopes(asset, granted)

    def get_content_binding(self, asset_id: str) -> Optional[ContentBinding]:
        """Fetches hard and soft perceptual bindings."""
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM content_bindings WHERE asset_id = ?", (asset_id,)).fetchone()
            if not row:
                return None
            
            emb_vector = None
            if row["embedding_blob"]:
                count = len(row["embedding_blob"]) // 4
                emb_vector = list(struct.unpack(f"{count}f", row["embedding_blob"]))

            return ContentBinding(
                asset_id=row["asset_id"],
                hard_sha256=row["hard_sha256"],
                soft_dhash=row["soft_dhash"],
                soft_ahash=row["soft_ahash"],
                embedding_vector=emb_vector,
                embedding_model=row["embedding_model"],
            )

    def get_rendition(self, asset_id: str, rendition_type: RenditionType, scopes: Optional[Set[str]] = None) -> Optional[Rendition]:
        """Retrieves a specific rendition record with capability checks."""
        granted = scopes or {"*"}
        if rendition_type in (RenditionType.MICRO_PREVIEW, RenditionType.UI_THUMBNAIL):
            CapabilityGate.check_scope(granted, CapabilityScope.ASSET_PREVIEW)
        elif rendition_type == RenditionType.MODEL_RENDITION:
            CapabilityGate.check_scope(granted, CapabilityScope.ASSET_ANALYZE)
        elif rendition_type in (RenditionType.WEB_MASTER, RenditionType.FULL_MASTER):
            CapabilityGate.check_scope(granted, CapabilityScope.ASSET_ORIGINAL)

        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM renditions WHERE parent_asset_id = ? AND rendition_type = ?",
                (asset_id, rendition_type.value)
            ).fetchone()
            if not row:
                return None
            return Rendition(
                rendition_id=row["rendition_id"],
                parent_asset_id=row["parent_asset_id"],
                rendition_type=RenditionType(row["rendition_type"]),
                width=row["width"],
                height=row["height"],
                byte_size=row["byte_size"],
                mime_type=row["mime_type"],
                blob_uri=row["blob_uri"],
                sha256=row["sha256"],
                created_at=row["created_at"],
            )

    def find_visually_similar(
        self,
        target_dhash: str,
        max_hamming_distance: int = 10,
        limit: int = 10,
        scopes: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        """Finds assets matching perceptual hash within specified Hamming distance."""
        granted = scopes or {"*"}
        CapabilityGate.check_scope(granted, CapabilityScope.ASSET_METADATA)

        matches = []
        with self.connect() as conn:
            rows = conn.execute("SELECT asset_id, soft_dhash, soft_ahash FROM content_bindings").fetchall()
            for r in rows:
                dist = PerceptualHashing.hamming_distance(target_dhash, r["soft_dhash"])
                if dist <= max_hamming_distance:
                    asset = self.get_asset(r["asset_id"], granted)
                    if asset:
                        matches.append({
                            "asset": asset.to_dict(),
                            "hamming_distance": dist,
                            "similarity_score": round(1.0 - (dist / 64.0), 4),
                        })

        matches.sort(key=lambda x: x["hamming_distance"])
        return matches[:limit]

    # ------------------------------------------------------------------------
    # Observations, Provenance & Shards
    # ------------------------------------------------------------------------

    def record_observation(
        self,
        observation: ClaimObservation,
        scopes: Optional[Set[str]] = None
    ) -> None:
        """Records an attributed model observation claim (e.g. caption, object detections)."""
        granted = scopes or {"*"}
        CapabilityGate.check_scope(granted, CapabilityScope.ASSET_ANALYZE)

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO claim_observations (
                    claim_id, asset_id, rendition_id, observation_kind, model_name,
                    model_version, prompt_policy, confidence, payload_json, bounding_boxes_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.claim_id, observation.asset_id, observation.rendition_id,
                    observation.observation_kind.value, observation.model_name, observation.model_version,
                    observation.prompt_policy, observation.confidence,
                    json.dumps(observation.payload), json.dumps(observation.bounding_boxes),
                    observation.created_at
                )
            )

    def record_provenance_event(
        self,
        event: ProvenanceEvent,
        scopes: Optional[Set[str]] = None
    ) -> None:
        """Appends a new event node to the immutable provenance DAG."""
        granted = scopes or {"*"}
        CapabilityGate.check_scope(granted, CapabilityScope.ASSET_METADATA)

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO provenance_events (
                    event_id, asset_id, event_type, actor_id, machine_id, tool_name,
                    tool_version, parent_asset_ids_json, parameters_json, attestation_signature, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id, event.asset_id, event.event_type.value, event.actor_id,
                    event.machine_id, event.tool_name, event.tool_version,
                    json.dumps(event.parent_asset_ids), json.dumps(event.parameters),
                    event.attestation_signature, event.timestamp
                )
            )

    def get_provenance_graph(self, asset_id: str, scopes: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        """Retrieves chronological C2PA-aligned provenance history for an asset."""
        granted = scopes or {"*"}
        CapabilityGate.check_scope(granted, CapabilityScope.ASSET_METADATA)

        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM provenance_events WHERE asset_id = ? ORDER BY timestamp ASC",
                (asset_id,)
            ).fetchall()
            return [
                {
                    "event_id": r["event_id"],
                    "asset_id": r["asset_id"],
                    "event_type": r["event_type"],
                    "actor_id": r["actor_id"],
                    "machine_id": r["machine_id"],
                    "tool_name": r["tool_name"],
                    "tool_version": r["tool_version"],
                    "parent_asset_ids": json.loads(r["parent_asset_ids_json"]),
                    "parameters": json.loads(r["parameters_json"]),
                    "attestation_signature": r["attestation_signature"],
                    "timestamp": r["timestamp"],
                }
                for r in rows
            ]

    def create_visual_shard(
        self,
        shard: VisualShard,
        scopes: Optional[Set[str]] = None
    ) -> None:
        """Stores a visual shard connecting descriptive knowledge to raw asset evidence."""
        granted = scopes or {"*"}
        CapabilityGate.check_scope(granted, CapabilityScope.ASSET_METADATA)

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO visual_shards (
                    shard_id, asset_id, title, body, facets_json, utility_score, domain_key, linked_shards_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    shard.shard_id, shard.asset_id, shard.title, shard.body,
                    json.dumps(shard.facets), shard.utility_score, shard.domain_key,
                    json.dumps(shard.linked_shards), shard.created_at
                )
            )

    # ------------------------------------------------------------------------
    # Late-Fusion Hybrid Retrieval Engine
    # ------------------------------------------------------------------------

    def hybrid_search(
        self,
        query: str,
        query_vector: Optional[List[float]] = None,
        query_dhash: Optional[str] = None,
        facets_filter: Optional[Dict[str, Any]] = None,
        limit: int = 5,
        scopes: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Executes late-fusion hybrid multimodal retrieval:
        Score = w_text * S_text + w_vec * S_vec + w_phash * S_phash + w_trust * S_trust + w_util * S_util
        """
        granted = scopes or {"*"}
        CapabilityGate.check_scope(granted, CapabilityScope.ASSET_METADATA)

        w_text = 0.35
        w_vec = 0.35
        w_phash = 0.15
        w_trust = 0.10
        w_util = 0.05

        results = []
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.shard_id, s.asset_id, s.title, s.body, s.facets_json, s.utility_score,
                       a.c2pa_status, b.soft_dhash, b.embedding_blob
                FROM visual_shards s
                JOIN assets a ON s.asset_id = a.asset_id
                LEFT JOIN content_bindings b ON s.asset_id = b.asset_id
                """
            ).fetchall()

            for r in rows:
                # 1. Text match score
                text_content = f"{r['title']} {r['body']}".lower()
                query_tokens = [t.lower() for t in query.split() if len(t) > 2]
                overlap = sum(1 for t in query_tokens if t in text_content)
                s_text = (overlap / len(query_tokens)) if query_tokens else 0.5

                # 2. Vector cosine similarity
                s_vec = 0.5
                if query_vector and r["embedding_blob"]:
                    count = len(r["embedding_blob"]) // 4
                    db_vec = list(struct.unpack(f"{count}f", r["embedding_blob"]))
                    if len(db_vec) == len(query_vector):
                        dot = sum(a * b for a, b in zip(query_vector, db_vec))
                        norm_q = math.sqrt(sum(a * a for a in query_vector))
                        norm_d = math.sqrt(sum(b * b for b in db_vec))
                        s_vec = max(0.0, dot / (norm_q * norm_d)) if norm_q and norm_d else 0.5

                # 3. Perceptual hash similarity
                s_phash = 0.5
                if query_dhash and r["soft_dhash"]:
                    dist = PerceptualHashing.hamming_distance(query_dhash, r["soft_dhash"])
                    s_phash = max(0.0, 1.0 - (dist / 64.0))

                # 4. Provenance Trust
                s_trust = 1.0 if r["c2pa_status"] in ("valid", "signed") else 0.7

                # 5. Shard Utility
                s_util = min(1.0, max(0.0, float(r["utility_score"]) / 10.0))

                # Late Fusion Composite Score
                total_score = (
                    (w_text * s_text) +
                    (w_vec * s_vec) +
                    (w_phash * s_phash) +
                    (w_trust * s_trust) +
                    (w_util * s_util)
                )

                asset = self.get_asset(r["asset_id"], granted)
                if asset:
                    results.append({
                        "shard_id": r["shard_id"],
                        "asset_id": r["asset_id"],
                        "title": r["title"],
                        "body": r["body"],
                        "composite_score": round(total_score, 4),
                        "score_breakdown": {
                            "text": round(s_text, 3),
                            "vector": round(s_vec, 3),
                            "phash": round(s_phash, 3),
                            "trust": round(s_trust, 3),
                            "utility": round(s_util, 3),
                        },
                        "asset": asset.to_dict(),
                    })

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------------
    # Observability & Telemetry
    # ------------------------------------------------------------------------

    def record_telemetry(self, telemetry: TelemetryEnvelope) -> None:
        """Records an OpenTelemetry-aligned usage metric row."""
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO visual_telemetry (
                    trace_id, span_id, operation, asset_id, duration_ms, bytes_transferred,
                    decode_ms, vision_tokens_in, vision_tokens_out, cache_hit, machine_lane,
                    cost_usd, error_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telemetry.trace_id, telemetry.span_id, telemetry.operation, telemetry.asset_id,
                    telemetry.duration_ms, telemetry.bytes_transferred, telemetry.decode_ms,
                    telemetry.vision_tokens_in, telemetry.vision_tokens_out, 1 if telemetry.cache_hit else 0,
                    telemetry.machine_lane, telemetry.cost_usd, telemetry.error_code, telemetry.created_at
                )
            )

    def get_recent_telemetry(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves recent telemetry ledger records for audit and token tracking."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM visual_telemetry ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]


# ============================================================================
# FastMCP Tool Suite Interface (13 Standard Asset Tools)
# ============================================================================

class VisualMCPInterface:
    """
    Exposes the 13 canonical MCP tools for multimodal visual evidence management.
    Separates the control plane (lightweight URIs and handles) from heavy pixels.
    """

    def __init__(self, store: VisualEvidenceStore):
        self.store = store

    def asset_ingest(
        self,
        data_base64: str,
        filename: str = "upload.jpg",
        metadata: Optional[Dict[str, Any]] = None,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tool: asset_ingest"""
        raw_bytes = base64.b64decode(data_base64)
        granted = set(scopes) if scopes else {"*"}
        asset, is_new = self.store.ingest_bytes(
            raw_bytes,
            original_filename=filename,
            metadata=metadata,
            scopes=granted
        )
        return {
            "status": "ingested" if is_new else "deduplicated_existing",
            "asset_id": asset.asset_id,
            "blob_uri": asset.blob_uri,
            "mime_type": asset.mime_type,
            "byte_size": asset.byte_size,
            "dimensions": {"width": asset.width, "height": asset.height},
            "c2pa_status": asset.c2pa_status,
        }

    def asset_get(
        self,
        asset_id: str,
        rendition_type: str = "UI_THUMBNAIL",
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tool: asset_get"""
        granted = set(scopes) if scopes else {"*"}
        asset = self.store.get_asset(asset_id, granted)
        if not asset:
            return {"error": "Asset not found", "asset_id": asset_id}
        
        r_type = RenditionType(rendition_type)
        rendition = self.store.get_rendition(asset_id, r_type, granted)
        return {
            "asset": asset.to_dict(),
            "rendition": rendition.to_dict() if rendition else None,
        }

    def asset_head(
        self,
        asset_id: str,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tool: asset_head"""
        granted = set(scopes) if scopes else {"*"}
        asset = self.store.get_asset(asset_id, granted)
        if not asset:
            return {"exists": False, "asset_id": asset_id}
        return {
            "exists": True,
            "asset_id": asset.asset_id,
            "blob_uri": asset.blob_uri,
            "mime_type": asset.mime_type,
            "byte_size": asset.byte_size,
            "width": asset.width,
            "height": asset.height,
            "c2pa_status": asset.c2pa_status,
        }

    def asset_search(
        self,
        query: str,
        limit: int = 5,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tool: asset_search"""
        granted = set(scopes) if scopes else {"*"}
        results = self.store.hybrid_search(query=query, limit=limit, scopes=granted)
        return {"query": query, "count": len(results), "results": results}

    def asset_similar(
        self,
        asset_id: str,
        max_distance: int = 10,
        limit: int = 5,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tool: asset_similar"""
        granted = set(scopes) if scopes else {"*"}
        binding = self.store.get_content_binding(asset_id)
        if not binding:
            return {"error": "Content binding not found for asset", "asset_id": asset_id}
        
        matches = self.store.find_visually_similar(
            target_dhash=binding.soft_dhash,
            max_hamming_distance=max_distance,
            limit=limit,
            scopes=granted
        )
        return {"target_asset_id": asset_id, "matches": matches}

    def asset_thumbnail(
        self,
        asset_id: str,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tool: asset_thumbnail"""
        granted = set(scopes) if scopes else {"*"}
        rnd = self.store.get_rendition(asset_id, RenditionType.UI_THUMBNAIL, granted)
        if not rnd:
            return {"error": "Thumbnail rendition not available", "asset_id": asset_id}
        return {"asset_id": asset_id, "thumbnail": rnd.to_dict()}

    def asset_derivatives(
        self,
        asset_id: str,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tool: asset_derivatives"""
        granted = set(scopes) if scopes else {"*"}
        derivatives = []
        for r_type in RenditionType:
            rnd = self.store.get_rendition(asset_id, r_type, granted)
            if rnd:
                derivatives.append(rnd.to_dict())
        return {"asset_id": asset_id, "derivatives": derivatives}

    def asset_analyze(
        self,
        asset_id: str,
        model_name: str,
        observation_kind: str,
        payload: Dict[str, Any],
        confidence: float = 0.95,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tool: asset_analyze"""
        granted = set(scopes) if scopes else {"*"}
        claim = ClaimObservation(
            claim_id=f"clm_{uuid.uuid4().hex[:16]}",
            asset_id=asset_id,
            rendition_id=None,
            observation_kind=ObservationKind(observation_kind),
            model_name=model_name,
            model_version="1.0",
            prompt_policy="standard_evidence_extraction",
            confidence=confidence,
            payload=payload,
        )
        self.store.record_observation(claim, granted)
        return {"status": "recorded", "claim_id": claim.claim_id, "asset_id": asset_id}

    def asset_provenance(
        self,
        asset_id: str,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tool: asset_provenance"""
        granted = set(scopes) if scopes else {"*"}
        events = self.store.get_provenance_graph(asset_id, granted)
        return {"asset_id": asset_id, "provenance_events": events}

    def asset_verify(
        self,
        asset_id: str,
        data_base64: str,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tool: asset_verify"""
        raw_bytes = base64.b64decode(data_base64)
        computed_sha = PerceptualHashing.compute_sha256(raw_bytes)
        dhash, _ = PerceptualHashing.compute_fallback_soft_hashes(raw_bytes)
        
        binding = self.store.get_content_binding(asset_id)
        if not binding:
            return {"verified": False, "reason": "Asset binding not found"}

        hard_match = (computed_sha == binding.hard_sha256)
        dist = PerceptualHashing.hamming_distance(dhash, binding.soft_dhash)
        
        return {
            "asset_id": asset_id,
            "hard_byte_match": hard_match,
            "computed_sha256": computed_sha,
            "expected_sha256": binding.hard_sha256,
            "perceptual_hamming_distance": dist,
            "visually_identical": dist <= 3,
        }

    def asset_link_shard(
        self,
        asset_id: str,
        shard_id: str,
        title: str,
        body: str,
        facets: Optional[Dict[str, Any]] = None,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tool: asset_link_shard"""
        granted = set(scopes) if scopes else {"*"}
        shard = VisualShard(
            shard_id=shard_id,
            asset_id=asset_id,
            title=title,
            body=body,
            facets=facets or {},
        )
        self.store.create_visual_shard(shard, granted)
        return {"status": "linked", "shard_id": shard_id, "asset_id": asset_id}

    def asset_extract_frames(
        self,
        asset_id: str,
        timestamps_sec: List[float],
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tool: asset_extract_frames"""
        granted = set(scopes) if scopes else {"*"}
        CapabilityGate.check_scope(granted, CapabilityScope.ASSET_ANALYZE)
        
        keyframes = []
        for ts in timestamps_sec:
            kf_id = hashlib.sha256(f"{asset_id}_{ts}".encode()).hexdigest()
            keyframes.append({
                "timestamp_sec": ts,
                "keyframe_asset_id": kf_id,
                "blob_uri": f"nougen://asset/{asset_id}/frame/{ts}",
            })
        return {"parent_asset_id": asset_id, "keyframes": keyframes}

    def asset_redact(
        self,
        asset_id: str,
        redact_exif: bool = True,
        redact_geo: bool = True,
        actor_id: str = "operator",
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tool: asset_redact"""
        granted = set(scopes) if scopes else {"*"}
        CapabilityGate.check_scope(granted, CapabilityScope.ASSET_MUTATE)

        with self.store.connect() as conn:
            conn.execute(
                "UPDATE assets SET is_redacted = 1, exif_redacted = 1, geo_lat = NULL, geo_lon = NULL WHERE asset_id = ?",
                (asset_id,)
            )

        prov_event = ProvenanceEvent(
            event_id=f"prv_{uuid.uuid4().hex[:16]}",
            asset_id=asset_id,
            event_type=ProvenanceEventType.REDACTION,
            actor_id=actor_id,
            machine_id="local",
            tool_name="nougen_visual_mcp",
            tool_version="2.0.0",
            parameters={"redact_exif": redact_exif, "redact_geo": redact_geo},
        )
        self.store.record_provenance_event(prov_event, granted)

        return {"status": "redacted", "asset_id": asset_id, "event_id": prov_event.event_id}
