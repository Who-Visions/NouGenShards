"""The cloud connector's hosting-edge authentication (private HF Spaces).

_apply_edge_auth adds an HF bearer alongside X-NGS-Token so push/pull/search
can reach a node on a PRIVATE Space; without a configured token it must be a
no-op (public nodes, self-hosted nodes).
"""
import json

import pytest

from nougen_shards.connectors import cloud


@pytest.fixture()
def captured(monkeypatch):
    """Intercept the network layer and record the outgoing request."""
    seen = {}

    def fake_open(req, url, timeout):
        seen["auth"] = req.get_header("Authorization")
        seen["ngs"] = req.get_header("X-ngs-token")
        return json.dumps({"status": "ok", "count": 0}).encode()

    monkeypatch.setattr(cloud, "_open_cloud", fake_open)
    return seen


def test_push_sends_bearer_when_configured(captured, monkeypatch):
    monkeypatch.setenv("NGS_HF_TOKEN", "hf_edge_token")
    res = cloud.push_to_cloud([], "https://node.hf.space", "node-token")
    assert res["status"] == "ok"
    assert captured["auth"] == "Bearer hf_edge_token"
    assert captured["ngs"] == "node-token"


def test_pull_falls_back_to_huggingface_api_key(captured, monkeypatch):
    monkeypatch.delenv("NGS_HF_TOKEN", raising=False)
    monkeypatch.setenv("HUGGINGFACE_API_KEY", "hf_byok_key")
    cloud.pull_from_cloud("https://node.hf.space", "node-token")
    assert captured["auth"] == "Bearer hf_byok_key"


def test_no_bearer_without_configuration(captured, monkeypatch):
    monkeypatch.delenv("NGS_HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_API_KEY", raising=False)
    cloud.push_to_cloud([], "https://node.hf.space", "node-token")
    assert captured["auth"] is None
    assert captured["ngs"] == "node-token"
