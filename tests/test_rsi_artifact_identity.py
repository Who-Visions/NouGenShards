"""Tests for RSI artifact identity, canonical representations, and domain-separated hashing."""

import unittest
from nougen_shards.rsi_artifact_identity import (
    ArtifactDescriptor,
    InvalidArtifactError,
    canonical_json_bytes,
    create_artifact_descriptor,
    hash_artifact_bytes,
    verify_artifact_integrity,
)


class RSIArtifactIdentityTests(unittest.TestCase):
    def test_canonical_json_bytes_ordering(self):
        d1 = {"b": 2, "a": 1, "c": [3, 2, 1]}
        d2 = {"a": 1, "c": [3, 2, 1], "b": 2}
        self.assertEqual(canonical_json_bytes(d1), canonical_json_bytes(d2))
        self.assertEqual(canonical_json_bytes(d1), b'{"a":1,"b":2,"c":[3,2,1]}')

    def test_domain_separation_prevents_hash_collision(self):
        raw = b"candidate_evaluation_code_x"
        code_hash = hash_artifact_bytes("candidate_code", raw)
        data_hash = hash_artifact_bytes("dataset_manifest", raw)
        self.assertNotEqual(code_hash, data_hash)
        self.assertEqual(len(code_hash), 64)
        self.assertEqual(len(data_hash), 64)

    def test_create_and_verify_string_artifact(self):
        text = "def candidate_solution(): return 42\n"
        desc = create_artifact_descriptor(
            artifact_type="python_source",
            artifact_id="cand_42",
            content=text,
            metadata={"author": "sol-ai", "epoch": "epoch-1"},
        )
        self.assertEqual(desc.artifact_type, "python_source")
        self.assertEqual(desc.artifact_id, "cand_42")
        self.assertEqual(desc.byte_size, len(text.encode("utf-8")))
        self.assertTrue(verify_artifact_integrity(desc, text))
        self.assertFalse(verify_artifact_integrity(desc, text + " "))

    def test_create_and_verify_json_artifact(self):
        payload = {"hyperparameters": {"lr": 0.001, "batch_size": 32}}
        desc = create_artifact_descriptor(
            artifact_type="hyperparameters",
            artifact_id="hp_cfg_01",
            content=payload,
        )
        self.assertTrue(verify_artifact_integrity(desc, payload))
        mutated = {"hyperparameters": {"lr": 0.002, "batch_size": 32}}
        self.assertFalse(verify_artifact_integrity(desc, mutated))

    def test_invalid_artifact_descriptor_validation(self):
        with self.assertRaises(InvalidArtifactError):
            create_artifact_descriptor("", "valid_id", "content")

        with self.assertRaises(InvalidArtifactError):
            create_artifact_descriptor("type", "", "content")

        with self.assertRaises(InvalidArtifactError):
            ArtifactDescriptor(
                artifact_type="type",
                artifact_id="id",
                content_hash="short_hash",
                byte_size=10,
                metadata={},
            )


if __name__ == "__main__":
    unittest.main()
