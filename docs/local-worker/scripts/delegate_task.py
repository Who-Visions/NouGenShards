# Copyright 2026 Who Visions LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
