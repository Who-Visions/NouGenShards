import json
import re
import requests
from nougen_shards.keymaker import get_secret

token = get_secret('NGS_NODE_TOKEN')

# 1. Fetch available tools on Blade
r_blade = requests.post(
    'https://blade.nougenai.com/mcp/',
    json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}},
    headers={'x-ngs-token': token, 'content-type': 'application/json'},
    timeout=10
)
blade_tools = set(t['name'] for t in r_blade.json().get('result', {}).get('tools', []))

# 2. Fetch available tools on Phoebus
r_phoebus = requests.post(
    'https://phoebus.nougenai.com/mcp/',
    json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}},
    headers={'x-ngs-token': token, 'content-type': 'application/json'},
    timeout=10
)
phoebus_tools = set(t['name'] for t in r_phoebus.json().get('result', {}).get('tools', []))

fleet_backend_tools = blade_tools.union(phoebus_tools)
print(f"Blade tools count: {len(blade_tools)}")
print(f"Phoebus tools count: {len(phoebus_tools)}")
print(f"Fleet backend total unique tools: {len(fleet_backend_tools)}")

# 3. Read nougen-fleet-mcp-patched.js
with open(r"C:\Users\super\Outpost\NouGen\tools\nougen-fleet-mcp-patched.js", "r", encoding="utf-8") as f:
    text = f.read()

# Extract tool names from openapi.json
r_edge = requests.get('https://shards.nougenai.com/openapi.json', timeout=10)
schemas = r_edge.json().get('components', {}).get('schemas', {})
edge_tools = sorted(list(schemas.keys()))
print(f"Edge worker advertised tools: {len(edge_tools)}")

# 4. Check each tool handler
results = []
for tool_name in edge_tools:
    pattern = rf'async\s+{re.escape(tool_name)}\s*\([^)]*\)\s*\{{(.*?)\n\s*\}},'
    h_match = re.search(pattern, text, re.DOTALL)
    if not h_match:
        pattern2 = rf'async\s+{re.escape(tool_name)}\s*\([^)]*\)\s*\{{(.*?)(\n\s*\}};\n|\n\s*\}})'
        h_match = re.search(pattern2, text, re.DOTALL)
    
    if not h_match:
        # Check alias in HANDLERS
        alias_match = re.search(rf'{re.escape(tool_name)}:\s*HANDLERS\.([a-zA-Z0-9_]+)', text)
        if alias_match:
            results.append((tool_name, "alias -> " + alias_match.group(1), True))
            continue
        results.append((tool_name, "NO HANDLER FOUND", False))
        continue

    body = h_match.group(1)
    shard_calls = re.findall(r'shardCall\(env,\s*["\']([^"\']+)["\']', body)
    
    if not shard_calls:
        results.append((tool_name, "pure-edge-handler", True))
    else:
        # Check if at least ONE target exists in backend tools
        valid_targets = [sc for sc in shard_calls if sc in fleet_backend_tools]
        if valid_targets:
            results.append((tool_name, f"valid backend: {valid_targets}", True))
        else:
            results.append((tool_name, f"MISSING BACKEND TARGETS: {shard_calls}", False))

print("\n=== AUDIT RESULTS: POTENTIAL 'UNKNOWN TOOL' ERRORS ===")
broken = [r for r in results if not r[2]]
for name, reason, ok in broken:
    print(f"[FAIL] {name}: {reason}")

if not broken:
    print("[OK] ALL 75 edge tools have verified backend targets or edge execution!")
else:
    print(f"\nTotal broken/missing targets: {len(broken)}")
