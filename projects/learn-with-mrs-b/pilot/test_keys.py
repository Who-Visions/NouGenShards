import os
import urllib.request
import json

def test_openai():
    p = r"~\Outpost\Yuki-Ai\.env"
    if not os.path.exists(p):
        return
    with open(p, "r", errors="ignore") as f:
        for line in f:
            if line.startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                print(f"Testing OPENAI_API_KEY: {key[:12]}... (len={len(key)})")
                req = urllib.request.Request("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"})
                try:
                    with urllib.request.urlopen(req) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        print("  SUCCESS! OpenAI Connected, models:", len(data.get("data", [])))
                except Exception as e:
                    print(f"  OpenAI Error: {e}")

test_openai()
