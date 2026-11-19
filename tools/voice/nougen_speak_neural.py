#!/usr/bin/env python3
import sys
import os
import argparse
import subprocess
from pathlib import Path
import numpy as np

# Ensure environment uses NouGenVoice venv
repo_root = Path(__file__).resolve().parent
venv_dir = str(repo_root / "NouGenVoice" / "backend" / "venv")
venv_bin = os.path.join(venv_dir, "bin")
os.environ["VIRTUAL_ENV"] = venv_dir
os.environ["PATH"] = f"{venv_bin}:{os.environ.get('PATH', '')}"

PERSONA_VOICE_MAP = {
    "emma": ("af_river", "a"),
    "rhea": ("af_bella", "a"),
    "rhea-noir": ("af_bella", "a"),
    "sarah": ("af_sarah", "a"),
    "nicole": ("af_nicole", "a"),
    "coach": ("bm_daniel", "b"),
    "daniel": ("bm_daniel", "b"),
    "heart": ("af_heart", "a"),
    "river": ("af_river", "a"),
    "koroko": ("af_river", "a"),
    "kokoro": ("af_river", "a"),
}

def resolve_persona_style(persona_name: str) -> str:
    """Hooks NouGenVoice personality resolver."""
    try:
        sys.path.insert(0, str(repo_root / "NouGenVoice"))
        from backend.services.personality import resolve_nougen_persona
        return resolve_nougen_persona(persona_name)
    except Exception:
        return persona_name

def speak_neural(text: str, voice: str = "af_river", lang_code: str | None = None, speed: float = 1.0, persona: str | None = None):
    if not text.strip():
        return

    if persona and persona.lower() in PERSONA_VOICE_MAP:
        mapped_voice, mapped_lang = PERSONA_VOICE_MAP[persona.lower()]
        voice = mapped_voice
        if lang_code is None:
            lang_code = mapped_lang
    
    # Vocal Rhythm v2 Multiscale Prosody Modulation
    effective_speed = speed
    try:
        shadow_src = repo_root / "ShadowDweller" / "src"
        if shadow_src.exists():
            sys.path.insert(0, str(shadow_src))
            from engine.vocal_rhythm_math import analyze_vocal_rhythm
            prosody = analyze_vocal_rhythm(text)
            if prosody.vocal_energy_slope > 0:
                effective_speed = round(min(1.30, speed * (1.0 + (prosody.vocal_energy_slope * 0.08))), 3)
            elif prosody.pause_occupancy > 0.3:
                effective_speed = round(max(0.90, speed * 0.96), 3)
    except Exception:
        pass

    from kokoro import KPipeline
    import soundfile as sf

    if lang_code is None:
        lang_code = "b" if voice.startswith("b") else "a"
    pipeline = KPipeline(lang_code=lang_code)
    generator = pipeline(text, voice=voice, speed=effective_speed)
    
    chunks = []
    for i, (gs, ps, audio) in enumerate(generator):
        chunks.append(audio)
        
    if chunks:
        full_audio = np.concatenate(chunks)
        out_wav = "/tmp/nougen_neural_speech.wav"
        sf.write(out_wav, full_audio, 24000)
        
        # Ensure unmuted 100% volume
        subprocess.run(["osascript", "-e", "set volume output volume 100 without output muted"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["afplay", out_wav])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NouGen Neural Voice Synthesizer")
    parser.add_argument("text", nargs="*", help="Text to speak")
    parser.add_argument("--persona", default=os.environ.get("NOUGEN_PERSONA"), help="Persona name (emma, rhea, coach, etc.)")
    parser.add_argument("--voice", default=os.environ.get("NOUGEN_VOICE", "af_river"), help="Kokoro voice tag")
    parser.add_argument("--speed", type=float, default=float(os.environ.get("NOUGEN_SPEED", "1.0")), help="Speech speed multiplier")
    args = parser.parse_args()

    if args.text:
        text_arg = " ".join(args.text)
        speak_neural(
            text_arg,
            voice=args.voice,
            speed=args.speed,
            persona=args.persona
        )
