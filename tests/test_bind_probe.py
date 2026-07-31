"""The HUD exposure decision — the control that keeps an unauthenticated vault
UI off a public bind. Each case names the deployment it protects."""

from nougen_shards import bind_probe


def exposed(argv=None, **env):
    return bind_probe.is_network_exposed(argv or ["uvicorn"], env)


# --- the two ways the old NGS_HOST rule failed open ------------------------

def test_ngs_host_loopback_cannot_unmask_a_managed_platform():
    """The reported bug: NGS_HOST=127.0.0.1 on HF Spaces used to read as
    local-only while uvicorn was bound 0.0.0.0 on a public domain."""
    assert exposed(SPACE_ID="nougenai/NouGenShards", NGS_HOST="127.0.0.1") is True


def test_shipped_dockerfile_off_platform_is_exposed_by_default():
    """Worse case, no operator error: the shipped CMD binds 0.0.0.0, but off
    HF there is no SPACE_ID, so the old default assumed loopback."""
    argv = ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
    assert exposed(argv) is True


# --- the real bind outranks the advisory variable --------------------------

def test_argv_host_beats_contradicting_ngs_host():
    argv = ["uvicorn", "app:app", "--host", "0.0.0.0"]
    assert exposed(argv, NGS_HOST="127.0.0.1") is True


def test_equals_form_and_bind_alias_are_read():
    assert exposed(["gunicorn", "--bind=0.0.0.0:7860"]) is True
    assert exposed(["uvicorn", "--host=0.0.0.0"]) is True


def test_uvicorn_env_beats_ngs_host():
    assert exposed(UVICORN_HOST="0.0.0.0", NGS_HOST="127.0.0.1") is True


# --- local development still works ----------------------------------------

def test_plain_loopback_is_not_exposed():
    assert exposed(["uvicorn", "--host", "127.0.0.1"]) is False
    assert exposed(NGS_HOST="localhost") is False


def test_nothing_claimed_is_not_exposed():
    """Bare `python app.py` with no flags binds loopback by default."""
    assert exposed(["python", "app.py"]) is False


# --- ambiguity fails closed ------------------------------------------------

def test_unknown_host_counts_as_exposed():
    assert exposed(["uvicorn", "--host", "10.0.0.5"]) is True
    assert exposed(NGS_HOST="0.0.0.0") is True


def test_ipv6_loopback_forms_are_recognised():
    assert exposed(["uvicorn", "--host", "[::1]"]) is False
    assert exposed(["uvicorn", "--host", "0:0:0:0:0:0:0:1"]) is False
    assert exposed(["uvicorn", "--host", "::"]) is True


def test_case_and_whitespace_do_not_defeat_the_check():
    assert exposed(NGS_HOST=" LocalHost ") is False


def test_every_platform_marker_forces_exposed():
    for var in bind_probe.PLATFORM_VARS:
        assert exposed(["uvicorn"], **{var: "1"}) is True, var


def test_empty_platform_var_is_not_a_marker():
    assert exposed(["uvicorn"], SPACE_ID="") is False
