"""Tests for Darwin (macOS) hardware gate, Mach VM telemetry, and XNU QoS control."""
import platform
import pytest
from unittest.mock import patch

from nougen_shards import darwin_gate, vram_gate


def test_is_darwin():
    assert darwin_gate.is_darwin() == (platform.system() == "Darwin")


def test_memory_pressure_levels_and_names():
    assert darwin_gate.get_memory_pressure_name(darwin_gate.PRESSURE_NORMAL) == "Normal"
    assert darwin_gate.get_memory_pressure_name(darwin_gate.PRESSURE_WARNING) == "Warning"
    assert darwin_gate.get_memory_pressure_name(darwin_gate.PRESSURE_CRITICAL) == "Critical"
    assert "Unknown" in darwin_gate.get_memory_pressure_name(99)


def test_live_darwin_vm_telemetry():
    if not darwin_gate.is_darwin():
        pytest.skip("Test requires macOS (Darwin)")
    vm = darwin_gate.get_darwin_vm_telemetry()
    assert vm.pressure_level in (1, 2, 4)
    assert vm.total_ram_gb > 0
    assert vm.available_ram_gb >= 0
    assert vm.compression_ratio >= 1.0
    assert vm.page_size in (4096, 16384)


def test_apple_silicon_vram_headroom():
    if not darwin_gate.is_darwin():
        pytest.skip("Test requires macOS (Darwin)")
    headroom = darwin_gate.get_apple_silicon_vram_headroom_gb()
    assert isinstance(headroom, float)
    assert headroom >= 0.0


def test_thread_qos_control():
    if not darwin_gate.is_darwin():
        pytest.skip("Test requires macOS (Darwin)")
    # Set to Interactive
    assert darwin_gate.set_thread_qos(darwin_gate.QOS_CLASS_USER_INTERACTIVE) is True
    qos, _ = darwin_gate.get_thread_qos()
    assert qos == darwin_gate.QOS_CLASS_USER_INTERACTIVE

    # Demote to Background (E-cores)
    assert darwin_gate.demote_to_background_qos() is True
    qos_bg, _ = darwin_gate.get_thread_qos()
    assert qos_bg == darwin_gate.QOS_CLASS_BACKGROUND

    # Context manager restores previous QoS
    darwin_gate.set_thread_qos(darwin_gate.QOS_CLASS_USER_INTERACTIVE)
    with darwin_gate.background_qos():
        inner_qos, _ = darwin_gate.get_thread_qos()
        assert inner_qos == darwin_gate.QOS_CLASS_BACKGROUND
    outer_qos, _ = darwin_gate.get_thread_qos()
    assert outer_qos == darwin_gate.QOS_CLASS_USER_INTERACTIVE


def test_darwin_admission_normal_pressure():
    with patch.object(darwin_gate, "is_darwin", return_value=True), \
         patch.object(darwin_gate, "get_memory_pressure_level", return_value=1), \
         patch.object(darwin_gate, "get_apple_silicon_vram_headroom_gb", return_value=8.0), \
         patch.object(darwin_gate, "_ollama_residents", return_value=[]):
        v = darwin_gate.check_darwin_admission("gemma4:e2b-qat")
        assert v.ok is True
        assert "fits Apple Silicon unified memory" in v.reason


def test_darwin_admission_oversized_model_refused():
    with patch.object(darwin_gate, "is_darwin", return_value=True), \
         patch.object(darwin_gate, "get_memory_pressure_level", return_value=1), \
         patch.object(darwin_gate, "get_apple_silicon_vram_headroom_gb", return_value=2.0), \
         patch.object(darwin_gate, "_ollama_residents", return_value=[]):
        v = darwin_gate.check_darwin_admission("gemma4:e4b")  # needs 9.52 GB
        assert v.ok is False
        assert "needs 9.52 GB but only 2.00 GB unified headroom" in v.reason


def test_darwin_admission_warning_pressure_defers_cold_load():
    with patch.object(darwin_gate, "is_darwin", return_value=True), \
         patch.object(darwin_gate, "get_memory_pressure_level", return_value=2), \
         patch.object(darwin_gate, "get_apple_silicon_vram_headroom_gb", return_value=6.0), \
         patch.object(darwin_gate, "_ollama_residents", return_value=[]):
        v = darwin_gate.check_darwin_admission("gemma4:e4b")
        assert v.ok is False
        assert "WARNING (level 2)" in v.reason
        assert "deferring cold load" in v.reason


def test_darwin_admission_warning_pressure_allows_resident_model():
    with patch.object(darwin_gate, "is_darwin", return_value=True), \
         patch.object(darwin_gate, "get_memory_pressure_level", return_value=2), \
         patch.object(darwin_gate, "get_apple_silicon_vram_headroom_gb", return_value=6.0), \
         patch.object(darwin_gate, "_ollama_residents", return_value=[{"name": "gemma4:e2b"}]):
        v = darwin_gate.check_darwin_admission("gemma4:e2b")
        assert v.ok is True
        assert "already resident" in v.reason


def test_darwin_admission_critical_pressure_halts():
    with patch.object(darwin_gate, "is_darwin", return_value=True), \
         patch.object(darwin_gate, "get_memory_pressure_level", return_value=4), \
         patch.object(darwin_gate, "_ollama_residents", return_value=[{"name": "gemma4:e2b"}]):
        v = darwin_gate.check_darwin_admission("gemma4:e2b")
        assert v.ok is False
        assert "CRITICAL (level 4)" in v.reason
        assert "Jetsam OOM killer active" in v.reason


def test_darwin_admission_cloud_model():
    v = darwin_gate.check_darwin_admission("gemma4:e2b:cloud")
    assert v.ok is True
    assert "cloud" in v.reason.lower()


def test_dynamic_sqlite_scaling():
    # Normal pressure, good ratio -> 64MB cache / 256MB mmap
    norm_vm = darwin_gate.DarwinVMTelemetry(
        pressure_level=1, pressure_name="Normal", total_ram_gb=16.0,
        free_ram_gb=2.0, active_ram_gb=4.0, available_ram_gb=8.0, wired_ram_gb=4.0,
        compressor_stored_gb=20.0, compressor_occupied_gb=5.0,
        compression_ratio=4.0, page_size=4096,
    )
    with patch.object(darwin_gate, "is_darwin", return_value=True), \
         patch.object(darwin_gate, "get_darwin_vm_telemetry", return_value=norm_vm), \
         patch.object(darwin_gate, "get_memory_pressure_level", return_value=1):
        assert darwin_gate.get_scaled_sqlite_cache_size(64000) == -64000
        assert darwin_gate.get_scaled_sqlite_mmap_size(268435456) == 268435456

    # Warning pressure -> 16MB cache / 32MB mmap
    warn_vm = darwin_gate.DarwinVMTelemetry(
        pressure_level=2, pressure_name="Warning", total_ram_gb=16.0,
        free_ram_gb=0.5, active_ram_gb=6.0, available_ram_gb=2.0, wired_ram_gb=6.0,
        compressor_stored_gb=20.0, compressor_occupied_gb=11.0,
        compression_ratio=1.8, page_size=4096,
    )
    with patch.object(darwin_gate, "is_darwin", return_value=True), \
         patch.object(darwin_gate, "get_darwin_vm_telemetry", return_value=warn_vm), \
         patch.object(darwin_gate, "get_memory_pressure_level", return_value=2):
        assert darwin_gate.get_scaled_sqlite_cache_size(64000) == -16000
        assert darwin_gate.get_scaled_sqlite_mmap_size(268435456) == 33554432

    # Critical pressure -> 4MB cache / 0 mmap
    crit_vm = darwin_gate.DarwinVMTelemetry(
        pressure_level=4, pressure_name="Critical", total_ram_gb=16.0,
        free_ram_gb=0.1, active_ram_gb=5.0, available_ram_gb=0.5, wired_ram_gb=10.0,
        compressor_stored_gb=25.0, compressor_occupied_gb=18.0,
        compression_ratio=1.38, page_size=4096,
    )
    with patch.object(darwin_gate, "is_darwin", return_value=True), \
         patch.object(darwin_gate, "get_darwin_vm_telemetry", return_value=crit_vm), \
         patch.object(darwin_gate, "get_memory_pressure_level", return_value=4):
        assert darwin_gate.get_scaled_sqlite_cache_size(64000) == -4000
        assert darwin_gate.get_scaled_sqlite_mmap_size(268435456) == 0


def test_vram_gate_integration(monkeypatch):
    monkeypatch.setenv("NOUGEN_VRAM_GATE", "1")
    if not darwin_gate.is_darwin():
        pytest.skip("Test requires macOS (Darwin)")
    free_vram = vram_gate._free_vram_gb()
    assert isinstance(free_vram, float)
    assert free_vram >= 0.0

    v = vram_gate.check_vram("gemma4:e2b-qat")
    assert isinstance(v, vram_gate.Verdict)
    assert isinstance(v.ok, bool)


def _admission_env(monkeypatch, *, residents=(), headroom=100.0, pressure=1):
    monkeypatch.setattr(darwin_gate, "get_memory_pressure_level", lambda: pressure)
    monkeypatch.setattr(darwin_gate, "_ollama_residents", lambda: [{"name": n} for n in residents])
    monkeypatch.setattr(darwin_gate, "get_apple_silicon_vram_headroom_gb", lambda: headroom)


def test_unmeasured_model_is_refused_not_guessed_as_2gb(monkeypatch):
    _admission_env(monkeypatch, headroom=100.0)  # plenty of headroom: the old 2 GB guess would admit
    v = darwin_gate.check_darwin_admission("brand-new-405b:latest")
    assert v.ok is False
    assert "no measured load size" in v.reason


def test_unmeasured_model_is_admitted_with_an_explicit_need(monkeypatch):
    _admission_env(monkeypatch, headroom=100.0)
    assert darwin_gate.check_darwin_admission("brand-new-405b:latest", need_gb=3.0).ok is True


def test_unmeasured_but_already_resident_model_is_still_allowed(monkeypatch):
    _admission_env(monkeypatch, residents=("brand-new-405b:latest",))
    assert darwin_gate.check_darwin_admission("brand-new-405b:latest").ok is True


def _backfill_db(tmp_path, n):
    import sqlite3
    db = tmp_path / "v.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, title TEXT, content TEXT, embedding BLOB)")
    conn.executemany("INSERT INTO shards (id, title, content) VALUES (?,?,?)", [(i, f"t{i}", f"c{i}") for i in range(n)])
    conn.commit()
    conn.close()
    return str(db)


def test_backfill_waits_out_memory_pressure_and_still_embeds_the_chunk(tmp_path, monkeypatch):
    from nougen_shards import embedding_backfill as eb
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    levels = iter([2, 2, 1])
    monkeypatch.setattr(darwin_gate, "get_memory_pressure_level", lambda: next(levels, 1))
    monkeypatch.setattr(darwin_gate, "demote_to_background_qos", lambda: None)
    monkeypatch.setattr(eb.time, "sleep", lambda s: None)
    monkeypatch.setattr(eb, "embed", lambda *a, **k: [0.1, 0.2])
    monkeypatch.setattr(eb, "embed_many", lambda texts, model: [[0.1, 0.2] for _ in texts])
    res = eb.backfill_db(_backfill_db(tmp_path, 3), "m", execute=True, batch=3, probe=False, progress=False)
    assert res["embedded"] == 3 and "deferred" not in res


def test_backfill_reports_deferred_when_pressure_never_clears(tmp_path, monkeypatch):
    from nougen_shards import embedding_backfill as eb
    monkeypatch.setenv("NOUGEN_BACKFILL_PRESSURE_WAIT_S", "0")
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(darwin_gate, "get_memory_pressure_level", lambda: 2)
    monkeypatch.setattr(darwin_gate, "demote_to_background_qos", lambda: None)
    monkeypatch.setattr(eb.time, "sleep", lambda s: None)
    res = eb.backfill_db(_backfill_db(tmp_path, 3), "m", execute=True, batch=3, probe=False, progress=False)
    assert res["embedded"] == 0
    assert res["deferred"] == "memory pressure" and res["remaining"] == 3
