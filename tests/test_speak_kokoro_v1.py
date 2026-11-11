"""Kokoro v1.0 / v0.19 model resolution and voice fallback in tools/voice/speak.py.

These call the real speak() with the Kokoro runtime, soundfile and macOS commands
replaced by fakes, so they fail if the resolution or fallback logic changes.
"""
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SPEAK_PATH = Path(__file__).resolve().parents[1] / "tools" / "voice" / "speak.py"


def _load_speak():
    spec = importlib.util.spec_from_file_location("speak_under_test", SPEAK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeKokoro:
    instances = []
    voices = ["af_bella", "af_sky", "am_adam"]

    def __init__(self, model, voices):
        self.model, self.voices_path = model, voices
        self.calls = []
        _FakeKokoro.instances.append(self)

    def get_voices(self):
        return list(self.voices)

    def create(self, text, voice, speed, lang):
        self.calls.append({"voice": voice, "speed": speed, "lang": lang})
        return [0.0] * 10, 24000


class KokoroResolutionTests(unittest.TestCase):
    def setUp(self):
        self.speak = _load_speak()
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.voices = self.home / ".nougen" / "voices"
        self.voices.mkdir(parents=True)
        _FakeKokoro.instances = []

        fake_kokoro = types.ModuleType("kokoro_onnx")
        fake_kokoro.Kokoro = _FakeKokoro
        fake_sf = types.ModuleType("soundfile")
        fake_sf.write = mock.MagicMock()
        self.sf = fake_sf
        patches = [
            mock.patch.dict(sys.modules, {"kokoro_onnx": fake_kokoro, "soundfile": fake_sf}),
            mock.patch.object(self.speak, "VOICE_VENV", self.home / "no-venv"),
            mock.patch.object(self.speak, "ROOT", self.home / "no-root"),
            mock.patch.object(self.speak.subprocess, "run", mock.MagicMock()),
            mock.patch.object(self.speak.os.path, "expanduser",
                              side_effect=lambda p: str(self.home / ".nougen" / "voices") if p == "~/.nougen/voices" else p),
            mock.patch.object(self.speak, "get_dynamic_voice_and_speed", return_value=("af_river", 1.0)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.run_mock = self.speak.subprocess.run
        self.addCleanup(self.tmp.cleanup)

    def _touch(self, *names):
        for n in names:
            (self.voices / n).write_bytes(b"x")

    def test_prefers_v1_model_when_both_files_present(self):
        self._touch("kokoro-v1.0.onnx", "voices-v1.0.bin", "kokoro-v0_19.onnx", "voices.bin")
        self.speak.speak("hello")
        k = _FakeKokoro.instances[-1]
        self.assertTrue(k.model.endswith("kokoro-v1.0.onnx"))
        self.assertTrue(k.voices_path.endswith("voices-v1.0.bin"))

    def test_falls_back_to_v019_when_v1_missing(self):
        self._touch("kokoro-v0_19.onnx", "voices.bin")
        self.speak.speak("hello")
        k = _FakeKokoro.instances[-1]
        self.assertTrue(k.model.endswith("kokoro-v0_19.onnx"))

    def test_v1_needs_both_files_or_it_is_skipped(self):
        self._touch("kokoro-v1.0.onnx", "kokoro-v0_19.onnx", "voices.bin")  # voices-v1.0.bin missing
        self.speak.speak("hello")
        k = _FakeKokoro.instances[-1]
        self.assertTrue(k.model.endswith("kokoro-v0_19.onnx"))

    def test_unavailable_voice_falls_back_to_available_one(self):
        self._touch("kokoro-v0_19.onnx", "voices.bin")
        self.speak.speak("hello")
        k = _FakeKokoro.instances[-1]
        self.assertEqual(k.calls[-1]["voice"], "af_bella")  # af_river is not in the model
        self.assertEqual(k.calls[-1]["lang"], "en-us")

    def test_available_requested_voice_is_kept(self):
        self._touch("kokoro-v1.0.onnx", "voices-v1.0.bin")
        with mock.patch.object(self.speak, "get_dynamic_voice_and_speed", return_value=("am_adam", 1.0)):
            self.speak.speak("hello")
        k = _FakeKokoro.instances[-1]
        self.assertEqual(k.calls[-1]["voice"], "am_adam")

    def test_no_model_files_uses_native_fallback(self):
        self.speak.speak("hello")
        self.assertEqual(_FakeKokoro.instances, [])
        last = self.run_mock.call_args_list[-1].args[0]
        self.assertEqual(last[0], "say")


if __name__ == "__main__":
    unittest.main()
