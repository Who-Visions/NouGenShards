"""Cloud Connector for remote NouGenShards instances."""
import json
import urllib.request
import urllib.error

def query_cloud_shards(query: str, cloud_configs: list, limit: int = 3) -> list:
    """
    Queries remote NouGenShards cloud nodes and maps to standard format.
    Expects a remote POST endpoint that accepts {"query": "...", "limit": 3}
    """
    results = []
    
    for conf in cloud_configs:
        url = conf.get("url")
        name = conf.get("name", "remote_node")
        node_id = conf.get("id", "cloud")
        
        try:
            payload = {"query": query, "limit": limit}
            data = json.dumps(payload).encode("utf-8")
            
            # Use standard search endpoint (Module 10 strategy)
            req = urllib.request.Request(f"{url}/search", data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            # In v2.2, we might want to add X-Sol-Ai-Key if available in vault
            
            with urllib.request.urlopen(req, timeout=5) as response:
                remote_data = json.loads(response.read().decode("utf-8"))
                
                # Remote data might be a list of shards already
                for item in remote_data:
                    # Standardize Shard format with cloud source tracking
                    results.append({
                        "id": f"cloud_{node_id}_{item.get('id', hash(item.get('title', '')))}",
                        "event_type": "CLOUD_SHARD",
                        "title": item.get("title", "Remote Shard"),
                        "content": item.get("content", ""),
                        "tags": item.get("tags", "[\"cloud\"]"),
                        "utility_score": item.get("utility_score", 1.0),
                        "access_count": 0,
                        "file_hash": item.get("file_hash", ""),
                        "bm25_score": 0.0,
                        "final_score": 0.45, # Slightly lower prior than local/SQL
                        "_db_index": f"cloud_{name}"
                    })
        except Exception as e:
            # Silent fail to prevent blocking the federation loop
            # (Module 10: Graceful Degradation)
            continue
            
    return results
