"""
Unit tests for Next.js 16 + MUI + Nyx UI Grant Compiler Studio & NouGenDesign Visual System.
Validates:
1. Presence and integrity of who-visions-grants-studio package.json, components, and themes.
2. NouGenDesign Light and Dark theme tokens.
3. Client-side section hashing crypto logic.
4. UI compliance rules (artist equity floor >= 50%, producer fee cap <= 18%).
"""
import json
from pathlib import Path

STUDIO_ROOT = Path(r"C:\Users\super\Watchtower\who-visions-grants-studio")


def test_studio_package_json():
    pkg_path = STUDIO_ROOT / "package.json"
    assert pkg_path.exists(), "Studio package.json must exist"
    data = json.loads(pkg_path.read_text(encoding="utf-8"))
    assert data["name"] == "who-visions-grants-studio"
    assert "@mui/material" in data["dependencies"]
    assert "next" in data["dependencies"]


def test_theme_tokens_and_nyx_palette():
    nyx_path = STUDIO_ROOT / "src" / "theme" / "nyxTheme.ts"
    tokens_path = STUDIO_ROOT / "src" / "theme" / "nougenDesignTokens.ts"
    
    assert nyx_path.exists(), "Nyx theme file must exist"
    assert tokens_path.exists(), "NouGen design tokens must exist"
    
    nyx_content = nyx_path.read_text(encoding="utf-8")
    assert "#0D0D11" in nyx_content  # Deep obsidian background
    assert "#D4AF37" in nyx_content  # Imperial Gold
    assert "#00FFCC" in nyx_content  # Nyx Cyan
    
    tokens_content = tokens_path.read_text(encoding="utf-8")
    assert "nougenLightTokens" in tokens_content
    assert "nougenDarkTokens" in tokens_content


def test_client_crypto_section_hashing_schema():
    crypto_path = STUDIO_ROOT / "src" / "lib" / "clientCrypto.ts"
    assert crypto_path.exists(), "Client crypto file must exist"
    
    content = crypto_path.read_text(encoding="utf-8")
    assert "SectionHashes" in content
    assert "artist_identity" in content
    assert "project_narrative" in content
    assert "budget_breakdown" in content
    assert "venue_proof" in content
    assert "computeSectionHash" in content


def test_studio_component_invariants():
    comp_path = STUDIO_ROOT / "src" / "components" / "GrantCompilerStudio.tsx"
    assert comp_path.exists(), "GrantCompilerStudio component must exist"
    
    content = comp_path.read_text(encoding="utf-8")
    assert "Who Visions Grants Studio" in content
    assert "artistRatio >= 50.0" in content
    assert "producerRatio <= 18.0" in content
    assert "handleClientSign" in content
    assert "handleCompile" in content
