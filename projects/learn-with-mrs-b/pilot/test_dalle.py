import urllib.request
import json

key = ""
with open(r"C:\Users\super\Outpost\Yuki-Ai\.env") as f:
    for line in f:
        if line.startswith("OPENAI_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")

url = "https://api.openai.com/v1/images/generations"
headers = {
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json"
}

payload = {
    "model": "gpt-image-1",
    "prompt": "Children coloring book page, letter A is for Astronaut. Pure black outline vector art on white background.",
    "size": "1024x1024"
}

req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print("SUCCESS from gpt-image-1!", data)
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
except Exception as e:
    print(f"Error: {e}")
