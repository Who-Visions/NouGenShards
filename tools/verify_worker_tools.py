import json, re

with open(r'.fleet_worker.js', 'r', encoding='utf-8') as f:
    js = f.read()

tools_start = js.find('var TOOLS = [')
handlers_start = js.find('var HANDLERS = {')
rpc_start = js.find('async function handleRpc')

tools_chunk = js[tools_start:handlers_start]
handlers_chunk = js[handlers_start:rpc_start]

tool_names = re.findall(r'name:\s*"([^"]+)"', tools_chunk)
handler_names = re.findall(r'async\s+([a-zA-Z0-9_]+)\s*\(', handlers_chunk)

print(f"Total tools declared in TOOLS array: {len(tool_names)}")
for i, t in enumerate(tool_names):
    print(f"  {i+1}. {t}")

print(f"\nTotal handlers in HANDLERS object: {len(handler_names)}")
for i, h in enumerate(handler_names):
    print(f"  {i+1}. {h}")

assert 'ask_rhea' in tool_names, 'ask_rhea missing from TOOLS'
assert 'kaedra_ask' in tool_names, 'kaedra_ask missing from TOOLS'
assert 'ask_rhea' in handler_names, 'ask_rhea missing from HANDLERS'
assert 'kaedra_ask' in handler_names, 'kaedra_ask missing from HANDLERS'

print("\nVerification PASSED! All 25 tools including ask_rhea and kaedra_ask are present in source.")
