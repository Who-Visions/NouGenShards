"""NOU talking head: one still + one voice line -> one audio-driven take (locked 2026-11-06).

One pass of OmniAvatar (HF Space alexnasa/OmniAvatar) drives head, eyes, brows and lips from the
audio together. Never animate first and lip-sync on top: that is what looked pieced together.

The free ZeroGPU tier renders about 5 s of audio per job, so a longer line is cut at its pauses
and each chunk starts from the last frame of the one before. When an account's quota runs out
the next Hugging Face account from the Keymaker takes the job.

    python -m nougen_shards.talkinghead still.png line.wav out.mp4
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

SPACE = "alexnasa/OmniAvatar"
CHUNK = 4.6  # seconds of audio per job; the Space cuts at ~5 s
STEPS = 4    # 8 steps asks for more GPU than one free job allows
PROMPT = ("A realistic video of a news anchor speaking calmly and warmly to the camera in a studio, "
          "natural head and eye movement, blinking, subtle shoulder motion")
LAST = ", she finishes and gives a warm small smile."
# Key NAMES only; values stay in the Keymaker.
ACCOUNTS = ["HUGGINGFACE_KEY_WHOVISIONSLLC_GMAIL_COM", "HUGGINGFACE_KEY_NOUGENAI_GMAIL_COM",
            "HUGGINGFACE_KEY_AIWITHDAV3_GMAIL_COM", "HUGGINGFACE_KEY_CONTACT_WHOVISIONS_COM",
            "HUGGINGFACE_KEY_DAVE_WHOVISIONS_COM", "HUGGINGFACE_KEY_DAVEMERALUS_GMAIL_COM",
            "HUGGINGFACE_KEY_SUPERDAVEWHO_GMAIL_COM", "HUGGINGFACE_KEY_EATSRUGER_GMAIL_COM",
            "HUGGINGFACE_KEY_RICKSPANISHWHO_GMAIL_COM", "HUGGINGFACE_KEY_EDIEBRIKELL12_GMAIL_COM",
            "HUGGINGFACE_KEY_WHOENTERTAINS_GMAIL_COM_02", "HF_TOKEN"]


def pauses(silencedetect_log: str) -> list[float]:
    """Midpoints of the pauses ffmpeg's silencedetect reported."""
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", silencedetect_log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", silencedetect_log)]
    return [(s + e) / 2 for s, e in zip(starts, ends) if s > 0]


def cuts(duration: float, gaps: list[float], chunk: float = CHUNK) -> list[float]:
    """Cut points so no chunk runs past `chunk` seconds, cutting at the latest pause that fits."""
    out, start = [], 0.0
    while duration - start > chunk:
        fit = [g for g in gaps if start + 1.0 < g <= start + chunk]
        start = fit[-1] if fit else start + chunk
        out.append(round(start, 3))
    return out


def _ff(*args: str) -> str:
    return subprocess.run(["ffmpeg", "-v", "info", "-y", *args], capture_output=True, text=True, check=True).stderr


def _duration(path: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(path)], capture_output=True, text=True, check=True).stdout)


def _render(img: Path, wav: Path, prompt: str, out: Path, accounts: list[str]) -> str:
    """Try each account until one has quota. Returns the key name that rendered it."""
    from gradio_client import Client, handle_file
    from nougen_shards import keymaker
    errors = []
    while accounts:
        name = accounts[0]
        try:
            c = Client(SPACE, token=keymaker.get_secret(name), verbose=False)
            try:
                c.predict(api_name="/start_session")
            except Exception:
                pass
            r = c.predict(handle_file(str(img)), handle_file(str(wav)), prompt, STEPS, api_name="/infer_scene")
            shutil.copy(r.get("video", r) if isinstance(r, dict) else r, out)
            return name
        except Exception as e:  # quota, cold start, or a missing key: move to the next account
            errors.append(f"{name}: {str(e)[:80]}")
            accounts.pop(0)
    raise RuntimeError("no account could render: " + "; ".join(errors))


def make(still: Path, audio: Path, out: Path, prompt: str = PROMPT, accounts: list[str] | None = None) -> dict:
    accounts = list(accounts or ACCOUNTS)
    dur = _duration(audio)
    points = cuts(dur, pauses(_ff("-i", str(audio), "-af", "silencedetect=n=-35dB:d=0.12", "-f", "null", "-")))
    bounds = [0.0, *points, dur]
    used, clips = [], []
    with tempfile.TemporaryDirectory() as tmp:
        t, img = Path(tmp), still
        for i, (a, b) in enumerate(zip(bounds, bounds[1:])):
            last = i == len(bounds) - 2
            wav, clip = t / f"{i}.wav", t / f"{i}.mp4"
            _ff("-ss", str(a), "-t", str(b - a), "-i", str(audio), *(["-af", "apad=pad_dur=0.6"] if last else []), str(wav))
            used.append(_render(img, wav, prompt + (LAST if last else "."), clip, accounts))
            clips.append(clip)
            img = t / f"{i}.png"
            _ff("-sseof", "-0.05", "-i", str(clip), "-frames:v", "1", str(img))
        ins = [x for c in clips for x in ("-i", str(c))]
        parts = "".join(f"[{i}:v]fps=24,{'trim=start_frame=1,' if i else ''}setpts=PTS-STARTPTS[v{i}];"
                        for i in range(len(clips)))
        cat = "".join(f"[v{i}][{i}:a]" for i in range(len(clips)))
        _ff(*ins, "-filter_complex", f"{parts}{cat}concat=n={len(clips)}:v=1:a=1[v][a];"
            "[v]scale=720:1296:flags=lanczos,format=yuv420p[o]", "-map", "[o]", "-map", "[a]",
            "-c:v", "libx264", "-crf", "17", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out))
    return {"out": str(out), "seconds": round(_duration(out), 2), "cuts": points, "accounts": used}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("still", type=Path)
    ap.add_argument("audio", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--prompt", default=PROMPT)
    a = ap.parse_args(argv)
    print(make(a.still, a.audio, a.out, a.prompt))


if __name__ == "__main__":
    main()
