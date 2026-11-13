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


def test_support_is_read_from_the_imported_relay_not_the_registry(tmp_path):
    """An installed nougen_relay without --publish must win over a registry that has it."""
    reg = _registry(tmp_path, True)
    old = tmp_path / "installed_core.py"
    old.write_text("# relay without the flag\n", encoding="utf-8")
    assert cli._with_create_publish(["create", "-g", "x"], reg, old) == ["create", "-g", "x"]


def test_relay_core_path_follows_the_imported_module():
    import sys
    import types
    mod = types.ModuleType("fake_relay_cli")
    mod.__file__ = "/x/nougen_relay/cli.py"
    sys.modules["fake_relay_cli"] = mod
    try:
        def main():
            pass
        main.__module__ = "fake_relay_cli"
        assert str(cli._relay_core_path(main)) == "/x/nougen_relay/core.py"
    finally:
        del sys.modules["fake_relay_cli"]
