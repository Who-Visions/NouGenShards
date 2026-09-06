import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pinned_route_survives_other_session(tmp_path):
    hook = load('lifecycle_fixture', TOOLS / 'codex_lifecycle.py')
    hook.STATE_DIR = tmp_path
    hook.RELAY_TARGET = tmp_path / 'relay_target.json'
    original = {'thread_id': '01a07427-3a1d-7df3-94b0-b5310f93a1d9', 'pinned': True}
    hook.RELAY_TARGET.write_text(json.dumps(original))
    hook.refresh_relay_target({'session_id': 'another-task', 'hook_event_name': 'Stop'})
    assert json.loads(hook.RELAY_TARGET.read_text()) == original


def test_unpinned_route_refreshes_atomically(tmp_path):
    hook = load('lifecycle_fixture', TOOLS / 'codex_lifecycle.py')
    hook.STATE_DIR = tmp_path
    hook.RELAY_TARGET = tmp_path / 'relay_target.json'
    hook.refresh_relay_target({'session_id': 'valid-session'})
    assert json.loads(hook.RELAY_TARGET.read_text())['thread_id'] == 'valid-session'
    assert list(tmp_path.glob('*.tmp')) == []


def test_codex_target_wakes_after_approval_without_extra_field():
    import nougenmsg_node as node
    with patch.object(node, '_wake_enabled', return_value=True), patch.object(node, '_wake_dispatch', return_value={'attempted': True}) as dispatch:
        assert node._maybe_wake({'target': 'codex', 'text': 'hello'}, {'kaedra_approved': True})['attempted']
        assert dispatch.call_args.args[0] == 'codex'
        dispatch.reset_mock()
        result = node._maybe_wake({'target': 'codex', 'text': 'hello'}, {'kaedra_approved': True, 'live_delivery': {'codex': {'delivered': True}}})
        assert result['wake'] == 'already queued'
        dispatch.assert_not_called()
        assert not node._maybe_wake({'target': 'codex', 'text': 'hello'}, {'kaedra_approved': False})['attempted']
        dispatch.assert_not_called()
