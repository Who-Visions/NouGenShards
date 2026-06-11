"""
NouGenShards Production Node for Hugging Face Spaces.
Architecture: FastAPI + Persistent Storage (/data) + Token Auth + Cloud Gateway.
"""
import os
import sys
import json
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel

# Add src to path for absolute imports
sys.path.append(os.path.join(os.getcwd(), 'src'))

# Override Storage for HF Persistence
if os.environ.get("SPACE_ID"):
    os.environ["NOUGEN_HOME"] = "/data"
    os.environ["NOUGEN_VAULT_DIR"] = "/data/.vault"

from nougen_shards import core, federation, history, keymaker, billing
from nougen_shards.models_client import OpenRouterClient, OpenAIClient

app = FastAPI(title="NouGenShards Node")

# --- Security (Module 10: Enforced Auth) ---

NODE_TOKEN = os.environ.get("NGS_NODE_TOKEN")

def verify_token(x_ngs_token: str = Header(None)):
    """Verifies the NGS_NODE_TOKEN for mutative operations and gateway access."""
    if not NODE_TOKEN:
        raise HTTPException(status_code=503, detail="Node write-auth not configured.")
    if x_ngs_token != NODE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid node token.")
    return x_ngs_token

# --- Schemas ---

class SearchQuery(BaseModel):
    query: str
    limit: int = 3
    semantic: bool = False

class ShardInput(BaseModel):
    event_type: str
    title: str
    content: str
    tags: Optional[List[str]] = None
    embedding: Optional[List[float]] = None

class MarkInput(BaseModel):
    shard_id: int
    worked: bool

class SyncPushInput(BaseModel):
    shards: List[dict]

class CloudChatInput(BaseModel):
    model: str
    messages: List[dict]
    stream: bool = False
    fallback_models: Optional[List[str]] = None
    session_id: Optional[str] = None

# --- Endpoints ---

@app.get("/health")
def health():
    return {
        "status": "ignited",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "storage": os.environ.get("NOUGEN_HOME", "default")
    }

@app.post("/search")
def search(q: SearchQuery):
    results = core.retrieve(q.query, limit=q.limit)
    for r in results:
        if "embedding" in r and isinstance(r["embedding"], bytes):
            r["embedding"] = json.loads(r["embedding"].decode())
    return results

@app.post("/capture", dependencies=[Depends(verify_token)])
def capture(shard: ShardInput):
    success = core.capture(
        shard.event_type, 
        shard.title, 
        shard.content, 
        shard.tags, 
        embedding=shard.embedding
    )
    if not success:
        return {"status": "exists", "message": "Shard already in substrate."}
    return {"status": "captured"}

# --- Who Visions Cloud Gateway (Module 8: System Harmonization) ---

@app.post("/cloud/chat")
def cloud_chat(input: CloudChatInput, token: str = Depends(verify_token)):
    """
    Hosted Cloud LLM Gateway.
    Protects Who Visions keys and enforces metered billing.
    """
    # 1. Check Subscription
    sub = billing.check_subscription(token)
    if sub["status"] != "active":
        raise HTTPException(status_code=402, detail=sub["message"])
        
    # 2. Call Provider Server-Side
    # (Uses the node's own OpenRouter key from environment)
    client = OpenRouterClient()
    if not client.is_alive():
        raise HTTPException(status_code=500, detail="Cloud provider not configured on node.")
        
    res = client.chat_with_fallback(
        model=input.model,
        messages=input.messages,
        fallback_models=input.fallback_models,
        session_id=input.session_id,
        stream=input.stream
    )
    
    # 3. Meter Usage
    if "usage" in res:
        billing.log_usage(token, "openrouter", res.get("model", "unknown"), res["usage"])
        
    return res

@app.get("/stats")
def stats(period: str = "week"):
    engine = history.HistoryEngine()
    return {
        "growth": engine.get_growth_rate(period),
        "utility": engine.get_utility_delta(period),
        "timeline": engine.get_timeline(period)
    }

# --- Sync Fabric ---

@app.get("/sync/pull", dependencies=[Depends(verify_token)])
def sync_pull():
    all_shards = []
    for i in range(1, core.MAX_DB_COUNT + 1):
        if not core.get_db_path(i).exists(): continue
        conn = core.get_connection(i)
        rows = conn.execute("SELECT * FROM shards").fetchall()
        for r in rows:
            d = dict(r)
            if d.get("embedding"): d["embedding"] = json.loads(d["embedding"].decode())
            all_shards.append(d)
        conn.close()
    return all_shards

@app.post("/sync/push", dependencies=[Depends(verify_token)])
def sync_push(input: SyncPushInput):
    count = 0
    for s in input.shards:
        success = core.capture(
            s.get("event_type", "SYNC"),
            s.get("title", "Synced Shard"),
            s.get("content", ""),
            json.loads(s.get("tags", "[]")) if isinstance(s.get("tags"), str) else s.get("tags"),
            embedding=s.get("embedding")
        )
        if success: count += 1
    return {"status": "synced", "count": count}

# --- Gradio UI (Secondary Explorer) ---
import gradio as gr

def gr_search(query):
    results = core.retrieve(query, limit=5)
    if not results: return "No records found."
    return "\n---\n".join([f"### {r['title']}\n{r['content']}" for r in results])

io = gr.Interface(
    fn=gr_search,
    inputs="text",
    outputs="markdown",
    title="NouGenShards Explorer",
    allow_flagging="never"
)

app = gr.mount_gradio_app(app, io, path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=4444)
