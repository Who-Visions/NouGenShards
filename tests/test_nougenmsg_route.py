

def test_per_node_port_wins_over_global(monkeypatch):
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("nm", pathlib.Path("tools/nougenmsg.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    monkeypatch.setenv("NOUGEN_MSG_PORT", "8765")
    monkeypatch.setenv("NOUGEN_NODE_WHOART_PORT", "8766")
    assert m._route_port("whoart") == (8766, "NOUGEN_NODE_WHOART_PORT")
    assert m._route_port("blade") == (8765, "NOUGEN_MSG_PORT")
    monkeypatch.delenv("NOUGEN_MSG_PORT")
    assert m._route_port("blade") == (m.HTTP_ROUTE_FALLBACK_PORT, "fallback")
