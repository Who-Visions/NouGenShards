"""KAEDRA_SYSTEM_OVERRIDE: a per-node prompt without changing the shared default.

The default KAEDRA_SYSTEM was measured against kaedracode:e2b specifically and
fixed 4/4 false negatives THERE (see the comment above it in
_agy_live_delivery.py) -- it is a prompt tuned to one model's failure mode,
not a general-purpose one. Measured on whoart running Yukiai:e2b instead
(2026-09-08): the default produced a self-contradictory NO / DENY verdict on
a plainly benign message, repeatably. A shorter prompt restored consistent
NO-implies-APPROVE / YES-implies-DENY logic. Rather than change the shared
default and risk recalibrating phoebus/blade's already-working gate on an
unrelated model's measurement, the override is opt-in per node via env var.

These tests cover the override MECHANISM (env var respected, default
untouched when unset, policy version follows the override) -- not the
model's judgment quality, which is not something a unit test can pin.
"""

import importlib
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))


def _reload_module(monkeypatch, **env):
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    if "_agy_live_delivery" in sys.modules:
        del sys.modules["_agy_live_delivery"]
    return importlib.import_module("_agy_live_delivery")


def test_default_system_prompt_unchanged_when_override_unset(monkeypatch):
    mod = _reload_module(monkeypatch, KAEDRA_SYSTEM_OVERRIDE=None)
    assert "APPROVE if your answer above was NO" in mod.KAEDRA_SYSTEM
    assert mod.POLICY_VERSION == "gate-v2-verdict-last-2026-09-03"


def test_override_replaces_the_prompt_and_the_policy_version(monkeypatch):
    custom_prompt = "TEST PROMPT: answer YES/NO then APPROVE/DENY."
    mod = _reload_module(
        monkeypatch,
        KAEDRA_SYSTEM_OVERRIDE=custom_prompt,
        KAEDRA_POLICY_VERSION="whoart-yukiai-v1-2026-09-08",
    )
    assert mod.KAEDRA_SYSTEM == custom_prompt
    assert mod.POLICY_VERSION == "whoart-yukiai-v1-2026-09-08"


def test_override_without_a_policy_version_still_falls_back_to_the_default_label(monkeypatch):
    """A node that sets the prompt override but forgets the version override
    still gets a version string in the record -- silently blank would be
    worse than a stale-but-present label, since a verdict with no policy
    version at all can't be told apart from a payload that never had one."""
    mod = _reload_module(
        monkeypatch,
        KAEDRA_SYSTEM_OVERRIDE="TEST PROMPT",
        KAEDRA_POLICY_VERSION=None,
    )
    assert mod.KAEDRA_SYSTEM == "TEST PROMPT"
    assert mod.POLICY_VERSION == "gate-v2-verdict-last-2026-09-03"
