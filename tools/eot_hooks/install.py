import json,shutil,sys,pathlib
h=pathlib.Path.home(); s=pathlib.Path(__file__).resolve().parent; py=sys.executable
for d in [".codex/hooks",".gemini/config/scripts",".nougen/codex/inbox",".nougen/agy_inbox",".nougen/state"]: (h/d).mkdir(parents=True,exist_ok=True)
shutil.copy2(s/"codex_nougen_lifecycle.py",h/".codex/hooks/nougen_lifecycle.py")
shutil.copy2(s/"agy_check_inbox_and_continue.py",h/".gemini/config/scripts/check_inbox_and_continue.py")
for f in [h/".codex/hooks.json",h/".gemini/config/hooks.json"]:
    if f.exists(): shutil.copy2(f,f.with_suffix(".json.bak-20260929")); print("backed up",f)
c=f'"{py}" "{h/".codex/hooks/nougen_lifecycle.py"}"'
codex={"description":"NouGen lifecycle + end-of-turn inbox continue for Codex on this node.","hooks":{e:[{"hooks":[{"type":"command","command":c,"timeout":12}]}] for e in ["SessionStart","UserPromptSubmit","Stop","SessionEnd"]}}
(h/".codex/hooks.json").write_text(json.dumps(codex,indent=1))
a=f'"{py}" "{h/".gemini/config/scripts/check_inbox_and_continue.py"}"'
gp=h/".gemini/config/hooks.json"; g=json.loads(gp.read_text()) if gp.exists() else {}
g["end-of-turn-inbox-continue"]={"enabled":True,"PostInvocation":[{"type":"command","command":a,"timeout":10}],"Stop":[{"type":"command","command":a,"timeout":10}]}
gp.write_text(json.dumps(g,indent=1)); print("installed")
