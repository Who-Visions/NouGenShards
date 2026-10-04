"""
Unit tests for Next.js and Three.js Intelligent Animation System.
Validates:
1. Presence and structure of ThreeGrantVisualizer.tsx.
2. Presence and structure of NEXTJS_THREEJS_ANIMATION_SYSTEM.md specification.
3. GPU lifecycle and idle conservation logic (visibilitychange listener, requestAnimationFrame).
4. Dual-state compliance palette rendering (Imperial Gold/Nyx Cyan for valid, Warning for invalid).
"""
from pathlib import Path

STUDIO_ROOT = Path(r"C:\Users\super\Watchtower\who-visions-grants-studio")
SPEC_PATH = Path(r"C:\Users\super\Watchtower\NEXTJS_THREEJS_ANIMATION_SYSTEM.md")


def test_animation_spec_document_integrity():
    assert SPEC_PATH.exists(), "Animation specification document must exist"
    content = SPEC_PATH.read_text(encoding="utf-8")
    assert "Next.js & Three.js Intelligent Animation System" in content
    assert "MeshPhysicalMaterial" in content
    assert "IntersectionObserver" in content or "visibilitychange" in content
    assert "Imperial Gold" in content


def test_threejs_component_integrity():
    comp_path = STUDIO_ROOT / "src" / "components" / "ThreeGrantVisualizer.tsx"
    assert comp_path.exists(), "ThreeGrantVisualizer component must exist"
    
    content = comp_path.read_text(encoding="utf-8")
    assert "ThreeGrantVisualizer" in content
    assert "visibilitychange" in content
    assert "requestAnimationFrame" in content
    assert "cancelAnimationFrame" in content
    assert "#D4AF37" in content  # Imperial Gold
    assert "#00FFCC" in content  # Nyx Cyan
    assert "isCompliant" in content
