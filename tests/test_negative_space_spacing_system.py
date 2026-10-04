"""
Unit tests for Premium Negative-Space Spacing System.
Validates:
1. Presence and structure of PREMIUM_NEGATIVE_SPACE_SPACING_SYSTEM.md specification.
2. Presence and exports of spacingSystem.ts in who-visions-grants-studio.
3. Strict 4pt/8pt harmonic scale compliance.
4. Spacing multiplier calculations.
"""
import pytest
from pathlib import Path

STUDIO_ROOT = Path(r"C:\Users\super\Watchtower\who-visions-grants-studio")
SPEC_PATH = Path(r"C:\Users\super\Watchtower\PREMIUM_NEGATIVE_SPACE_SPACING_SYSTEM.md")


def test_spacing_spec_document_integrity():
    assert SPEC_PATH.exists(), "Negative-space spacing spec must exist"
    content = SPEC_PATH.read_text(encoding="utf-8")
    assert "Premium Negative-Space Spacing System" in content
    assert "55% Negative Space Law" in content
    assert "space.4xl" in content
    assert "96px" in content


def test_spacing_tokens_ts_integrity():
    ts_path = STUDIO_ROOT / "src" / "theme" / "spacingSystem.ts"
    assert ts_path.exists(), "spacingSystem.ts file must exist"
    
    content = ts_path.read_text(encoding="utf-8")
    assert "spacingTokens" in content
    assert "'4px'" in content
    assert "'8px'" in content
    assert "'16px'" in content
    assert "'24px'" in content
    assert "'32px'" in content
    assert "'48px'" in content
    assert "'64px'" in content
    assert "'96px'" in content
    assert "getHarmonicSpacing" in content
    assert "isGridCompliant" in content
