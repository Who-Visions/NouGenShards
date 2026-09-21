"""Regression test for issue #350: relay_claim_leg/relay_ack_leg path traversal.

leg_id reaches _safe_claims_path from the MCP tool surface unsanitized.
Path's "/" operator does not normalize "..", so a crafted leg_id used to let
relay_claim_leg/relay_ack_leg write a claim/ack file outside claims_dir
(arbitrary file write). _safe_claims_path resolves the candidate path and
rejects it unless it stays inside claims_dir, which also catches absolute
paths and symlink escapes rather than only "../" segments.
"""
import sys
from pathlib import Path

import pytest

pytest.importorskip("gradio")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as node  # noqa: E402


def test_legitimate_leg_id_resolves_inside_claims_dir(tmp_path):
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    result = node._safe_claims_path(
        claims_dir, "20260914T190000Z__whoart__claude-cli", "__autonomous.json"
    )
    assert result.parent == claims_dir.resolve()
    assert result.name == "20260914T190000Z__whoart__claude-cli__autonomous.json"


def test_parent_dir_traversal_is_rejected(tmp_path):
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    with pytest.raises(ValueError):
        node._safe_claims_path(claims_dir, "../../../../etc/passwd", "__autonomous.json")


def test_absolute_path_leg_id_is_rejected(tmp_path):
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    with pytest.raises(ValueError):
        node._safe_claims_path(claims_dir, "/etc/cron.d/evil", "")


def test_symlink_escape_is_rejected(tmp_path):
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    # A leg_id naming a symlink that lives inside claims_dir but points
    # outside it must still be rejected once the path is resolved.
    (claims_dir / "escape_link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        node._safe_claims_path(claims_dir, "escape_link/pwned", "__autonomous.json")


def test_relay_claim_leg_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with pytest.raises(ValueError):
        node.relay_claim_leg.fn("../../../../etc/passwd")


def test_relay_ack_leg_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with pytest.raises(ValueError):
        node.relay_ack_leg.fn("../../../../etc/passwd", "artifact", "pass")
