import subprocess
import sys
import os

rca_content = """FLEET TRIANGLE POST-MORTEM & FAILURE AUDIT (2026-09-11)
SUBJECT: Why 3-Vault Federation Failed and Mistakes Made Across Lanes

1. FLAPPING SERVICES FROM BACKGROUND CLI CHAOS & BLIND KILL CALLS
- What went wrong: Ran 'Stop-Process -Name python' and blind taskkill commands on local Hyperion and remote Blade. This killed active uvicorn runners and sibling background tasks repeatedly.
- Consequence: As soon as WhoArt or Blade was verified green (200 OK), a subsequent command killed python or spawned a duplicate un-routed process, throwing the nodes back into 502 / Connection Refused.
- Lesson for next lane: Never run broad 'kill python' or 'taskkill cloudflared' blindly across nodes. Use explicit PID tracking or dedicated lifecycle scripts (node_lane.ps1 stop / start).

2. LOCAL CONSOLE CP1252 ENCODING CRASHES
- What went wrong: Injected Unicode arrows (→) and status emojis (✅, ❌, 🟢, 🔴) directly into Python print statements on Windows PowerShell.
- Consequence: The script crashed on line 48 and line 65 with UnicodeEncodeError before verification logic could even run or report truthfully.
- Lesson for next lane: Windows console defaults to cp1252. Stick to strict ASCII tags ([OK], [FAIL], [INFO], ->) or explicitly set PYTHONIOENCODING=utf-8 / utf-8 stream wrappers.

3. HARDCODED PORT DIVERGENCE (8765 vs 4444)
- What went wrong: WhoArt Cloudflare tunnel ingress was legacy-configured to route to http://127.0.0.1:8765, while the node app was listening on port 4444.
- Consequence: Cloudflare edge returned 502 Bad Gateway even when uvicorn was running.
- Fix executed: Updated Cloudflare tunnel configuration via API (cfd_tunnel/4b66f5fa-ce85-469b-9496-49608fd2e3eb/configurations) to route to http://127.0.0.1:4444. Next lane must ensure port 4444 is preserved across all ingress rules.

4. MULTIPLE STALE DAEMONS BATTLING OVER TUNNEL CONNECTIONS
- What went wrong: Blade had three separate cloudflared.exe instances (PIDs 36456, 22488, 19408) running concurrently from previous uncleaned tasks, causing edge connection drops, socket cancellation, and request timeouts.
- Consequence: blade.nougenai.com returned timeout / status 0 despite tunnel showing healthy.
- Lesson for next lane: Always verify single-instance daemon ownership before launching new tunnel processes over SSH.

5. MISSING RUNTIME TOKEN CONTEXT (NGS_NODE_TOKEN)
- What went wrong: Attempted to run 'python app.py' directly without exporting NGS_NODE_TOKEN from Keymaker.
- Consequence: /health reported node_token_configured=False and /mcp/ endpoint rejected valid lane tokens with 401 Unauthorized.
- Lesson for next lane: App must be launched via tools/node_lane.ps1 or with explicit Keymaker token extraction so the node token is set in the environment.

6. PEER FEDERATION PRINCIPLE (DO NOT REWRITE INGRESS)
- Rule violated earlier: Connector was repointed directly to whoart-vault instead of maintaining equal peer status across Blade, Phoebus, and WhoArt.
- Truth: All 3 nodes are peers. Gateway Worker must fan out to all 3 endpoints concurrently without king/leader bias.
"""

cmd = [
    sys.executable,
    "-m",
    "nougen_shards.cli",
    "add",
    "--domain",
    "fleet_ops",
    "--tags",
    "rca,post_mortem,fleet_ops,failure_audit,tunnel,federation",
    rca_content.strip()
]

proc = subprocess.run(cmd, cwd=r"C:\Users\super\Outpost\NouGen", capture_output=True, text=True, encoding="utf-8")
print("STDOUT:", proc.stdout.encode('ascii', 'backslashreplace').decode('ascii'))
print("STDERR:", proc.stderr.encode('ascii', 'backslashreplace').decode('ascii'))
print("EXIT CODE:", proc.returncode)
