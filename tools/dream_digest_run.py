"""Nightly dream-lane digest: extract last-24h transcript text, delegate summarization
to local Ollama (/v1/chat/completions), write digests to disk. 100% local, $0."""
import json, os, sys, time, urllib.request, glob, datetime, subprocess

from nougen_shards.brain_scan.redaction import redact_content

OLLAMA = "http://localhost:11434/v1/chat/completions"
TAGS = "http://localhost:11434/api/tags"
HOME = os.path.expanduser("~")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HOME, ".nougen", "dreams",
                   "work_" + datetime.date.today().strftime("%Y%m%d"))
CUTOFF = time.time() - 24 * 3600
# The dream-lane's OWN session transcript is in the 24h window while it runs.
# Digesting it just echoes tonight's instructions back. Set DREAM_SELF_SESSION
# to the running session id to skip it.
SELF_SESSION = os.environ.get("DREAM_SELF_SESSION", "")
HANDOFF_DIR = os.path.join(REPO_ROOT, ".handoffs")

# --- HARD VRAM GATE -------------------------------------------------------
# WhoArt is a 6 GB-VRAM box (RTX 4050 Laptop). Loading a model larger than the
# card spills into system RAM and thrashes the machine. Operator rule: never
# run 12B here. This gate refuses oversized models instead of degrading.
VRAM_SAFETY = 0.85
# Gate on MEASURED Ollama load size (/api/ps `size`), not disk size and not the
# vendor Q4_0 table. Three different numbers exist for the same model and they do
# not agree:
#   ollama disk        gemma4:e2b 7.2 GB   gemma4:e4b 9.6 GB
#   report bf16        E2B 4.6 GB          E4B 9.0 GB      (arXiv:2607.02770 Tab.3)
#   report mobile-QAT  E2B 0.8 GB          E4B 2.3 GB      (int2/int4 + int8 acts)
#   MEASURED on WhoArt E2B 7.51 GB         E4B 9.52 GB     (/api/ps, 2026-08-08)
# Ollama's e-series builds land near bf16 because per-layer embeddings (2.34B of
# E2B, 2.82B of E4B) are not compressed. So on a 6141 MiB card NEITHER fits, and
# both spill (measured 26% / 32% resident). The fix is the official QAT GGUFs
# (HF collections/google/gemma-4-qat-q4-0), not a different tag.
# KV cache is NOT the constraint: int8 KV at 32k is 0.05 GB (E2B) / 0.14 GB (E4B).
LOAD_GB = {
    "gemma4:e2b": 7.51, "Yukiai:e2b": 7.51, "solai:e2b": 7.51,
    "gemma4:e4b": 9.52, "Yukiai:e4b": 9.52, "solai:e4b": 9.52,
    "qwen3-vl:4b": 3.53,
    "gemma4:e2b-qat": 1.66,  # measured resident 2026-08-08; QAT pages PLE lazily
}
# Operator lane: the pinned RESIDENT (IRIS's model, gemma4:e2b-qat since
# 2026-08-08) is the primary — one model serves vision AND text, nothing else
# loads. Legacy full-fat personas listed after it will be gate-refused while
# anything is resident; that is correct.
PREFERRED = ["gemma4:e2b-qat", "Yukiai:e2b", "gemma4:e2b", "Yukiai:e4b", "gemma4:e4b"]
BANNED = {"gemma4:12b", "gemma4:26b", "gemma4:31b", "Yukiai:latest", "solai:latest"}
# Gemma 4 E-series emit a `reasoning` field that eats the budget; below ~900 the
# visible content comes back EMPTY. Measured 2026-08-08. Root cause: a <|think|>
# token in a leading system turn activates thinking (tech report Table 11).
# Raised 900 -> 2048 on independent confirmation: Chiaberge et al. 2026
# (arXiv:2606.00415) ran these same models on llama.cpp and found --n-predict 2048
# "essential to prevent silent output truncation in verbose prompt variants, which
# otherwise caused JSON parse errors on galaxies that elicited long reasoning
# chains." Same failure mode, same models, more headroom. Take theirs.
MIN_MAX_TOKENS = 2048
# 2026-08-08: spill CRASHED WhoArt. Running a 7.5-9.5 GB model against a 6141 MiB
# card with qwen3-vl:4b resident (3.53 GB) ran VRAM+RAM to the ceiling and took the
# box down mid-session. Spill is not "slow but works" on this machine — it is a
# crash. Default OFF. If nothing fits: degrade to the fleet-down fork (handoffs-only)
# or wait for the QAT GGUFs (E4B 2.3 GB / E2B 0.8 GB) which fit outright.
ALLOW_SPILL = False


def total_vram_bytes():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=30)
        return int(out.stdout.strip().splitlines()[0]) * 1024 * 1024
    except Exception:
        return 0


def pick_model():
    """Return the largest PREFERRED model that fits the VRAM budget, else abort."""
    with urllib.request.urlopen(TAGS, timeout=30) as r:
        installed = {m["name"]: m["size"] for m in json.loads(r.read())["models"]}
    vram = total_vram_bytes()
    if not vram:
        raise SystemExit("VRAM GATE: cannot read nvidia-smi; refusing to guess. Aborting.")
    budget = int(vram * VRAM_SAFETY)
    print(f"VRAM GATE: total={vram/1e9:.2f} GB  budget={budget/1e9:.2f} GB")
    chosen = spill = None
    for name in PREFERRED:
        if name in BANNED or name not in installed:
            continue
        need = LOAD_GB.get(name)
        if need is None:
            print(f"VRAM GATE: skip {name} (no measured load size on file)")
            continue
        if need * 1e9 <= budget:
            chosen = (name, need)
            break
        print(f"VRAM GATE: {name} needs {need:.2f} GB > budget {budget/1e9:.2f} GB")
        spill = spill or (name, need)
    if not chosen and spill and ALLOW_SPILL:
        print(f"VRAM GATE: WARNING nothing fits; running {spill[0]} SPILLED to CPU "
              f"({spill[1]:.2f} GB vs {budget/1e9:.2f} GB budget). Slow but local and $0. "
              "Pull the QAT GGUFs to fix properly.")
        chosen = spill
    if not chosen:
        raise SystemExit(
            "VRAM GATE: no installed gemma model available at all. "
            "Refusing to fall back to cloud. Aborting (fleet-down fork).")
    print(f"VRAM GATE: using {chosen[0]} ({chosen[1]:.2f} GB measured load)")
    return chosen[0]


MODEL = None

SYSTEM = (
    "You are a memory-curation digester. You read a raw agent session transcript and "
    "extract ONLY durable, reusable knowledge. Output terse markdown with these sections, "
    "omitting any section that is empty:\n"
    "## Decisions made\n## Facts stated by the operator\n## Corrections\n"
    "## Preferences\n## Contradicts prior knowledge\n"
    "Each bullet: one sentence, plus a short verbatim quote in double-quotes when available. "
    "No preamble, no summary of what the agent did mechanically. Skip tool noise, file dumps, "
    "and routine coding steps. If nothing durable is present, output exactly: NOTHING DURABLE."
)


def extract(path):
    """Pull user/assistant text turns from a claude-code jsonl transcript."""
    turns = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            msg = rec.get("message")
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            content = msg.get("content")
            parts = []
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        parts.append(b.get("text") or "")
            text = "\n".join(p for p in parts if p).strip()
            if not text:
                continue
            # drop system-reminder blobs and tool-result echoes
            if text.startswith("<system-reminder>") or "<local-command-stdout>" in text:
                continue
            turns.append(redact_content(f"[{role}] {text}"))
    return turns


def chunk(turns, max_chars=28000):
    buf, size, out = [], 0, []
    for t in turns:
        t = t[:6000]
        if size + len(t) > max_chars and buf:
            out.append("\n\n".join(buf))
            buf, size = [], 0
        buf.append(t)
        size += len(t)
    if buf:
        out.append("\n\n".join(buf))
    return out


def _is_resident(model):
    """True if `model` is currently pinned in Ollama (e.g. by IRIS)."""
    try:
        with urllib.request.urlopen(
                "http://localhost:11434/api/ps", timeout=10) as r:
            return model in {m.get("name") for m in
                             json.loads(r.read()).get("models", [])}
    except Exception:
        return False


def inference_preflight(model):
    """Prove the selected model can load and execute before writing digests.

    `/api/tags` only proves that a manifest exists. A tiny completion exercises
    the runner binary, model load, and generation path that the digest actually
    depends on.
    """
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with OK."}],
        "temperature": 0,
        "max_tokens": 64,
        "stream": False,
    }
    if not _is_resident(model):
        body["keep_alive"] = 0
    req = urllib.request.Request(
        OLLAMA, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            data = json.loads(response.read().decode())
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("completion response contained no choices")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ValueError("completion response contained no message")
    except Exception as exc:
        raise SystemExit(
            f"INFERENCE PREFLIGHT FAILED for {model}: {exc}. "
            "No dream digests were written.") from exc
    print(f"INFERENCE PREFLIGHT: {model} generated successfully")


def ask(prompt, model=None, retries=3):
    """Digest one chunk with an EMPTY-OUTPUT GATE (operator rule 2026-08-08:
    responses must persistently never come back empty).

    Gemma 4 E-series spend budget on a reasoning channel first — too small a
    max_tokens returns EMPTY content with no error. So: verify non-empty,
    and on an empty response DOUBLE the budget and reverify. keep_alive is
    only forced to 0 for NON-resident models; unloading the resident (IRIS's
    pinned model) would evict the watcher's model after every call.
    """
    model = model or MODEL
    if not model:
        raise RuntimeError("ask() requires a selected model")
    resident = _is_resident(model)
    last = "ERROR: exhausted retries"
    tokens = MIN_MAX_TOKENS
    for i in range(retries):
        body_d = {
            "model": model,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": redact_content(prompt)}],
            "temperature": 0.2,
            "max_tokens": tokens,
            "stream": False,
        }
        if not resident:
            body_d["keep_alive"] = 0
        try:
            req = urllib.request.Request(
                OLLAMA, data=json.dumps(body_d).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as r:
                data = json.loads(r.read().decode())
            content = (data["choices"][0]["message"].get("content") or "").strip()
            if content:
                return redact_content(content)
            last = f"ERROR: EMPTY_OUTPUT at max_tokens={tokens}"
            tokens *= 2  # reasoning ate the budget — reverify with double
        except Exception as e:
            last = f"ERROR: {e}"
            time.sleep(5)
    return last


def handoff_turns(path):
    """A handoff .md is already prose — feed it to the digester as one turn."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read().strip()
    return [redact_content(f"[handoff {os.path.basename(path)}]\n{text}")] if text else []


def main(source_paths=None):
    global MODEL
    MODEL = pick_model()
    inference_preflight(MODEL)
    os.makedirs(OUT, exist_ok=True)
    root = os.path.join(HOME, ".claude", "projects")
    if source_paths:
        files = [os.path.abspath(p) for p in source_paths
                 if os.path.isfile(p) and p.lower().endswith(".jsonl")]
    else:
        files = [p for p in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)
                 if os.path.getmtime(p) >= CUTOFF
                 and (not SELF_SESSION or SELF_SESSION not in p)]
    print(f"transcripts in 24h: {len(files)}")
    index = []

    # --- handoffs (last 24h) — digested first; they are the densest source ---
    hos = [] if source_paths else [
        p for p in glob.glob(os.path.join(HANDOFF_DIR, "**", "*.md"), recursive=True)
        if os.path.getmtime(p) >= CUTOFF]
    print(f"handoffs in 24h: {len(hos)}")
    if hos:
        turns = []
        for p in sorted(hos):
            turns += handoff_turns(p)
        digests = []
        chunks = chunk(turns)
        for i, c in enumerate(chunks):
            d = ask(f"Source: NouGen handoff notes (chunk {i+1}/{len(chunks)})\n\n"
                    f"--- HANDOFFS ---\n{c}\n--- END ---")
            digests.append(f"### chunk {i+1}/{len(chunks)}\n{d}")
            print(f"  handoff chunk {i+1} done ({len(d)} chars)")
        outp = os.path.join(OUT, "handoffs.digest.md")
        with open(outp, "w", encoding="utf-8") as f:
            f.write("# digest: handoffs (last 24h)\nsources:\n"
                    + "".join(f"- {p}\n" for p in sorted(hos)) + "\n"
                    + "\n\n".join(digests))
        index.append(outp)

    for p in sorted(files):
        turns = extract(p)
        if not turns:
            print(f"SKIP (no text turns): {p}")
            continue
        chunks = chunk(turns)
        print(f"{os.path.basename(p)}: {len(turns)} turns -> {len(chunks)} chunk(s)")
        digests = []
        for i, c in enumerate(chunks):
            d = ask(f"Session file: {os.path.basename(p)} (chunk {i+1}/{len(chunks)})\n\n"
                    f"--- TRANSCRIPT ---\n{c}\n--- END ---")
            digests.append(f"### chunk {i+1}/{len(chunks)}\n{d}")
            print(f"  chunk {i+1} done ({len(d)} chars)")
        outp = os.path.join(OUT, os.path.basename(p).replace(".jsonl", "") + ".digest.md")
        with open(outp, "w", encoding="utf-8") as f:
            f.write(f"# digest: {p}\nproject: {os.path.basename(os.path.dirname(p))}\n"
                    f"mtime: {datetime.datetime.fromtimestamp(os.path.getmtime(p))}\n\n"
                    + "\n\n".join(digests))
        index.append(outp)
    print("WROTE:")
    for i in index:
        print(" ", i)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
