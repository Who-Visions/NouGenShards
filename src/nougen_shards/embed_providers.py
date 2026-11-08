"""Embedding providers: ollama (server), onnx (in-process, no server), none.

Why (wargame muse-review-elevations-20261107, E2): on any box without an Ollama
server the semantic lane is dead and recall is keyword-only. An in-process ONNX
sentence model (all-MiniLM-L6-v2, 384-d, CPU) needs no server and answers in
tens of milliseconds, so a fresh install gets semantic recall by default once
the model file is present.

Selection (``NOUGEN_EMBED_PROVIDER``):
  auto   (default) ollama if ``NOUGEN_EMBED_MODEL`` names an ollama model and the
         server answers; otherwise onnx if its deps and model file are present;
         otherwise none. The choice is cached per process and logged once.
  ollama / onnx / none  force a provider.

Model spec: ``NOUGEN_EMBED_MODEL`` stays the ollama model name by default
(``nomic-embed-text``). ``onnx:<hf_repo>`` selects the onnx provider with that
repo; the default repo is ``sentence-transformers/all-MiniLM-L6-v2``.

Dimensions differ between providers (nomic 768, MiniLM 384). The vector cache
groups a DB's rows by the first dimension it sees and the lane only scores a
cache whose dimension equals the query's, so a mixed vault degrades to the
majority provider rather than producing wrong scores. ``nougen embed status``
reports the mix. Switching providers means a backfill.

Model files are never downloaded implicitly. ``nougen embed fetch`` downloads
them (or set ``NOUGEN_EMBED_AUTO_DOWNLOAD=1``). They live under
``~/.nougen/models/<repo>/``.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import urllib.request
from pathlib import Path
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_MODEL = "nomic-embed-text"
DEFAULT_ONNX_REPO = "sentence-transformers/all-MiniLM-L6-v2"
#: Files fetched from the repo. ``NOUGEN_ONNX_FILE`` overrides the weights
#: (e.g. ``onnx/model_quint8_avx2.onnx`` for the 23 MB quantized build).
DEFAULT_ONNX_FILE = "onnx/model.onnx"
TOKENIZER_FILE = "tokenizer.json"
MAX_TOKENS = 256

_LOCK = threading.Lock()
_RESOLVED: Optional[tuple] = None          # (provider, model)
_SESSIONS: dict = {}                       # repo -> (session, tokenizer, input_names)


def models_dir() -> Path:
    base = os.environ.get("NOUGEN_MODELS_DIR") or os.path.join(os.path.expanduser("~"), ".nougen", "models")
    return Path(base)


def model_dir(repo: str = DEFAULT_ONNX_REPO) -> Path:
    return models_dir() / repo.replace("/", "__")


def onnx_files_present(repo: str = DEFAULT_ONNX_REPO) -> bool:
    d = model_dir(repo)
    return (d / Path(_onnx_file()).name).exists() and (d / TOKENIZER_FILE).exists()


def _onnx_file() -> str:
    return os.environ.get("NOUGEN_ONNX_FILE", DEFAULT_ONNX_FILE)


def onnx_deps_present() -> bool:
    try:
        import onnxruntime  # noqa: F401  pylint: disable=import-outside-toplevel,unused-import
        import tokenizers  # noqa: F401  pylint: disable=import-outside-toplevel,unused-import
        return True
    except Exception:
        return False


def _parse_model_spec(spec: Optional[str]) -> tuple[str, str]:
    """'onnx:repo' -> ('onnx', repo); anything else -> ('ollama', name)."""
    spec = (spec or os.environ.get("NOUGEN_EMBED_MODEL") or DEFAULT_OLLAMA_MODEL).strip()
    if spec.lower().startswith("onnx:"):
        return "onnx", spec[5:].strip() or DEFAULT_ONNX_REPO
    if spec.lower() == "onnx":
        return "onnx", DEFAULT_ONNX_REPO
    return "ollama", spec


def _ollama_reachable(timeout_s: float = 0.4) -> bool:
    from .embedding_backfill import ollama_host  # pylint: disable=import-outside-toplevel
    try:
        with urllib.request.urlopen(f"{ollama_host()}/api/tags", timeout=timeout_s) as r:
            return r.status == 200
    except Exception:
        return False


def resolve(model: Optional[str] = None, refresh: bool = False) -> tuple[str, str]:
    """Return (provider, model). Cached per process; ``refresh`` re-probes."""
    global _RESOLVED  # pylint: disable=global-statement
    with _LOCK:
        if _RESOLVED is not None and not refresh and model is None:
            return _RESOLVED
        forced = os.environ.get("NOUGEN_EMBED_PROVIDER", "auto").strip().lower()
        kind, name = _parse_model_spec(model)
        if forced == "none":
            out = ("none", "")
        elif forced == "onnx":
            out = ("onnx", name if kind == "onnx" else DEFAULT_ONNX_REPO)
        elif forced == "ollama":
            out = ("ollama", name if kind == "ollama" else DEFAULT_OLLAMA_MODEL)
        elif kind == "onnx":
            out = ("onnx", name)
        elif _ollama_reachable():
            out = ("ollama", name)
        elif onnx_deps_present() and onnx_files_present(DEFAULT_ONNX_REPO):
            out = ("onnx", DEFAULT_ONNX_REPO)
            logger.info("embed provider: ollama not reachable; using in-process onnx (%s)", DEFAULT_ONNX_REPO)
        else:
            out = ("none", name)
        if model is None:
            _RESOLVED = out
        return out


def provider_status() -> dict:
    provider, name = resolve(refresh=True)
    return {
        "provider": provider, "model": name,
        "forced": os.environ.get("NOUGEN_EMBED_PROVIDER", "auto"),
        "ollama_reachable": _ollama_reachable(),
        "onnx_deps": onnx_deps_present(),
        "onnx_model_present": onnx_files_present(DEFAULT_ONNX_REPO),
        "onnx_model_dir": str(model_dir(DEFAULT_ONNX_REPO)),
        "dims": {"ollama:nomic-embed-text": 768, "onnx:" + DEFAULT_ONNX_REPO: 384},
    }


# ---------------------------------------------------------------- onnx lane

def fetch_onnx_model(repo: str = DEFAULT_ONNX_REPO, force: bool = False) -> dict:
    """Download weights + tokenizer from the Hugging Face Hub into model_dir.

    Explicit by design: nothing in the recall path calls this unless
    ``NOUGEN_EMBED_AUTO_DOWNLOAD=1``. Returns a receipt with paths and sizes.
    """
    from huggingface_hub import hf_hub_download  # pylint: disable=import-outside-toplevel
    dest = model_dir(repo)
    dest.mkdir(parents=True, exist_ok=True)
    out = {"repo": repo, "dir": str(dest), "files": {}}
    for fname in (_onnx_file(), TOKENIZER_FILE):
        target = dest / Path(fname).name
        if target.exists() and not force:
            out["files"][fname] = {"path": str(target), "bytes": target.stat().st_size, "cached": True}
            continue
        got = Path(hf_hub_download(repo_id=repo, filename=fname))
        # Copy out of the HF cache so the model has one home the fleet can find.
        import shutil  # pylint: disable=import-outside-toplevel
        shutil.copyfile(got, target)
        out["files"][fname] = {"path": str(target), "bytes": target.stat().st_size, "cached": False}
    return out


def _load_onnx(repo: str):
    with _LOCK:
        if repo in _SESSIONS:
            return _SESSIONS[repo]
    if not onnx_files_present(repo):
        if os.environ.get("NOUGEN_EMBED_AUTO_DOWNLOAD", "0").strip() == "1":
            fetch_onnx_model(repo)
        else:
            raise FileNotFoundError(
                f"onnx embedding model not present in {model_dir(repo)}; run `nougen embed fetch` "
                f"(or set NOUGEN_EMBED_AUTO_DOWNLOAD=1)")
    import onnxruntime as ort  # pylint: disable=import-outside-toplevel
    from tokenizers import Tokenizer  # pylint: disable=import-outside-toplevel
    d = model_dir(repo)
    so = ort.SessionOptions()
    so.intra_op_num_threads = int(os.environ.get("NOUGEN_ONNX_THREADS", "2"))
    sess = ort.InferenceSession(str(d / Path(_onnx_file()).name), so, providers=["CPUExecutionProvider"])
    tok = Tokenizer.from_file(str(d / TOKENIZER_FILE))
    tok.enable_truncation(max_length=MAX_TOKENS)
    tok.enable_padding(length=None)
    names = {i.name for i in sess.get_inputs()}
    with _LOCK:
        _SESSIONS[repo] = (sess, tok, names)
    return _SESSIONS[repo]


def onnx_embed(texts: Sequence[str], repo: str = DEFAULT_ONNX_REPO) -> List[List[float]]:
    """Mean-pooled, L2-normalised sentence embeddings, in-process on CPU."""
    import numpy as np  # pylint: disable=import-outside-toplevel
    sess, tok, names = _load_onnx(repo)
    enc = tok.encode_batch([t or "" for t in texts])
    ids = np.asarray([e.ids for e in enc], dtype=np.int64)
    mask = np.asarray([e.attention_mask for e in enc], dtype=np.int64)
    feed = {"input_ids": ids, "attention_mask": mask}
    if "token_type_ids" in names:
        feed["token_type_ids"] = np.zeros_like(ids)
    out = sess.run(None, feed)[0]                       # (batch, seq, hidden)
    m = mask[..., None].astype(np.float32)
    pooled = (out * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
    pooled = pooled / np.clip(norms, 1e-9, None)
    return pooled.astype(np.float32).tolist()


# ------------------------------------------------------------- dispatchers

def embed_text(text: str, model: Optional[str] = None, timeout: float = 60.0) -> Optional[List[float]]:
    """One vector via the resolved provider, or None (never raises)."""
    provider, name = resolve(model)
    try:
        if provider == "ollama":
            from .embedding_backfill import embed as _ollama_embed  # pylint: disable=import-outside-toplevel
            return _ollama_embed(text, name, timeout=timeout)
        if provider == "onnx":
            return onnx_embed([text], name)[0]
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("embed_text via %s failed: %s", provider, exc)
    return None


def embed_texts(texts: List[str], model: Optional[str] = None, timeout: float = 180.0) -> Optional[List[List[float]]]:
    """One vector per text via the resolved provider, or None (never raises)."""
    provider, name = resolve(model)
    try:
        if provider == "ollama":
            from .embedding_backfill import embed_many  # pylint: disable=import-outside-toplevel
            return embed_many(texts, name, timeout=timeout)
        if provider == "onnx":
            out: List[List[float]] = []
            for start in range(0, len(texts), 32):
                out.extend(onnx_embed(texts[start:start + 32], name))
            return out
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("embed_texts via %s failed: %s", provider, exc)
    return None


def describe_unavailable(model: Optional[str] = None) -> str:
    """One line for the 'written WITHOUT embedding' warning, provider-aware."""
    provider, name = resolve(model)
    if provider == "ollama":
        return f"ollama model {name!r} did not answer -- is ollama up?"
    if provider == "onnx":
        return f"onnx model {name!r} failed -- run `nougen embed status`"
    return ("no embedding provider: ollama not reachable and no onnx model -- "
            "run `nougen embed fetch` for in-process semantic recall")


def timed_self_test(repo: str = DEFAULT_ONNX_REPO) -> dict:
    t = time.monotonic()
    vec = onnx_embed(["self test"], repo)[0]
    return {"repo": repo, "dim": len(vec), "ms": int((time.monotonic() - t) * 1000)}


__all__ = ["resolve", "provider_status", "embed_text", "embed_texts", "onnx_embed",
           "fetch_onnx_model", "describe_unavailable", "timed_self_test",
           "DEFAULT_ONNX_REPO", "DEFAULT_OLLAMA_MODEL"]
