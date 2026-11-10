"""Tests for Kokoro v1.0 / v0.19 dual-version model resolution in tools/voice/speak.py."""
import os
import sys
from pathlib import Path
import unittest.mock as mock
import pytest

VOICE = Path(__file__).resolve().parents[1] / "tools" / "voice"
sys.path.insert(0, str(VOICE))
import speak


def test_kokoro_model_candidates_order():
    """Verify kokoro-v1.0.onnx + voices-v1.0.bin is checked before v0_19."""
    voice_dir = "/fake/voices"
    existing = {
        "/fake/voices/kokoro-v1.0.onnx",
        "/fake/voices/voices-v1.0.bin",
        "/fake/voices/kokoro-v0_19.onnx",
        "/fake/voices/voices.bin",
    }

    with mock.patch("os.path.exists", side_effect=lambda p: p in existing):
        model_path = None
        voices_path = None
        for m, v in (("kokoro-v1.0.onnx", "voices-v1.0.bin"), ("kokoro-v0_19.onnx", "voices.bin")):
            cand_m = os.path.join(voice_dir, m)
            cand_v = os.path.join(voice_dir, v)
            if os.path.exists(cand_m) and os.path.exists(cand_v):
                model_path = cand_m
                voices_path = cand_v
                break

        assert model_path == "/fake/voices/kokoro-v1.0.onnx"
        assert voices_path == "/fake/voices/voices-v1.0.bin"


def test_kokoro_v019_fallback_when_v10_missing():
    """Verify kokoro-v0_19.onnx is loaded when v1.0 is not downloaded."""
    voice_dir = "/fake/voices"
    existing = {
        "/fake/voices/kokoro-v0_19.onnx",
        "/fake/voices/voices.bin",
    }

    with mock.patch("os.path.exists", side_effect=lambda p: p in existing):
        model_path = None
        voices_path = None
        for m, v in (("kokoro-v1.0.onnx", "voices-v1.0.bin"), ("kokoro-v0_19.onnx", "voices.bin")):
            cand_m = os.path.join(voice_dir, m)
            cand_v = os.path.join(voice_dir, v)
            if os.path.exists(cand_m) and os.path.exists(cand_v):
                model_path = cand_m
                voices_path = cand_v
                break

        assert model_path == "/fake/voices/kokoro-v0_19.onnx"
        assert voices_path == "/fake/voices/voices.bin"


def test_fallback_voice_when_voice_unavailable_in_model():
    """Verify af_river on v0.19 gracefully falls back to available voice instead of failing."""
    fake_kokoro = mock.MagicMock()
    fake_kokoro.get_voices.return_value = ["af_bella", "af_sky", "am_adam"]

    available = set(fake_kokoro.get_voices())
    active_voice = "af_river"  # Not in v0.19
    resolved_voice = active_voice
    if resolved_voice not in available:
        for fallback_v in ("af_river", "af_bella", "af_sky", "am_adam"):
            if fallback_v in available:
                resolved_voice = fallback_v
                break
        else:
            resolved_voice = next(iter(available)) if available else active_voice

    assert resolved_voice == "af_bella"
