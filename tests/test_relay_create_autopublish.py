"""`nougen relay create` publishes the leg when the registry's relay supports it."""
from nougen_shards import cli


def _registry(tmp_path, supports):
    core = tmp_path / "src" / "nougen_relay"
    core.mkdir(parents=True)
    (core / "core.py").write_text('c.add_argument("--publish")' if supports else "", encoding="utf-8")
    return tmp_path


def test_create_gets_publish_when_supported(tmp_path):
    assert cli._with_create_publish(["create", "-g", "x"], _registry(tmp_path, True))[-1] == "--publish"


def test_old_relay_is_left_alone(tmp_path):
    assert cli._with_create_publish(["create", "-g", "x"], _registry(tmp_path, False)) == ["create", "-g", "x"]


def test_opt_out_and_other_actions(tmp_path):
    reg = _registry(tmp_path, True)
    assert cli._with_create_publish(["create", "--no-publish"], reg) == ["create"]
    assert cli._with_create_publish(["open"], reg) == ["open"]
    assert cli._with_create_publish(["create", "--publish"], reg).count("--publish") == 1
