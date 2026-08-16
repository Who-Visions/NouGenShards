import sys
import json
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    if len(sys.argv) < 2:
        print("Usage: delegate_task.py '<instruction>' [<model_name>]")
        sys.exit(1)
        
    task = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "gemma4:e2b"
    url = "http://localhost:11434/api/generate"
    
    data = {
        "model": model,
        "prompt": f"You are a local free agent. Execute this task:\n\n{task}",
        "stream": False
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    print("[INFO] Delegating task to local Free Agent (Yukiai:latest)...")
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            res = json.loads(response.read().decode('utf-8'))
            print("\n--- [Free Agent Output] ---")
            print(res.get("response", ""))
            print("---------------------------")
    except Exception as e:
        print(f"[ERROR] Delegation failed: {e}")

if __name__ == "__main__":
    main()
