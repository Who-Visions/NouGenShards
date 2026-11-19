#!/usr/bin/env python3
"""Blade-side runner for the vision-model war-game (run ON Blade, not here).

Stdlib only. Talks to Ollama on localhost:11434. Writes results.json next to
this script. Run from the folder that holds test-set/ :

  python run-on-blade.py --model qwen2.5vl:3b
  python run-on-blade.py --model moondream        (bulk-sweep comparison)

What it does, in order:
  1. Prints Ollama version + `ollama list` (which models are already pulled).
  2. Reads GPU VRAM used before load (nvidia-smi; if nvidia-smi is missing,
     prints NOT-MEASURED and continues).
  3. Loads the model with one warm-up call on a fixed frame, records VRAM used
     after load (the delta is the load receipt).
  4. Tokens/sec on the fixed prompt + fixed frame fh-001.jpg (Ollama's
     eval_count / eval_duration, plus wall time).
  5. Accuracy loop: every frame in test-set/manifest.json, same fixed prompt,
     records the model's JSON reply + timing per frame.
  6. Reads VRAM used after the loop and prints a one-line summary.

Nothing is uploaded anywhere. No fleet tools, no credentials, no writes
outside this folder. If `ollama pull` is needed, do it first by hand:
  ollama pull qwen2.5vl:3b     (~2 GB; verify the tag with `ollama list`
                                or search before pulling)
  ollama pull moondream        (~1.7 GB)
"""
import argparse, base64, json, os, subprocess, sys, time, urllib.request

FIXED_PROMPT = (
    "Count the vehicles visible in this traffic-camera frame at night in the rain. "
    "Reply with ONLY this JSON object, no other text: "
    '{"vehicles": <integer>, "conditions": "<one short phrase, e.g. night rain, wet road, droplets on lens>", '
    '"signal_visible": <true or false>, "notes": "<one sentence max>"}. '
    "Count every car, SUV, truck or bus you can see, including partial ones at the frame edges. "
    "Do not guess vehicles you cannot see."
)

OLLAMA = "http://127.0.0.1:11434"


def vram_used():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=30)
        used, total = out.stdout.strip().split(",")
        return {"used_mb": int(used), "total_mb": int(total)}
    except Exception as e:
        return {"used_mb": None, "total_mb": None, "error": f"NOT-MEASURED: {e}"}


def ollama_generate(model, prompt, image_b64, timeout=300):
    body = json.dumps({
        "model": model, "prompt": prompt,
        "images": [image_b64], "stream": False,
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(
        OLLAMA + "/api/generate", data=body,
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        res = json.load(r)
    return res, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--frames-dir", default="test-set")
    args = ap.parse_args()

    print("== ollama list ==")
    print(subprocess.run(["ollama", "list"], capture_output=True,
                         text=True, timeout=60).stdout)
    vram_before = vram_used()
    print("VRAM before load:", vram_before)

    manifest = json.load(open(os.path.join(args.frames_dir, "manifest.json")))
    sets = [("congress", manifest["congress"]), ("military", manifest["military"])]

    results = {"model": args.model, "fixed_prompt": FIXED_PROMPT,
               "vram_before": vram_before, "runs": []}

    # warm-up + load receipt on the fixed frame
    first = os.path.join(args.frames_dir, "frames-congress", "fh-001.jpg")
    b64 = base64.b64encode(open(first, "rb").read()).decode()
    res, wall = ollama_generate(args.model, FIXED_PROMPT, b64)
    vram_after_load = vram_used()
    results["vram_after_load"] = vram_after_load
    results["toks_per_sec"] = {
        "frame": "fh-001.jpg",
        "eval_count": res.get("eval_count"),
        "eval_duration_s": (res.get("eval_duration") or 0) / 1e9,
        "toks_per_sec": (res.get("eval_count") or 0) / ((res.get("eval_duration") or 1) / 1e9),
        "wall_s": round(wall, 2),
        "raw_reply": res.get("response"),
    }
    print("VRAM after load:", vram_after_load)
    print("tok/s (fh-001):", results["toks_per_sec"]["toks_per_sec"],
          "eval_count:", res.get("eval_count"))

    for set_name, s in sets:
        sub = "frames-congress" if set_name == "congress" else "frames-military"
        for fr in s["frames"]:
            path = os.path.join(args.frames_dir, sub, fr["file"])
            b64 = base64.b64encode(open(path, "rb").read()).decode()
            res, wall = ollama_generate(args.model, FIXED_PROMPT, b64)
            results["runs"].append({
                "set": set_name, "file": fr["file"],
                "sha256": fr["sha256"],
                "ground_truth_count": fr["ground_truth_count"],
                "model_reply": res.get("response"),
                "eval_count": res.get("eval_count"),
                "eval_duration_s": (res.get("eval_duration") or 0) / 1e9,
                "wall_s": round(wall, 2),
            })
            print(f"{set_name}/{fr['file']}: gt={fr['ground_truth_count']} "
                  f"wall={wall:.1f}s reply={str(res.get('response'))[:120]}")

    results["vram_after_loop"] = vram_used()
    print("VRAM after loop:", results["vram_after_loop"])
    out = f"results-{args.model.replace(':', '_').replace('/', '_')}.json"
    json.dump(results, open(out, "w"), indent=2, sort_keys=True)
    print("WROTE", out)


if __name__ == "__main__":
    main()
