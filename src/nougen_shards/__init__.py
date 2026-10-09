"""NouGenShards: Persistent local memory for coding agents.

Engine: Valerion — The Metameric Memory Engine (21-step cognitive architecture).
"""
import importlib
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

# Keep ordinary package imports light. In particular, the Tauri chat sidecar
# must not initialize the complete 9-DB engine just to load chat_service.
_EXPORTS = {
    "capture": ("core", "capture"),
    "retrieve": ("core", "retrieve"),
    "mark_shard": ("core", "mark_shard"),
    "compile_recall_packet": ("core", "compile_recall_packet"),
    "federated_retrieve": ("federation", "federated_retrieve"),
    "HistoryEngine": ("history", "HistoryEngine"),
    "log_event": ("history", "log_event"),
    "init_history_db": ("history", "init_history_db"),
    "link_shards": ("graph", "link_shards"),
    "related_shards": ("graph", "related_shards"),
    "check_mutation_gate": ("gatekeeper", "check_mutation_gate"),
    "TemporalEnvelope": ("temporal_fabric", "TemporalEnvelope"),
    "TemporalFabric": ("temporal_fabric", "TemporalFabric"),
    "extract_temporal_mentions": ("temporal_fabric", "extract_temporal_mentions"),
    "CloudflareClient": ("cloudflare", "CloudflareClient"),
    "WorkerInfo": ("cloudflare", "WorkerInfo"),
    "SecretInfo": ("cloudflare", "SecretInfo"),
    "NouGenTranscriber": ("transcriber", "NouGenTranscriber"),
    "TranscribeEngine": ("transcriber", "TranscribeEngine"),
    "resolve_end_of_turn": ("end_of_turn_voice", "resolve_end_of_turn"),
    "EndOfTurnResolution": ("end_of_turn_voice", "EndOfTurnResolution"),
}
__all__ = list(_EXPORTS)


def __getattr__(name: str):
    """Load public exports and submodules only when a caller asks for them."""
    if name in _EXPORTS:
        module_name, attribute = _EXPORTS[name]
        try:
            value = getattr(importlib.import_module(f".{module_name}", __name__), attribute)
        except (ImportError, ModuleNotFoundError):
            if name not in ("NouGenTranscriber", "TranscribeEngine"):
                raise
            value = None
        globals()[name] = value
        return value
    try:
        module = importlib.import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    except ImportError:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'") from None


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))


def __get_popen_wrapper__():
    """Retained no-op hook for compatibility; process control belongs to callers."""
    return None


if sys.platform == "win32":
    import subprocess
    _NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    _orig_popen_init = subprocess.Popen.__init__

    def _nougen_popen_init(self, *args, **kwargs):
        if "creationflags" not in kwargs:
            kwargs["creationflags"] = _NO_WINDOW
        elif _NO_WINDOW:
            kwargs["creationflags"] |= _NO_WINDOW
        if "input" not in kwargs and kwargs.get("stdin") is None:
            kwargs["stdin"] = subprocess.DEVNULL
        return _orig_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _nougen_popen_init

# Read from installed package metadata rather than restated here. The v1.2.0
# release bumped pyproject.toml and left this line at 1.1.0, so `nougen
# --version` reported a version that had not shipped for two releases — the one
# number whose whole job is to be trustworthy. One source, no drift.
try:
    __version__ = _pkg_version("nougen-shards")
except PackageNotFoundError:
    try:
        __version__ = _pkg_version("nougen_shards")
    except PackageNotFoundError:
        # Running from source tree before pip install -e . -> read pyproject.toml if present
        import pathlib
        import re
        _root = pathlib.Path(__file__).resolve().parents[2]
        _pyproject = _root / "pyproject.toml"
        if _pyproject.is_file():
            _m = re.search(r'^version\s*=\s*"([^"]+)"', _pyproject.read_text(encoding="utf-8"), re.MULTILINE)
            __version__ = _m.group(1) if _m else "0.0.0+unknown"
        else:
            __version__ = "0.0.0+unknown"
VALERION_ENGINE = "Valerion"
