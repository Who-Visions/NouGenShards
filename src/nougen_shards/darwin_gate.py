"""Darwin (macOS) hardware, Mach VM, and XNU QoS admission gate.

Provides native kernel integration for Phoebus (Mac mini M4 / Darwin):
  1. Jetsam & Memory Pressure Guard: Inspects `sysctl kern.memorystatus_vm_pressure_level`
     (Normal=1, Warning=2, Critical=4) to pause model inference and embedding builds
     before macOS Jetsam terminates processes.
  2. Apple Silicon Unified Memory Headroom: Measures Mach VM pages (active, wired,
     free, inactive, speculative, compressor) to calculate real GPU/inference headroom.
  3. QoS Worker Threading: Demotes background FTS indexers, vector cache matrix loaders,
     and backfill workers to `QOS_CLASS_BACKGROUND` (0x09) via `pthread_set_qos_class_self_np`,
     pinning them to Efficiency cores (E-cores) and leaving Performance cores (P-cores)
     100% available for interactive chat and UI.
  4. Dynamic SQLite PRAGMA Scaling: Automatically scales SQLite `cache_size` and
     `mmap_size` based on live Mach VM compressor ratio and kernel memory pressure.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import platform
import subprocess
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from .vram_gate import Verdict

logger = logging.getLogger(__name__)

# XNU kernel memory pressure levels from <sys/event.h> / kern.memorystatus_vm_pressure_level
PRESSURE_NORMAL = 1
PRESSURE_WARNING = 2
PRESSURE_CRITICAL = 4

PRESSURE_NAMES = {
    PRESSURE_NORMAL: "Normal",
    PRESSURE_WARNING: "Warning",
    PRESSURE_CRITICAL: "Critical",
}

# Mach pthread Quality of Service (QoS) classes from <pthread/qos.h>
QOS_CLASS_USER_INTERACTIVE = 0x21  # 33 - High priority, interactive main UI thread
QOS_CLASS_USER_INITIATED   = 0x19  # 25 - Responsive user requests
QOS_CLASS_DEFAULT          = 0x15  # 21 - Default thread priority
QOS_CLASS_UTILITY          = 0x11  # 17 - Long-running user-visible work
QOS_CLASS_BACKGROUND       = 0x09  # 9  - Background jobs: runs on E-cores, throttled I/O
QOS_CLASS_UNSPECIFIED      = 0x00

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

# Load libSystem on Darwin for native pthread QoS bindings
_LIBSYSTEM: Optional[ctypes.CDLL] = None
if platform.system() == "Darwin":
    try:
        _LIBSYSTEM = ctypes.CDLL("libSystem.B.dylib")
        _LIBSYSTEM.pthread_self.restype = ctypes.c_void_p
        _LIBSYSTEM.pthread_get_qos_class_np.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_int),
        ]
        _LIBSYSTEM.pthread_get_qos_class_np.restype = ctypes.c_int
        _LIBSYSTEM.pthread_set_qos_class_self_np.argtypes = [ctypes.c_uint, ctypes.c_int]
        _LIBSYSTEM.pthread_set_qos_class_self_np.restype = ctypes.c_int
    except Exception as exc:
        logger.warning("darwin_gate: failed to bind libSystem pthread QoS: %s", exc)
        _LIBSYSTEM = None


def is_darwin() -> bool:
    """Returns True if running on macOS (Darwin)."""
    return platform.system() == "Darwin"


def get_memory_pressure_level() -> int:
    """Returns the live macOS kernel memory pressure level.

    Values:
      1: Normal (plenty of free/compressed headroom)
      2: Warning (compressor active, memory tight; pause non-essential batch work)
      4: Critical (Jetsam killer active; suspend memory allocations immediately)
    """
    if not is_darwin():
        return PRESSURE_NORMAL
    try:
        out = subprocess.run(
            ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        return int(out) if out.isdigit() else PRESSURE_NORMAL
    except Exception:
        return PRESSURE_NORMAL


def get_memory_pressure_name(level: Optional[int] = None) -> str:
    """Returns human-readable name for a given pressure level."""
    if level is None:
        level = get_memory_pressure_level()
    return PRESSURE_NAMES.get(level, f"Unknown ({level})")


@dataclass
class DarwinVMTelemetry:
    pressure_level: int
    pressure_name: str
    total_ram_gb: float
    free_ram_gb: float
    active_ram_gb: float
    available_ram_gb: float
    wired_ram_gb: float
    compressor_stored_gb: float
    compressor_occupied_gb: float
    compression_ratio: float
    page_size: int


def get_darwin_vm_telemetry() -> DarwinVMTelemetry:
    """Reads live Mach Virtual Memory statistics and compressor metrics."""
    if not is_darwin():
        return DarwinVMTelemetry(
            pressure_level=PRESSURE_NORMAL,
            pressure_name="Normal",
            total_ram_gb=16.0,
            free_ram_gb=8.0,
            active_ram_gb=4.0,
            available_ram_gb=8.0,
            wired_ram_gb=4.0,
            compressor_stored_gb=0.0,
            compressor_occupied_gb=0.0,
            compression_ratio=1.0,
            page_size=4096,
        )

    # 1. Total RAM & Page size
    total_ram_bytes = 16 * 1024**3
    page_size = 4096
    try:
        mem_out = subprocess.run(
            ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=2
        ).stdout.strip()
        if mem_out.isdigit():
            total_ram_bytes = int(mem_out)
        page_out = subprocess.run(
            ["sysctl", "-n", "hw.pagesize"], capture_output=True, text=True, timeout=2
        ).stdout.strip()
        if page_out.isdigit():
            page_size = int(page_out)
    except Exception:
        pass

    # 2. vm_stat output
    stats: dict[str, int] = {}
    try:
        vm_out = subprocess.run(
            ["vm_stat"], capture_output=True, text=True, timeout=2
        ).stdout
        for line in vm_out.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                val_clean = val.strip().rstrip(".").replace(" ", "")
                if val_clean.isdigit():
                    stats[key.strip()] = int(val_clean)
    except Exception:
        pass

    pages_free = stats.get("Pages free", 0)
    pages_active = stats.get("Pages active", 0)
    pages_inactive = stats.get("Pages inactive", 0)
    pages_speculative = stats.get("Pages speculative", 0)
    pages_wired = stats.get("Pages wired down", 0)
    pages_stored = stats.get("Pages stored in compressor", 0)
    pages_occupied = stats.get("Pages occupied by compressor", 0)

    stored_bytes = pages_stored * page_size
    occupied_bytes = pages_occupied * page_size
    comp_ratio = (stored_bytes / occupied_bytes) if occupied_bytes > 0 else 1.0

    free_bytes = pages_free * page_size
    active_bytes = pages_active * page_size
    available_bytes = (pages_free + pages_inactive + pages_speculative) * page_size
    wired_bytes = pages_wired * page_size

    pressure = get_memory_pressure_level()

    return DarwinVMTelemetry(
        pressure_level=pressure,
        pressure_name=get_memory_pressure_name(pressure),
        total_ram_gb=round(total_ram_bytes / 1e9, 2),
        free_ram_gb=round(free_bytes / 1e9, 2),
        active_ram_gb=round(active_bytes / 1e9, 2),
        available_ram_gb=round(available_bytes / 1e9, 2),
        wired_ram_gb=round(wired_bytes / 1e9, 2),
        compressor_stored_gb=round(stored_bytes / 1e9, 2),
        compressor_occupied_gb=round(occupied_bytes / 1e9, 2),
        compression_ratio=round(comp_ratio, 2),
        page_size=page_size,
    )


def get_apple_silicon_vram_headroom_gb() -> float:
    """Calculates available memory headroom for GPU/unified inference on Darwin.

    On Apple Silicon, CPU and GPU share the unified memory pool. Headroom is
    calculated as available RAM (free + inactive + speculative pages) minus a
    1.2 GB safety cushion reserved for system compositor and UI interactivity.
    """
    if not is_darwin():
        return 4.0
    vm = get_darwin_vm_telemetry()
    headroom = max(0.0, vm.available_ram_gb - 1.2)
    return round(headroom, 2)


def _ollama_residents() -> list[dict]:
    """Queries local Ollama /api/ps for currently resident models."""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/ps")
        with urllib.request.urlopen(req, timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8")).get("models", [])
    except Exception:
        return []


def check_darwin_admission(model: str, need_gb: Optional[float] = None) -> "Verdict":
    """VRAM / Unified Memory and Jetsam admission gate for macOS (Darwin).

    Evaluates live memory pressure level (Normal/Warning/Critical) and unified
    RAM headroom before admitting local model generation or heavy embedding jobs.
    """
    from .vram_gate import MEASURED_LOAD_GB, Verdict

    if ":cloud" in model or model.endswith("-cloud") or "/cloud" in model:
        return Verdict(True, f"admitted to Ollama Cloud gateway ({model}); zero local VRAM footprint")

    pressure = get_memory_pressure_level()
    p_name = get_memory_pressure_name(pressure)

    # 1. Critical memory pressure (level 4): Stop immediately to avoid Jetsam kill
    if pressure >= PRESSURE_CRITICAL:
        return Verdict(
            False,
            f"macOS memory pressure is CRITICAL (level {pressure}) — Jetsam OOM killer active. "
            f"Halting {model} to preserve system stability.",
            free_gb=0.0,
            need_gb=need_gb or 0.0,
        )

    # 2. Check if model is already loaded in unified memory
    residents = _ollama_residents()
    names = tuple(m.get("name", "?") for m in residents)
    need = need_gb if need_gb is not None else MEASURED_LOAD_GB.get(model)

    if model in names:
        # Already resident in Metal/unified memory — only KV cache expansion needed
        if pressure == PRESSURE_WARNING:
            # Under warning, allow resident models if KV footprint is modest
            return Verdict(True, f"already resident under {p_name} pressure", need_gb=need or 0.0, residents=names)
        return Verdict(True, "already resident in unified memory", need_gb=need or 0.0, residents=names)

    if need is None:
        # No measured footprint = no admission, same rule as the non-Darwin gate. Guessing a
        # small size would let an arbitrarily large new model cold-load and exhaust unified
        # memory, the failure this gate exists to prevent.
        return Verdict(
            False,
            f"no measured load size for {model!r}; measure it and add it to MEASURED_LOAD_GB, "
            f"or pass need_gb, before it can be cold-loaded on macOS.",
            free_gb=get_apple_silicon_vram_headroom_gb(),
            need_gb=0.0,
            residents=names,
        )

    # 3. Under warning pressure (level 2), refuse cold-loading large models
    if pressure == PRESSURE_WARNING:
        return Verdict(
            False,
            f"macOS memory pressure is WARNING (level 2) — deferring cold load of {model} "
            f"({need:.2f} GB) to prevent Jetsam OOM kill.",
            free_gb=get_apple_silicon_vram_headroom_gb(),
            need_gb=need,
            residents=names,
        )

    # 4. Normal pressure (level 1): Check unified headroom
    free = get_apple_silicon_vram_headroom_gb()
    safety_margin_gb = 0.5
    if need + safety_margin_gb <= free:
        return Verdict(
            True,
            f"fits Apple Silicon unified memory ({free:.2f} GB available, need {need:.2f} GB)",
            free_gb=free,
            need_gb=need,
            residents=names,
        )

    return Verdict(
        False,
        f"{model} needs {need:.2f} GB but only {free:.2f} GB unified headroom available "
        f"(residents: {', '.join(names) or 'none'}). Route to fleet or offload.",
        free_gb=free,
        need_gb=need,
        residents=names,
    )


# --- pthread Quality of Service (QoS) Control ---

def set_thread_qos(qos_class: int, relative_priority: int = 0) -> bool:
    """Sets the calling thread's Mach QoS class on Darwin.

    Supported classes:
      - QOS_CLASS_USER_INTERACTIVE (0x21): P-cores, high priority (chat, UI)
      - QOS_CLASS_USER_INITIATED   (0x19): Responsive user tasks
      - QOS_CLASS_DEFAULT          (0x15): Standard thread priority
      - QOS_CLASS_UTILITY          (0x11): Long batch tasks
      - QOS_CLASS_BACKGROUND       (0x09): E-cores only, throttled I/O (indexers, vector cache)

    Returns True if successfully set or if not on Darwin; False if call failed.
    """
    if not is_darwin() or _LIBSYSTEM is None:
        return True
    try:
        ret = _LIBSYSTEM.pthread_set_qos_class_self_np(qos_class, relative_priority)
        return ret == 0
    except Exception as exc:
        logger.debug("darwin_gate: pthread_set_qos_class_self_np failed: %s", exc)
        return False


def get_thread_qos() -> Tuple[Optional[int], Optional[int]]:
    """Returns (qos_class, relative_priority) for the calling thread on Darwin."""
    if not is_darwin() or _LIBSYSTEM is None:
        return (None, None)
    try:
        self_ptr = _LIBSYSTEM.pthread_self()
        qos = ctypes.c_uint()
        rel = ctypes.c_int()
        ret = _LIBSYSTEM.pthread_get_qos_class_np(self_ptr, ctypes.byref(qos), ctypes.byref(rel))
        if ret == 0:
            return (qos.value, rel.value)
        return (None, None)
    except Exception:
        return (None, None)


def demote_to_background_qos() -> bool:
    """Demotes the current thread to QOS_CLASS_BACKGROUND (0x09).

    Ensures the XNU kernel schedules this thread exclusively on Efficiency
    cores (E-cores) with throttled I/O priority, keeping Performance cores
    (P-cores) 100% free for interactive chat and UI rendering.
    """
    return set_thread_qos(QOS_CLASS_BACKGROUND, 0)


@contextmanager
def background_qos():
    """Context manager that temporarily demotes thread execution to QOS_CLASS_BACKGROUND."""
    prev_qos, prev_rel = get_thread_qos()
    demote_to_background_qos()
    try:
        yield
    finally:
        if prev_qos is not None and prev_qos != QOS_CLASS_UNSPECIFIED:
            set_thread_qos(prev_qos, prev_rel or 0)


# --- Dynamic SQLite PRAGMA Scaling ---

def get_scaled_sqlite_cache_size(base_cache_kb: int = 64000) -> int:
    """Calculates dynamic SQLite `cache_size` (negative number = kibibytes)
    based on live Mach VM compressor ratio and kernel memory pressure.

    Behavior:
      - Memory Pressure Critical (4) OR compressor ratio < 1.5x:
        Shrink aggressively to -4000 (4 MB) to prevent Jetsam kills.
      - Memory Pressure Warning (2) OR compressor ratio < 2.0x:
        Shrink to -16000 (16 MB).
      - Normal (1) AND compressor ratio >= 2.0x:
        Use full base_cache_kb (default -64000, 64 MB).
    """
    if not is_darwin():
        return -abs(base_cache_kb)

    try:
        vm = get_darwin_vm_telemetry()
        if vm.pressure_level >= PRESSURE_CRITICAL or vm.compression_ratio < 1.5:
            logger.debug("darwin_gate: scaling SQLite cache to 4MB under memory pressure (%s, ratio %.2f)",
                         vm.pressure_name, vm.compression_ratio)
            return -4000  # 4 MB
        if vm.pressure_level == PRESSURE_WARNING or vm.compression_ratio < 2.0:
            logger.debug("darwin_gate: scaling SQLite cache to 16MB under warning pressure (%s, ratio %.2f)",
                         vm.pressure_name, vm.compression_ratio)
            return -16000  # 16 MB
        return -abs(base_cache_kb)
    except Exception:
        return -abs(base_cache_kb)


def get_scaled_sqlite_mmap_size(base_mmap_bytes: int = 268435456) -> int:
    """Calculates dynamic SQLite `mmap_size` based on live memory pressure.

    Under Warning or Critical pressure, shrinks mmap allocations from 256MB to
    32MB or 0 (disabled) to unmap dirty virtual memory segments.
    """
    if not is_darwin():
        return base_mmap_bytes

    try:
        pressure = get_memory_pressure_level()
        if pressure >= PRESSURE_CRITICAL:
            return 0  # Disable mmap completely under critical pressure
        if pressure == PRESSURE_WARNING:
            return 33554432  # 32 MB
        return base_mmap_bytes
    except Exception:
        return base_mmap_bytes
