"""Cloud Connector for remote NouGenShards instances."""
import json
import urllib.request
import urllib.error

def query_cloud_shards(query: str, cloud_configs: list, limit: int = 3) -> list:
    """
    Queries remote NouGenShards nodes and maps results to standard format.
    """
    results = []
    
    for conf in cloud_configs:
        url = conf['url'].rstrip('/')
        name = conf['name']
        
        try:
            # POST /search
            payload = {"query": query, "limit": limit}
            req = urllib.request.Request(
                f"{url}/search",
                data=json.dumps(payload).encode(),
                method="POST"
            )
            req.add_header("Content-Type", "application/json")
            
            with urllib.request.urlopen(req, timeout=5.0) as res:
                remote_data = json.loads(res.read().decode())
                if isinstance(remote_data, list):
                    for r in remote_data:
                        # Normalize to local shard shape
                        results.append({
                            "id": f"cloud_{conf['id']}_{r.get('id')}",
                            "event_type": f"CLOUD_{r.get('event_type', 'SHARD')}",
                            "title": r.get('title', 'Untitled Cloud Shard'),
                            "content": r.get('content', ''),
                            "tags": r.get('tags', '[]'),
                            "utility_score": r.get('utility_score', 1.0),
                            "access_count": r.get('access_count', 0),
                            "file_hash": r.get('file_hash', ''),
                            "final_score": r.get('final_score', 0.45),
                            "_db_index": f"cloud_{name}"
                        })
        except Exception:
            # Silent fail to prevent blocking the federation loop
            # (Module 10: Graceful Degradation)
            continue
            
    return results

def push_to_cloud(shards: list, cloud_url: str, token: str) -> dict:
    """Pushes a list of shards to a remote cloud node."""
    url = cloud_url.rstrip('/')
    payload = {"shards": shards}
    try:
        req = urllib.request.Request(
            f"{url}/sync/push",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("X-NGS-Token", token)
        
        with urllib.request.urlopen(req, timeout=10.0) as res:
            return json.loads(res.read().decode())
    except Exception as e:
        return {"status": "error", "message": str(e)}

def pull_from_cloud(cloud_url: str, token: str) -> list:
    """Pulls all shards from a remote cloud node."""
    url = cloud_url.rstrip('/')
    try:
        req = urllib.request.Request(f"{url}/sync/pull", method="GET")
        req.add_header("X-NGS-Token", token)
        
        with urllib.request.urlopen(req, timeout=10.0) as res:
            return json.loads(res.read().decode())
    except Exception:
        return []
