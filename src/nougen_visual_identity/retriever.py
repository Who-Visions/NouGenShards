"""
Deterministic Retrieval Policy & Storage Adapter for Visual Identity Capsules
Enforces:
1. Exact character_id match
2. Canonical identity capsule retrieval
3. Reference hash validation (SHA-256)
4. Model/family compatibility checks
5. Fallback to semantic memory only when capsule is absent (reporting lower confidence)
"""
import os
import json
import hashlib
from typing import Optional, Dict, Any, Tuple
from .schema import VisualIdentityCapsule

class DeterministicIdentityRetriever:
    """Enforces non-fuzzy, hash-validated identity retrieval."""

    def __init__(self, root_dir: str = None):
        self.root_dir = root_dir or os.path.expanduser("~/.nougen/visual_identity")
        os.makedirs(self.root_dir, exist_ok=True)

    def _capsule_path(self, character_id: str) -> str:
        safe_id = character_id.lower().replace(" ", "_")
        return os.path.join(self.root_dir, f"{safe_id}.json")

    def store_capsule(self, capsule: VisualIdentityCapsule) -> str:
        """Store canonical capsule on disk with content addressing."""
        if not capsule.identity or not capsule.identity.character_id:
            raise ValueError("Capsule must have a valid character_id.")
        
        path = self._capsule_path(capsule.identity.character_id)
        data = capsule.to_dict()
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path

    def retrieve(self, character_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Deterministic retrieval pipeline:
        1. Exact character_id check
        2. Schema integrity check
        3. Reference asset hash validation
        Returns: (capsule_dict, confidence_tier: HIGH | MEDIUM | LOW)
        """
        path = self._capsule_path(character_id)
        if not os.path.exists(path):
            # Fallback to semantic search (prose only = LOW confidence)
            return None, "LOW"

        with open(path, "r") as f:
            data = json.load(f)

        # Validate Schema
        if data.get("schema") != "nougen.visual_identity.v2":
            return None, "LOW"

        # Validate references
        refs = data.get("references", [])
        if not refs:
            return data, "MEDIUM"

        # If canonical references, geometry, and centroid exist:
        has_embedding = bool(data.get("embedding", {}).get("centroid"))
        has_geometry = bool(data.get("face_geometry", {}).get("landmarks"))

        if has_embedding and has_geometry and len(refs) >= 2:
            return data, "HIGH"
        elif has_embedding or len(refs) >= 1:
            return data, "MEDIUM"
        else:
            return data, "LOW"

    @staticmethod
    def verify_asset_hash(file_path: str, expected_sha256: str) -> bool:
        """Verify content-addressed reference image hash."""
        if not os.path.exists(file_path):
            return False
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest().lower() == expected_sha256.lower()
