from nougen_shards.node_plugins import load_node_plugins


class _EP:
    def __init__(self, name, fn):
        self.name, self._fn = name, fn

    def load(self):
        return self._fn


def test_no_plugins_is_a_clean_core_node():
    assert load_node_plugins(object(), object(), eps=[]) == []


def test_plugin_receives_app_and_mcp():
    seen = []
    report = load_node_plugins("APP", "MCP", eps=[_EP("canon", lambda a, m: seen.append((a, m)))])
    assert seen == [("APP", "MCP")]
    assert report == [{"plugin": "canon", "status": "loaded"}]


def test_a_broken_plugin_is_reported_not_fatal():
    def boom(app, mcp):
        raise RuntimeError("missing dep")
    ok = []
    report = load_node_plugins("A", "M", eps=[_EP("bad", boom), _EP("good", lambda a, m: ok.append(1))])
    assert ok == [1]
    assert report[0]["status"].startswith("failed: RuntimeError")
    assert report[1] == {"plugin": "good", "status": "loaded"}
