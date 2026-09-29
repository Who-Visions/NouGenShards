"""Tenant-scoped capsule storage and deterministic local reference verification."""
import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional, Tuple

from .schema import VisualIdentityCapsule


_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_SEGMENT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")


class DeterministicIdentityRetriever:
    """Retrieve exact tenant and character identities without fuzzy fallback."""

    def __init__(self, root_dir: str = None):
        self.root_dir = Path(
            root_dir or os.path.expanduser("~/.nougen/visual_identity")
        ).expanduser().resolve()

    @staticmethod
    def _validate_segment(value: str, label: str) -> str:
        if not isinstance(value, str) or not _SEGMENT_PATTERN.fullmatch(value):
            raise ValueError(f"{label} must use lowercase letters, digits, '_' or '-'")
        return value

    def _capsule_path(self, character_id: str, tenant_id: str = "global") -> Path:
        tenant = self._validate_segment(tenant_id, "tenant_id")
        character = self._validate_segment(character_id, "character_id")
        path = (self.root_dir / tenant / character / "capsule.json").resolve()
        if os.path.commonpath((str(self.root_dir), str(path))) != str(self.root_dir):
            raise ValueError("Capsule path escapes the configured storage root")
        return path

    @staticmethod
    def _asset_path(capsule_dir: Path, uri: str) -> Optional[Path]:
        if not isinstance(uri, str) or not uri or "\\" in uri:
            return None
        relative = PurePosixPath(uri)
        if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
            return None
        path = (capsule_dir / Path(*relative.parts)).resolve()
        if os.path.commonpath((str(capsule_dir.resolve()), str(path))) != str(capsule_dir.resolve()):
            return None
        return path

    def store_capsule(self, capsule: VisualIdentityCapsule) -> str:
        """Atomically store a capsule under its tenant and exact character ID."""
        if not capsule.identity or not capsule.identity.character_id:
            raise ValueError("Capsule must have a valid character_id")
        tenant_id = capsule.identity.tenant_id
        path = self._capsule_path(capsule.identity.character_id, tenant_id)
        data = capsule.to_dict()
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(data, indent=2, allow_nan=False).encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".capsule-")
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return str(path)

    def retrieve(
        self, character_id: str, tenant_id: str = "global"
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Return a capsule only when identity and every local asset hash match."""
        path = self._capsule_path(character_id, tenant_id)
        if not path.is_file():
            return None, "LOW"
        try:
            with path.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, json.JSONDecodeError):
            return None, "LOW"

        if not isinstance(data, dict):
            return None, "LOW"
        identity = data.get("identity")
        if (
            data.get("schema") != "nougen.visual_identity.v2"
            or not isinstance(identity, dict)
            or identity.get("character_id") != character_id
            or identity.get("tenant_id", "global") != tenant_id
        ):
            return None, "LOW"

        references = data.get("references")
        if not isinstance(references, list) or not references:
            return data, "LOW"

        capsule_dir = path.parent
        for reference in references:
            if not isinstance(reference, dict) or not _SHA256_PATTERN.fullmatch(
                str(reference.get("sha256", ""))
            ):
                return None, "LOW"
            asset_path = self._asset_path(capsule_dir, reference.get("uri"))
            if asset_path is None or not self.verify_asset_hash(
                str(asset_path), reference["sha256"]
            ):
                return None, "LOW"

        embedding = data.get("embedding")
        centroid = embedding.get("centroid") if isinstance(embedding, dict) else None
        dimension = embedding.get("dimension") if isinstance(embedding, dict) else None
        has_embedding = (
            isinstance(centroid, list)
            and isinstance(dimension, int)
            and not isinstance(dimension, bool)
            and len(centroid) == dimension
            and dimension > 0
            and all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                for value in centroid
            )
            and any(value != 0.0 for value in centroid)
        )
        geometry = data.get("face_geometry")
        has_geometry = isinstance(geometry, dict) and bool(geometry.get("landmarks"))
        if has_embedding and has_geometry and len(references) >= 2:
            return data, "HIGH"
        return data, "MEDIUM"

    @staticmethod
    def verify_asset_hash(file_path: str, expected_sha256: str) -> bool:
        """Verify a local asset against a SHA-256 digest."""
        if not _SHA256_PATTERN.fullmatch(str(expected_sha256)):
            return False
        path = Path(file_path)
        if not path.is_file():
            return False
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    digest.update(chunk)
        except OSError:
            return False
        return digest.hexdigest().lower() == expected_sha256.lower()
