import json,subprocess,sys,time,pathlib
h=pathlib.Path.home()
for p in [h/".codex/hooks.json",h/".codex/hooks/nougen_lifecycle.py",h/".gemini/config/hooks.json",h/".gemini/config/scripts/check_inbox_and_continue.py"]:
    print("OK " if p.exists() else "MISSING ", p)
lc=str(h/".codex/hooks/nougen_lifecycle.py"); cur=h/".nougen/state/codex_eot_cursor.json"
cur.unlink(missing_ok=True); E='{"hook_event_name":"Stop","session_id":"test"}'
def run():
    return subprocess.run([sys.executable, lc], input=E, capture_output=True, text=True, timeout=60)

r=run(); print("1 seed:",r.stdout[:120],r.stderr[-200:])
r=run(); print("2 idle:",r.stdout[:120])
time.sleep(1.2); t=h/".nougen/codex/inbox/ping_test_eot.json"; t.write_text('{"message":"TEST ping"}')
r=run(); print("3 new:",r.stdout[:120])
r=run(); print("4 after:",r.stdout[:120]); t.unlink()
r=subprocess.run([sys.executable,str(h/".gemini/config/scripts/check_inbox_and_continue.py")],input='{"hook_event_name":"Stop"}',capture_output=True,text=True,timeout=60)
print("5 agy:",r.stdout[:160],r.stderr[-200:])
print("codex hooks.json valid:", bool(json.loads((h/".codex/hooks.json").read_text(encoding="utf-8-sig"))["hooks"]["Stop"]))
