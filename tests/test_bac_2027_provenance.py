"""Test suite for BAC 2027 Sakura Soiree brand provenance & IP dossier validation."""
from pathlib import Path
import pytest

DOSSIER_PATH = Path(r"C:\Users\super\Watchtower\BAC_2027_SAKURA_SOIREE_DOSSIER.md")


def test_bac_2027_dossier_exists_and_has_required_sections():
    assert DOSSIER_PATH.exists(), f"Dossier must exist at {DOSSIER_PATH}"
    content = DOSSIER_PATH.read_text(encoding="utf-8")
    
    # Required sections
    assert "# 🌸 BAC 2027 Brand & Provenance Dossier: Sakura Soiree Lineage" in content
    assert "2024 Sakura Soiree" in content
    assert "IP & Licensing Audit" in content
    assert "2027 Evolved Mark Specification" in content
    assert "Who Visions Grant Engine" in content


def test_bac_2027_brand_tokens_and_provenance_motifs():
    content = DOSSIER_PATH.read_text(encoding="utf-8")
    
    # Provenance motifs
    assert "Heart Silhouette" in content or "Heart Mark" in content
    assert "cherry blossom" in content.lower()
    assert "butterfly" in content.lower()
    assert "purple" in content.lower() or "violet" in content.lower()
    
    # Color tokens
    assert "#6B2D5C" in content  # Royal Sakura Purple
    assert "#F7CAD0" in content  # Blossom Pink
    assert "#D4AF37" in content  # Imperial Gold
    assert "#0D0D11" in content  # Obsidian


def test_bac_2027_clean_chain_ip_enforcement():
    content = DOSSIER_PATH.read_text(encoding="utf-8")
    assert "sovereign copyright" in content.lower() or "clean-chain" in content.lower()
    assert "Who Visions LLC" in content
