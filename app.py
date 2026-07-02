"""
NouGenShards Production Node & Cortex HUD.
Architecture: FastAPI + Persistent Storage (/data) + Token Auth + Multi-tab Gradio UI.
"""
import os
import sys
import hmac
import json
import contextlib
from typing import List, Optional
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel
import gradio as gr
import subprocess


# Add src to path for absolute imports
sys.path.append(os.path.join(os.getcwd(), 'src'))

# Override Storage for HF Persistence
if os.environ.get("SPACE_ID"):
    os.environ["NOUGEN_HOME"] = "/data"
    os.environ["NOUGEN_VAULT_DIR"] = "/data/.vault"

from nougen_shards import core, history
from nougen_shards.brain_scan import scan_environment

NODE_TOKEN = os.environ.get("NGS_NODE_TOKEN")


# --- Remote MCP server (mobile / Claude-app connector) ---
# Streamable-HTTP MCP endpoint mounted at /mcp so remote MCP clients (the
# Claude mobile/web app's custom connectors, MCP inspector, other agents) can
# use the node's memory directly. Deliberately exposes ONLY the memory tools:
# execute_sandboxed_code and brain scan/import stay stdio-local - remote code
# execution and container-filesystem recon do not belong on a network surface.
from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

node_mcp = FastMCP(
    "NouGenShards",
    instructions=(
        "Persistent memory node. Use recall_memory before reasoning from "
        "scratch and capture_experience to store durable learnings."
    ),
    # Stateless JSON mode: every request is self-contained, which suits a
    # Space that may cold-start between calls.
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    # DNS-rebinding protection is a defense for loopback-bound servers whose
    # only gate is network locality; this endpoint is explicitly token-gated
    # (see _TokenGatedMCP) and served from a public host whose Host header
    # varies (hf.space, custom domains), so host allow-listing would only
    # break legitimate clients without adding security.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@node_mcp.tool()
def recall_memory(query: str, limit: int = 5) -> list:
    """Search the memory substrate. Returns ranked shards (fuzzy recall
    included when exact matching misses)."""
    results = core.retrieve(query, limit=max(1, min(limit, 20)))
    return [{k: v for k, v in r.items() if not isinstance(v, (bytes, bytearray))}
            for r in results]


@node_mcp.tool()
def capture_experience(title: str, content: str, event_type: str = "KNOWLEDGE",
                       tags: list[str] | None = None) -> dict:
    """Store a unit of experience as a shard (deduplicated by content)."""
    ok = core.capture(event_type, title, content, tags=tags)
    return {"captured": bool(ok)}


@node_mcp.tool()
def mark_utility(shard_id: int, worked: bool, db_index: int | None = None) -> dict:
    """Feed back whether a recalled shard was useful; adjusts its ranking prior."""
    core.mark_shard(shard_id, worked=worked, db_index=db_index)
    return {"marked": shard_id, "worked": worked}


@node_mcp.tool()
def node_status() -> dict:
    """Node health: shard count and storage mode."""
    return {"status": "ignited",
            "total_shards": _total_shards(),
            "storage": os.environ.get("NOUGEN_HOME", "default")}


_mcp_asgi = node_mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def _lifespan(_app):
    # The streamable-HTTP session manager needs a running task group.
    async with node_mcp.session_manager.run():
        yield


app = FastAPI(title="NouGenShards Node", lifespan=_lifespan)

# --- Security ---

def verify_token(x_ngs_token: str = Header(None)):
    if not NODE_TOKEN:
        raise HTTPException(status_code=503, detail="Node write-auth not configured.")
    # Constant-time comparison to avoid leaking the token via timing.
    if not x_ngs_token or not hmac.compare_digest(str(x_ngs_token), str(NODE_TOKEN)):
        raise HTTPException(status_code=401, detail="Invalid node token.")
    return x_ngs_token

# --- API Endpoints ---

def _total_shards() -> int:
    total = 0
    for i in range(1, core.MAX_DB_COUNT + 1):
        p = core.get_db_path(i)
        if not p.exists():
            continue
        try:
            conn = core.get_connection(i)
            total += conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
            conn.close()
        except Exception:
            pass
    return total


@app.get("/health")
def health():
    """Launch-readiness report. Contains no secret values - only whether each
    gate is configured - so it is safe to serve unauthenticated and doubles as
    the go/no-go check before flipping the Space public."""
    deploy_sha = None
    try:
        with open(".deploy_sha", encoding="utf-8") as f:
            deploy_sha = f.read().strip() or None
    except OSError:
        pass

    node_token_ok = bool(NODE_TOKEN)
    hud_auth_ok = bool(os.environ.get("NGS_HUD_USER") and os.environ.get("NGS_HUD_PASSWORD"))
    # On HF, enabling persistent storage mounts /data as its own filesystem;
    # without it /data is just a directory inside the ephemeral container.
    persistent = os.path.isdir("/data") and os.path.ismount("/data")

    warnings = []
    if not node_token_ok:
        warnings.append("NGS_NODE_TOKEN not set: data API returns 503 (deny-by-default)")
    if not hud_auth_ok:
        warnings.append("NGS_HUD_USER/NGS_HUD_PASSWORD not set: HUD would be open to anyone on a public Space")
    if not persistent:
        warnings.append("persistent storage not detected: memories are wiped on every restart/deploy")

    return {
        "status": "ignited",
        "deploy_sha": deploy_sha,
        "storage": os.environ.get("NOUGEN_HOME", "default"),
        "persistent_storage": persistent,
        "node_token_configured": node_token_ok,
        "hud_auth_configured": hud_auth_ok,
        "total_shards": _total_shards(),
        # Auth gates are the hard requirement for a public flip; storage is a
        # durability concern surfaced via warnings.
        "public_ready": node_token_ok and hud_auth_ok,
        "warnings": warnings,
    }


# --- API models ---

class SearchRequest(BaseModel):
    query: str
    limit: int = 5


class CaptureRequest(BaseModel):
    event_type: str = "KNOWLEDGE"
    title: str
    content: str
    tags: Optional[List[str]] = None


class SyncPushRequest(BaseModel):
    shards: List[dict]


def _json_safe(item: dict) -> dict:
    """Drop non-JSON-serializable fields (raw embedding bytes) from a shard row."""
    return {k: v for k, v in item.items() if not isinstance(v, (bytes, bytearray))}


# Every data endpoint requires X-NGS-Token (verify_token 503s until
# NGS_NODE_TOKEN is configured, so the node is deny-by-default). This is what
# makes it safe to run the Space public: reads and writes are both gated;
# only /health and the separately-authed HUD are reachable without the token.

@app.post("/search")
def search(req: SearchRequest, _token: str = Depends(verify_token)):
    """Memory recall for cloud callers (mirrors the connector's POST /search)."""
    results = core.retrieve(req.query, limit=max(1, min(req.limit, 50)))
    return [_json_safe(r) for r in results]


@app.post("/capture")
def capture_shard(req: CaptureRequest, _token: str = Depends(verify_token)):
    """Single-shard capture for user agents."""
    ok = core.capture(req.event_type, req.title, req.content, tags=req.tags)
    return {"status": "ok", "captured": bool(ok)}


@app.post("/sync/push")
def sync_push(req: SyncPushRequest, _token: str = Depends(verify_token)):
    """Bulk ingest (contract of connectors.cloud.push_to_cloud)."""
    count = 0
    skipped = 0
    for s in req.shards:
        title, content = s.get("title"), s.get("content")
        if not title or not content:
            skipped += 1
            continue
        tags = s.get("tags")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except ValueError:
                tags = None
        emb = s.get("embedding")
        if emb is not None and not isinstance(emb, list):
            emb = None
        ok = core.capture(
            s.get("event_type") or "KNOWLEDGE", title, content,
            tags=tags, embedding=emb,
            domain_key=s.get("domain_key"),
            density_score=s.get("density_score"),
        )
        if ok:
            count += 1
        else:
            skipped += 1  # capture() dedups; an already-known shard is a skip
    return {"status": "ok", "count": count, "skipped": skipped}


@app.get("/sync/pull")
def sync_pull(_token: str = Depends(verify_token)):
    """Full export (contract of connectors.cloud.pull_from_cloud)."""
    all_shards = []
    for i in range(1, core.MAX_DB_COUNT + 1):
        if not core.get_db_path(i).exists():
            continue
        conn = core.get_connection(i)
        try:
            for r in conn.execute("SELECT * FROM shards").fetchall():
                d = dict(r)
                emb = d.get("embedding")
                if emb:
                    try:
                        raw = emb.decode() if isinstance(emb, (bytes, bytearray)) else emb
                        d["embedding"] = json.loads(raw)
                    except (AttributeError, ValueError, TypeError, UnicodeDecodeError):
                        d["embedding"] = None
                all_shards.append(d)
        finally:
            conn.close()
    return all_shards

# --- Cortex HUD UI Logic ---

def get_substrate_map():
    """Generates a visual map of the 9-DB cluster."""
    active_idx = core.get_active_db_index()
    stats = []
    for i in range(1, 10):
        p = core.get_db_path(i)
        size = p.stat().st_size / (1024 * 1024) if p.exists() else 0
        shards_count = 0
        if p.exists():
            try:
                conn = core.get_connection(i)
                shards_count = conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
                conn.close()
            except Exception: pass
        
        status = "🟢 ACTIVE" if i == active_idx else "⚪ READY"
        if size > 900: status = "🔴 FULL"
        
        stats.append(f"### DB #{i} [{status}]\n- {shards_count} shards\n- {size:.2f} MB / 1024 MB")
    
    return stats

def run_recon():
    """Runs a brain scan and returns a summary for the UI."""
    candidates = scan_environment()
    high = [c for c in candidates if c.score_tier == "high"]
    tools = {}
    for c in candidates: tools[c.tool] = tools.get(c.tool, 0) + 1
    
    report = ["### Discovered Memory Sources"]
    for t, count in tools.items():
        if t != "unknown": report.append(f"- **.{t}**: {count} artifacts found")
    
    report.append(f"\n**Total potential shards**: {len(high) * 2}")
    return "\n".join(report)

def gr_search(query):
    results = core.retrieve(query, limit=5)
    if not results: return "No records found."
    
    output = []
    for r in results:
        sentiment = "🌟" if r['utility_score'] > 1.0 else "🌑"
        output.append(f"## {r['title']} {sentiment}\n**ID**: {r['id']} | **Score**: {r['final_score']:.2f}\n\n{r['content']}\n")
    return "\n---\n".join(output)

def get_analytics():
    engine = history.HistoryEngine()
    growth = engine.get_growth_rate("week")
    utility = engine.get_utility_delta("week")
    timeline = engine.get_timeline("week")
    
    stats = f"""
# 📈 Intelligence Growth
- **New Shards (Week)**: {growth['new_shards']}
- **Total Substrate Size**: {growth['total_shards']} shards
- **Usefulness Delta**: {'+' if utility >= 0 else ''}{utility:.2f}
"""
    return stats, timeline


def check_current_transcript():
    log_path = os.path.join(os.getcwd(), "transcript.log")
    if os.path.exists(log_path):
        size_mb = os.path.getsize(log_path) / (1024 * 1024)
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                # Read last 100 lines for preview
                lines = f.readlines()
                preview = "".join(lines[-100:])
        except Exception as e:
            preview = f"Error reading log preview: {e}"
        return f"🟢 Transcript exists.\n- **Size**: {size_mb:.2f} MB\n- **Log File**: `{log_path}`", log_path, preview
    return "⚪ No transcript generated yet. Click 'Generate Transcript' below.", None, ""


def generate_transcript():
    script_path = os.path.join(os.getcwd(), "tools", "read_vault_shards.py")
    res = subprocess.run([sys.executable, script_path, "--cluster"], capture_output=True, text=True, encoding="utf-8")
    if res.returncode == 0:
        return check_current_transcript()
    else:
        err_msg = res.stderr or res.stdout or "Unknown execution error."
        return f"🔴 Generation failed:\n```\n{err_msg}\n```", None, ""


# --- The HUD Layout ---

with gr.Blocks(title="NouGenShards Cortex HUD", theme=gr.themes.Soft()) as cortex_hud:
    gr.Markdown("# 🪩 NouGenShards Cortex HUD")
    
    with gr.Tabs():
        with gr.Tab("🔍 Search"):
            search_input = gr.Textbox(label="Query the substrate", placeholder="What do I know about...")
            search_output = gr.Markdown()
            search_btn = gr.Button("Search Memory")
            search_btn.click(fn=gr_search, inputs=search_input, outputs=search_output)
            
        with gr.Tab("📈 History"):
            with gr.Row():
                with gr.Column():
                    stats_output = gr.Markdown()
                with gr.Column():
                    timeline_output = gr.Code(label="Growth Timeline (ASCII)")
            refresh_history = gr.Button("Refresh Analytics")
            refresh_history.click(fn=get_analytics, outputs=[stats_output, timeline_output])
            
        with gr.Tab("🗺️ Substrate"):
            gr.Markdown("## 9-Node SQLite Cluster")
            with gr.Row():
                maps = [gr.Markdown() for _ in range(9)]
            refresh_map = gr.Button("Refresh Substrate Map")
            for i in range(9):
                refresh_map.click(fn=lambda i=i: get_substrate_map()[i], outputs=maps[i])
                
        with gr.Tab("🧠 Recon"):
            recon_output = gr.Markdown("Click to scan local AI history.")
            recon_btn = gr.Button("Run Brain Scan")
            recon_btn.click(fn=run_recon, outputs=recon_output)

        with gr.Tab("📝 Transcript"):
            gr.Markdown("## 🗂️ Local Node Transcripter")
            status_md = gr.Markdown("Checking status...")
            download_file = gr.File(label="Download transcript.log")
            preview_box = gr.Textbox(label="Log Preview (Last 100 lines)", lines=15, interactive=False)
            generate_btn = gr.Button("Generate Transcript")
            
            generate_btn.click(
                fn=generate_transcript,
                inputs=[],
                outputs=[status_md, download_file, preview_box]
            )
            cortex_hud.load(
                fn=check_current_transcript,
                inputs=[],
                outputs=[status_md, download_file, preview_box]
            )


# The Cortex HUD exposes search, recon, substrate maps and full vault transcript
# dumps — none of it behind the write-token. When the node is reachable beyond
# loopback the UI MUST require a login: set NGS_HUD_USER / NGS_HUD_PASSWORD.
_hud_user = os.environ.get("NGS_HUD_USER")
_hud_pass = os.environ.get("NGS_HUD_PASSWORD")
_hud_auth = (_hud_user, _hud_pass) if _hud_user and _hud_pass else None


class _TokenGatedMCP:
    """ASGI gate for the /mcp mount: same deny-by-default semantics as
    verify_token (503 unconfigured, 401 mismatch), but accepts the token as
    either the X-NGS-Token header or a ?token= query parameter - the Claude
    app's custom connectors cannot attach arbitrary headers, so the query
    form is the mobile path. NODE_TOKEN is read at call time so tests (and
    runtime reconfiguration) can swap it without re-importing the module."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            if not NODE_TOKEN:
                await self._reject(send, 503, "Node write-auth not configured.")
                return
            headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                       for k, v in scope.get("headers", [])}
            supplied = headers.get("x-ngs-token")
            if not supplied:
                from urllib.parse import parse_qs
                qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
                supplied = (qs.get("token") or [None])[0]
            if not supplied or not hmac.compare_digest(str(supplied), str(NODE_TOKEN)):
                await self._reject(send, 401, "Invalid node token.")
                return
        await self.inner(scope, receive, send)

    @staticmethod
    async def _reject(send, status, detail):
        body = json.dumps({"detail": detail}).encode("utf-8")
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


# Mount BEFORE the Gradio catch-all at "/" so /mcp is routed to the MCP app.
app.mount("/mcp", _TokenGatedMCP(_mcp_asgi))

app = gr.mount_gradio_app(app, cortex_hud, path="/", auth=_hud_auth)

if __name__ == "__main__":
    import uvicorn
    # Bind to loopback by default so the (intentionally unauthenticated) read /
    # recon / transcript UI is not silently exposed. HF Spaces / explicit deploys
    # set NGS_HOST=0.0.0.0; warn if bound non-loopback without HUD auth.
    default_host = "0.0.0.0" if os.environ.get("SPACE_ID") else "127.0.0.1"
    host = os.environ.get("NGS_HOST", default_host)
    port = int(os.environ.get("NGS_PORT", "4444"))
    if host not in ("127.0.0.1", "localhost", "::1") and not _hud_auth:
        print("[WARN] Cortex HUD bound to a non-loopback host without "
              "NGS_HUD_USER/NGS_HUD_PASSWORD — search/recon/transcript "
              "endpoints are unauthenticated and network-exposed.")
    uvicorn.run(app, host=host, port=port)
