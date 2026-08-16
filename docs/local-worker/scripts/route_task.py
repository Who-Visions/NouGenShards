#!/usr/bin/env python3
import sys
import json
import urllib.request
from model_router import route_task

def run_local_task(task_description, category, model="gemma4:e2b"):
    print(f"⚡ [Routing Decision] Category: {category} -> Running task locally on {model}...")
    url = "http://localhost:11434/api/generate"
    data = {
        "model": model,
        "prompt": task_description,
        "stream": False
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode('utf-8'))
            print("\n--- [Local Output] ---")
            print(res.get("response", ""))
            print("----------------------")
    except Exception as e:
        print(f"❌ Error running local execution: {e}")

def main():
    if len(sys.argv) < 2:
        print("Usage: route_task.py '<task_description>'")
        sys.exit(1)
        
    task = sys.argv[1]
    print(f"🤔 Classifying task: '{task[:60]}...'")
    
    decision = route_task(task)
    category = decision.get("category", "CLOUD_COMPLEX")
    reason = decision.get("reason", "")
    
    print(f"💡 Classifier result: {category} ({reason})")
    
    if category in ["LOCAL_FAST", "LOCAL_STRUCTURED", "LOCAL_SCOPED_CODE"]:
        run_local_task(task, category)
    else:
        print("\n☁️ [Routing Decision] Category: CLOUD_COMPLEX -> Escaling task to remote Cloud model (Gemini 3.5 Flash/Pro).")

if __name__ == "__main__":
    main()
