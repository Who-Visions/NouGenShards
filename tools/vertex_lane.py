"""
NouGen VERTEX LANE — Google Cloud Vertex AI as fleet routes.

Vertex exposes an OpenAI-compatible surface at
    {host}/v1/projects/{PROJECT}/locations/{LOC}/endpoints/openapi/chat/completions
so a Vertex route slots into fleet.py's route dict unchanged, with two
differences from every other lane:

1. **The bearer token expires.** gcloud access tokens live ~60 min, so the
   Authorization header cannot be baked into the route dict the way an
   OpenRouter key is. Routes carry a ``token_fn`` callable instead and
   fleet._call mints the header at request time (cached, refreshed at 55 min).

2. **This lane is BILLED.** Every other lane in the registry is free tier or
   local GPU. Vertex bills the attached Cloud Billing account per token, so it
   is OFF by default — opt in with Fleet(include_vertex=True) or
   NOUGEN_VERTEX=1. It is NOT a "free agent" lane under Rule 0.3.

Verified 2026-08-15: both projects below answer on location ``global``, and
Gemini 3.x text IS reachable (3.1-pro-preview, 3.5/3.6/3.7-flash,
3.1-flash-lite). Only some ids are dead — ``gemini-3-pro-preview`` and
``gemini-3-flash`` 404, while ``gemini-3.1-pro-preview`` works. Check the live
publisher catalogue before assuming a family is missing:

    GET {loc}-aiplatform.googleapis.com/v1beta1/publishers/google/models
        ?pageSize=200          (needs header x-goog-user-project: <billed proj>)

Image generation lives in vertex_image.py — it needs the native
:generateContent surface, not the OpenAI shim used here.

Usage
-----
    from vertex_lane import vertex_routes
    routes = vertex_routes()          # [] if gcloud/ADC is not usable

    from fleet import Fleet
    f = Fleet(include_vertex=True)
    f.probe()

CLI
---
    python vertex_lane.py             # show routes + live probe
"""
from __future__ import annotations
import json, os, subprocess, sys, threading, time

# Projects with billing enabled AND aiplatform reachable (checked 2026-08-15).
# endless-duality-480201-t3 and project-049eaecf-3887-48a2-af5 both 403 on
# billing — left out deliberately, adding them just manufactures dead routes.
VERTEX_PROJECTS = [
    ("cw", "project-c76da12d-f33f-4525-b1f"),
    ("gl", "gen-lang-client-0751460202"),
]

# location -> host. "global" has the widest model coverage; regional hosts are
# {region}-aiplatform.googleapis.com and are only needed for pinned residency.
VERTEX_LOCATION = "global"

# (tag, publisher model, min_tokens). Gemini 2.5 spends a hidden reasoning
# budget BEFORE emitting content -- pro burned 172 reasoning tokens to answer
# "OK". Too small a max_tokens returns empty content with HTTP 200 and no
# error, which reads as a dead route. Same trap as the Gemma 4 E-series.
VERTEX_MODELS = [
    ("pro",        "google/gemini-3.1-pro-preview", 1400),
    ("flash",      "google/gemini-3.7-flash",       1400),
    # 3.1-flash-lite shuts down 2027-05-07; 3.5 is its documented replacement.
    ("flash-lite", "google/gemini-3.5-flash-lite",   800),
]
# Also live if you want an older/cheaper vote: google/gemini-2.5-pro,
# -2.5-flash, -2.5-flash-lite, google/gemini-3.5-flash, -3.6-flash.

_TOKEN_TTL = 40 * 60          # gcloud tokens last ~60 min. 40 not 55: a
                              # 55-minute cache still produced mid-run 401s
                              # under concurrent load (2026-08-15, 42 of them).
_tok_lock = threading.Lock()
_tok_cache: dict = {"value": None, "exp": 0.0}


def _host(location: str) -> str:
    return ("https://aiplatform.googleapis.com" if location == "global"
            else f"https://{location}-aiplatform.googleapis.com")


def access_token(force: bool = False) -> str:
    """Current gcloud access token, cached until it nears expiry.

    Threadsafe: fleet.probe() hits every route from a 16-wide pool, and without
    the lock each worker would shell out to gcloud simultaneously.
    """
    with _tok_lock:
        now = time.time()
        if not force and _tok_cache["value"] and now < _tok_cache["exp"]:
            return _tok_cache["value"]
        out = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, shell=(os.name == "nt"),
        )
        if out.returncode != 0:
            raise RuntimeError(f"gcloud auth failed: {out.stderr.strip()[:200]}")
        tok = out.stdout.strip()
        if not tok:
            raise RuntimeError("gcloud returned an empty access token")
        _tok_cache.update(value=tok, exp=now + _TOKEN_TTL)
        return tok


def vertex_routes(location: str = VERTEX_LOCATION,
                  projects: list | None = None,
                  models: list | None = None) -> list[dict]:
    """Vertex routes in fleet.py's route shape. Empty list if gcloud is unusable."""
    try:
        access_token()
    except Exception as ex:
        print(f"[vertex] lane unavailable: {ex}", file=sys.stderr)
        return []
    host = _host(location)
    routes = []
    for ptag, project in (projects or VERTEX_PROJECTS):
        base = f"{host}/v1/projects/{project}/locations/{location}/endpoints/openapi"
        for mtag, model, min_tokens in (models or VERTEX_MODELS):
            routes.append({
                "name": f"vertex-{ptag}-{mtag}",
                "url": base,
                "model": model,
                "headers": {},              # filled per call from token_fn
                "kind": "vertex",
                "token_fn": access_token,
                "min_tokens": min_tokens,
                "vendor": "google-vertex",
                "billed": True,
            })
    return routes


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from fleet import Fleet

    rts = vertex_routes()
    print(f"{len(rts)} vertex routes ({len(VERTEX_PROJECTS)} projects "
          f"x {len(VERTEX_MODELS)} models) @ location={VERTEX_LOCATION}")
    for r in rts:
        print(f'  {r["name"]:<22} {r["model"]}')
    if "--no-probe" in sys.argv:
        sys.exit(0)
    print("\n  BILLED LANE -- this probe costs money.\n")
    f = Fleet(include_local=False, include_vertex=True)
    f.routes = [r for r in f.routes if r["kind"] == "vertex"]
    f.probe()
