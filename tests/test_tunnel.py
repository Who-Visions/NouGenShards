from nougen_shards import tunnel

def test_get_ngrok_token_from_env(monkeypatch):
    monkeypatch.setenv("NGROK_AUTHTOKEN", "test_env_token_12345")
    token = tunnel.get_ngrok_token()
    assert token == "test_env_token_12345"

def test_get_ngrok_token_from_vault(monkeypatch, tmp_path):
    monkeypatch.delenv("NGROK_AUTHTOKEN", raising=False)
    vault_file = tmp_path / "ngrok.env"
    vault_file.write_text('NGROK_AUTHTOKEN="vault_token_abcde"\n')
    monkeypatch.setattr(tunnel, "VAULT_PATH", vault_file)
    
    token = tunnel.get_ngrok_token()
    assert token == "vault_token_abcde"

def test_get_ngrok_token_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("NGROK_AUTHTOKEN", raising=False)
    non_existent = tmp_path / "non_existent.env"
    monkeypatch.setattr(tunnel, "VAULT_PATH", non_existent)
    
    token = tunnel.get_ngrok_token()
    assert token == ""


# --- Cloudflare tunnel status -------------------------------------------------

def _fake_get(table):
    def fake(url, timeout):
        val = table.get(url)
        if val is None:
            raise OSError("connection refused")
        return val
    return fake


def test_unconfigured_install_names_no_fleet_and_says_how(monkeypatch, tmp_path):
    monkeypatch.delenv("NOUGEN_TUNNEL_TARGETS", raising=False)
    monkeypatch.delenv("NOUGEN_FLEET_GATEWAY_URL", raising=False)
    monkeypatch.setenv("NOUGEN_ENDPOINTS_FILE", str(tmp_path / "none.json"))
    monkeypatch.setattr(tunnel, "_http_get", _fake_get({}))
    out = tunnel.get_active_tunnels(metrics=("127.0.0.1:1",))
    assert out["status"] == "not_configured" and out["routes"] == [] and "NOUGEN_TUNNEL_TARGETS" in out["fix"]


def test_routes_and_sleepers_come_from_the_endpoints_file(monkeypatch, tmp_path):
    import json
    f = tmp_path / "endpoints.json"
    f.write_text(json.dumps({"fleet_gateway_url": "https://door.example.test",
                             "tunnel_routes": {"node-a": "https://door.example.test/a/health",
                                               "node-b": "https://b.example.test/health"},
                             "tunnel_sleepers": ["node-b"]}))
    monkeypatch.delenv("NOUGEN_TUNNEL_TARGETS", raising=False)
    monkeypatch.delenv("NOUGEN_TUNNEL_SLEEPERS", raising=False)
    monkeypatch.delenv("NOUGEN_FLEET_GATEWAY_URL", raising=False)
    monkeypatch.setenv("NOUGEN_ENDPOINTS_FILE", str(f))
    monkeypatch.setattr(tunnel, "_http_get", _fake_get({
        "https://door.example.test/health": (200, "ok"), "https://door.example.test/a/health": (200, "ok")}))
    out = tunnel.get_active_tunnels(metrics=("127.0.0.1:1",))
    by = {r["name"]: r["status"] for r in out["routes"]}
    assert by == {"front-door": "up", "node-a": "up", "node-b": "asleep"}
    assert out["status"] == "up" and out["total"] == 2


def test_status_reports_cloudflare_routes_and_local_connector(monkeypatch):
    monkeypatch.setattr(tunnel, "_http_get", _fake_get({
        "http://127.0.0.1:20241/ready": (200, '{"status":200,"readyConnections":4,"connectorId":"c1"}'),
        "https://door.example.test/health": (200, "ok"),
        "https://m.example.test/health": (401, "auth"),
    }))
    out = tunnel.get_active_tunnels(
        targets=[("front-door", "https://door.example.test/health"), "msgs=m.example.test"],
        metrics=("127.0.0.1:20241",), sleepers=())
    assert out["provider"] == "cloudflare" and out["status"] == "up"
    assert out["local_connector"]["status"] == "up" and out["local_connector"]["ready_connections"] == 4
    assert [r["status"] for r in out["routes"]] == ["up", "reachable"]
    assert "ngrok" not in repr(out).lower() and "4040" not in repr(out)


def test_tunnel_down_and_origin_down_are_told_apart(monkeypatch):
    monkeypatch.setattr(tunnel, "_http_get", _fake_get({
        "https://door.example.test/a/health": (530, "error code: 1033"),
        "https://b.example.test/health": (502, "bad gateway"),
        "https://door.example.test/health": (200, "ok"),
    }))
    out = tunnel.get_active_tunnels(targets=[
        "node-a=https://door.example.test/a/health",
        "node-b=https://b.example.test/health",
        "front-door=https://door.example.test/health"], metrics=("127.0.0.1:1",), sleepers=())
    by = {r["name"]: r["status"] for r in out["routes"]}
    assert by == {"node-a": "tunnel_down", "node-b": "origin_down", "front-door": "up"}
    assert out["status"] == "degraded" and out["up"] == 1 and out["total"] == 3
    assert out["local_connector"]["status"] == "not_running"


def test_sleeping_machine_is_asleep_not_an_outage(monkeypatch):
    monkeypatch.setattr(tunnel, "_http_get", _fake_get({"https://door.example.test/health": (200, "ok")}))
    out = tunnel.get_active_tunnels(targets=[
        "front-door=https://door.example.test/health",
        "night-box=https://night.example.test/health"], metrics=("127.0.0.1:1",), sleepers=("night-box",))
    by = {r["name"]: r["status"] for r in out["routes"]}
    assert by["night-box"] == "asleep" and out["status"] == "up" and out["total"] == 1


def test_all_routes_unreachable_is_down(monkeypatch):
    monkeypatch.setattr(tunnel, "_http_get", _fake_get({}))
    out = tunnel.get_active_tunnels(targets=["front-door=door.example.test"], metrics=("127.0.0.1:1",), sleepers=())
    assert out["status"] == "down" and out["routes"][0]["status"] == "down"


def test_local_connector_with_zero_connections_is_down(monkeypatch):
    monkeypatch.setattr(tunnel, "_http_get", _fake_get({
        "http://127.0.0.1:20242/ready": (503, '{"status":503,"readyConnections":0}'),
    }))
    local = tunnel.cloudflared_local(metrics=("127.0.0.1:20241", "127.0.0.1:20242"))
    assert local["status"] == "down" and local["metrics"].endswith(":20242/ready")


def test_targets_and_metrics_come_from_env(monkeypatch):
    seen = []
    def fake(url, timeout):
        seen.append(url)
        raise OSError("refused")
    monkeypatch.setattr(tunnel, "_http_get", fake)
    monkeypatch.setenv("NOUGEN_TUNNEL_TARGETS", "front-door=https://a.example.test/health, tenant-1=https://a.example.test/t1/health")
    monkeypatch.setenv("NOUGEN_CLOUDFLARED_METRICS", "127.0.0.1:9")
    out = tunnel.get_active_tunnels(sleepers=())
    assert [r["name"] for r in out["routes"]] == ["front-door", "tenant-1"]
    assert "https://a.example.test/t1/health" in seen and "http://127.0.0.1:9/ready" in seen
