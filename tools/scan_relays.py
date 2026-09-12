import os
import json
import glob

files = sorted(glob.glob(r'C:\Users\super\Outpost\NouGenRelay\.handoffs\*.json'))
print(f"Total handoff files: {len(files)}")
open_count = 0
for f in files:
    try:
        data = json.load(open(f, encoding='utf-8'))
        status = data.get('status')
        if status not in ('complete', 'resolved', 'done'):
            open_count += 1
            title = data.get('meta', {}).get('title') or data.get('title') or data.get('task') or data.get('goal')
            print(f"[{status}] {os.path.basename(f)}")
            print(f"   Target: {data.get('target_agent')} | Author: {data.get('author')}")
            print(f"   Title: {title}")
            print("---")
    except Exception as e:
        print(f"Error {f}: {e}")

print(f"Total open handoffs: {open_count}")
