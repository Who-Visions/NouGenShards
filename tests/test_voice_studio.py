"""Tests for wispr voice dictation and studio lighting in NouGen."""
import pytest
from nougen_shards import wispr, studio


def test_wispr_resolver():
    path = wispr.resolve_wispr_db()
    # It might be None if Wispr Flow is not installed on this specific OS test path,
    # but the function must return Optional[Path] without crashing
    assert path is None or isinstance(path, wispr.Path)


def test_studio_controllers():
    rz = studio.RazerController()
    assert "green" in rz.COLORS
    assert rz.COLORS["green"] == 0x00FF00

    lx = studio.LIFXController()
    assert isinstance(lx.is_configured(), bool)
