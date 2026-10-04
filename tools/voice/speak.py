#!/usr/bin/env python3
"""
NouGen Voice Gateway (speak.py)
Unified, local-first neural speech synthesis with hardware-bound speaker routing.
Priority: Kokoro-82M (af_bella studio neural voice) -> native fallback (device 181).
"""
import os
import sys
import subprocess
from pathlib import Path

DEFAULT_VOICE = os.environ.get("NOUGEN_VOICE", "af_river")
DEFAULT_SPEED = float(os.environ.get("NOUGEN_VOICE_SPEED", "1.05"))
DEVICE_ID = "181"  # Mac mini internal physical speaker
HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("NOUGEN_ROOT") or Path.home() / "The Observatory" / "NouGen")   # holds NouGenVoice/ and ShadowDweller/
VOICE_VENV = ROOT / "NouGenVoice" / "backend" / "venv" / "bin" / "python"
NEURAL_RUNNER = HERE / "nougen_speak_neural.py"

def get_dynamic_voice_and_speed(override_voice: str | None = None, override_speed: float | None = None) -> tuple[str, float]:
    try:
        sys.path.insert(0, str(HERE))
        from whoart_voice_sync import resolve_dynamic_voice
        v, s = resolve_dynamic_voice(override_voice)
        return v, (override_speed if override_speed is not None else s)
    except Exception:
        v = override_voice or os.environ.get("NOUGEN_VOICE", "af_river")
        s = override_speed if override_speed is not None else float(os.environ.get("NOUGEN_VOICE_SPEED", "1.05"))
        return v, s

def speak(text: str, voice: str | None = None, speed: float | None = None):
    if not text or not text.strip():
        return

    active_voice, active_speed = get_dynamic_voice_and_speed(voice, speed)

    # Guarantee volume is unmuted
    subprocess.run(["osascript", "-e", "set volume output volume 100 without output muted"], 
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Prefer the Kokoro installation already provisioned with NouGenVoice.
    # Its venv keeps the voice model and runtime versions aligned.
    if VOICE_VENV.is_file() and NEURAL_RUNNER.is_file():
        try:
            subprocess.run(
                [str(VOICE_VENV), str(NEURAL_RUNNER), text, "--voice", active_voice, "--speed", str(active_speed)],
                env={**os.environ, "NOUGEN_VOICE": active_voice, "NOUGEN_SPEED": str(active_speed)},
                check=True,
            )
            return
        except (OSError, subprocess.CalledProcessError):
            pass

    # 1. Primary: Multiscale Neural Synthesis with Vocal Rhythm v2 Dynamics
    try:
        from kokoro_onnx import Kokoro
        import soundfile as sf

        voice_dir = os.path.expanduser("~/.nougen/voices")
        model_path = os.path.join(voice_dir, "kokoro-v0_19.onnx")
        voices_path = os.path.join(voice_dir, "voices.bin")

        if os.path.exists(model_path) and os.path.exists(voices_path):
            kokoro = Kokoro(model_path, voices_path)
            lang = "en-gb" if active_voice.startswith("b") else "en-us"

            # Vocal Rhythm v2 Dynamics: Modulate articulation rate based on phrase emphasis
            effective_speed = active_speed
            try:
                shadow_engine = ROOT / "ShadowDweller" / "src"
                if shadow_engine.exists():
                    sys.path.insert(0, str(shadow_engine))
                    from engine.vocal_rhythm_math import analyze_vocal_rhythm
                    prosody = analyze_vocal_rhythm(text)
                    # Natural pace modulation: higher prominence accelerates, punctuation allows breath
                    if prosody.vocal_energy_slope > 0:
                        effective_speed = round(min(1.30, active_speed * (1.0 + (prosody.vocal_energy_slope * 0.08))), 3)
                    elif prosody.pause_occupancy > 0.3:
                        effective_speed = round(max(0.90, active_speed * 0.96), 3)
            except Exception:
                pass

            samples, sr = kokoro.create(text, voice=active_voice, speed=effective_speed, lang=lang)

            wav_path = f"/tmp/nougen_voice_{os.getpid()}.wav"
            sf.write(wav_path, samples, sr)

            subprocess.run(["afplay", wav_path], check=True)
            if os.path.exists(wav_path):
                os.remove(wav_path)
            return
    except Exception:
        pass

    # 2. Fallback: macOS native synthesis directed to Device 181
    try:
        subprocess.run(["say", f"--audio-device={DEVICE_ID}", "-v", "Samantha", text], check=True)
    except Exception:
        subprocess.run(["say", text])

if __name__ == "__main__":
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
        speak(message)
