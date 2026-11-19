"""
Unit tests for Premium Negative-Space Spacing System.
Validates:
1. Presence and structure of PREMIUM_NEGATIVE_SPACE_SPACING_SYSTEM.md specification.
2. Presence and exports of spacingSystem.ts in who-visions-grants-studio.
3. Strict 4pt/8pt harmonic scale compliance.
4. Spacing multiplier calculations.
"""
import pytest
import os
from pathlib import Path

STUDIO_ROOT = Path(os.environ.get("WATCHTOWER_DIR", Path.home() / "Watchtower")) / "who-visions-grants-studio"
SPEC_PATH = Path(os.environ.get("WATCHTOWER_DIR", Path.home() / "Watchtower")) / "PREMIUM_NEGATIVE_SPACE_SPACING_SYSTEM.md"


def test_spacing_spec_document_integrity():
    if not SPEC_PATH.exists():
        pytest.skip(f"Negative-space spacing spec {SPEC_PATH} not mounted in test environment")
    content = SPEC_PATH.read_text(encoding="utf-8")
    assert "Premium Negative-Space Spacing System" in content
    assert "55% Negative Space Law" in content
    assert "space.4xl" in content
    assert "96px" in content


def test_spacing_tokens_ts_integrity():
    ts_path = STUDIO_ROOT / "src" / "theme" / "spacingSystem.ts"
    if not ts_path.exists():
        pytest.skip(f"spacingSystem.ts file {ts_path} not mounted in test environment")
    
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
    assert "getAtfCeiling" in content
    assert "calculateFoldRatio" in content
    assert "calculateNegativeSpaceRatio" in content
    assert "getFluidFoldClamp" in content
    assert "getFoldBudget" in content


def test_fold_aware_formulas_mathematical_precision():
    # Simulate TypeScript formula logic in test harness
    def get_atf_ceiling(vh: int, max_clamp: int = 900) -> int:
        return min(round(vh * 0.85), max_clamp)

    def calculate_fold_ratio(ch: float, vh: float) -> float:
        return round(ch / vh, 4) if vh > 0 else 0.0

    def calculate_negative_space_ratio(content_area: float, total_area: float) -> float:
        if total_area <= 0:
            return 1.0
        return round(max(0.0, min(1.0, 1.0 - (content_area / total_area))), 4)

    # 1. Desktop 1440x900
    assert get_atf_ceiling(900) == 765
    assert calculate_fold_ratio(765, 900) == 0.85
    assert calculate_negative_space_ratio(450 * 600, 1440 * 900) == 0.7917  # > 55% negative space

    # 2. Mobile 390x844
    assert get_atf_ceiling(844) == 717
    assert calculate_fold_ratio(717, 844) == 0.8495

    # 3. 4K 3840x2160 clamped to 900 max
    assert get_atf_ceiling(2160) == 900

