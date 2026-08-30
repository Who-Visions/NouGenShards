"""NouGenShards: Persistent local memory for coding agents.

Engine: Valerion — The Metameric Memory Engine (21-step cognitive architecture).
"""
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from .core import capture, retrieve, mark_shard, compile_recall_packet
from .federation import federated_retrieve
from .history import HistoryEngine, log_event, init_history_db
from .graph import link_shards, related_shards
from .gatekeeper import check_mutation_gate
from .dav1d_executor import run_dav1d_agy
from .relay_daemon import RelayDaemon, TriageResult, HeartbeatPulse

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

__all__ = [
    "capture",
    "retrieve",
    "mark_shard",
    "compile_recall_packet",
    "federated_retrieve",
    "HistoryEngine",
    "log_event",
    "init_history_db",
    "link_shards",
    "related_shards",
    "check_mutation_gate",
    "run_dav1d_agy",
    "RelayDaemon",
    "TriageResult",
    "HeartbeatPulse",
]

