import os
import re

def repl(path, old, new):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    if old in content:
        content = content.replace(old, new)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

# importer.py
repl('NouGenShards/src/nougen_shards/brain_scan/importer.py', 'from typing import List, Dict', 'from typing import List, Dict, Optional')
repl('NouGenShards/src/nougen_shards/brain_scan/importer.py', 'project_path: str = None', 'project_path: Optional[str] = None')
repl('NouGenShards/src/nougen_shards/brain_scan/importer.py', 'source_filter: str = None', 'source_filter: Optional[str] = None')

# scanner.py
repl('NouGenShards/src/nougen_shards/brain_scan/scanner.py', 'from typing import List', 'from typing import List, Optional')
repl('NouGenShards/src/nougen_shards/brain_scan/scanner.py', 'project_path: str = None', 'project_path: Optional[str] = None')

# cli.py
repl('NouGenShards/src/nougen_shards/cli.py', 'project_path=getattr(args, \'project\', None),', 'project_path=str(getattr(args, \'project\')) if getattr(args, \'project\', None) else None,')
repl('NouGenShards/src/nougen_shards/cli.py', 'source_filter=getattr(args, \'source\', None),', 'source_filter=str(getattr(args, \'source\')) if getattr(args, \'source\', None) else None,')
repl('NouGenShards/src/nougen_shards/cli.py', 'engine.get_growth_stats(period)', 'engine.get_growth_rate(period)')

# core.py
repl('NouGenShards/src/nougen_shards/core.py', 'from pathlib import Path\n', 'from pathlib import Path\nfrom typing import List, Optional\n')
repl('NouGenShards/src/nougen_shards/core.py', 'tags: list = None, embedding: list = None', 'tags: Optional[List[str]] = None, embedding: Optional[List[float]] = None')
repl('NouGenShards/src/nougen_shards/core.py', 'history.log_event(cursor.lastrowid, target_idx, "CREATED", new_score=1.0)', 'history.log_event(cursor.lastrowid or 0, target_idx, "CREATED", new_score=1.0)')
repl('NouGenShards/src/nougen_shards/core.py', 'query_embedding: list = None', 'query_embedding: Optional[List[float]] = None')

# federation.py
repl('NouGenShards/src/nougen_shards/federation.py', 'from . import keymaker\n', 'from . import keymaker\nfrom typing import List, Optional\n')
repl('NouGenShards/src/nougen_shards/federation.py', 'query_embedding: list = None', 'query_embedding: Optional[List[float]] = None')

# history.py
repl('NouGenShards/src/nougen_shards/history.py', 'from datetime import datetime, timedelta\n', 'from datetime import datetime, timedelta\nfrom typing import Optional\n')
repl('NouGenShards/src/nougen_shards/history.py', 'old_score: float = None, new_score: float = None, metadata: dict = None', 'old_score: Optional[float] = None, new_score: Optional[float] = None, metadata: Optional[dict] = None')

# keymaker.py
repl('NouGenShards/src/nougen_shards/keymaker.py', 'from pathlib import Path\n', 'from pathlib import Path\nfrom typing import Optional\n')
repl('NouGenShards/src/nougen_shards/keymaker.py', 'def get_secret(key: str) -> str:', 'def get_secret(key: str) -> Optional[str]:')
repl('NouGenShards/src/nougen_shards/keymaker.py', 'return row[0] if row else None', 'return str(row[0]) if row else None')

# mcp.py
repl('NouGenShards/src/nougen_shards/mcp.py', 'import json\n', 'import json\nfrom typing import Optional, List\n')
repl('NouGenShards/src/nougen_shards/mcp.py', 'tags: list = None', 'tags: Optional[List[str]] = None')
repl('NouGenShards/src/nougen_shards/mcp.py', 'metadata: dict = None', 'metadata: Optional[dict] = None')
repl('NouGenShards/src/nougen_shards/mcp.py', 'nougen_context.search_events', 'nougen_context.get_event')

# models_client.py
repl('NouGenShards/src/nougen_shards/models_client.py', 'api_key: str = None', 'api_key: Optional[str] = None')
repl('NouGenShards/src/nougen_shards/models_client.py', 'fallback_models: list = None', 'fallback_models: Optional[list] = None')
repl('NouGenShards/src/nougen_shards/models_client.py', 'session_id: str = None', 'session_id: Optional[str] = None')
repl('NouGenShards/src/nougen_shards/models_client.py', 'node_url: str = None, user_token: str = None', 'node_url: Optional[str] = None, user_token: Optional[str] = None')

with open('NouGenShards/src/nougen_shards/models_client.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('req.add_header("Authorization", f"Bearer {self.api_key}")', 'req.add_header("Authorization", f"Bearer {self.api_key or \'\'}")')
content = content.replace('req.add_header("x-api-key", self.api_key)', 'req.add_header("x-api-key", self.api_key or "")')
content = content.replace('url = self.node_url.rstrip(\'/\')', 'url = self.node_url.rstrip(\'/\') if self.node_url else \'\'')
content = content.replace('req.add_header("X-NGS-Token", self.user_token)', 'req.add_header("X-NGS-Token", self.user_token or "")')

with open('NouGenShards/src/nougen_shards/models_client.py', 'w', encoding='utf-8') as f:
    f.write(content)

# nougen_context.py
repl('NouGenShards/src/nougen_shards/nougen_context.py', 'from datetime import datetime, timezone\n', 'from datetime import datetime, timezone\nfrom typing import Optional\n')
repl('NouGenShards/src/nougen_shards/nougen_context.py', 'metadata: dict = None', 'metadata: Optional[dict] = None')

with open('NouGenShards/src/nougen_shards/nougen_context.py', 'r', encoding='utf-8') as f:
    ctx_content = f.read()
if 'def search_events' not in ctx_content:
    with open('NouGenShards/src/nougen_shards/nougen_context.py', 'a', encoding='utf-8') as f:
        f.write('''
def search_events(query: str, limit: int = 5) -> list:
    conn = get_context_connection()
    try:
        rows = conn.execute("SELECT id, type, content as description, timestamp, metadata FROM ctx_events LIMIT ?", (limit,)).fetchall()
        return [{"id": r["id"], "event_type": r["type"], "description": r["description"], "timestamp": r["timestamp"], "metadata": r["metadata"]} for r in rows]
    finally:
        conn.close()
''')

print("Types patched.")
