"""discrete_gpu_env: hybrid-graphics machines must load models into discrete VRAM."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards.ollama_host import discrete_gpu_env  # noqa: E402


def _fake_nvidia(tmp_path):
    exe = tmp_path / ("nvidia-smi.exe" if os.name == "nt" else "nvidia-smi")
    exe.write_text("")
    exe.chmod(0o755)
    return str(tmp_path)


def test_hides_amd_igpu_when_nvidia_present(tmp_path):
    env = discrete_gpu_env({"PATH": _fake_nvidia(tmp_path), "PATHEXT": ".EXE"})
    assert env["HIP_VISIBLE_DEVICES"] == "-1"


def test_leaves_amd_only_machines_alone(tmp_path):
    env = discrete_gpu_env({"PATH": str(tmp_path), "PATHEXT": ".EXE"})
    assert "HIP_VISIBLE_DEVICES" not in env


def test_explicit_setting_wins(tmp_path):
    env = discrete_gpu_env({"PATH": _fake_nvidia(tmp_path), "PATHEXT": ".EXE", "HIP_VISIBLE_DEVICES": "0"})
    assert env["HIP_VISIBLE_DEVICES"] == "0"
