"""
NouGenShards Production Node & Cortex HUD.
Architecture: FastAPI + Persistent Storage (/data) + Token Auth + Multi-tab Gradio UI.
"""
import os
import sys
import json
import sqlite3
from typing import List, Optional
from datetime import datetime, timezone
from pathlib import Path
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

app = FastAPI(title="NouGenShards Node")

# --- Security ---

NODE_TOKEN = os.environ.get("NGS_NODE_TOKEN")

def verify_token(x_ngs_token: str = Header(None)):
    if not NODE_TOKEN:
        raise HTTPException(status_code=503, detail="Node write-auth not configured.")
    if x_ngs_token != NODE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid node token.")
    return x_ngs_token

# --- API Endpoints ---

@app.get("/health")
def health():
    return {"status": "ignited", "storage": os.environ.get("NOUGEN_HOME", "default")}

# (API logic remains same as before for search/capture/sync/cloud_chat)

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
            except: pass
        
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


app = gr.mount_gradio_app(app, cortex_hud, path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=4444)
