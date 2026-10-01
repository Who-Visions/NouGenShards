"""Programmatic verification of the locked NouGen Origin Chronology."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
CHRONO_PATH = REPO_ROOT / "NOUGEN_ORIGIN_CHRONOLOGY.md"


def test_chronology_document_exists():
    assert CHRONO_PATH.exists(), "NOUGEN_ORIGIN_CHRONOLOGY.md must exist at repo root"
    content = CHRONO_PATH.read_text(encoding="utf-8")
    assert len(content) > 1000


def test_dual_birth_milestones_present():
    content = CHRONO_PATH.read_text(encoding="utf-8")
    
    # 1. NouGen Naming / Agent OS Genesis (Feb 16-18, 2026)
    assert "February 16, 2026" in content or "Feb 16, 2026" in content
    assert "February 17, 2026" in content
    assert "Valerion" in content
    assert "February 18, 2026" in content
    assert "NOUGENAI_OS_STRATEGY.md" in content
    
    # 2. Sol-Ai Genesis (Apr 6, 2026)
    assert "April 6, 2026" in content
    assert "sol.py" in content
    
    # 3. Shards Storage Genesis (Apr 11-15, 2026)
    assert "April 11, 2026" in content
    assert "migrate_to_shards.py" in content
    assert "memory -> shards" in content or "memory" in content
    assert "April 15, 2026" in content
    assert "Council of Shards" in content
    
    # 4. Mesh Expansion & May 19 Convergence
    assert "May 6, 2026" in content
    assert "May 7, 2026" in content
    assert "Netlify" in content
    assert "Cloudflare" in content
    assert "May 19, 2026" in content
    assert "Convergence" in content
    
    # 5. ArXiv footnote caveat
    assert "ArXiv" in content
    assert "NouGenAi-Orchestrator" in content
