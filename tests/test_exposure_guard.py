"""Guard tests for network-exposure detection (nougen_shards.exposure).

The Cortex HUD is an unauthenticated vault UI: raw shard search returns shard
``content`` and the transcript tab serves a whole-vault dump. These tests pin
the rule that it may only mount on a node that is provably loopback-only, and
that the verdict comes from the real bind -- not from ``NGS_HOST``, which the
shipped ``uvicorn app:app --host 0.0.0.0`` container command ignores.

Every case injects env and argv explicitly, so nothing here depends on the
machine running the suite.
"""

import os

import pytest

from nougen_shards.exposure import (
    ExposureDecision,
    detect_exposure,
    is_loopback_host,
    log_exposure_decision,
    resolve_bind_host,
    resolve_blocked_paths,
    should_mount_hud,
)

# The container command line from the Dockerfile CMD. This, not NGS_HOST, is
# what actually binds the socket in the deployed node.
DOCKER_ARGV = ["/usr/local/bin/uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
# A developer running `python app.py` on their own machine.
LOCAL_ARGV = ["app.py"]

NO_AUTH = None
WITH_AUTH = ("hud-user", "hud-pass")


def _legacy_network_exposed(env, argv=None):
    """The guard this module replaced, kept as an executable specimen.

    Reproduced from app.py before the fix::

        _default_host = "0.0.0.0" if os.environ.get("SPACE_ID") else "127.0.0.1"
        _bind_host = os.environ.get("NGS_HOST", _default_host)
        _network_exposed = _bind_host not in ("127.0.0.1", "localhost", "::1")

    Note it never looks at argv at all -- that is precisely the defect.
    """
    default_host = "0.0.0.0" if env.get("SPACE_ID") else "127.0.0.1"
    bind_host = env.get("NGS_HOST", default_host)
    return bind_host not in ("127.0.0.1", "localhost", "::1")


class TestHostedPlatformIsExposed:
    def test_space_id_set_means_exposed_and_hud_not_mounted(self):
        env = {"SPACE_ID": "nougenai/nougenshards"}
        decision = detect_exposure(env=env, argv=DOCKER_ARGV)

        assert decision.exposed is True
        assert "SPACE_ID" in decision.platform_indicators
        assert should_mount_hud(decision, NO_AUTH) is False

    def test_platform_indicator_alone_is_enough_even_on_loopback_bind(self):
        """A platform indicator outvotes a loopback-looking bind. Fail closed."""
        env = {"SPACE_ID": "nougenai/nougenshards", "NGS_HOST": "127.0.0.1"}
        decision = detect_exposure(env=env, argv=LOCAL_ARGV)

        assert decision.exposed is True
        assert should_mount_hud(decision, NO_AUTH) is False

    @pytest.mark.parametrize(
        "var,value",
        [
            ("SPACE_ID", "nougenai/nougenshards"),
            ("DYNO", "web.1"),
            ("K_SERVICE", "nougen-node"),
            ("FLY_APP_NAME", "nougen"),
            ("KUBERNETES_SERVICE_HOST", "10.0.0.1"),
            ("CODESPACE_NAME", "fluffy-space-engine"),
        ],
    )
    def test_each_recognized_platform_indicator_forces_exposed(self, var, value):
        decision = detect_exposure(env={var: value}, argv=LOCAL_ARGV)
        assert decision.exposed is True


class TestNgsHostCannotDisableTheGuard:
    """THE REGRESSION THIS FIX EXISTS FOR.

    Setting NGS_HOST=127.0.0.1 in the hosting platform's settings does not
    change the bind: the container runs `uvicorn --host 0.0.0.0`. Under the old
    guard that single env var made the app believe it was local-only and mount
    the unauthenticated vault HUD on a public domain.
    """

    def test_ngs_host_loopback_with_wildcard_bind_is_still_exposed(self):
        env = {"NGS_HOST": "127.0.0.1"}  # no SPACE_ID: bind evidence must stand alone
        decision = detect_exposure(env=env, argv=DOCKER_ARGV)

        assert decision.bind_host == "0.0.0.0"
        assert decision.bind_source == "argv:--host"
        assert decision.exposed is True, (
            "NGS_HOST=127.0.0.1 must not override an actual --host 0.0.0.0 bind"
        )
        assert should_mount_hud(decision, NO_AUTH) is False

    def test_full_space_scenario_ngs_host_loopback_on_hf(self):
        env = {"SPACE_ID": "nougenai/nougenshards", "NGS_HOST": "127.0.0.1"}
        decision = detect_exposure(env=env, argv=DOCKER_ARGV)

        assert decision.exposed is True
        assert should_mount_hud(decision, NO_AUTH) is False

    def test_old_logic_fails_this_case_new_logic_does_not(self):
        """Documents the exact behaviour delta the fix introduces."""
        env = {"NGS_HOST": "127.0.0.1"}

        assert _legacy_network_exposed(env) is False  # old guard: "we are local"
        assert detect_exposure(env=env, argv=DOCKER_ARGV).exposed is True

    def test_bind_probe_beats_advisory_ngs_host_in_every_form(self):
        for argv in (
            ["uvicorn", "app:app", "--host=0.0.0.0"],
            ["uvicorn", "app:app", "--host", "::"],
            ["gunicorn", "app:app", "--bind", "0.0.0.0:7860"],
        ):
            decision = detect_exposure(env={"NGS_HOST": "localhost"}, argv=argv)
            assert decision.exposed is True, argv


class TestGenuineLocalDevelopmentStillGetsTheHud:
    def test_loopback_no_platform_indicator_mounts_the_hud(self):
        decision = detect_exposure(env={}, argv=LOCAL_ARGV)

        assert decision.exposed is False
        assert decision.bind_host == "127.0.0.1"
        assert should_mount_hud(decision, NO_AUTH) is True

    def test_explicit_loopback_ngs_host_mounts_the_hud(self):
        decision = detect_exposure(env={"NGS_HOST": "127.0.0.1"}, argv=LOCAL_ARGV)
        assert decision.exposed is False
        assert should_mount_hud(decision, NO_AUTH) is True

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.53"])
    def test_loopback_forms_are_recognized(self, host):
        decision = detect_exposure(env={}, argv=["uvicorn", "app:app", "--host", host])
        assert decision.exposed is False, host

    def test_exposed_node_with_hud_credentials_still_mounts(self):
        decision = detect_exposure(env={"SPACE_ID": "x"}, argv=DOCKER_ARGV)
        assert decision.exposed is True
        assert should_mount_hud(decision, WITH_AUTH) is True


class TestAmbiguityFailsClosed:
    @pytest.mark.parametrize(
        "host",
        ["0.0.0.0", "::", "*", "", "not-a-host", "example.com", "10.0.0.4", "192.168.1.16"],
    )
    def test_non_loopback_or_unresolvable_hosts_are_exposed(self, host):
        assert is_loopback_host(host, env={}) is False
        decision = detect_exposure(env={}, argv=["uvicorn", "app:app", "--host", host])
        assert decision.exposed is True, host

    def test_unknown_host_is_not_treated_as_loopback(self):
        assert is_loopback_host(None, env={}) is False

    def test_decision_records_a_human_readable_reason(self):
        decision = detect_exposure(env={"SPACE_ID": "x"}, argv=DOCKER_ARGV)
        described = decision.describe()
        assert "EXPOSED" in described
        assert "SPACE_ID" in described
        assert decision.reasons


class TestBindHostResolution:
    def test_argv_host_wins_over_uvicorn_env(self):
        host, source = resolve_bind_host(
            env={"UVICORN_HOST": "127.0.0.1"}, argv=DOCKER_ARGV
        )
        assert (host, source) == ("0.0.0.0", "argv:--host")

    def test_uvicorn_env_wins_over_advisory_ngs_host(self):
        host, source = resolve_bind_host(
            env={"UVICORN_HOST": "0.0.0.0", "NGS_HOST": "127.0.0.1"}, argv=LOCAL_ARGV
        )
        assert (host, source) == ("0.0.0.0", "env:UVICORN_HOST")

    def test_gunicorn_cmd_args_are_parsed(self):
        host, source = resolve_bind_host(
            env={"GUNICORN_CMD_ARGS": "--workers 2 --bind 0.0.0.0:7860"}, argv=LOCAL_ARGV
        )
        assert host == "0.0.0.0"
        assert source == "env:GUNICORN_CMD_ARGS"

    def test_fallback_is_labelled_as_a_fallback(self):
        host, source = resolve_bind_host(env={}, argv=LOCAL_ARGV)
        assert host == "127.0.0.1"
        assert source.startswith("fallback:")

    def test_loopback_set_is_configurable_not_hardcoded(self):
        env = {"NGS_LOOPBACK_HOSTS": "127.0.0.1"}
        decision = detect_exposure(env=env, argv=["uvicorn", "--host", "localhost"])
        assert decision.exposed is True  # localhost no longer in the configured set


class TestBlockedPaths:
    def test_data_mount_is_always_blocked(self):
        assert "/data" in resolve_blocked_paths(env={})

    def test_vault_and_home_are_blocked_on_a_space(self):
        env = {"NOUGEN_HOME": "/data", "NOUGEN_VAULT_DIR": "/data/.vault"}
        blocked = resolve_blocked_paths(env=env)
        assert "/data" in blocked
        assert "/data/.vault" in blocked

    def test_local_vault_dir_is_blocked(self):
        env = {"NOUGEN_VAULT_DIR": "/home/dev/.nougen/.vault"}
        assert "/home/dev/.nougen/.vault" in resolve_blocked_paths(env=env)

    def test_operator_can_add_paths_and_entries_are_deduped(self):
        env = {
            "NGS_HUD_BLOCKED_PATHS": os.pathsep.join(["/secrets", "/data"]),
            "NOUGEN_HOME": "/data",
        }
        blocked = resolve_blocked_paths(env=env)
        assert "/secrets" in blocked
        assert blocked.count("/data") == 1

    def test_data_mount_location_is_configurable(self):
        blocked = resolve_blocked_paths(env={"NGS_DATA_MOUNT": "/mnt/vault"})
        assert "/mnt/vault" in blocked

    def test_transcript_workdir_is_not_blocked(self):
        """The HUD's transcript.log lives in the CWD, not the vault mount, so
        blocking the vault must not break the legitimate download."""
        blocked = resolve_blocked_paths(
            env={"NOUGEN_HOME": "/data", "NOUGEN_VAULT_DIR": "/data/.vault"}
        )
        assert "/app" not in blocked
        assert os.getcwd() not in blocked


class TestStartupLogging:
    def test_startup_line_states_the_verdict_and_the_reason(self, capsys):
        decision = detect_exposure(env={"SPACE_ID": "x"}, argv=DOCKER_ARGV)
        message = log_exposure_decision(decision, hud_mounted=False, blocked=["/data"])

        assert "EXPOSED" in message
        assert "NOT mounted" in message
        assert "/data" in message
        assert message in capsys.readouterr().err

    def test_local_startup_line_reports_local_only(self, capsys):
        decision = detect_exposure(env={}, argv=LOCAL_ARGV)
        message = log_exposure_decision(decision, hud_mounted=True, blocked=["/data"])

        assert "LOCAL-ONLY" in message
        assert "MOUNTED" in message
        capsys.readouterr()

    def test_decision_is_immutable(self):
        decision = detect_exposure(env={"SPACE_ID": "x"}, argv=DOCKER_ARGV)
        assert isinstance(decision, ExposureDecision)
        with pytest.raises(Exception):
            decision.exposed = False  # frozen dataclass
