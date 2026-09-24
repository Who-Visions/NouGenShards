#!/usr/bin/env python3
"""nougenvoice_say.py — give a fleet lane a voice through the local NouGenVoice backend.

NouGenVoice (Who-Visions/NouGenVoice, a NouGenMorph of jamiepine/voicebox, MIT) runs a FastAPI server on
http://127.0.0.1:17493 with 7 TTS engines. This client talks to it with nothing but the standard library, so any
lane on the box (Rhea, Kaedra, a relay watcher) can speak without importing torch.

    python nougenvoice_say.py "Olympus Mons, street level."                 # default persona: rhea
    python nougenvoice_say.py --persona kaedra --out clip.wav "text"          # write the wav somewhere specific
    python nougenvoice_say.py --list                                          # personas + backend health
    python nougenvoice_say.py --play "text"                                   # play it (Windows: winsound)

Personas map to NouGenVoice profiles (created on first use, Kokoro preset voices, CPU-friendly, ~1 s per 5 s of
speech on WhoArt's CPU). Engine and voice ids come from the backend's own preset list, never guessed here.
Exit codes: 0 ok, 2 backend down, 3 generation failed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("NOUGENVOICE_URL", "http://127.0.0.1:17493")
OUT_DIR = os.environ.get("NOUGENVOICE_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fleet", "voice"))

# persona -> (profile name, engine, preset voice id). Voice ids are Kokoro presets served by /profiles/presets/kokoro.
PERSONAS = {
    "rhea":   ("Rhea (Kokoro Heart)",  "kokoro", "af_heart"),
    "kaedra": ("Kaedra (Kokoro Nova)", "kokoro", "af_nova"),
    "dav1d":  ("Dav1d (Kokoro Adam)",  "kokoro", "am_adam"),
    "griot":  ("Griot (Kokoro Onyx)",  "kokoro", "am_onyx"),
}


def _req(method: str, path: str, body: dict | None = None, timeout: float = 30) -> tuple[int, bytes]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise SystemExit(f"nougenvoice: backend not reachable at {BASE} ({e}); start it with "
                         f"`cd Outpost/NouGenVoice && .venv/Scripts/python -m uvicorn backend.main:app --port 17493`") from None


def health() -> dict:
    code, b = _req("GET", "/health", timeout=5)
    if code != 200:
        raise SystemExit(2)
    return json.loads(b)


def ensure_profile(persona: str) -> str:
    name, engine, voice = PERSONAS[persona]
    code, b = _req("GET", "/profiles")
    for p in json.loads(b) if code == 200 else []:
        if p.get("name") == name:
            return p["id"]
    code, b = _req("POST", "/profiles", {"name": name, "description": f"NouGen fleet voice: {persona}", "language": "en",
                                         "voice_type": "preset", "preset_engine": engine, "preset_voice_id": voice,
                                         "default_engine": engine})
    if code != 200:
        raise SystemExit(f"nougenvoice: could not create profile {name}: {b[:200]!r}")
    return json.loads(b)["id"]


def say(text: str, persona: str = "rhea", out: str | None = None, timeout: float = 300) -> str:
    """Generate `text` in `persona`'s voice; return the wav path."""
    pid = ensure_profile(persona)
    engine = PERSONAS[persona][1]
    code, b = _req("POST", "/generate", {"profile_id": pid, "text": text, "engine": engine, "language": "en"}, timeout=timeout)
    if code != 200:
        raise SystemExit(f"nougenvoice: generate failed {code}: {b[:200]!r}")
    gid = json.loads(b)["id"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        code, b = _req("GET", f"/generate/{gid}/status", timeout=10)
        # the status route streams one SSE event; take the last JSON line
        line = [l for l in b.decode(errors="replace").splitlines() if l.startswith("data:")]
        st = json.loads(line[-1][5:]) if line else {}
        if st.get("status") == "completed":
            break
        if st.get("status") in ("failed", "error"):
            raise SystemExit(f"nougenvoice: generation {gid} failed: {st.get('error')}")
        time.sleep(0.5)
    else:
        raise SystemExit(f"nougenvoice: generation {gid} timed out")
    code, wav = _req("GET", f"/audio/{gid}", timeout=30)
    if code != 200:
        raise SystemExit(3)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = out or os.path.join(OUT_DIR, f"{persona}-{time.strftime('%Y%m%dT%H%M%S')}.wav")
    with open(path, "wb") as f:
        f.write(wav)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("text", nargs="?")
    ap.add_argument("--persona", default="rhea", choices=sorted(PERSONAS))
    ap.add_argument("--out")
    ap.add_argument("--play", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list or not a.text:
        h = health()
        print(f"backend {BASE}: {h.get('status')} · {h.get('backend_type')}/{h.get('backend_variant')} · model_loaded={h.get('model_loaded')}")
        for k, (n, e, v) in PERSONAS.items():
            print(f"  {k:8s} {n:24s} {e}:{v}")
        return 0
    path = say(a.text, a.persona, a.out)
    print(path)
    if a.play and sys.platform == "win32":
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME)
    return 0


if __name__ == "__main__":
    sys.exit(main())
