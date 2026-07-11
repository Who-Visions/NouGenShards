"""arXiv shard semantic tagger (arxiv-evolution Move 3).

Tags each arXiv intelligence shard with 1-5 topic tags using embedding-nearest
matching against a controlled vocabulary (local nomic-embed via ollama), gated
by a relative margin off the paper's top score (strong tags only, no quota).
Reuse-first: no new tags are minted here — papers below the similarity floor
get the 'uncategorized' tag for a later fleet review pass (tag-explosion guard).

Idempotent and non-destructive: shards that already carry a `tags:` frontmatter
line are skipped; the tagger only inserts one line, never rewrites content.
Dynamic per Rule 0.2: vault/model/URL/thresholds env-resolved with probes.
"""
import os
import re
import sys
import json
import glob
import math
import argparse
import urllib.request

OLLAMA_URL = os.environ.get("NOUGEN_OLLAMA_URL", "http://127.0.0.1:11434")
MAX_TAGS = int(os.environ.get("NOUGEN_TAG_MAX", "5"))
SIM_FLOOR = float(os.environ.get("NOUGEN_TAG_SIM_FLOOR", "0.45"))
# nomic cosine scores compress into ~0.55-0.75; an absolute floor alone passes
# everything, so tags must also sit within REL_MARGIN of the paper's top score.
REL_MARGIN = float(os.environ.get("NOUGEN_TAG_REL_MARGIN", "0.06"))
EMBED_CHARS = int(os.environ.get("NOUGEN_TAG_EMBED_CHARS", "1200"))

# Controlled vocabulary: tag -> short description embedded for matching.
# Extend via NOUGEN_TAG_VOCAB_JSON (path to {tag: description} JSON).
VOCAB = {
    "llm-agents": "autonomous LLM agents, agentic workflows, long-horizon tasks",
    "agent-memory": "memory systems for agents, context retention, episodic memory banks",
    "multi-agent": "multi-agent systems, orchestration, collaboration, delegation between agents",
    "rag-retrieval": "retrieval-augmented generation, retrievers, grounding, faithfulness to context",
    "context-compression": "context window management, prompt/context compression, token reduction",
    "tool-use": "LLM tool calling, function calling, API use by models",
    "evals-benchmarks": "benchmarks, evaluation suites, leaderboards, metrics for models or agents",
    "reasoning": "chain-of-thought, reasoning models, planning, test-time compute",
    "reinforcement-learning": "reinforcement learning, RLHF, GRPO, policy optimization",
    "fine-tuning-distillation": "fine-tuning, knowledge distillation, SFT, LoRA, model compression",
    "quantization-efficiency": "quantization, pruning, sparsity, inference efficiency",
    "local-edge-inference": "on-device or edge inference, consumer hardware, mobile deployment",
    "moe-architecture": "mixture-of-experts and novel model architectures",
    "embeddings-vectors": "embedding models, vector search, semantic similarity, representation learning",
    "safety-security": "AI safety, security, jailbreaks, prompt injection, alignment",
    "privacy": "privacy, PII protection, federated learning, unlearning",
    "code-generation": "code generation, coding agents, software engineering with LLMs",
    "vision-multimodal": "vision-language models, multimodal learning, video, image understanding",
    "speech-audio": "speech, audio models, text-to-speech, audio understanding",
    "robotics-embodied": "robotics, embodied agents, vision-language-action models",
    "knowledge-graphs": "knowledge graphs, structured knowledge, symbolic integration",
    "training-dynamics": "training methods, optimization, scaling laws, learning dynamics",
    "data-synthesis": "synthetic data generation, data curation, dataset construction",
    "healthcare-science": "medical, biology, chemistry, scientific discovery applications",
}


def _resolve_vault_root():
    env = os.environ.get("NOUGEN_VAULT_DIR")
    if env:
        return env
    try:
        with open(os.path.join(os.path.expanduser("~"), ".nougen", "config.json"), encoding="utf-8") as f:
            vd = json.load(f).get("vault_dir")
        if vd:
            return vd
    except Exception:
        pass
    return r"C:\Users\super\Watchtower\vault"


def _resolve_embed_model():
    env = os.environ.get("NOUGEN_EMBED_MODEL")
    if env:
        return env
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
            models = [m["name"] for m in json.loads(r.read())["models"]]
        embed = [m for m in models if "embed" in m.lower()]
        if embed:
            return embed[0]
    except Exception as e:
        print(f"embed-model probe failed: {e}", file=sys.stderr)
    return "nomic-embed-text:latest"


def _load_vocab():
    path = os.environ.get("NOUGEN_TAG_VOCAB_JSON")
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return VOCAB


def embed(model, texts):
    payload = json.dumps({"model": model, "input": texts}).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/embed", data=payload, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["embeddings"]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", required=True, help="announce day YYYY-MM-DD (published_date match)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    vault = _resolve_vault_root()
    model = _resolve_embed_model()
    vocab = _load_vocab()
    print(f"embed model: {model}, vocab: {len(vocab)} tags", file=sys.stderr)

    tag_names = list(vocab.keys())
    tag_vecs = embed(model, [f"{t}: {d}" for t, d in vocab.items()])

    tagged, skipped, uncategorized = 0, 0, 0
    tag_counts = {}
    for path in glob.iglob(os.path.join(vault, "intelligence_shard_arxiv_*.md")):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if f"published_date: {args.day}" not in text:
            continue
        fm = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if not fm or re.search(r"^tags:", fm.group(1), re.MULTILINE):
            skipped += 1
            continue
        tm = re.search(r"^# (.+)$", text, re.MULTILINE)
        am = re.search(r"## Abstract\n(.*?)(?:\n---|\Z)", text, re.DOTALL)
        doc = f"{tm.group(1) if tm else ''}\n{(am.group(1) if am else '')[:EMBED_CHARS]}"

        vec = embed(model, [doc])[0]
        scored = sorted(((cosine(vec, tv), tn) for tv, tn in zip(tag_vecs, tag_names)), reverse=True)
        top_score = scored[0][0]
        picks = [tn for s, tn in scored[:MAX_TAGS]
                 if s >= SIM_FLOOR and s >= top_score - REL_MARGIN]
        if not picks:
            picks = ["uncategorized"]
            uncategorized += 1
        tags_line = f"tags: [{', '.join(picks)}]"

        new_text = text.replace("\n---\n", f"\n{tags_line}\n---\n", 1)
        if not args.dry_run:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_text)
        tagged += 1
        for t in picks:
            tag_counts[t] = tag_counts.get(t, 0) + 1

    print(json.dumps({
        "day": args.day, "tagged": tagged, "skipped_already_tagged": skipped,
        "uncategorized": uncategorized,
        "top_tags": dict(sorted(tag_counts.items(), key=lambda kv: -kv[1])[:8]),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
