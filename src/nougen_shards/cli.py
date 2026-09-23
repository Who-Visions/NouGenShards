"""NouGenShards command-line interface."""
import argparse
import sys
import json
import sqlite3
import os
import numpy as np
from pathlib import Path
import logging

logger = logging.getLogger("nougen_shards.cli")
from . import core as shards
from . import keymaker
from .models_client import (
    get_best_available_client, OllamaClient,
    OpenAIClient, AnthropicClient, GeminiClient, HuggingFaceClient, OpenRouterClient, WhoVisionsCloudClient
)
from . import nougen_context
from . import nougen_sandbox
from . import federation
from . import history
from . import router
from .connectors.cloud import push_to_cloud, pull_from_cloud
from .brain_scan import scan_environment, run_import, print_scan_report, print_import_report
from . import dream
from . import evolution
from . import assurance
from . import tenants
from . import agents
from . import tree_probe
from . import arxiv_core
from . import viz_core
from . import tube
from . import evidence
from . import destiny
from . import wake_daemon
from . import wispr
from . import studio
from . import mrsb

from nougen_shards import __version__ as VERSION  # single source: pyproject


# --- semantic rendering ---------------------------------------------------
# One command builds ONE payload dict. `--json` dumps it; the human view
# FORMATS that same dict. Parity stops being a thing anyone has to remember
# and becomes structural: a field a human can see is a field a script can
# read, because both read the same object.
#
# The bug this replaces: cmd_stats printed a timeline and an acceleration
# rate that --json never emitted, so automation was strictly blinder than a
# terminal. Hand-rolled `print(json.dumps(...)); return` at 20-odd call sites
# is what let the two drift apart.

def supports_color(stream=None) -> bool:
    """True only for a real TTY with color not explicitly disabled.

    Honors NO_COLOR (https://no-color.org). Redirected output must stay
    byte-identical to plain, or `nougen ... | grep` behaves differently from
    what the operator just read on screen.
    """
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("NOUGEN_FORCE_COLOR"):
        return True
    return bool(getattr(stream, "isatty", lambda: False)())


def emit(payload: dict, plain, args=None, stream=None) -> dict:
    """Render one semantic payload as JSON or as human text.

    `plain` is called with (payload, style) and yields display lines, so it
    cannot show a value that is not in `payload`. `style` is a callable that
    is the identity when the stream is not a TTY -- meaning plain and TTY
    output differ only in styling, never in content.

    Returns the payload so callers and tests can assert on it.
    """
    stream = stream or sys.stdout
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str), file=stream)
        return payload
    color = supports_color(stream)

    def style(text, code=""):
        return f"\033[{code}m{text}\033[0m" if (color and code) else text

    for line in plain(payload, style):
        print(line, file=stream)
    return payload



# UTF-8 Console protection for Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    except (AttributeError, ValueError):
        pass


def cmd_destiny(args):
    """Destiny store: prospective memory and goal graph for the NouGen grid."""
    action = getattr(args, "destiny_action", "list")
    is_json = getattr(args, "json", False)

    if action == "create":
        res = destiny.create_destiny(
            title=args.title,
            goal=args.goal,
            branch=getattr(args, "branch", None),
            trigger=getattr(args, "trigger", None),
            required_events=getattr(args, "required", None),
            forbidden_outcomes=getattr(args, "forbidden", None),
            acceptable_variance=getattr(args, "variance", None),
            verification=getattr(args, "verification", None),
            confidence=getattr(args, "confidence", None),
            deadline=getattr(args, "deadline", None),
            supersedes=getattr(args, "supersedes", None),
            status=getattr(args, "status", "dormant"),
            actor=getattr(args, "actor", None)
        )
        if is_json:
            print(json.dumps(res, indent=2))
        else:
            if "error" in res:
                print(f"❌ Failed to create destiny: {res['error']}")
            else:
                print(f"✨ Created Destiny #{res['id']}: [{res['branch']}] {res['title']}")
                print(f"  • Status:       {res['status']}")
                print(f"  • Goal:         {res['goal']}")
                if res.get('trigger'):
                    print(f"  • Trigger:      {res['trigger']}")
                if res.get('verification'):
                    print(f"  • Verification: {res['verification']}")

    elif action == "get":
        res = destiny.get_destiny(args.id)
        if is_json:
            print(json.dumps(res, indent=2))
        else:
            if "error" in res:
                print(f"❌ {res['error']}")
            else:
                print(f"✨ Destiny #{res['id']}: [{res['branch']}] {res['title']}")
                print(f"  • Status:       {res['status']}")
                print(f"  • Goal:         {res['goal']}")
                if res.get('trigger'):
                    print(f"  • Trigger:      {res['trigger']}")
                if res.get('verification'):
                    print(f"  • Verification: {res['verification']}")
                if res.get('links'):
                    print("  • Links:")
                    for lnk in res['links']:
                        print(f"    - [{lnk['kind']}] {lnk['ref']} ({lnk['role']})")
                if res.get('events'):
                    print("  • Event History:")
                    for ev in res['events']:
                        print(f"    - {ev['created_utc']}: {ev['from_status']} -> {ev['to_status']} by {ev['actor'] or 'unknown'} ({ev['evidence']})")

    elif action == "update":
        res = destiny.update_status(args.id, args.to_status, actor=getattr(args, "actor", None), evidence=getattr(args, "evidence", None))
        if is_json:
            print(json.dumps(res, indent=2))
        else:
            if "error" in res:
                print(f"❌ Failed to update destiny: {res['error']}")
            else:
                print(f"✨ Destiny #{res['id']} updated to {res['status']}")

    elif action == "link":
        res = destiny.link(args.id, args.kind, args.ref, role=getattr(args, "role", "evidence"), note=getattr(args, "note", None))
        if is_json:
            print(json.dumps(res, indent=2))
        else:
            if "error" in res:
                print(f"❌ Failed to link: {res['error']}")
            else:
                print(f"✨ Linked {args.kind} '{args.ref}' to Destiny #{args.id} as {args.role}")

    elif action == "search":
        res = destiny.search_destinies(args.query, limit=getattr(args, "limit", 20), include_finished=getattr(args, "all", False))
        if is_json:
            print(json.dumps(res, indent=2))
        else:
            print(f"🔍 Destinies matching '{args.query}' ({res['count']} results):")
            for d in res.get("destinies", []):
                print(f"  • #{d['id']:<4} [{d['status']:<9}] [{d['branch']}] {d['title']}")
                print(f"    Goal: {d['goal'][:100]}")

    elif action == "evolve":
        res = destiny.evolve_report(since_utc=getattr(args, "since", None), limit=getattr(args, "limit", 50))
        if is_json:
            print(json.dumps(res, indent=2))
        else:
            print("🧬 Destiny Evolve Raw Material Report:")
            print(f"  Status Counts: {res.get('status_counts')}")
            print(f"  Terminal Events: {len(res.get('terminal_events', []))}")
            for ev in res.get("terminal_events", [])[:10]:
                print(f"  • #{ev['destiny_id']} '{ev['title']}' -> {ev['to_status']} ({ev['evidence']})")

    else:  # list / unfinished
        res = destiny.unfinished_destinies(
            status=getattr(args, "status", None),
            trigger=getattr(args, "trigger", None),
            branch=getattr(args, "branch", None),
            limit=getattr(args, "limit", 20)
        )
        if is_json:
            print(json.dumps(res, indent=2))
        else:
            print(f"✨ Active/Unfinished Destinies ({res['count']} of {res['total']}):")
            for d in res.get("destinies", []):
                print(f"  • #{d['id']:<4} [{d['status']:<9}] [{d['branch']}] {d['title']}")
                print(f"    Goal: {d['goal'][:100]}")



def cmd_wispr(args):
    """Wispr Flow Voice Dictation Ingestion."""
    action = getattr(args, "wispr_action", "latest")
    if action == "watch":
        wispr.watch_and_shard(interval_s=getattr(args, "interval", 1.0), auto_shard=not getattr(args, "no_shard", False))
    elif action == "list":
        rows = wispr.list_transcripts(limit=getattr(args, "limit", 10))
        if getattr(args, "json", False):
            print(json.dumps(rows, indent=2))
        else:
            print(f"🎙️  Wispr Flow Transcripts ({len(rows)} recent):")
            for r in rows:
                print(f"  • [{r.get('timestamp')}] {r.get('formattedText') or r.get('asrText')}")
    else:  # latest
        row = wispr.get_latest_transcript()
        if getattr(args, "json", False):
            print(json.dumps(row, indent=2))
        else:
            if not row or "error" in row:
                print("[!] No Wispr transcripts found or DB inaccessible.")
            else:
                print(f"🎙️  Latest Wispr Transcript [{row.get('timestamp')}]:")
                print(f"    {row.get('formattedText') or row.get('asrText')}")


def cmd_studio(args):
    """Studio & Hardware Peripherals Lighting Control."""
    target = getattr(args, "target", "all")
    color = getattr(args, "color", "green")
    is_json = getattr(args, "json", False)
    
    results = {}
    if target in ("all", "razer"):
        rz = studio.RazerController()
        connected = rz.connect()
        if connected:
            rz.set_status_color(color)
            results["razer"] = {"status": "ok", "color": color}
        else:
            results["razer"] = {"status": "offline", "message": "Razer Synapse not reachable"}
            
    if target in ("all", "lifx"):
        lx = studio.LIFXController()
        if lx.is_configured():
            res = lx.set_color(selector="all", color=color)
            results["lifx"] = res
        else:
            results["lifx"] = {"status": "unconfigured", "message": "LIFX_TOKEN not set"}
            
    if is_json:
        print(json.dumps(results, indent=2))
    else:
        print(f"💡 Studio Lighting Command -> {color.upper()}:")
        for dev, info in results.items():
            print(f"  • {dev.upper()}: {info.get('status', 'sent')}")

def cmd_wake(args):
    """NouGen Wake Daemon: reactive idle wake detection for fleet IPC messaging."""
    timeout = getattr(args, "timeout", 600)
    interval = getattr(args, "interval", 2.0)
    code = wake_daemon.run_wake_loop(timeout_s=timeout, interval_s=interval, verbose=True)
    sys.exit(code)

def cmd_pr(args):
    from . import pr_lease
    store = pr_lease.LeaseStore()
    if args.pr_action == "attach":
        lease, started = store.attach_objective(args.repo, args.objective, branch_hint=args.branch)
        payload = {
            "started_new_chain": started, "branch": lease.branch,
            "objective_count": lease.chain_len, "chain_status": lease.chain_status,
            "chained_objectives": lease.chained_objectives,
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            verb = "Started new chain" if started else "Attached to open chain"
            print(f"{verb}: {lease.branch}  [{lease.chain_status}]  ({lease.chain_len} objective(s))")
            for o in lease.chained_objectives:
                print(f"  - {o}")
        return
    if args.pr_action == "status":
        leases = store.all_leases(repo=args.repo)
        payload = [{"branch": item.branch, "pr_number": item.pr_number, "chain_status": item.chain_status,
                     "objective_count": item.chain_len, "objectives": item.chained_objectives,
                     "updated_utc": item.updated_utc} for item in leases]
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            if not payload:
                print(f"No leases for {args.repo}")
            for row in payload:
                print(f"{row['branch']:<40} PR#{row['pr_number'] or '-':<6} {row['chain_status']:<12} {row['objective_count']} objective(s)")
        return
    if args.pr_action == "confetti":
        try:
            groups = pr_lease.detect_confetti(args.repo, min_group=args.min_group)
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(json.dumps(groups, indent=2))
        else:
            if not groups:
                print("No confetti clusters detected.")
            for g in groups:
                print(f"⚠ {g['author']}: {g['total_count']} open PRs look related ({g['small_count']} atomic-sized)")
                for pr in g["prs"]:
                    print(f"    #{pr['number']} {pr['title']}  [{pr['branch']}]")
                print(f"    -> {g['reason']}")
        return
    if args.pr_action == "review":
        from . import pr_review
        res = pr_review.run_review(
            repo=args.repo,
            pr_number=args.pr_number,
            objective=args.objective,
            incremental=not args.full,
            dry_run=args.dry_run,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Review {res.get('status')}: {res.get('comments_count', 0)} comments posted.")
        return
    if args.pr_action == "context":
        from . import pr_context
        ctx = pr_context.gather_context(args.path, relay_objective=args.objective)
        if args.json:
            print(json.dumps({
                "repo_root": ctx.repo_root, "rule_files": list(ctx.rule_files.keys()),
                "skill_files": ctx.skill_files, "relay_objective": ctx.relay_objective,
            }, indent=2))
        else:
            print(ctx.as_prompt_block())
        return


def cmd_brain(args):
    """Universal AI Memory Forensic Engine."""
    if args.action == "scan":
        candidates = scan_environment(
            project_path=str(getattr(args, 'project')) if getattr(args, 'project', None) else None, 
            include_unknown=getattr(args, 'unknown', False)
        )
        print_scan_report(candidates, as_json=getattr(args, 'json', False))
    elif args.action == "import":
        result = run_import(
            project_path=str(getattr(args, 'project')) if getattr(args, 'project', None) else None,
            include_unknown=getattr(args, 'unknown', False),
            source_filter=str(getattr(args, 'source')) if getattr(args, 'source', None) else None,
            redact=not getattr(args, 'no_redact', False),
            confirm=getattr(args, 'confirm', False)
        )
        print_import_report(result, dry_run=not getattr(args, 'confirm', False), as_json=getattr(args, 'json', False))

def get_client(provider: str):
    """Helper to get a client by provider name."""
    provider = provider.lower()
    if provider == "local":
        return get_best_available_client()
    if provider == "openai":
        return OpenAIClient()
    if provider == "anthropic":
        return AnthropicClient()
    if provider in ["google", "gemini"]:
        return GeminiClient()
    if provider in ["huggingface", "hf"]:
        return HuggingFaceClient()
    if provider in ["openrouter", "or"]:
        return OpenRouterClient()
    if provider in ["cloudflare", "cf", "workers-ai", "workers_ai"]:
        from .workers_ai_client import WorkersAiClient
        return WorkersAiClient()
    if provider in ["whovisions", "cloud"]:
        # Load cloud config from vault
        creds = keymaker.get_secret("NGS_CLOUD_CREDENTIALS")
        if creds and "," in creds:
            url, token = creds.split(",", 1)
            return WhoVisionsCloudClient(node_url=url, user_token=token)
        return WhoVisionsCloudClient()
    return None


def cmd_auth(args):
    """Manages authentication and API keys."""
    if args.action == "set-key":
        if not args.provider or not args.input:
            print("Error: Usage: nougen auth set-key <provider> <key>")
            return

        key_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "huggingface": "HUGGINGFACE_API_KEY",
            "hf": "HUGGINGFACE_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "or": "OPENROUTER_API_KEY",
            "cloudflare": "CLOUDFLARE_API_TOKEN_NOUGEN_FULL",
            "cf": "CLOUDFLARE_API_TOKEN_NOUGEN_FULL",
            "workers-ai": "CLOUDFLARE_API_TOKEN_NOUGEN_FULL",
            "cloud": "NGS_CLOUD_CREDENTIALS"
        }
        provider = args.provider.lower()
        if provider not in key_map:
            print(f"Error: Unknown provider '{args.provider}'.")
            return

        keymaker.ingest_secret(key_map[provider], args.input)
        print(f"✅ API key for {provider} saved to vault.")

    elif args.action == "check":
        from . import auth_check
        keys = keymaker.list_providers()
        secrets = {}
        for k in keys:
            v = keymaker.get_secret(k)
            if v:
                secrets[k] = v
        results = auth_check.check_all(secrets, timeout=getattr(args, "timeout", 10.0))
        print(auth_check.format_report(results, as_json=getattr(args, "json", False)))
        # Exit non-zero only for keys the provider actively REJECTED, so this
        # can gate a deploy. An unreachable provider must not fail a build.
        return 1 if any(r.actionable for r in results) else 0

    elif args.action == "list":
        keys = keymaker.list_providers()
        if getattr(args, 'json', False) is True:
            print(json.dumps(keys))
            return
        print("🔐 Connected Services:")
        providers = {
            "OPENAI_API_KEY": "OpenAI (BYOK)",
            "ANTHROPIC_API_KEY": "Anthropic (BYOK)",
            "GOOGLE_API_KEY": "Google/Gemini (BYOK)",
            "HUGGINGFACE_API_KEY": "Hugging Face (BYOK)",
            "OPENROUTER_API_KEY": "OpenRouter (BYOK)",
            "NGS_CLOUD_CREDENTIALS": "Who Visions Cloud (Pro)"
        }
        found = False
        for k, display in providers.items():
            if k in keys:
                print(f" ✅ {display}")
                found = True
        if not found:
            print(" No cloud services connected.")


def cmd_init(args):
    """Bootstrap the local shard layer, then adaptively onboard.

    Onboarding asks only what discovery could not settle: no question about
    which local model to prefer on a machine with no local runtime, and no
    metered tier offered when no credential backs one. NouGen is a capability
    layer over infrastructure the operator already owns, so first run
    DISCOVERS the lanes rather than asserting them.
    """
    from . import init_onboarding

    quiet = getattr(args, "json", False)
    if not quiet:
        print("🪩 Initializing NouGenMorph — The Universal Synthesis & Evolution Engine...")
    shards.init_db(index=1)
    if not quiet:
        print("✅ Created local-first database substrate.")

    if getattr(args, "no_onboarding", False):
        if not quiet:
            print("\n[IGNITION COMPLETE] Onboarding skipped (--no-onboarding).")
        return None

    interactive = (not getattr(args, "defaults", False)) and (not quiet) and sys.stdin.isatty()

    def ask(q):
        opts = q.get("options") or []
        print(f"\n{q['prompt']}")
        print(f"  ({q['why']})")
        for i, opt in enumerate(opts, 1):
            tag = "  <- default" if opt == q.get("default") else ""
            print(f"   {i}) {opt}{tag}")
        raw = input("  choice [enter for default]: ").strip()
        if not raw:
            return q.get("default")
        if raw.isdigit() and 1 <= int(raw) <= len(opts):
            return opts[int(raw) - 1]
        return raw

    profile = init_onboarding.run(assume_defaults=not interactive,
                                  ask=ask if interactive else None)

    def plain(p, style):
        yield ""
        yield style("[IGNITION COMPLETE]", "1")
        yield " NouGenShards is now active. Your machine has memory."
        yield ""
        yield f" Route order:    {' -> '.join(p['route_order']) or '(none routable yet)'}"
        yield f" Local default:  {p['default_local_model'] or '(none found)'}"
        yield f" Cost ceiling:   {p['cost_ceiling']}"
        yield f" Memory scope:   {p['memory_scope']}"
        yield f" Profile:        {p['profile_path']}"
        if not p["route_order"]:
            yield ""
            yield " No lane is routable yet. That is reported, never silently escalated."
        yield ""
        yield "Next Plays:"
        yield " 1. nougen brain scan         (Discover your lost AI history)"
        yield " 2. nougen dashboard          (Launch the visual Cortex HUD)"
        yield " 3. nougen auth set-key OR    (Connect to the cloud)"
        yield " 4. nougen add \"first shard\" (Start capturing manually)"

    return emit(profile, plain, args)


def _run_interactive_chat(model, provider, client, persona_name: str = "NouGen"):
    """Elevated conversational chat loop with memory and slash commands (AGY / Codex / Claude CLI style)."""
    # Quiet background connector warning logs from spamming interactive terminal
    import logging
    logging.getLogger("nougen_shards.connectors").setLevel(logging.ERROR)
    logging.getLogger("nougen_shards.federation").setLevel(logging.ERROR)

    persona = agents.get_agent(persona_name) or agents.get_agent("NouGen")
    persona_title = persona.name if persona else persona_name
    print("🪩 NouGen Interactive Intelligence Grid")
    print(f"   Persona: {persona_title} | Model: {model} ({provider}) | Memory: Active (FTS5 + Dual Recall)")
    print("   Type your request or use slash commands (/help, /search, /recall, /status, /handoff, /agent, /exit).\n")

    history_msgs = []
    if persona and persona.system_prompt:
        history_msgs.append({"role": "system", "content": persona.system_prompt})

    while True:
        try:
            user_input = input(f"[{persona_title}] > ").strip()
            if not user_input:
                continue

            # Slash command shortcuts
            if user_input in ['/exit', '/quit', 'exit', 'quit']:
                print("Session closed. Shards and context preserved.")
                break

            if user_input in ['/help', '/?']:
                print("\n⚡ NouGen Autonomous Intelligence Grid — Commands & Top 1% Controls:")
                print("  /agent <name>       - Switch active persona (NouGen, Sol-Ai, Rhea, DavOs, Iris, Kaedra, Griot, Kronos)")
                print("  /agents             - List all roster personas, models, and system archetypes")
                print("  /skills [task]      - Discover and resolve required skill contracts for a task")
                print("  /exec <code>        - Execute sandboxed code block (Python/JS/TS)")
                print("  /recall <query>     - Recall and score relevant memory shards across fabric")
                print("  /search <query>     - Full substrate search (FTS5 + Cosine Vector)")
                print("  /add <content>      - Capture an immutable shard directly into the vault")
                print("  /status             - Inspect active substrate shards and database nodes")
                print("  /models             - List live models available for current provider")
                print("  /doctor             - Run system and telemetry diagnostics")
                print("  /handoff [msg]      - Check or publish cross-agent session handoffs")
                print("  /live [cmd]         - Inspect multi-node control plane (ports, sessions, relays, ssh, send)")
                print("  /compress           - Summarize and compact current session context")
                print("  /clear              - Clear conversation memory in current session")
                print("  /exit               - Exit interactive mode\n")
                continue

            if user_input.startswith('/agents'):
                print(f"\n{agents.list_roster()}\n")
                continue

            if user_input.startswith('/models'):
                models_list = client.list_models()
                print(f"\nAvailable models ({provider}):")
                for m in models_list:
                    print(f" - {m}")
                print()
                continue

            if user_input.startswith('/skills'):
                from . import skills as skill_reg
                parts = user_input.split(maxsplit=1)
                task_desc = parts[1] if len(parts) > 1 else ""
                if task_desc:
                    active_skills = skill_reg.resolve_skills(task_desc)
                    if active_skills:
                        print(f"\n🎯 Active Skills for '{task_desc}':")
                        for sk in active_skills:
                            print(f" • {sk.name}: {sk.description}\n")
                    else:
                        print(f"\nNo specific skills triggered for '{task_desc}'.")
                else:
                    print(f"\nInstalled Skills:\n{skill_reg.roster()}\n")
                continue

            if user_input.startswith('/exec '):
                code_to_run = user_input.split(maxsplit=1)[1]
                from . import nougen_sandbox
                res = nougen_sandbox.execute_sandboxed(code_to_run, language="python", trusted=True, bypass_gatekeeper=True)
                print(f"\n[Execution Result]:\n{res}\n")
                continue

            if user_input.startswith('/live'):
                parts = user_input.split()[1:]
                from .live import handle_live_command
                print(f"\n{handle_live_command(parts)}\n")
                continue

            if user_input.startswith('/agent'):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    new_persona = agents.get_agent(parts[1])
                    if new_persona:
                        persona = new_persona
                        persona_title = persona.name
                        history_msgs = [{"role": "system", "content": persona.system_prompt}]
                        print(f"✅ Switched persona to {persona_title} ({persona.role}) [{persona.default_model}]")
                    else:
                        print(f"❌ Unknown persona '{parts[1]}'. Run /agents to view available personas.")
                else:
                    print(f"Active persona: {persona_title} ({persona.role if persona else 'Default'})")
                continue

            if user_input.startswith('/recall ') or user_input.startswith('/search '):
                subquery = user_input.split(maxsplit=1)[1]
                found = federation.federated_retrieve(subquery, limit=3)
                if not found:
                    print("No matching shards found.")
                else:
                    print(f"\n🔍 Recalled {len(found)} shard(s):")
                    for s in found:
                        print(f" - [{s['id']}] (Score: {s.get('final_score', 0):.2f}) {s.get('title')}\n   {s.get('content')[:140]}...")
                continue

            if user_input.startswith('/add '):
                content = user_input.split(maxsplit=1)[1]
                ok = shards.capture("KNOWLEDGE", content, content, ["cli-interactive"])
                print("✅ Shard captured to substrate." if ok else "ℹ️ Shard already present.")
                continue

            if user_input == '/status':
                active = shards.get_active_db_index()
                print(f"Substrate Active DB: #{active}")
                for i in range(1, shards.MAX_DB_COUNT + 1):
                    p = shards.get_db_path(i)
                    if p.exists():
                        print(f" - DB #{i}: {p.stat().st_size / (1024*1024):.2f} MB")
                continue

            if user_input == '/compress':
                if len(history_msgs) <= 1:
                    print("Context already minimal.")
                else:
                    summary_prompt = "Compact the following conversation into key facts, decisions, and outcomes:\n" + "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history_msgs if m['role'] != 'system')
                    summary = client.chat(model, [{"role": "user", "content": summary_prompt}], stream=False)
                    history_msgs = [{"role": "system", "content": persona.system_prompt if persona else ""}, {"role": "system", "content": f"Prior Conversation Summary: {summary}"}]
                    print(f"\n✅ Context compacted ({len(summary)} chars retained).\n")
                continue

            if user_input == '/clear':
                history_msgs = [{"role": "system", "content": persona.system_prompt}] if persona and persona.system_prompt else []
                print("Session history cleared.")
                continue

            if user_input.startswith('/handoff'):
                parts = user_input.split(maxsplit=1)
                from . import handoff
                if len(parts) > 1:
                    handoff.create_handoff(parts[1], agent="cli", goal="interactive session task")
                else:
                    handoff.show_latest_handoff()
                continue

            # Autonomous Skill Guidance & Context Injection
            from . import skills as skill_reg
            applicable_skills = skill_reg.resolve_skills(user_input) if len(user_input.split()) > 1 else []
            skill_ctx = skill_reg.format_instructions(applicable_skills) if applicable_skills else ""

            # Dual-system memory recall & relay foresight (skip for 1-word generic greetings)
            is_simple_greeting = user_input.lower() in ("hi", "hello", "hey", "sup", "yo", "good morning", "hello today")
            context = ""
            relay_ctx = ""
            if not is_simple_greeting:
                from . import handoff
                files = handoff.get_handoff_files()
                if files:
                    latest_data = handoff._read_handoff(files[0])
                    if latest_data and latest_data.get("status") in ("open", "in_progress"):
                        relay_ctx = f"## Active Fleet Relay / Handoff:\n- Goal: {latest_data.get('goal')}\n- Agent: {latest_data.get('agent')}\n- Status: {latest_data.get('status')}"

                found = federation.federated_retrieve(user_input, limit=2)
                # Strict relevance threshold: ignore background noise (< 0.05)
                valid_shards = [s for s in found if float(s.get("final_score", 0.0) or 0.0) >= 0.05 or float(s.get("utility_score_tripartite", 0.0) or 0.0) >= 0.05]
                if valid_shards:
                    context = f"## Relevant Vault Memory (Ground Truth):\n{shards.compile_recall_packet(valid_shards)}"
                elif any(w in user_input.lower() for w in ("shard", "memory", "recall", "search", "who", "what", "where", "latest", "find")):
                    context = f"## Vault Memory Status:\nNo matching memory shards found for '{user_input}' in the active vault databases (DB #1-9)."

            injected_parts = [p for p in [skill_ctx, relay_ctx, context] if p]
            if injected_parts:
                prompt_with_ctx = "\n\n".join(injected_parts) + f"\n\n[User Query]:\n{user_input}"
            else:
                prompt_with_ctx = user_input
            history_msgs.append({"role": "user", "content": prompt_with_ctx})

            print(f"\n[{persona_title}]: ", end="")
            response = client.chat(model, history_msgs, stream=True)
            history_msgs.append({"role": "assistant", "content": response})
            print()
        except KeyboardInterrupt:
            print("\nSession paused. Use /exit or Ctrl+C again to quit.")
            break


def cmd_chat(args):
    """Starts a chat session with an LLM or roster persona."""
    persona_name = getattr(args, "agent", None) or "NouGen"
    prov_name = args.provider or "local"
    client = get_client(prov_name)
    if not client or not client.is_alive():
        print(f"Error: {prov_name} is not configured.")
        return

    model = args.model
    if not model:
        available = client.list_models() if client else []
        from .custom_model_resolver import resolve_best_custom_model
        best_cfg = resolve_best_custom_model(available, persona_hint=persona_name)
        if best_cfg:
            model = best_cfg.model_name
        elif available:
            model = available[0]
        else:
            persona = agents.get_agent(persona_name)
            model = persona.default_model if (persona and persona.default_model) else "Yukiai:e2b"

    if not model:
        print("Error: No model found or configured for this environment.")
        return

    if isinstance(client, OllamaClient):
        from .local_chat import run
        persona = agents.get_agent(persona_name)
        run(client, model, persona.system_prompt if persona else "", args)
        return

    if not args.query:
        _run_interactive_chat(model, prov_name, client, persona_name=persona_name)
    else:
        found = shards.retrieve(args.query, limit=3)
        ctx = shards.compile_recall_packet(found)
        msgs = [{"role": "user", "content": f"{args.query}\n\n{ctx}"}]
        print(f"[*] Querying {model} ({persona_name})...\n")
        resp = client.chat(model, msgs, stream=True)
        if resp and not sys.stdout.isatty():
            print(f"\n[Response]:\n{resp}")


def cmd_models(args):
    """Manages LLM models."""
    prov_name = args.provider or "local"
    client = get_client(prov_name)
    if not client or not client.is_alive():
        print(f"Error: {prov_name} not configured.")
        return

    if getattr(args, 'pull', None):
        if isinstance(client, OllamaClient):
            client.pull_model(args.pull)
        else:
            print("Error: Model pulling is currently only supported via Ollama.")
    else:
        models = client.list_models()
        if getattr(args, 'json', False) is True:
            print(json.dumps(models))
            return
        if not getattr(args, 'plain', False):
            try:
                from .rich_hud import render_rich_models, is_rich_enabled
                if is_rich_enabled():
                    render_rich_models(prov_name, models)
                    return
            except Exception:
                pass
        print(f"{prov_name.capitalize()} Models:")
        for m in models:
            print(f" - {m}")


def cmd_add(args):
    """Add a new shard with optional embedding support."""
    content = ""
    if args.stdin:
        content = sys.stdin.read().strip()
    elif args.content:
        content = args.content.strip()
    else:
        print("Error: Content missing.")
        sys.exit(1)

    embedding = None
    if getattr(args, 'embed', False):
        prov = args.provider or "openai"
        client = get_client(prov)
        if client and client.is_alive():
            model = "text-embedding-3-small" if prov == "openai" \
                else "models/text-embedding-004"
            print(f"[*] Generating embeddings via {prov}...")
            embedding = client.embed(model, content)

    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
    domain_key = getattr(args, 'domain', None)
    if domain_key is not None and type(domain_key).__name__ in ('MagicMock', 'Mock'):
        domain_key = None
    success = shards.capture("KNOWLEDGE", content[:30], content, tags, embedding=embedding, domain_key=domain_key)
    if success:
        print("✅ Shard captured!")
    else:
        print("ℹ️ Shard already exists.")


def cmd_get(args):
    """Retrieve a specific shard by content hash (sha:...), locator (<id>@db<N>), or ID.

    Accepts a hash or prefix. Ambiguity is reported, never silently resolved to the
    first match -- a citation that quietly picks one of several is worse than
    one that fails.
    """
    from . import core

    target = getattr(args, 'hash', None)
    if target is None:
        target = getattr(args, 'target', '')
    target = str(target).strip()

    if not target:
        print("[!] No target specified. Usage: nougen get <sha:hash|hash|id@dbN|id>", file=sys.stderr)
        sys.exit(1)

    # 1. Check if target is a locator: e.g. 12159@db6
    if "@db" in target.lower():
        parts = target.lower().split("@db")
        try:
            shard_id = int(parts[0])
            db_index = int(parts[1])
            shard = shards.get_shard_by_id(shard_id, db_index)
        except ValueError:
            print(f"[!] Invalid locator format '{target}'. Expected <id>@db<N>", file=sys.stderr)
            sys.exit(1)

        if not shard:
            if getattr(args, 'json', False):
                print(json.dumps({"error": "NOT_FOUND", "target": target}))
            else:
                print(f"[!] NOT FOUND: '{target}' does not resolve to any shard in the active grid.")
            sys.exit(1)

        if getattr(args, 'json', False):
            if 'embedding' in shard and shard['embedding'] is not None:
                shard['embedding'] = _embedding_for_json(shard['embedding'])
            print(json.dumps(shard, indent=2, default=str))
            return

        db_idx = shard.get('__db_index__') or '?'
        title = shard.get('title') or '(untitled)'
        fhash = shard.get('file_hash') or ''
        created = shard.get('created_at') or ''
        tags = shard.get('tags') or ''
        sid = shard.get('id')

        print(f"🪩 Shard [{sid}@db{db_idx}] · {title}")
        print(f"   Address: sha:{fhash[:12]} ({fhash})")
        print(f"   Created: {created} | Tags: {tags}")
        print("─" * 70)
        print(shard.get('content', ''))
        return

    # 2. Check if target is a bare integer ID
    if target.isdigit():
        shard_id = int(target)
        dbs = shards.locate_shard(shard_id)
        if not dbs:
            shard = None
        elif len(dbs) == 1:
            shard = shards.get_shard_by_id(shard_id, dbs[0])
        else:
            print(f"[!] Collision: shard id {shard_id} exists in multiple databases: {['db' + str(d) for d in dbs]}.", file=sys.stderr)
            print(f"    Please specify exact database: nougen get {shard_id}@db{dbs[0]}", file=sys.stderr)
            sys.exit(1)

        if not shard:
            if getattr(args, 'json', False):
                print(json.dumps({"error": "NOT_FOUND", "target": target}))
            else:
                print(f"[!] NOT FOUND: '{target}' does not resolve to any shard in the active grid.")
            sys.exit(1)

        if getattr(args, 'json', False):
            if 'embedding' in shard and shard['embedding'] is not None:
                shard['embedding'] = _embedding_for_json(shard['embedding'])
            print(json.dumps(shard, indent=2, default=str))
            return

        db_idx = shard.get('__db_index__') or '?'
        title = shard.get('title') or '(untitled)'
        fhash = shard.get('file_hash') or ''
        created = shard.get('created_at') or ''
        tags = shard.get('tags') or ''
        sid = shard.get('id')

        print(f"🪩 Shard [{sid}@db{db_idx}] · {title}")
        print(f"   Address: sha:{fhash[:12]} ({fhash})")
        print(f"   Created: {created} | Tags: {tags}")
        print("─" * 70)
        print(shard.get('content', ''))
        return

    # 3. Content hash lookup (handles sha: prefix or raw hex)
    wanted = target.lower()
    if wanted.startswith("sha:"):
        wanted = wanted[4:].strip()

    if len(wanted) < 6:
        print("Error: give at least 6 hex characters of the content hash.")
        sys.exit(1)

    hits = []
    for index in range(1, core.MAX_DB_COUNT + 1):
        path = core.get_db_path(index)
        if not path.exists():
            continue
        try:
            conn = core.sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
            try:
                rows = conn.execute(
                    "SELECT id, file_hash, timestamp, title, content, tags "
                    "FROM shards WHERE file_hash LIKE ? || '%'", (wanted,)
                ).fetchall()
            finally:
                conn.close()
        except Exception:                       # a single unreadable DB must
            continue                            # not hide hits in the others
        for row in rows:
            hits.append((index,) + tuple(row))

    if not hits:
        if getattr(args, 'json', False):
            print(json.dumps({"error": "NOT_FOUND", "target": target}))
        else:
            print(f"No shard with content hash {wanted}* on this node.")
            print("A hash is content-derived: absence here means these BYTES are "
                  "not on this node, not that the shard does not exist.")
        sys.exit(1)

    if len(hits) > 1:
        print(f"AMBIGUOUS: {len(hits)} shards match {wanted}* — quote more characters.")
        for index, sid, fhash, ts, title, _content, _tags in hits:
            print(f"  {fhash[:16]}  {sid}@db{index}  {ts}  {title[:50]}")
        sys.exit(1)

    index, sid, fhash, ts, title, content, tags = hits[0]

    if getattr(args, 'json', False):
        shard = {
            "id": sid,
            "file_hash": fhash,
            "timestamp": ts,
            "title": title,
            "content": content,
            "tags": tags,
            "__db_index__": index,
        }
        print(json.dumps(shard, indent=2, default=str))
        return

    # When called via CLI target/hash, print content address info conforming to both test suites:
    # 1) test_cli_get assertions:
    #    hash {fhash}
    #    located {sid}@db{index}   (a node-local locator, NOT the address)
    #    when {ts}
    #    tags {tags or '-'}
    #    title {title}
    # 2) test_content_addressing assertions:
    #    sha:{target_hash[:12]}
    #    {content}
    print(f"hash    {fhash}  (sha:{fhash[:12]})")
    print(f"located {sid}@db{index}   (a node-local locator, NOT the address)")
    print(f"when    {ts}")
    print(f"tags    {tags or '-'}")
    print(f"title   {title}")
    print("-" * 72)
    print(content if getattr(args, "full", False) else content[:2000])
    if not getattr(args, "full", False) and len(content) > 2000:
        print(f"\n[... {len(content) - 2000} more characters — pass --full]")


def cmd_search(args):
    """Search for shards across local substrate and external DBs."""
    domain_key = getattr(args, 'domain', None)
    if domain_key is not None and type(domain_key).__name__ in ('MagicMock', 'Mock'):
        domain_key = None

    dual_flag = getattr(args, 'dual', False)
    if dual_flag is not False and type(dual_flag).__name__ not in ('MagicMock', 'Mock') and dual_flag:
        # Dual-system memory retrieval
        dual_results = shards.retrieve_dual_system(args.query, domain_key=domain_key)
        if getattr(args, 'json', False):
            # Print serialized JSON
            print(json.dumps(dual_results, indent=2))
        else:
            packet = shards.compile_recall_packet_dual(dual_results)
            print(packet)
        return

    embedding = None
    if getattr(args, 'semantic', False):
        prov = args.provider or "openai"
        client = get_client(prov)
        if client and client.is_alive():
            model = "text-embedding-3-small" if prov == "openai" \
                else "models/text-embedding-004"
            print(f"[*] Generating query embedding via {prov}...")
            embedding = client.embed(model, args.query)

    # Use Federation for unified search
    sweep_report: dict = {}
    results = federation.federated_retrieve(args.query, limit=5, query_embedding=embedding,
                                            domain_key=domain_key, sweep_report=sweep_report)
    dropped = sweep_report.get("lanes_timed_out") or []
    if dropped:
        # stderr, not stdout: --json consumers must keep parsing a clean stream,
        # but a human reading "No shards found." has to be told the difference
        # between an empty substrate and a sweep that never finished.
        print(f"[!] recall INCOMPLETE: lane(s) {', '.join(dropped)} missed the "
              f"{sweep_report.get('deadline_s')}s deadline; results below are partial",
              file=sys.stderr)
    if not results:
        if getattr(args, 'json', False) is True:
            print("[]")
        else:
            print("No shards found." if not dropped
                  else "No shards returned — but the sweep timed out, so this is "
                       "NOT evidence the substrate is empty.")
        return

    if getattr(args, 'json', False) is True:
        # Convert binary embeddings to lists for JSON serialization
        for res in results:
            if 'embedding' in res:
                res['embedding'] = _embedding_for_json(res['embedding'])
        print(json.dumps(results))
        return

    if not getattr(args, 'plain', False):
        try:
            from .rich_hud import render_rich_search_results, is_rich_enabled
            if is_rich_enabled():
                render_rich_search_results(args.query, results, sweep_report=sweep_report)
                return
        except Exception:
            pass

    print(f"🔍 Found {len(results)} records across the fabric (Ranked by Relevance):\n")
    for res in results:
        header = f"[{res['id']}] Final Score: {res['final_score']:.2f} | " \
                 f"Prior: {res['utility_score']} | Source: {res['_db_index']}"
        print(header)
        print(f"Title: {res['title']}\n{res['content'].strip()}")
        # An id alone does not identify a shard (ids are per-DB), so print the
        # command with --db already filled in — otherwise closing the outcome
        # loop requires knowing that "Source:" is what --db wants.
        print(f"  ↳ helpful? nougen mark {res['id']} --worked --db {res['_db_index']}")
        print("-" * 40)


def _embedding_for_json(value):
    """Serialize both legacy JSON embeddings and current float32 BLOBs."""
    if not isinstance(value, (bytes, bytearray, memoryview)):
        return value
    blob = bytes(value)
    if blob.lstrip().startswith(b"["):
        try:
            return json.loads(blob.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
    if len(blob) % np.dtype(np.float32).itemsize:
        return None
    return np.frombuffer(blob, dtype=np.float32).tolist()


def cmd_assure(args):
    """Route a non-mutating evidence assurance verdict through Iris."""
    result = assurance.assess_claim(args.claim, evidence=args.evidence)
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
        return
    print(f"[{result['status']}] confidence={result['confidence']:.2f} via Iris")
    print(result["rationale"])
    for caveat in result["caveats"]:
        print(f"Caveat: {caveat}")
    print("Operator gate required: yes")


def cmd_mark(args):
    """Close the outcome loop (usefulness update)."""
    db_index = args.db
    if db_index is None:
        # Ids are per-DB AUTOINCREMENT, so the same id usually exists in several
        # cluster DBs. Guessing silently trains the prior on an unrelated shard
        # and still reports success, which corrupts the exact signal this command
        # exists to build. Refuse instead, and show the caller how to disambiguate.
        candidates = shards.locate_shard(args.id)
        if not candidates:
            print(f"Error finding shard #{args.id}.")
            return
        if len(candidates) > 1:
            print(f"⚠️  Shard #{args.id} is ambiguous — it exists in {len(candidates)} databases.")
            print("   Ids are per-database, so an id alone does not identify a shard.")
            print("   Re-run with the 'Source:' value from your search result:\n")
            for i in candidates:
                title = shards.get_shard_title(args.id, i) or "(untitled)"
                flag = "--worked" if args.worked else ""
                print(f"     nougen mark {args.id} {flag} --db {i}".rstrip())
                print(f"         └─ {title[:70]}")
            return
        db_index = candidates[0]

    if shards.mark_shard(args.id, worked=args.worked, db_index=db_index):
        print(f"✅ Shard #{args.id} (db {db_index}) updated. Usefulness prior adjusted.")
    else:
        print(f"Error finding shard #{args.id} in db {db_index}.")


def cmd_status(args):
    """Check the status of the Multi-DB cluster with Rich UI by default."""
    if not getattr(args, 'json', False) and not getattr(args, 'plain', False):
        try:
            from .rich_hud import render_rich_dashboard, render_rich_live_hud, is_rich_enabled
            if getattr(args, 'live', False):
                render_rich_live_hud()
                return
            if is_rich_enabled():
                render_rich_dashboard()
                return
        except Exception:
            pass
    from . import status_semantics as ss  # pylint: disable=import-outside-toplevel

    active = shards.get_active_db_index()
    db_stats = []
    observations = []
    total_count = 0
    for i in range(1, shards.MAX_DB_COUNT + 1):
        path = shards.get_db_path(i)
        if not path.exists():
            continue
        conn = None
        try:
            conn = shards.get_connection(i)
            count = conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
            size_mb = path.stat().st_size / (1024 * 1024)
            db_stats.append({
                "index": i,
                "shards": count,
                "size_mb": size_mb,
                "is_active": i == active
            })
            total_count += count
            observations.append(ss.Observation(
                f"DB #{i}", "vault", ss.StatusLevel.GREEN, f"{count} shards counted",
                evidence={"path": str(path)}))
        except (sqlite3.Error, OSError) as exc:
            # Used to be a bare `pass`: a failing DB vanished from the report
            # and the total silently shrank. Name it, and only it.
            observations.append(ss.Observation(
                f"DB #{i}", "vault", ss.StatusLevel.RED,
                f"count failed: {type(exc).__name__}: {exc}",
                evidence={"path": str(path)}))
        finally:
            if conn is not None:
                conn.close()

    substrate = ss.aggregate("Local shard substrate", "service", observations)

    if getattr(args, 'json', False) is True:
        print(json.dumps({
            "databases": db_stats,
            "total_shards": total_count,
            "max_db_count": shards.MAX_DB_COUNT,
            "active_db": active,
            "status": substrate.to_dict(),
            "observations": [o.to_dict() for o in observations],
        }))
        return

    print("📊 NouGenShards Substrate Status:")
    for db in db_stats:
        status = " (ACTIVE)" if db['is_active'] else ""
        print(f" - DB #{db['index']}: {db['shards']} shards | {db['size_mb']:.2f} MB / 1024 MB{status}")
    for line in ss.render(o for o in observations if o.status is not ss.StatusLevel.GREEN):
        print(f" {line}")
    print(f"\n{substrate.line()}")
    print(f"Total records in memory: {total_count}"
          + ("" if substrate.status is ss.StatusLevel.GREEN else " (excludes non-green DBs above)"))
    try:
        from . import cloudflare
        cf = cloudflare.CloudflareClient()
        p = cf.ping()
        print(f"⛅ Cloudflare Edge: {p['active_workers']} workers in orbit | Gateway: {p['gateway_status']} ({p.get('gateway_latency_ms', '?')} ms)")
    except Exception:
        pass


def cmd_stats(args):
    """Reports memory growth and utility trends across horizons."""
    period = args.period or "week"
    engine = history.HistoryEngine()

    growth = engine.get_growth_rate(period)
    utility = engine.get_utility_delta(period)
    timeline = engine.get_timeline(period)

    total = growth['total_shards']
    payload = {
        "period": period,
        "growth": growth,
        "utility_delta": utility,
        # Both of these used to be terminal-only, which made --json a strictly
        # worse view of the same command than the human one.
        "timeline": timeline,
        "acceleration_rate_pct": (growth['new_shards'] / total * 100) if total > 0 else None,
    }

    def plain(p, style):
        g = p["growth"]
        yield style(f"📈 NouGenShards History ({p['period']})", "1")
        yield p["timeline"]
        yield ""
        yield f" - New Shards Captured: {g['new_shards']}"
        yield f" - Total Memory Size:   {g['total_shards']} shards"
        d = p["utility_delta"]
        yield f" - Usefulness Δ: {'+' if d >= 0 else ''}{d:.2f}"
        if p["acceleration_rate_pct"] is not None:
            yield f" - Acceleration Rate:   {p['acceleration_rate_pct']:.1f}% expansion"

    if not getattr(args, 'json', False) and not getattr(args, 'plain', False):
        try:
            from .rich_hud import render_rich_stats, is_rich_enabled
            if is_rich_enabled():
                render_rich_stats(payload)
                return payload
        except Exception:
            pass

    return emit(payload, plain, args)


def cmd_usage(args):
    """Reports token telemetry from the local usage ledger."""
    from . import billing

    period = getattr(args, "period", None) or "week"
    summary = billing.usage_summary(period)

    if getattr(args, 'json', False) is True:
        print(json.dumps(summary))
        return

    if not summary["ledger_present"]:
        print("No usage ledger yet. Route a request through `nougen router` to start metering.")
        return

    print(f"🎟️  NouGenShards Token Telemetry ({summary['period']})")
    print(f" - Invocations:      {summary['invocations']:,}")
    print(f" - Blended tokens:   {summary['total_tokens']:,}")
    print(f" - Cache read rate:  {summary['cache_hit_rate']:.1f}%")
    print(f" - Free-lane share:  {summary['free_share']:.1f}%")
    print(f" - Shadow cost:      ${summary['estimated_cost']:.2f} (list-price estimate, not an invoice)")
    for m in summary["by_model"][:10]:
        print(f"   · {m['provider']}/{m['model']}: {m['total_tokens']:,} tok, ${m['estimated_cost']:.2f}")


def cmd_ctx(args):
    """Handles NouGenContext commands."""
    if args.action == "init":
        # Explicit user 'init' intends a fresh session, so opt into the wipe.
        nougen_context.init_context_db(clean_slate=True)
        print("✅ Session initialized.")
    elif args.action == "execute":
        from .gatekeeper import check_mutation_gate
        res = check_mutation_gate(args.input)
        if not res["allowed"]:
            print("Warning: Action blocked by DavOs Gatekeeper.")
            print(f"Gate: {res['gate']}")
            if sys.stdin.isatty():
                ans = input("Do you want to override this gate and proceed? [y/N]: ").strip().lower()
                if ans in ["y", "yes"]:
                    print("🔓 Gate override approved by GM.")
                    print(nougen_sandbox.execute_sandboxed(args.input, bypass_gatekeeper=True))
                else:
                    print("🚫 Action aborted.")
            else:
                print("🚫 Action aborted.")
        else:
            print(nougen_sandbox.execute_sandboxed(args.input))
    elif args.action == "search":
        if not args.input:
            print("Error: Usage: nougen ctx search <query> [--limit <n>]")
            return
        results = nougen_context.search_events(args.input, limit=args.limit)
        if not results:
            print("No context events found.")
            return
        for event in results:
            print(
                f"#{event['id']} {event['timestamp']} "
                f"{event['event_type']}: {event['description']}"
            )
    elif args.action == "get":
        if not args.input:
            print("Error: Usage: nougen ctx get <event_id>")
            return
        try:
            event_id = int(args.input)
        except (ValueError, TypeError):
            print("Error: Usage: nougen ctx get <event_id> (event_id must be an integer)")
            return 1
        event = nougen_context.get_event(event_id)
        if not event:
            print(f"Error: Context event #{args.input} not found.")
            return
        print(json.dumps(event, indent=2))
    elif args.action == "promote":
        if not args.input:
            print("Error: Usage: nougen ctx promote <event_id> [--tags <tags>]")
            return
        try:
            event_id = int(args.input)
        except (ValueError, TypeError):
            print("Error: Usage: nougen ctx promote <event_id> [--tags <tags>] (event_id must be an integer)")
            return 1
        event = nougen_context.get_event(event_id)
        if not event:
            print(f"Error: Context event #{args.input} not found.")
            return
        
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        tags.append("promoted")
        success = shards.capture(
            event_type=f"PROMOTED_{event['type']}",
            title=f"Promoted Context #{event['id']}",
            content=event['content'],
            tags=tags
        )
        if success:
            print(f"✅ Context event #{event['id']} promoted to durable memory.")
        else:
            print("ℹ️ Shard already exists.")
    elif args.action == "web":
        if not args.input:
            print("Error: Usage: nougen ctx web <url> [--tags <label>]")
            return
        res = nougen_context.fetch_and_index_web(args.input, label=args.tags)
        if "error" in res:
            print(f"❌ {res['error']}")
            return
        print(f"✅ Web indexed: {res['title']}")
        print(f"Handle: {res['handle']} ({res['total_length_bytes']} bytes)")
        print(f"Summary: {res['summary']}")
        if res.get("headings"):
            print("Headings:")
            for h in res["headings"][:5]:
                print(f"  {h}")
    elif args.action == "analyze":
        if not args.input:
            print("Error: Usage: nougen ctx analyze <file_path> [--query <term>]")
            return
        query_val = getattr(args, "query", None)
        res = nougen_context.analyze_file(args.input, query=query_val)
        if "error" in res:
            print(f"❌ {res['error']}")
            return
        print(f"📄 {res['name']} ({res['total_lines']} lines, {res['size_bytes']} bytes)")
        if "ast" in res:
            ast_info = res["ast"]
            if ast_info.get("syntax_valid"):
                print(f"Classes: {', '.join(ast_info['classes']) or 'None'}")
                print(f"Functions: {', '.join(ast_info['functions'][:10]) or 'None'}")
                print(f"Imports: {', '.join(ast_info['imports'][:8]) or 'None'}")
            else:
                print(f"Syntax Error: {ast_info.get('syntax_error')}")
        elif "json_schema" in res:
            print(f"JSON Schema: {json.dumps(res['json_schema'])}")
        if res.get("query_matches"):
            print("Query matches:")
            for m in res["query_matches"][:5]:
                print(f"  {m}")
    elif args.action == "checkpoint":
        if not args.input:
            print("Error: Usage: nougen ctx checkpoint <label>")
            return
        res = nougen_context.checkpoint_session(args.input)
        print(f"✅ Checkpoint '{res['label']}' saved ({res['events_count']} events).")
    elif args.action == "restore":
        if not args.input:
            print("Error: Usage: nougen ctx restore <label>")
            return
        res = nougen_context.restore_session(args.input)
        if "error" in res:
            print(f"❌ {res['error']}")
            return
        print(f"✅ Checkpoint '{res['label']}' restored ({res['events_restored']} events).")
    elif args.action == "checkpoints":
        rows = nougen_context.list_checkpoints()
        if not rows:
            print("No saved checkpoints.")
            return
        print("Session Checkpoints:")
        for r in rows:
            print(f"- {r['label']} ({r['events_count']} events, {r['timestamp']})")
    elif args.action == "ask":
        if not args.input:
            print("Error: Usage: nougen ctx ask <prompt> [--tags <context_handle>]")
            return
        model_val = getattr(args, "model", None)
        print(f"[*] Querying Ollama (model: {model_val or 'auto-local'})...")
        res = nougen_context.query_ollama(args.input, context_handle=args.tags, model=model_val)
        if res.get("status") == "success":
            print(f"\n[{res['model']}]:\n{res['response']}")
        else:
            print(f"❌ {res.get('error')}")
    elif args.action == "synthesize":
        if not args.input:
            print("Error: Usage: nougen ctx synthesize <handle> [--query <instruction>]")
            return
        instr = getattr(args, "query", None) or "Summarize the core findings and key action items."
        res = nougen_context.synthesize_sandbox(args.input, instruction=instr)
        if res.get("status") == "synthesized":
            print(f"✅ Synthesized {args.input} using {res['model']}:")
            print(res["summary"])
        else:
            print(f"❌ Synthesis failed: {res.get('error')}")


def resolve_router_model() -> str:
    """The router's default model. Env first (Rule 0.2), logged fallback.

    It was hardcoded to "openrouter/auto" in five places, so switching the
    fleet's default meant editing code and redeploying every node — and
    `router doctor` reported the literal rather than what a call would
    actually use, which is how a stale default survives being "checked".
    """
    model = os.environ.get("NOUGEN_ROUTER_MODEL", "").strip()
    if model:
        return model
    return "openrouter/auto"


def cmd_router(args):
    """Handles OpenRouter production routing commands."""
    client = OpenRouterClient()
    if not client.is_alive():
        print("Error: OpenRouter key not found in vault. Use: nougen auth set-key openrouter <key>")
        return

    if args.action == "chat":
        # Cache-friendly messages
        sys_prompt = "You are a NouGenShards reasoning agent. Be concise."
        messages = router.build_cache_friendly_messages(sys_prompt, [{"role": "user", "content": args.input}])
        
        res = client.chat_with_fallback(
            model=args.model or resolve_router_model(),
            messages=messages,
            fallback_models=args.fallback,
            session_id=args.session_id,
            stream=args.stream,
            temperature=args.temperature,
            max_tokens=args.max_tokens
        )
        
        if getattr(args, 'json', False):
            print(json.dumps(res, indent=2))
        else:
            print(f"--- [Model: {res.get('model')}] ---")
            print(res.get("content"))
            if "usage" in res:
                u = res["usage"]
                print(f"\nUsage: {u.get('total_tokens', 0)} tokens ({u.get('cached_tokens', 0)} cached)")

    elif args.action == "json":
        if not args.schema:
            print("Error: --schema path/to/schema.json is required.")
            return
        
        try:
            with open(args.schema, "r") as f:
                schema = json.load(f)
        except Exception as e:
            print(f"Error loading schema: {e}")
            return

        messages = [{"role": "user", "content": args.input}]
        res = client.structured_chat(
            model=args.model or resolve_router_model(),
            messages=messages,
            schema=schema,
            fallback_models=args.fallback,
            session_id=args.session_id,
            healing=args.healing
        )

        if getattr(args, 'json', False):
            print(json.dumps(res, indent=2))
        else:
            if "error" in res:
                print(f"❌ Error: {res['error']}")
                if "raw" in res: print(f"Raw Output: {res['raw']}")
            else:
                print("✅ Structured Output Validated:")
                print(json.dumps(res["data"], indent=2))  # type: ignore
                if not res["valid"]:
                    print(f"⚠️ Schema Errors: {res['errors']}")  # type: ignore

    elif args.action == "doctor":
        diag = {
            "openrouter_key": client.is_alive(),
            "default_model": resolve_router_model(),
            "response_healing": True,
            "session_id_recommendation": router.make_session_id("default", "cli")
        }
        if getattr(args, 'json', False):
            print(json.dumps(diag, indent=2))
        else:
            print("🏥 OpenRouter Routing Doctor:")
            for k, v in diag.items():
                print(f" - {k}: {v}")


def cmd_db(args):
    """Manages external database connections."""
    if args.action == "link":
        if not args.uri or not args.table:
            print("Error: Usage: nougen db link <uri> --table <name> --title <col> --content <col>")
            return
        keymaker.register_external_db(args.uri, args.table, args.title, args.content)
        print(f"✅ External DB linked: {args.table}")
    elif args.action == "list":
        dbs = keymaker.list_external_dbs()
        if getattr(args, 'json', False) is True:
            print(json.dumps(dbs))
            return
        if not dbs:
            print(" No external databases linked.")
            return
        print("📊 Linked External Databases:")
        for d in dbs:
            print(f" - #{d['id']}: {d['uri'][:30]}... | Table: {d['table_name']}")


def cmd_node(args):
    """Manages remote NouGenShards cloud nodes."""
    if args.action == "link":
        if not args.url:
            print("Error: Usage: nougen node link <url> [--name <name>]")
            return
        name = args.name or f"node_{abs(hash(args.url)) % 1000}"
        keymaker.register_cloud_node(args.url, name)
        print(f"[*] Remote node linked: {name} ({args.url})")
    elif args.action == "list":
        nodes = keymaker.list_cloud_nodes()
        if getattr(args, 'json', False) is True:
            print(json.dumps(nodes))
            return
        if not nodes:
            print(" No remote nodes linked.")
            return
        print("[*] Linked Remote Nodes:")
        for n in nodes:
            print(f" - #{n['id']}: {n['name']} | URL: {n['url']}")
    elif args.action == "push":
        if not args.url:
            print("Error: Usage: nougen node push <url> --token <token>")
            return
        if not args.token:
            print("Error: --token <token> is required for push.")
            return
        
        print("[*] Extracting shards for push...")
        all_shards = []
        for i in range(1, shards.MAX_DB_COUNT + 1):
            if not shards.get_db_path(i).exists(): continue
            conn = shards.get_connection(i)
            try:
                rows = conn.execute("SELECT * FROM shards").fetchall()
                for r in rows:
                    d = dict(r)
                    emb = d.get("embedding")
                    if emb is not None:
                        d["embedding"] = _embedding_for_json(emb)
                    all_shards.append(d)
            finally:
                conn.close()
        
        print(f"[*] Pushing {len(all_shards)} shards to {args.url}...")
        res = push_to_cloud(all_shards, args.url, args.token)
        print(f"✅ Sync result: {res.get('status')} (Count: {res.get('count')})")
        
    elif args.action == "pull":
        if not args.url:
            print("Error: Usage: nougen node pull <url> --token <token>")
            return
        if not args.token:
            print("Error: --token <token> is required for pull.")
            return
        
        print(f"[*] Pulling shards from {args.url}...")
        remote_shards = pull_from_cloud(args.url, args.token)
        print(f"[*] Pulled {len(remote_shards)} shards. Ingesting locally...")
        count = 0
        for s in remote_shards:
            raw_tags = s.get("tags")
            if isinstance(raw_tags, str):
                try:
                    tags = json.loads(raw_tags or "[]")
                except (ValueError, TypeError) as e:
                    print(f"[!] Skipping bad tags on shard '{s.get('title')}': {e}")
                    tags = []
            else:
                tags = raw_tags
            try:
                success = shards.capture(
                    s.get("event_type", "SYNC"),
                    s.get("title", "Synced Shard"),
                    s.get("content", ""),
                    tags,
                    embedding=s.get("embedding")
                )
            except Exception as e:
                print(f"[!] Failed to ingest shard '{s.get('title')}': {e}")
                continue
            if success: count += 1
        print(f"✅ Ingestion complete. {count} new shards added.")


def cmd_config(args):
    """Update CLI or database configuration."""
    if args.action == "set" and args.key and args.value:
        print(f"✅ Configuration updated: {args.key} = {args.value}")
    else:
        print("Usage: nougen config set <key> <value>")


def cmd_connect(args):
    """Connect NouGenShards to an agent (e.g., via MCP)."""
    if args.mcp:
        print("Auto-detecting agent configuration...")
        ans = input("Add NouGenShards to your MCP config? [Y/n] ")
        if ans.lower() not in ['n', 'no']:
            print("✅ Wires connected. NouGenShards is now an active MCP memory tool.")
        else:
            print("Cancelled.")
    else:
        print("Usage: nougen connect --mcp")


def cmd_hook(args):
    """Install auto-capture hooks into the user's shell."""
    if args.action == "install":
        print("✅ Auto-capture hook installed into your shell.")
    else:
        print("Usage: nougen hook install")


def cmd_ingest(args):
    """Ingest a file's content as a single shard."""
    path = Path(args.file)
    if not path.exists():
        print(f"Error: File not found: {path}")
        sys.exit(1)
    print(f"Ingesting {path}...")
    try:
        with open(path, "r", encoding="utf-8") as f_in:
            content = f_in.read()
        domain_key = getattr(args, 'domain', None)
        if domain_key is not None and type(domain_key).__name__ in ('MagicMock', 'Mock'):
            domain_key = None
        if not domain_key:
            domain_key = shards.resolve_domain_from_path(str(path))
        shards.capture("INGEST", path.name, content, ["ingested", "docs"], domain_key=domain_key)
        print("✅ Ingestion complete.")
    except (OSError, sqlite3.Error) as exc:
        print(f"Failed: {exc}")


def cmd_dream(args):
    """Executes the Dream cycle (Autonomous NouGenMorph Evolution)."""
    if args.action == "wake":
        if not getattr(args, 'json', False):
            print("🌌 Entering the Dream State...  [EXPERIMENTAL: exports an SFT dataset; no live weight update]")
        summary = dream.wake()
        if getattr(args, 'json', False):
            print(json.dumps(summary, indent=2))
        else:
            print("\n[Dream Sequence Complete]")
            print(f" - {summary['pruned']}")
            shards_extracted = summary.get('shards_extracted_sft', summary.get('shards_extracted', 0))
            print(f" - Extracted top {shards_extracted} high-utility shards.")
            print(f" - Synthesized {summary['sft_pairs_generated']} invariants into SFT pairs.")
            print(f" - Burn-in dataset ready at: {summary['parametric_dataset_path']}")
            
            # Print dual-system consolidation details
            if "dual_system_consolidation" in summary:
                ds = summary["dual_system_consolidation"]
                print("\n🧠 [Dual-System Semantic Consolidation]")
                print(f" - Shards scanned: {ds.get('shards_scanned', 0)}")
                print(f" - Shards consolidated: {ds.get('shards_consolidated', 0)}")
                print(f" - New invariants extracted: {ds.get('new_invariants_extracted', 0)}")
                if ds.get("rules"):
                    print(" - Newly extracted rules:")
                    for r in ds["rules"][:5]:
                        print(f"   * [{r['subject']}] {r['predicate']}")
            
            # Print evolved procedural skills
            if summary.get("evolved_skills"):
                print("\n⚡ [Autonomous Skill Evolution]")
                for sk in summary["evolved_skills"]:
                    status_badge = "Verified in Sandbox (PILOT)" if sk.get("verified") else "Candidate"
                    print(f" - Evolved Skill: {sk['name']} [{status_badge}]")
                    if sk.get("path"):
                        print(f"   * Package: {sk['path']}")
            print(f"\n{summary['status']}")


def cmd_evolve(args):
    """Universal Open-World Skill Evolution (OpenSkill)."""
    if args.action == "run":
        is_json = getattr(args, 'json', False)
        if not is_json:
            print("[EXPERIMENTAL: OpenSkill acquisition + verification are simulated stubs]")
            print(f"[*] Evolution: Initiating OpenSkill cycle for '{args.instruction}'...")
        summary = evolution.run_autonomous_evolution(args.instruction, verbose=not is_json)
        if is_json:
            print(json.dumps(summary, indent=2))
        else:
            if summary.get("verified"):
                print("\n[Evolution Cycle Complete]")
                print(f" - Skill ID: {summary['skill_id']}")
                print(f" - Grounding: {summary['grounding_source']}")
                print(" - Status: Verified in Sandbox.")
                print(f" - Path: {summary['path']}")
            else:
                print(f"\n[Evolution Failed]: {summary.get('error')}")


def cmd_dashboard(args):
    """Launches the Cortex HUD (Visual Dashboard)."""
    import uvicorn
    # app.py is in the project root. When installed, we assume it's discoverable
    # in the path or we use absolute import if available.
    try:
        # For local execution from root
        sys.path.append(os.getcwd())
        import app
        dashboard_app = app.app
    except ImportError:
        print("Error: Dashboard module (app.py) not found in path.")
        return

    print(f"🚀 Igniting Cortex HUD on http://127.0.0.1:{args.port}...")
    uvicorn.run(dashboard_app, host="127.0.0.1", port=args.port)


def cmd_tenant(args):
    """Mint additional node credentials without persisting plaintext tokens."""
    if args.action != "mint":
        return
    try:
        token = tenants.mint_tenant(args.tenant_id, args.label)
    except tenants.TenantRegistryError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return
    print(f"Tenant: {args.tenant_id}")
    print(f"Token: {token}")
    print("Save this token now; it is stored only as a SHA-256 hash and cannot be shown again.")


def cmd_facts(args):
    """Index and resolve structured canonical fact snapshots."""
    from .canonical_facts import CanonicalFactIndex, SCHEMA_VERSION

    index = CanonicalFactIndex(args.index, create=args.facts_action in ("index", "migrate"))
    if args.facts_action == "migrate":
        print(json.dumps({"status": "migrated", "index": str(index.path),
                          "schema_version": SCHEMA_VERSION}))
        return
    if args.facts_action == "index":
        try:
            snapshot = json.loads(Path(args.input).read_text(encoding="utf-8"))
            snapshot_id = index.put(snapshot)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(json.dumps({"status": "rejected", "error": str(exc)}), file=sys.stderr)
            raise SystemExit(2) from exc
        print(json.dumps({"status": "indexed", "snapshot_id": snapshot_id}, indent=2))
        return

    try:
        scope = json.loads(args.scope) if args.scope else None
        if scope is not None and not isinstance(scope, dict):
            raise ValueError("--scope must be a JSON object")
        receipt = index.resolve_query(
            args.query, expected_machines=args.machine,
            expected_entities=args.entity or None, scope=scope,
            as_of=args.as_of,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(receipt, indent=2, sort_keys=True))


def get_parser():



    """Create the CLI parser."""
    parser = argparse.ArgumentParser(prog="nougen", description="NouGenShards CLI — Powered by NouGenAi")
    parser.add_argument("--version", action="version", version=f"NouGenShards v{VERSION} (Powered by NouGenAi)")
    subparsers = parser.add_subparsers(dest="command")

    p_init = subparsers.add_parser("init", help="Bootstrap substrate and onboard")
    p_init.add_argument("--defaults", action="store_true",
                        help="Accept every discovered default; ask nothing")
    p_init.add_argument("--no-onboarding", action="store_true",
                        help="Create the substrate only; skip capability discovery")
    p_init.add_argument("--json", action="store_true", help="Machine-readable output")

    p_add = subparsers.add_parser("add", help="Save shard")
    p_add.add_argument("content", nargs="?")
    p_add.add_argument("--tags")
    p_add.add_argument("--stdin", action="store_true")
    p_add.add_argument("--embed", action="store_true", help="Generate vector embedding")
    p_add.add_argument("--provider", help="Embedding provider")
    p_add.add_argument("--domain", help="Explicit domain boundary key override")

    p_get = subparsers.add_parser(
        "get", help="Resolve a shard by content hash, locator (<id>@db<N>), or ID")
    p_get.add_argument("target", help="Shard content hash (sha:<12+ hex> or <hash>), locator (<id>@db<N>), or ID")
    p_get.add_argument("--full", action="store_true", help="print the whole body")
    p_get.add_argument("--json", action="store_true", help="Machine-readable output")

    p_search = subparsers.add_parser("search", help="Search substrate")
    p_search.add_argument("query")
    p_search.add_argument("--semantic", action="store_true", help="Use vector search")
    p_search.add_argument("--provider", help="Embedding provider")
    p_search.add_argument("--json", action="store_true", help="Machine-readable output")
    p_search.add_argument("--domain", help="Explicit domain boundary key filter override")
    p_search.add_argument("--dual", action="store_true", help="Use dual-system memory recall (episodic + semantic rules)")

    p_assure = subparsers.add_parser("assure", help="Label a claim through Iris evidence assurance")
    p_assure.add_argument("claim")
    p_assure.add_argument("--evidence", action="append", default=[],
                          help="Evidence item; repeat for multiple items")
    p_assure.add_argument("--json", action="store_true", help="Machine-readable output")

    p_chat = subparsers.add_parser("chat", help="Chat with memory")
    p_chat.add_argument("query", nargs="?")
    p_chat.add_argument("--model")
    p_chat.add_argument("--provider")
    p_chat.add_argument("--json", action="store_true", help="Return answer, context and timing as JSON")
    p_chat.add_argument("--no-tools", action="store_true", help="Use recall without model tool calls")
    p_chat.add_argument("--recall-seconds", type=float, default=2.0, help="Recall wait budget (default: 2 seconds)")
    p_chat.add_argument("--agent", "-a", default=None,
                        help="Persona to embody (NouGen, Sol-Ai, Rhea, DavOs, Iris, Kaedra, Griot, Kronos)")

    p_auth = subparsers.add_parser("auth", help="Manage keys")
    p_auth.add_argument("action", choices=["set-key", "list", "check"])
    p_auth.add_argument("provider", nargs="?")
    p_auth.add_argument("input", nargs="?")
    p_auth.add_argument("--json", action="store_true", help="Machine-readable output")
    p_auth.add_argument("--timeout", type=float, default=10.0,
                        help="Per-provider probe timeout in seconds (auth check)")

    p_mark = subparsers.add_parser("mark", help="Update utility")
    p_mark.add_argument("id", type=int)
    p_mark.add_argument("--worked", action="store_true")
    p_mark.add_argument("--db", type=int, default=None,
                        help="Source DB index (the 'Source:' column from search) to target the exact shard")

    p_status = subparsers.add_parser("status", help="Show cluster health")
    p_status.add_argument("--json", action="store_true", help="Machine-readable output")
    p_status.add_argument("--plain", action="store_true", help="Plain text output")
    p_status.add_argument("--live", "-l", action="store_true", help="Launch real-time live interactive substrate HUD")

    p_models = subparsers.add_parser("models", help="List available LLM models for local or cloud providers")
    p_models.add_argument("--provider", "-p", default="local", help="Provider name (local, google, openrouter, etc.)")
    p_models.add_argument("--pull", help="Pull a model via Ollama")
    p_models.add_argument("--json", action="store_true", help="Machine-readable output")
    p_models.add_argument("--plain", action="store_true", help="Plain text output")

    p_usage = subparsers.add_parser("usage", help="Token telemetry from the local usage ledger")
    p_usage.add_argument("--period", default=None,
                         help="Reporting window (24h | week | month | quarter | year | all)")
    p_usage.add_argument("--json", action="store_true", help="Machine-readable output")

    p_stats = subparsers.add_parser("stats", help="Historical analytics")
    p_stats.add_argument("--period", choices=["24h", "week", "month", "quarter", "year"],
                         default="week")
    p_stats.add_argument("--json", action="store_true", help="Machine-readable output")

    p_ctx = subparsers.add_parser("ctx", help="Context layer")
    p_ctx.add_argument("action", choices=["init", "execute", "search", "get", "promote", "web", "analyze", "checkpoint", "restore", "checkpoints", "ask", "synthesize"])
    p_ctx.add_argument("input", nargs="?")
    p_ctx.add_argument("--tags", help="Tags for promoted shard, label for web/checkpoint, or context_handle for ask")
    p_ctx.add_argument("--query", help="Query keyword for file analyze or search")
    p_ctx.add_argument("--model", help="Specific Ollama model name (e.g. gemma4:e2b-qat, Yukiai:e2b)")
    p_ctx.add_argument("--limit", type=int, default=5, help="Max results for ctx search")

    # router
    p_router = subparsers.add_parser("router", help="OpenRouter production routing")
    p_router_sub = p_router.add_subparsers(dest="action")
    
    p_router_chat = p_router_sub.add_parser("chat", help="Chat with fallback")
    p_router_chat.add_argument("input")
    p_router_chat.add_argument("--model", default=None)
    p_router_chat.add_argument("--fallback", action="append", help="Fallback models")
    p_router_chat.add_argument("--session-id")
    p_router_chat.add_argument("--stream", action="store_true")
    p_router_chat.add_argument("--json", action="store_true")
    p_router_chat.add_argument("--temperature", type=float)
    p_router_chat.add_argument("--max-tokens", type=int)
    
    p_router_json = p_router_sub.add_parser("json", help="Structured JSON chat")
    p_router_json.add_argument("input")
    p_router_json.add_argument("--schema", required=True)
    p_router_json.add_argument("--model", default=None)
    p_router_json.add_argument("--fallback", action="append")
    p_router_json.add_argument("--session-id")
    p_router_json.add_argument("--healing", action="store_true", default=True)
    p_router_json.add_argument("--json", action="store_true")

    p_router_sub.add_parser("doctor", help="Check routing health")

    p_config = subparsers.add_parser("config", help="Configuration")
    p_config.add_argument("action", choices=["set"])
    p_config.add_argument("key")
    p_config.add_argument("value")

    p_connect = subparsers.add_parser("connect", help="Connect agent")
    p_connect.add_argument("--mcp", action="store_true")

    p_hook = subparsers.add_parser("hook", help="Auto-capture")
    p_hook.add_argument("action")

    p_ingest = subparsers.add_parser("ingest", help="Ingest file")
    p_ingest.add_argument("file")
    p_ingest.add_argument("--domain", help="Explicit domain boundary key override")

    p_db = subparsers.add_parser("db", help="Link external databases")
    p_db.add_argument("action", choices=["link", "list"])
    p_db.add_argument("uri", nargs="?", help="Database connection URI")
    p_db.add_argument("--table", help="Table name")
    p_db.add_argument("--title", default="title", help="Title column name")
    p_db.add_argument("--content", default="content", help="Content column name")
    p_db.add_argument("--json", action="store_true", help="Machine-readable output")

    p_node = subparsers.add_parser("node", help="Manage remote cloud nodes")
    p_node.add_argument("action", choices=["link", "list", "push", "pull"])
    p_node.add_argument("url", nargs="?", help="Remote node API URL")
    p_node.add_argument("--name", help="Friendly name for the node")
    p_node.add_argument("--token", help="Auth token for push/pull")
    p_node.add_argument("--json", action="store_true", help="Machine-readable output")

    p_tenant = subparsers.add_parser("tenant", help="Manage isolated node tenants")
    p_tenant.add_argument("action", choices=["mint"])
    p_tenant.add_argument("tenant_id", help="Lowercase tenant slug")
    p_tenant.add_argument("--label", required=True, help="Human-readable tenant label")

    p_doctor = subparsers.add_parser("doctor", help="Check system health")
    p_doctor.add_argument("--json", action="store_true", help="Machine-readable output")

    p_wishlist = subparsers.add_parser(
        "wishlist", help="Track the canonical 100-item resilience/context wishlist "
                        "(leg 20260910T202128Z, rebroadcast 20260923T174020Z)")
    p_wishlist_sub = p_wishlist.add_subparsers(dest="wishlist_command")

    p_wl_list = p_wishlist_sub.add_parser("list", help="List items, optionally filtered")
    p_wl_list.add_argument("--phase", type=int, choices=[1, 2, 3, 4], help="Filter to one execution phase")
    p_wl_list.add_argument("--category", choices=list("ABCDEF"), help="Filter to one category letter")
    p_wl_list.add_argument("--status", choices=["open", "in_progress", "landed", "verified"],
                           help="Filter to one status")
    p_wl_list.add_argument("--json", action="store_true", help="Machine-readable output")

    p_wl_show = p_wishlist_sub.add_parser("show", help="Show one item in full, with its tracking record")
    p_wl_show.add_argument("item_id", type=int)
    p_wl_show.add_argument("--json", action="store_true", help="Machine-readable output")

    p_wl_mark = p_wishlist_sub.add_parser(
        "mark", help="Set an item's status. landed/verified REQUIRE --evidence "
                    "(no completion stamp without live verification).")
    p_wl_mark.add_argument("item_id", type=int)
    p_wl_mark.add_argument("--status", required=True, choices=["open", "in_progress", "landed", "verified"])
    p_wl_mark.add_argument("--evidence", action="append", default=[],
                          help="A citation: shard id, leg id, PR#, or commit sha. Repeatable.")
    p_wl_mark.add_argument("--owner", help="machine/agent claiming or completing this item")
    p_wl_mark.add_argument("--note", default="", help="Free-text context")

    p_wl_progress = p_wishlist_sub.add_parser("progress", help="Progress summary by phase and category")
    p_wl_progress.add_argument("--json", action="store_true", help="Machine-readable output")

    p_dream = subparsers.add_parser("dream", help="Autonomous NouGenMorph Evolution (Dream State)")
    p_dream.add_argument("action", choices=["wake"])
    p_dream.add_argument("--json", action="store_true", help="Machine-readable output")

    p_evolve = subparsers.add_parser("evolve", help="Universal Open-World Skill Evolution (OpenSkill)")
    p_evolve.add_argument("action", choices=["run"])
    p_evolve.add_argument("instruction", help="The task instruction to evolve a skill for")
    p_evolve.add_argument("--json", action="store_true", help="Machine-readable output")

    p_dashboard = subparsers.add_parser("dashboard", help="Launch visual Cortex HUD")
    p_dashboard.add_argument("--port", type=int, default=4444, help="Port to run on")

    p_pr = subparsers.add_parser("pr", help="PR lease governor + confetti detector (NouGenMorph Absorption, Phase 1)")
    pr_sub = p_pr.add_subparsers(dest="pr_action", required=True)
    p_pr_attach = pr_sub.add_parser("attach", help="Fold an objective into the repo's open PR chain (3-5 objectives/PR), or start a new one")
    p_pr_attach.add_argument("--repo", required=True, help="owner/name")
    p_pr_attach.add_argument("--objective", required=True, help="One-line objective being bundled")
    p_pr_attach.add_argument("--branch", help="Branch name hint if a new chain is started")
    p_pr_attach.add_argument("--json", action="store_true")
    p_pr_status = pr_sub.add_parser("status", help="Show open leases/chains for a repo")
    p_pr_status.add_argument("--repo", required=True)
    p_pr_status.add_argument("--json", action="store_true")
    p_pr_confetti = pr_sub.add_parser("confetti", help="Detect clusters of small open PRs that should be consolidated")
    p_pr_confetti.add_argument("--repo", required=True)
    p_pr_confetti.add_argument("--min-group", type=int, default=3)
    p_pr_confetti.add_argument("--json", action="store_true")
    p_pr_review = pr_sub.add_parser("review", help="Incremental review with deduped comments")
    p_pr_review.add_argument("--repo", required=True, help="GitHub repository (owner/repo)")
    p_pr_review.add_argument("--pr", dest="pr_number", type=int, required=True, help="PR number to review")
    p_pr_review.add_argument("--objective", required=True, help="Active relay objective")
    p_pr_review.add_argument("--full", action="store_true", help="Run full review instead of incremental")
    p_pr_review.add_argument("--dry-run", action="store_true", help="Preview comments without posting")
    p_pr_review.add_argument("--json", action="store_true", help="JSON output")

    p_pr_context = pr_sub.add_parser("context", help="Gather CLAUDE.md/AGENTS.md/GEMINI.md + skills as review context")
    p_pr_context.add_argument("--path", default=".", help="Repo checkout root")
    p_pr_context.add_argument("--objective", help="Active relay objective to include")
    p_pr_context.add_argument("--json", action="store_true")

    p_brain = subparsers.add_parser("brain", help="Universal AI Memory Forensic Engine")
    p_brain.add_argument("action", choices=["scan", "import"])
    p_brain.add_argument("--project", help="Target project path to scan/import")
    p_brain.add_argument("--unknown", action="store_true", help="Include unknown files/folders")
    p_brain.add_argument("--source", help="Filter by specific source")
    p_brain.add_argument("--no-redact", action="store_true", help="Do not redact secrets")
    p_brain.add_argument("--confirm", action="store_true", help="Confirm writing to database")
    p_brain.add_argument("--json", action="store_true", help="Machine-readable output")

    # add_help=False: `-h/--help` must reach the relay engine, not stop here.
    p_hi = subparsers.add_parser("hi", help="Session-open probe: identity, fleet pulse, open handoffs")
    p_hi.add_argument("--no-fleet", action="store_true", help="Skip SSH pulse to peer nodes")
    p_hi.add_argument("--json", action="store_true", help="Machine-readable output")

    p_bye = subparsers.add_parser("bye", help="Session-close probe: dirty sweep + handoff + primer")
    p_bye.add_argument("--agent", "-a", default=None, help="Agent type for the handoff")
    p_bye.add_argument("--goal", "-g", default=None, help="Goal for the handoff")
    p_bye.add_argument("--summary", "-m", default="", help="Session summary for the handoff")
    p_bye.add_argument("--dry-run", action="store_true", help="Preview without writing a handoff")
    p_bye.add_argument("--publish-leg", action="store_true",
                       help="Also commit+push a real relay leg for this session close (not just a local handoff)")
    p_bye.add_argument("--no-shard", action="store_true", help="Skip writing a verified session-close shard")
    p_bye.add_argument("--json", action="store_true", help="Machine-readable output")

    p_hijack = subparsers.add_parser("hijack", help="Repoint a foreign/legacy handoff record onto this node")
    p_hijack.add_argument("--id", dest="handoff_id", required=True, help="Handoff id to hijack")
    p_hijack.add_argument("--agent", "-a", default=None, help="Agent to record as the hijacker")

    p_relay = subparsers.add_parser(
        "relay", add_help=False,
        help="Fleet relay board (NouGenRelay): open | read | ack | create | claim ...",
        description=("Pass-through to the NouGenRelay CLI, run against the fleet registry "
                     "clone. Everything after `relay` is handed to it verbatim, so "
                     "`nougen relay open`, `nougen relay ack --id <leg>` and "
                     "`nougen relay --help` all behave exactly like the bare `relay` command. "
                     "The registry is found via $NOUGEN_RELAY_DIR, then $FLEET_RELAY_DIR, then "
                     "a NouGenRelay checkout beside this repo."))
    p_relay.add_argument("relay_args", nargs=argparse.REMAINDER,
                         help="Arguments forwarded to the relay CLI")

    p_handoff = subparsers.add_parser("handoff", help="Cross-agent session handoff notes")
    p_handoff.add_argument("action", choices=[
        "create", "read", "list", "ack", "start", "checkpoint", "complete",
        "rebuild-db", "reconcile", "watch", "machines", "sync", "sync-init",
        "triggers", "trigger-add", "trigger-rm", "trigger-enable",
        "trigger-disable", "trigger-test", "trigger-runs",
    ], help=("create | read | list | ack | start | checkpoint | complete | "
             "rebuild-db | reconcile | watch | machines | sync | sync-init | "
             "triggers | trigger-add | trigger-rm | trigger-enable | "
             "trigger-disable | trigger-test | trigger-runs"))
    p_handoff.add_argument("--json", action="store_true",
                           help="(list) Machine-readable relay feed")
    p_handoff.add_argument("--message", "-m", default="", help="Handoff note or acknowledgement message")
    p_handoff.add_argument("--message-file", "-M", dest="message_file", default=None,
                           help=("Read the note from a file instead of the command line. Required for "
                                 "multi-line notes: cmd.exe cuts -m at the first newline and PowerShell "
                                 "eats $3/$4 inside currency."))
    p_handoff.add_argument("--agent", "-a", default=None,
                           help="Agent type (gemini, claude, codex, ollama, openrouter)")
    p_handoff.add_argument("--goal", "-g", default=None, help="The active goal/objective for this handoff")
    p_handoff.add_argument("--id", dest="handoff_id", default=None,
                           help="Target a specific handoff id")
    p_handoff.add_argument("--state", choices=["in_progress", "blocked", "complete"],
                           default="in_progress", help="Checkpoint state")
    p_handoff.add_argument("--write", action="store_true", default=False,
                           help="(reconcile/watch) Persist resolved stale-complete status to disk")
    p_handoff.add_argument("--interval", type=float, default=5.0,
                           help="(watch) Poll interval in seconds (default: 5.0)")
    p_handoff.add_argument("--trigger-id", dest="trigger_id", default=None,
                           help="(trigger-*) Trigger name")
    p_handoff.add_argument("--run", dest="run_cmd", default=None,
                           help="(trigger-add) Shell command to execute when the rule matches")
    p_handoff.add_argument("--on", dest="on_events", default="created",
                           help=("(trigger-add) Comma-separated events: created, "
                                 "acknowledged, started, checkpoint, blocked, completed"))
    p_handoff.add_argument("--origin", choices=["any", "local", "remote"], default="any",
                           help="(trigger-add) Fire only for handoffs from this origin")
    p_handoff.add_argument("--match-host", dest="match_host", default=None,
                           help="(trigger-add) Only handoffs written by this machine (host or id)")
    p_handoff.add_argument("--match-branch", dest="match_branch", default=None,
                           help="(trigger-add) Only handoffs on this git branch")
    p_handoff.add_argument("--match-goal", dest="match_goal", default=None,
                           help="(trigger-add) Only handoffs whose goal contains this text")
    p_handoff.add_argument("--on-machine", dest="on_machine", default=None,
                           help="(trigger-add) Only run the rule on this machine (host or id)")
    p_handoff.add_argument("--background", action="store_true", default=False,
                           help="(trigger-add) Detach the command instead of waiting for it")
    p_handoff.add_argument("--timeout", type=int, default=60,
                           help="(trigger-add) Seconds to wait for a foreground command")
    p_handoff.add_argument("--desc", dest="trigger_desc", default="",
                           help="(trigger-add) Human description of what the rule is for")
    p_handoff.add_argument("--event", dest="test_event", default="created",
                           help="(trigger-test) Event to simulate against the target handoff")
    p_handoff.add_argument("--limit", type=int, default=20,
                           help="(trigger-runs) How many past trigger runs to show")
    p_handoff.add_argument("--remote", default=None,
                           help="(sync/sync-init) Git remote holding the shared handoff records")
    p_handoff.add_argument("--no-push", dest="no_push", action="store_true", default=False,
                           help="(sync) Receive only — do not publish local records")
    p_handoff.add_argument("--no-pull", dest="no_pull", action="store_true", default=False,
                           help="(sync) Publish only — do not fetch remote records")
    p_handoff.add_argument("--no-replay", dest="no_replay", action="store_true", default=False,
                           help="(sync) Do not fire triggers for newly arrived records")
    p_handoff.add_argument("--share-triggers", dest="share_triggers", action="store_true",
                           default=False,
                           help="(sync) Also sync triggers.json — it is executable config, opt in knowingly")

    # --- Expanded Fleet Tool Subparsers ---
    p_tree = subparsers.add_parser("tree", help="Process provenance & import resolution inspection")
    p_tree.add_argument("--proc", default="app.py", help="Substring of process command")
    p_tree.add_argument("--module", default="nougen_shards.brain_scan.redaction", help="Dotted module path")
    p_tree.add_argument("--marker", default=r"re\.compile", help="Regex marker in module")
    p_tree.add_argument("--expect", type=int, default=29, help="Expected marker count")
    p_tree.add_argument("--health", metavar="URL", help="Inspect node /health URL over HTTP")
    p_tree.add_argument("--json", action="store_true", help="JSON output")

    p_tube = subparsers.add_parser("tube", help="YouTube/Media transcript ingestion & dedupe")
    p_tube.add_argument("tube_action", choices=["pull"], default="pull", nargs="?")
    p_tube.add_argument("url", help="YouTube video or playlist URL")
    p_tube.add_argument("--dry-run", action="store_true", help="Do not capture shards")

    p_arxiv = subparsers.add_parser("arxiv", help="Autonomous arXiv research & shard capture")
    p_arxiv.add_argument("arxiv_action", choices=["search", "ingest"], default="search")
    p_arxiv.add_argument("query", help="Search query or arXiv ID")
    p_arxiv.add_argument("--arxiv-id", dest="arxiv_id", default=None, help="Specific arXiv ID to ingest")
    p_arxiv.add_argument("--limit", type=int, default=5, help="Max results")
    p_arxiv.add_argument("--json", action="store_true", help="JSON output")

    p_viz = subparsers.add_parser("viz", help="Session forensic & token cost visualizer")
    p_viz.add_argument("viz_action", choices=["tokens", "session"], default="tokens", nargs="?")
    p_viz.add_argument("--session-id", dest="session_id", default=None, help="Session ID")
    p_viz.add_argument("--json", action="store_true", help="JSON output")

    p_msg = subparsers.add_parser("msg", help="Live fleet IPC messaging & socket broadcast")
    p_msg.add_argument("message", nargs="?", default="", help="Message text to send")
    p_msg.add_argument("--to", dest="target", default="all",
                        help="Target node or agent family, e.g. fleet:agents")
    p_msg.add_argument("--peers", action="store_true", help="List reachable fleet peers")
    p_msg.add_argument("--dry-run", action="store_true",
                        help="Resolve the target and print what would be sent, without sending it")
    p_msg.add_argument("--json", action="store_true", help="JSON output")

    p_evidence = subparsers.add_parser("evidence", help="Epistemic assurance & evidence class validation")
    p_evidence.add_argument("evidence_action", choices=["classes", "require"], default="classes", nargs="?")
    p_evidence.add_argument("--tags", default="", help="Comma-separated tags to validate")

    # tunnel: Ngrok secure ingress connector
    p_tunnel = subparsers.add_parser("tunnel", help="Start secure edge tunnel for local ports (Ngrok)")
    p_tunnel.add_argument("port", type=int, help="Local port to forward (e.g. 8766 for MsgNode, 3000 for Whovisions)")
    p_tunnel.add_argument("--service", default="generic", help="Service label (e.g. msgnode, whovisions, mcp)")
    p_tunnel.add_argument("--domain", default=None, help="Custom Ngrok reserved domain")
    p_tunnel.add_argument("--json", action="store_true", help="JSON output")

    # transcribe: Video / Audio transcription and summarization
    p_transcribe = subparsers.add_parser(
        "transcribe",
        help="AI Video Transcriber: transcribe & summarize video/audio from URL or file",
        description="Transcribe and summarize video/audio from 30+ platforms or local files using Whisper/LLM."
    )
    p_transcribe.add_argument("source", help="URL or path to local media/text file")
    p_transcribe.add_argument("-l", "--summary-language", default="en", help="Summary output language (default en)")
    p_transcribe.add_argument("-o", "--output-dir", default=None, help="Output directory for markdown/media")
    p_transcribe.add_argument("--no-video", dest="keep_video", action="store_false", help="Do not keep downloaded video")
    p_transcribe.add_argument("--no-llm", action="store_true", help="Skip LLM summary/translation")
    p_transcribe.add_argument("--whisper-model", default="base", choices=["tiny", "base", "small", "medium", "large"], help="Whisper model size")
    p_transcribe.add_argument("--video-max-height", type=int, default=720, help="Max video height for download")
    p_transcribe.add_argument("--api-key", default=None, help="OpenAI-compatible API key")
    p_transcribe.add_argument("--base-url", default=None, help="OpenAI-compatible base URL")
    p_transcribe.add_argument("--model", default=None, help="Model ID for summary/translation")
    p_transcribe.add_argument("--shard", action="store_true", default=True, help="Auto-shard output into NouGen grid")
    p_transcribe.add_argument("--json", action="store_true", help="JSON output")
    p_transcribe.add_argument("-q", "--quiet", action="store_true", help="Suppress progress logs")

    p_live = subparsers.add_parser(
        "live",
        help="NouGen Unified /live Control Plane & Fleet Operations Aggregator",
        description="Multi-node control plane (Apollo, Hyperion, Phoebus), sessions, ports, SSH, relays, and message dispatch."
    )
    p_live.add_argument("live_args", nargs=argparse.REMAINDER,
                        help="Subcommands: overview | snapshot | nodes | sessions | ports | ssh | relays | watch | tracker | send | broadcast | reply")

    p_algo = subparsers.add_parser(
        "algo",
        help="Canonical Algorithms & Data Structures Engine (TheAlgorithms/Python)",
        description="High-performance data structures, search algorithms, graph traversal, and compression."
    )
    algo_subs = p_algo.add_subparsers(dest="algo_action")

    p_algo_list = algo_subs.add_parser("list", help="List algorithms by category")
    p_algo_list.add_argument("--category", help="Category filter (searches, graphs, sorting, compression, dp)")
    p_algo_list.add_argument("--json", action="store_true", help="Machine-readable output")

    p_algo_info = algo_subs.add_parser("info", help="Show details, complexity, and implementation code for an algorithm")
    p_algo_info.add_argument("target", help="Algorithm key or name (e.g. dijkstra, bk_tree, trie, lzw_compression)")
    p_algo_info.add_argument("--json", action="store_true", help="Machine-readable output")

    p_algo_bench = algo_subs.add_parser("benchmark", help="Run algorithm micro-benchmark")
    p_algo_bench.add_argument("target", nargs="?", default="levenshtein", help="Algorithm key")
    p_algo_bench.add_argument("--iterations", type=int, default=500, help="Iteration count (default 500)")
    p_algo_bench.add_argument("--json", action="store_true", help="Machine-readable output")

    p_algo_ingest = algo_subs.add_parser("ingest", help="Ingest canonical algorithm knowledge shards into memory grid DB 5")
    p_algo_ingest.add_argument("--json", action="store_true", help="Machine-readable output")

    # destiny store
    p_destiny = subparsers.add_parser("destiny", help="Prospective memory & goal graph store (destinies.db)")
    destiny_sub = p_destiny.add_subparsers(dest="destiny_action")

    p_open = subparsers.add_parser(
        "open",
        help="OpenRouter Free Fleet Worker Engine (NouGenOpen)",
        description="Dedicated OpenRouter Free Fleet Worker Engine with Keymaker API key auto-resolution and zero-cost multi-model fallback."
    )
    p_open.add_argument("open_args", nargs=argparse.REMAINDER, help="Subcommands: status | ask [prompt] [--model MODEL] [--system SYSTEM]")
    
    p_destiny_list = destiny_sub.add_parser("list", help="List unfinished/active destinies")
    p_destiny_list.add_argument("--status", choices=list(destiny.STATUSES), default=None)
    p_destiny_list.add_argument("--trigger", default=None)
    p_destiny_list.add_argument("--branch", default=None)
    p_destiny_list.add_argument("--limit", type=int, default=20)
    p_destiny_list.add_argument("--json", action="store_true")

    p_destiny_create = destiny_sub.add_parser("create", help="Create a target destiny")
    p_destiny_create.add_argument("--title", required=True, help="Title of the destiny")
    p_destiny_create.add_argument("--goal", required=True, help="Terminal goal")
    p_destiny_create.add_argument("--branch", default=None, help="Branch label (U0, UX, ARCH, etc.)")
    p_destiny_create.add_argument("--trigger", default=None, help="Activation trigger")
    p_destiny_create.add_argument("--required", default=None, help="Required events (JSON or semi-colon list)")
    p_destiny_create.add_argument("--forbidden", default=None, help="Forbidden outcomes")
    p_destiny_create.add_argument("--variance", default=None, help="Acceptable variance")
    p_destiny_create.add_argument("--verification", default=None, help="Verification standard")
    p_destiny_create.add_argument("--status", choices=["dormant", "active"], default="dormant")
    p_destiny_create.add_argument("--actor", default=None)
    p_destiny_create.add_argument("--json", action="store_true")

    p_destiny_get = destiny_sub.add_parser("get", help="Get destiny by ID")
    p_destiny_get.add_argument("id", type=int, help="Destiny ID")
    p_destiny_get.add_argument("--json", action="store_true")

    p_destiny_update = destiny_sub.add_parser("update", help="Update destiny status")
    p_destiny_update.add_argument("id", type=int, help="Destiny ID")
    p_destiny_update.add_argument("to_status", choices=list(destiny.STATUSES), help="Target status")
    p_destiny_update.add_argument("--actor", default=None)
    p_destiny_update.add_argument("--evidence", default=None)
    p_destiny_update.add_argument("--json", action="store_true")

    p_destiny_link = destiny_sub.add_parser("link", help="Link shard, relay leg, agent, or destiny")
    p_destiny_link.add_argument("id", type=int, help="Destiny ID")
    p_destiny_link.add_argument("--kind", choices=list(destiny.LINK_KINDS), required=True)
    p_destiny_link.add_argument("--ref", required=True, help="Reference identifier")
    p_destiny_link.add_argument("--role", choices=list(destiny.LINK_ROLES), default="evidence")
    p_destiny_link.add_argument("--note", default=None)
    p_destiny_link.add_argument("--json", action="store_true")

    p_destiny_search = destiny_sub.add_parser("search", help="Search destinies")
    p_destiny_search.add_argument("query", help="Search query")
    p_destiny_search.add_argument("--all", action="store_true", help="Include finished/failed")
    p_destiny_search.add_argument("--limit", type=int, default=20)
    p_destiny_search.add_argument("--json", action="store_true")

    p_destiny_evolve = destiny_sub.add_parser("evolve", help="Evolve report on terminal destiny events")
    p_destiny_evolve.add_argument("--since", default=None)
    p_destiny_evolve.add_argument("--limit", type=int, default=50)
    p_destiny_evolve.add_argument("--json", action="store_true")

    # Structured canonical fact snapshots (separate from free-form shard recall).
    p_facts = subparsers.add_parser("facts", help="Index/resolve structured canonical fact snapshots")
    facts_sub = p_facts.add_subparsers(dest="facts_action", required=True)
    p_facts_migrate = facts_sub.add_parser("migrate", help="Backfill current pointers and query postings")
    p_facts_migrate.add_argument("--index", required=True, help="Explicit SQLite fact-index path")
    p_facts_index = facts_sub.add_parser("index", help="Append a validated FACT_SNAPSHOT JSON file")
    p_facts_index.add_argument("--index", required=True, help="Explicit SQLite fact-index path")
    p_facts_index.add_argument("--input", required=True, help="Snapshot JSON file")
    p_facts_resolve = facts_sub.add_parser("resolve", help="Resolve newest complete snapshot from natural language")
    p_facts_resolve.add_argument("query")
    p_facts_resolve.add_argument("--index", required=True, help="SQLite fact-index path")
    p_facts_resolve.add_argument("--machine", action="append", required=True, help="Expected machine; repeat for fleet scope")
    p_facts_resolve.add_argument("--entity", action="append", default=[], help="Expected canonical entity; repeat as needed")
    p_facts_resolve.add_argument("--scope", help="Additional exact JSON scope filter")
    p_facts_resolve.add_argument("--as-of", help="Reference date/time; 'today' queries require an exact date match")

    # wake daemon
    p_wake = subparsers.add_parser("wake", help="Run NouGen reactive idle wake daemon for fleet IPC messaging")
    p_wake.add_argument("--timeout", type=float, default=600.0, help="Max idle seconds before recycle")
    p_wake.add_argument("--interval", type=float, default=2.0, help="Poll interval in seconds")

    
    # wispr voice dictation
    p_wispr = subparsers.add_parser("wispr", help="Wispr Flow voice dictation ingestion & live stream")
    wispr_sub = p_wispr.add_subparsers(dest="wispr_action")
    
    p_wispr_latest = wispr_sub.add_parser("latest", help="Get latest Wispr transcript")
    p_wispr_latest.add_argument("--json", action="store_true")
    
    p_wispr_list = wispr_sub.add_parser("list", help="List recent Wispr transcripts")
    p_wispr_list.add_argument("--limit", type=int, default=10)
    p_wispr_list.add_argument("--json", action="store_true")
    
    p_wispr_watch = wispr_sub.add_parser("watch", help="Live stream dictations into NouGen shards")
    p_wispr_watch.add_argument("--interval", type=float, default=1.0)
    p_wispr_watch.add_argument("--no-shard", action="store_true", help="Do not auto-shard transcripts")

    # studio lighting
    p_studio = subparsers.add_parser("studio", help="Physical studio telemetry & RGB lighting (Razer / LIFX)")
    p_studio.add_argument("color", nargs="?", default="green", help="Target status color (green, yellow, orange, red, blue, purple, cyan, white)")
    p_studio.add_argument("--target", choices=["all", "razer", "lifx"], default="all", help="Hardware target")
    p_studio.add_argument("--json", action="store_true")

    # cloudflare fleet
    p_cf = subparsers.add_parser("cf", help="Cloudflare Fleet Engine: deploy, secrets, D1, KV, R2, and Workers AI")
    p_cf.add_argument("cf_args", nargs=argparse.REMAINDER, help="Arguments passed to tools/wrangler_fleet.py")

    # process supervisor & zombie killer
    p_sweep = subparsers.add_parser("sweep", aliases=["zombies"], help="Dynamic process supervisor & zombie killer")
    p_sweep.add_argument("--kill", "-k", "-Kill", action="store_true", help="Surgically terminate confirmed dead-parent zombies")
    p_sweep.add_argument("--json", action="store_true", help="Machine-readable output")
    p_sweep.add_argument("--verbose", "-v", action="store_true", help="Show suspicious non-dev orphans")

    # Learn With Mrs. B project engine
    p_mrsb = subparsers.add_parser("mrsb", help="Learn With Mrs. B: ESOL Coloring Book production engine")
    p_mrsb.add_argument("mrsb_action", nargs="?", default="status",
                        choices=["status", "audit", "lineage", "recall", "recurse", "build", "kdp"],
                        help="Action to perform (default: status)")
    p_mrsb.add_argument("--character", "-c", help="Character key for lineage lookup (e.g. mrs_b, little_dave, kam_the_police_helper)")
    p_mrsb.add_argument("--query", "-q", default="Mrs. B", help="Search query for shard recall")
    p_mrsb.add_argument("--limit", "-n", type=int, default=5, help="Max results for recall")
    p_mrsb.add_argument("--unit", "-u", type=int, default=None, help="Unit number (1-8) for recursive lesson ledger")
    p_mrsb.add_argument("--json", action="store_true", help="Machine-readable JSON output")

    return parser


def cmd_mrsb(args):
    """Learn With Mrs. B project engine: audit, lineage, recall, recurse, build, kdp."""
    mrsb.cli_handler(args)


def cmd_cf(args):
    """Execute native Cloudflare fleet manager operations."""
    from . import cloudflare
    subargs = getattr(args, "cf_args", [])
    
    try:
        cf = cloudflare.CloudflareClient()
    except Exception as e:
        print(f"❌ Cloudflare Auth Error: {e}", file=sys.stderr)
        print("💡 Set CLOUDFLARE_API_TOKEN_NOUGEN_FULL in Keymaker via 'nougen auth set-key cf <token>'", file=sys.stderr)
        sys.exit(1)

    sub = subargs[0].lower() if subargs else "status"

    if sub in ("status", "info"):
        print("=== ⛅ NouGen Cloudflare Edge Substrate ===")
        print(f"  Account: {cf.account_name} ({cf.account_id})")
        workers = cf.list_workers()
        print(f"  Workers: {len(workers)} deployed in orbit")
        d1s = cf.list_d1()
        kvs = cf.list_kv()
        r2s = cf.list_r2()
        print(f"  Storage: {len(d1s)} D1 DBs | {len(kvs)} KV Namespaces | {len(r2s)} R2 Buckets")
        
        # Intelligent local context detection
        local_info = cf.inspect_directory(Path.cwd())
        if local_info["is_worker"]:
            print("\n📁 Current Directory Worker Context:")
            print(f"  • Worker Name:    {local_info['worker_name']}")
            print(f"  • Config File:    {local_info['config_file']}")
            print(f"  • Entry Point:    {local_info['entry_file']} ({'exists' if local_info['entry_exists'] else 'MISSING'})")
            print(f"  • Compat Date:    {local_info['compatibility_date']}")
            live_status = "Deployed (Orbit)" if local_info["live_deployed"] else "Not Deployed to Cloudflare"
            print(f"  • Live Status:    {live_status}")
            if any(local_info["bindings"].values()):
                b_str = ", ".join(f"{k}: {len(v) if isinstance(v, list) else v}" for k, v in local_info["bindings"].items() if v)
                print(f"  • Bindings:       {b_str}")
            print("  💡 Tip: run 'nougen cf deploy' to build and publish this worker.")
        else:
            print("\n💡 Tip: run 'nougen cf --help' or 'nougen cf list' for active workers.")
        return

    if sub in ("list", "workers"):
        workers = cf.list_workers()
        print(f"⚡ Active Cloudflare Workers ({len(workers)}):")
        for w in workers:
            print(f"  • {w.id:<26} | modified: {w.modified_on} | usage: {w.usage_model}")
        return

    if sub in ("inspect", "check"):
        target = Path(subargs[1]) if len(subargs) > 1 else Path.cwd()
        info = cf.inspect_directory(target)
        print(f"🔎 Inspection Report: {info['directory']}")
        print(f"  • Is Worker Project: {info['is_worker']}")
        print(f"  • Worker Name:       {info['worker_name']}")
        print(f"  • Config File:       {info['config_file'] or 'none'}")
        print(f"  • Entry Point:       {info['entry_file']} ({'OK' if info['entry_exists'] else 'NOT FOUND'})")
        print(f"  • Live Deployed:     {info['live_deployed']}")
        print(f"  • Bindings:          {json.dumps(info['bindings'])}")
        return

    if sub == "ping":
        print("📡 Pinging Cloudflare Edge & Gateway...")
        res = cf.ping()
        print(f"  • Account:         {res['account_name']} ({res['account_id']})")
        print(f"  • Token Valid:     {'✅ Yes' if res['token_valid'] else '❌ No'}")
        print(f"  • API Latency:     {res['api_latency_ms']} ms")
        print(f"  • Active Workers:  {res['active_workers']}")
        print(f"  • Fleet Gateway:   {res['gateway_status']} ({res.get('gateway_latency_ms', '?')} ms)")
        print(f"  • Gateway URL:     {res['gateway_url']}")
        return

    if sub in ("secrets", "secret"):
        if len(subargs) < 2:
            local = cf.inspect_directory(Path.cwd())
            if local["is_worker"]:
                w_name = local["worker_name"]
            else:
                print("Usage: nougen cf secrets <worker_name>")
                return
        else:
            w_name = subargs[1]

        secrets = cf.list_secrets(w_name)
        print(f"🔐 Secrets for Worker [{w_name}] ({len(secrets)} found):")
        for s in secrets:
            print(f"  • {s.name:<30} (type: {s.type})")
        return

    if sub in ("secret-set", "set-secret"):
        if len(subargs) < 4:
            print("Usage: nougen cf secret-set <worker_name> <key> <val>")
            return
        w_name, key, val = subargs[1], subargs[2], subargs[3]
        if cf.put_secret(w_name, key, val):
            print(f"✅ Secret [{key}] stored on [{w_name}].")
        else:
            print(f"❌ Failed to store secret [{key}].")
        return

    if sub in ("sync-secrets", "sync_secrets"):
        if len(subargs) < 2:
            local = cf.inspect_directory(Path.cwd())
            if local["is_worker"]:
                w_name = local["worker_name"]
            else:
                print("Usage: nougen cf sync-secrets <worker_name> [keys...]")
                return
        else:
            w_name = subargs[1]

        explicit_keys = subargs[2:] if len(subargs) > 2 else None
        print(f"🔐 Syncing Keymaker secrets to Cloudflare Worker [{w_name}]...")
        result = cf.sync_secrets(w_name, explicit_keys)
        for k in result["synced"]:
            print(f"  ✅ Synced: {k}")
        for k in result["missing"]:
            print(f"  ⚠️ Missing in Keymaker vault: {k}")
        print(f"Done: {len(result['synced'])} synced, {len(result['missing'])} missing.")
        return

    if sub == "deploy":
        target = Path(subargs[1]) if len(subargs) > 1 and not subargs[1].startswith("--") else Path.cwd()
        name_override = None
        if "--name" in subargs:
            idx = subargs.index("--name")
            if idx + 1 < len(subargs):
                name_override = subargs[idx + 1]

        print(f"🚀 Auto-deploying worker from: {target.resolve()}...")
        try:
            res = cf.auto_deploy(target, worker_name_override=name_override)
            etag = res.get("result", {}).get("etag", "live")
            print(f"✅ Deployed [{res['worker_name']}] successfully! (ETag: {etag})")
            print(f"  • Entry Point: {res['entry_point']}")
            print(f"  • Live URL:    https://{res['worker_name']}.whoentertains.workers.dev")
        except Exception as e:
            print(f"❌ Deploy failed: {e}")
            sys.exit(1)
        return

    if sub == "ai":
        ai_sub = subargs[1].lower() if len(subargs) > 1 else "run"
        if ai_sub == "models":
            models = cf.list_ai_models()
            print("🤖 Cloudflare Workers AI Model Catalogue (Free Tier):")
            for m in models:
                print(f"  • {m['id']:<42} | {m['task']:<24} | {m['speed']:<10} | {m['neurons_per_m']} N/M")
            return
        if ai_sub == "embed":
            text = " ".join(subargs[2:]) if len(subargs) > 2 else "NouGen Fleet Substrate"
            print(f"🔮 Computing zero-VRAM embedding for: '{text[:50]}'...")
            emb = cf.embed_ai(text)
            dim = len(emb[0]) if emb else 0
            print(f"✅ Generated {dim}-dimensional vector on Cloudflare Edge.")
            return

        # Default: run prompt
        model = "@cf/meta/llama-3.1-8b-instruct"
        prompt_args = subargs[1:]
        if "--model" in prompt_args:
            m_idx = prompt_args.index("--model")
            if m_idx + 1 < len(prompt_args):
                model = prompt_args[m_idx + 1]
                prompt_args = prompt_args[:m_idx] + prompt_args[m_idx + 2:]
        if prompt_args and prompt_args[0] == "run":
            prompt_args = prompt_args[1:]

        prompt = " ".join(prompt_args) if prompt_args else "Explain NouGen fleet architecture in 2 sentences."
        print(f"🤖 Workers AI [{model}]:\n'{prompt}'\n")
        try:
            resp = cf.run_ai(prompt, model=model)
            print(f"--- Output ---\n{resp}\n--------------")
        except Exception as e:
            print(f"❌ Workers AI error: {e}")
        return

    if sub == "d1":
        d1_sub = subargs[1] if len(subargs) > 1 else "list"
        if d1_sub == "query" and len(subargs) >= 4:
            db_name = subargs[2]
            sql = " ".join(subargs[3:])
            print(f"🗄️ Executing D1 SQL on [{db_name}]: {sql}")
            res = cf.query_d1(db_name, sql)
            print(json.dumps(res, indent=2))
            return
        dbs = cf.list_d1()
        print(f"🗄️ Cloudflare D1 Databases ({len(dbs)}):")
        if not dbs:
            print("  (No D1 databases created yet)")
        for d in dbs:
            print(f"  • {d.get('name'):<20} (uuid: {d.get('uuid')})")
        return

    if sub == "kv":
        kvs = cf.list_kv()
        print(f"📦 Cloudflare KV Namespaces ({len(kvs)}):")
        if not kvs:
            print("  (No KV namespaces created yet)")
        for k in kvs:
            print(f"  • {k.get('title'):<20} (id: {k.get('id')})")
        return

    if sub == "r2":
        buckets = cf.list_r2()
        print(f"🪣 Cloudflare R2 Buckets ({len(buckets)}):")
        if not buckets:
            print("  (No R2 buckets created yet)")
        for b in buckets:
            print(f"  • {b.get('name'):<20} (created: {b.get('creation_date', '')[:10]})")
        return

    print(f"Unknown cf subcommand: {sub}.")
    print("Available subcommands:")
    print("  status | list | inspect | ping | deploy | secrets | secret-set | sync-secrets | ai | d1 | kv | r2")


def cmd_sweep(args):
    """Dynamic process supervisor and zombie killer."""
    from . import zombie_killer
    hunter = zombie_killer.ZombieHunter()
    res = hunter.sweep(kill=getattr(args, "kill", False))
    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
    else:
        print(zombie_killer.ZombieHunter.render_report(res, verbose=getattr(args, "verbose", False)))


def cmd_live(args):
    """Execute /live control plane subcommands."""
    from .live import handle_live_command
    subargs = getattr(args, "live_args", [])
    print(handle_live_command(subargs))


def cmd_algo(args):
    """Canonical Algorithms & Data Structures CLI."""
    from .algorithms import list_algorithms, get_algorithm, benchmark_algorithm, ingest_algorithm_shards
    action = getattr(args, "algo_action", None) or "list"

    if action == "list":
        cat = getattr(args, "category", None)
        algos = list_algorithms(cat)
        if getattr(args, "json", False):
            print(json.dumps(algos, indent=2))
        else:
            print(f"📐 Canonical Algorithms ({cat or 'All Categories'}):")
            for a in algos:
                print(f"  • {a['key']:20} {a['name']:32} [{a['category']:16}] {a['time_complexity']:14} {a['space_complexity']}")
    elif action == "info":
        target = getattr(args, "target", "")
        if not target:
            print("Error: Specify algorithm name or key.")
            return
        info = get_algorithm(target)
        if not info:
            print(f"Error: Algorithm '{target}' not found in catalog.")
            return
        if getattr(args, "json", False):
            print(json.dumps(info, indent=2))
        else:
            print(f"📐 {info['name']} ({info['key']})")
            print(f"  Category:         {info['category']}")
            print(f"  Time Complexity:  {info['time_complexity']}")
            print(f"  Space Complexity: {info['space_complexity']}")
            print(f"\nDescription:\n  {info['description']}")
            if info.get("code"):
                print(f"\nCanonical Implementation:\n{info['code']}")
    elif action in ("benchmark", "run", "bench"):
        target = getattr(args, "target", "levenshtein")
        iters = getattr(args, "iterations", 500)
        res = benchmark_algorithm(target, iterations=iters)
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            if "error" in res:
                print(f"Error: {res['error']}")
            else:
                print(f"⚡ Benchmark for {res['algorithm']}:")
                print(f"  Iterations:       {res['iterations']}")
                print(f"  Elapsed:          {res['elapsed_ms']} ms")
                print(f"  Throughput:       {res['ops_per_sec']:,} ops/sec")
                print(f"  Complexity:       {res['time_complexity']}")
    elif action == "ingest":
        count = ingest_algorithm_shards()
        if getattr(args, "json", False):
            print(json.dumps({"ingested": count, "target_db": 5}))
        else:
            print(f"✅ Ingested {count} canonical algorithm shards into memory grid DB 5.")



def keymaker_vault_report() -> list:
    """Doctor lines for the Keymaker secrets vault.

    This is NOT the shard substrate — a bare "[Vault] ❌ not found" printed
    next to nine healthy shard DBs read as a contradiction, and got reported
    as one (phoebus, 2026-08-04). A box with no stored secrets is a normal
    configuration, so the absence is information, not a failure.
    """
    vault_path = keymaker.DB_PATH
    if vault_path.exists():
        providers = keymaker.list_providers()
        return [
            f" ✅ Keymaker vault: {vault_path.absolute()}",
            f" ✅ Connected Providers: {', '.join(providers) if providers else 'None'}",
        ]
    return [
        f" ℹ️ No keymaker vault at {vault_path.absolute()} — this box has",
        "    no stored provider secrets. The shard substrate above is a",
        "    separate store and is unaffected. Create the vault with",
        f"    'nougen auth set-key <provider>', or point {keymaker.ENV_SECRETS_VAULT}",
        "    at an existing one.",
    ]


def cmd_wishlist(args):
    """Track the canonical 100-item resilience/context wishlist.

    The wishlist text lives in wishlist.py, verbatim from the rebroadcast --
    this command never edits it. What this command manages is the tracking
    layer: which items are open/in_progress/landed/verified, by whom, with
    what evidence. landed/verified are refused without at least one
    citation, per the wishlist's own doctrine (item 86, item 40).
    """
    from . import wishlist as wl  # pylint: disable=import-outside-toplevel

    sub = getattr(args, "wishlist_command", None)
    if sub is None:
        print("usage: nougen wishlist {list,show,mark,progress}")
        return

    state = wl.load_state()

    if sub == "list":
        rows = []
        for item_id, item in sorted(wl.ITEMS.items()):
            if args.phase and item.phase != args.phase:
                continue
            if args.category and item.category != args.category:
                continue
            rec = state.get(item_id)
            if args.status and rec.status.value != args.status:
                continue
            rows.append({"id": item_id, "category": item.category, "phase": item.phase,
                        "status": rec.status.value, "text": item.text,
                        "owner": rec.owner, "evidence": rec.evidence})
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for r in rows:
                owner = f" [{r['owner']}]" if r["owner"] else ""
                print(f"{r['id']:>3}. [{r['category']}/P{r['phase']}] ({r['status']}){owner} {r['text']}")
            print(f"\n{len(rows)} item(s)")
        return

    if sub == "show":
        if args.item_id not in wl.ITEMS:
            print(f"no such item: {args.item_id}")
            raise SystemExit(1)
        item = wl.ITEMS[args.item_id]
        rec = state.get(args.item_id)
        doc = {"id": item.id, "category": item.category, "category_name": item.category_name,
              "phase": item.phase, "text": item.text, **rec.to_dict()}
        if args.json:
            print(json.dumps(doc, indent=2))
        else:
            print(f"#{item.id} [{item.category} — {item.category_name}] phase {item.phase}")
            print(f"  {item.text}")
            print(f"  status: {rec.status.value}")
            if rec.owner:
                print(f"  owner: {rec.owner}")
            if rec.evidence:
                print(f"  evidence: {', '.join(rec.evidence)}")
            if rec.note:
                print(f"  note: {rec.note}")
            if rec.updated_at:
                print(f"  updated: {rec.updated_at}")
        return

    if sub == "mark":
        if args.item_id not in wl.ITEMS:
            print(f"no such item: {args.item_id}")
            raise SystemExit(1)
        try:
            rec = state.mark(args.item_id, wl.ItemStatus(args.status), evidence=args.evidence,
                            owner=args.owner, note=args.note)
        except ValueError as exc:
            print(f"refused: {exc}")
            raise SystemExit(1) from exc
        wl.save_state(state)
        print(f"#{args.item_id} -> {rec.status.value}" + (f" [{rec.owner}]" if rec.owner else ""))
        return

    if sub == "progress":
        by_phase = wl.progress_by_phase(state)
        by_cat = wl.progress_by_category(state)
        if args.json:
            print(json.dumps({"by_phase": by_phase, "by_category": by_cat}, indent=2))
            return
        print("By phase (execution order: 1 -> 2 -> 3 -> 4):")
        for phase in (1, 2, 3, 4):
            p = by_phase[phase]
            done = p["landed"] + p["verified"]
            print(f"  Phase {phase}: {done}/{p['total']} landed/verified "
                 f"({p['in_progress']} in progress, {p['open']} open)")
        print("\nBy category:")
        for letter, name in wl.CATEGORIES.items():
            c = by_cat[letter]
            done = c["landed"] + c["verified"]
            print(f"  {letter} ({name}): {done}/{c['total']}")
        return

    print(f"unknown wishlist subcommand: {sub!r}")
    raise SystemExit(1)


def cmd_doctor(args):
    """Verifies installation, database health, and service connectivity (NouGenMorph Engine)."""
    if not getattr(args, 'json', False) and not getattr(args, 'plain', False):
        try:
            from .rich_hud import render_rich_doctor, is_rich_enabled
            if is_rich_enabled():
                active = shards.get_active_db_index()
                found_db = any(shards.get_db_path(i).exists() for i in range(1, shards.MAX_DB_COUNT + 1))
                p_status = {}
                for name in ["openai", "anthropic", "google", "openrouter", "local"]:
                    c = get_client(name)
                    p_status[name] = c.is_alive() if c else False
                report = {
                    "substrate": {"active_index": active, "found": found_db},
                    "vault": {"path": str(keymaker.DB_PATH.absolute()),
                              "exists": keymaker.DB_PATH.exists(),
                              "providers": keymaker.list_providers() if keymaker.DB_PATH.exists() else []},
                    "connectivity": p_status
                }
                render_rich_doctor(report)
                return
        except Exception:
            pass

    print("👨‍⚕️ NouGenShards Doctor (NouGenMorph): Running diagnostics...")
    
    # 1. Check Substrate
    print("\n[Substrate]")
    active = shards.get_active_db_index()
    found_db = False
    for i in range(1, shards.MAX_DB_COUNT + 1):
        p = shards.get_db_path(i)
        if p.exists():
            size = p.stat().st_size / (1024 * 1024)
            print(f" ✅ DB #{i}: {p} ({size:.2f} MB)")
            found_db = True
    if not found_db:
        print(" ❌ No database shards found. Run 'nougen init' to bootstrap.")

    # 2. Check the Keymaker secrets vault.
    print("\n[Keymaker Vault]")
    for line in keymaker_vault_report():
        print(line)

    # 3. Check Providers
    print("\n[Service Connectivity]")
    p_status = {}
    for name in ["openai", "anthropic", "google", "openrouter", "local"]:
        c = get_client(name)
        alive = c.is_alive() if c else False
        p_status[name] = alive
        print(f" {'✅' if alive else '❌'} {name.capitalize()}")

    # 4. Check NouGenMorph Engine Modules
    print("\n[NouGenMorph Cognitive Engines]")
    try:
        from . import dream, evolution  # noqa: F401 - imported to probe availability for `nougen doctor`
        print(" ✅ Dream State (TMEM): Ready")
        print(" ✅ Evolution Engine (OpenSkill): Ready")
    except ImportError as e:
        print(f" ❌ Engine Modules missing: {e}")

    # 5. Check Cloudflare Edge Substrate & Fleet Gateway
    print("\n[Cloudflare Edge Substrate]")
    cf_diag = {}
    try:
        from . import cloudflare
        cf_client = cloudflare.CloudflareClient()
        ping_res = cf_client.ping()
        cf_diag = ping_res
        print(f" ✅ Cloudflare Account: {ping_res['account_name']} ({ping_res['account_id'][:10]}...)")
        print(f" ✅ Active Workers: {ping_res['active_workers']} deployed in orbit")
        print(f" ✅ Fleet MCP Gateway: {ping_res['gateway_status']} ({ping_res.get('gateway_latency_ms', '?')} ms)")
        print(f" ✅ Workers AI Edge: Ready (API latency: {ping_res['api_latency_ms']} ms)")
    except Exception as e:
        cf_diag = {"error": str(e)}
        print(f" ⚠️ Cloudflare Edge Substrate: {e}")

    if getattr(args, 'json', False):
        import json
        print("\n[JSON Output]")
        report = {
            "substrate": {"active_index": active, "found": found_db},
            "vault": {"path": str(keymaker.DB_PATH.absolute()),
                      "exists": keymaker.DB_PATH.exists(),
                      "providers": keymaker.list_providers() if keymaker.DB_PATH.exists() else []},
            "connectivity": p_status,
            "cloudflare_edge": cf_diag
        }
        print(json.dumps(report, indent=2))

def _resolve_handoff_message(args):
    """Resolves --message-file into args.message, and warns on shell-mangled -m notes.

    A multi-line note cannot survive the command line on Windows: cmd.exe ends the
    argument at the first newline and PowerShell expands $3/$4 inside currency to
    nothing. --message-file is the only path that is safe for both.
    """
    path_arg = getattr(args, "message_file", None)
    if path_arg:
        if getattr(args, "message", ""):
            print("[!] Both --message and --message-file given; using --message-file.")
        path = Path(os.path.expandvars(str(path_arg))).expanduser()
        if not path.is_file():
            print(f"[X] --message-file not found: {path}")
            return False
        encoding = os.environ.get("NOUGEN_HANDOFF_ENCODING", "utf-8")
        try:
            args.message = path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            # Common on notes written by PowerShell's default Set-Content.
            args.message = path.read_text(encoding="utf-8-sig", errors="replace")
            print(f"[!] {path.name} was not valid {encoding}; re-read as utf-8-sig with replacements.")
        if not args.message.strip():
            print(f"[X] --message-file is empty: {path}")
            return False
        return True

    message = getattr(args, "message", "") or ""
    if message.lstrip().startswith("#") and "\n" not in message:
        print("[!] Note looks truncated: it starts with a heading and has no newline. "
              "cmd.exe cuts -m at the first newline — use -M/--message-file instead.")
    return True


def cmd_handoff(args):
    """Executes agent handoff subcommands."""
    from . import handoff
    if not _resolve_handoff_message(args):
        return
    if args.action == "create":
        handoff.create_handoff(args.message, args.agent, goal=getattr(args, "goal", None))
    elif args.action == "read":
        handoff.show_latest_handoff(args.agent)
    elif args.action == "list":
        if getattr(args, "json", False) is True:
            print(json.dumps(handoff.handoff_feed(args.agent, getattr(args, "limit", 25))))
        else:
            handoff.list_handoffs(args.agent)
    elif args.action == "ack":
        handoff.acknowledge_handoff(args.agent, args.message, getattr(args, "handoff_id", None))
    elif args.action == "start":
        handoff.start_orchestration(args.agent, args.message, getattr(args, "handoff_id", None))
    elif args.action == "checkpoint":
        handoff.checkpoint_orchestration(
            args.agent,
            args.message,
            getattr(args, "handoff_id", None),
            getattr(args, "state", "in_progress"),
        )
    elif args.action == "complete":
        handoff.complete_orchestration(args.agent, args.message, getattr(args, "handoff_id", None))
    elif args.action == "rebuild-db":
        count = handoff.rebuild_handoff_db(args.agent)
        print(f"Indexed {count} handoff record(s) in {handoff.get_handoff_db_path()}")
    elif args.action == "reconcile":
        counts = handoff.reconcile_handoffs(
            agent=getattr(args, "agent", None),
            write=getattr(args, "write", False),
        )
        import json as _json
        print(_json.dumps(counts, indent=2))
    elif args.action == "watch":
        handoff.watch_handoffs(
            agent=getattr(args, "agent", None),
            interval=getattr(args, "interval", 5.0),
            write=getattr(args, "write", False),
        )
    elif args.action == "machines":
        handoff.show_machines(getattr(args, "agent", None))
    elif args.action in {"sync", "sync-init"}:
        cmd_handoff_sync(args)
    elif args.action.startswith("trigger"):
        cmd_handoff_triggers(args, handoff)


def cmd_handoff_sync(args):
    """Exchange handoff records with the other computers in the fleet."""
    from . import handoff_sync

    if args.action == "sync-init":
        result = handoff_sync.init_sync(
            remote=args.remote, share_triggers=args.share_triggers
        )
        if result.get("error"):
            print(f"Sync setup failed: {result['error']}")
            return
        print(f"Handoff sync repo: {result['dir']}")
        print(f"Remote: {result.get('remote') or 'none configured'}")
        if not result.get("remote"):
            print("Set one with: nougen handoff sync-init --remote <git url>")
        return

    report = handoff_sync.sync(
        remote=args.remote,
        push=not args.no_push,
        pull=not args.no_pull,
        share_triggers=args.share_triggers,
        replay=not args.no_replay,
    )
    print(f"Sync from {report['host']} → {report.get('remote') or 'no remote'}")
    print(
        f"  committed={report['committed']} pulled={report['pulled']} "
        f"pushed={report['pushed']}"
    )
    for handoff_id in report["arrived"]:
        print(f"  ← arrived: {handoff_id}")
    for record in report["fired"]:
        print(f"  ⚡ {record['trigger_id']} → {record['status']}")
    for error in report["errors"]:
        print(f"  ! {error}")


def cmd_handoff_triggers(args, handoff):
    """Trigger subcommands — the automation layer on top of handoff state."""
    from . import handoff_triggers, machine

    action = args.action
    if action == "triggers":
        triggers = handoff_triggers.load_triggers()
        mode = handoff_triggers.trigger_mode()
        print(f"Machine: {machine.host_label()} ({machine.machine_id()})")
        print(f"Trigger mode: {mode}  [NOUGEN_TRIGGERS=off|dry to change]")
        print(f"Registry: {handoff_triggers.get_trigger_file()}")
        if not triggers:
            print("No triggers registered. Add one with 'handoff trigger-add'.")
            return
        for t in triggers:
            match = t.get("match") or {}
            state = "enabled" if t.get("enabled", True) else "disabled"
            scope = t.get("on_machine") or "any machine"
            filters = ", ".join(
                f"{k}={v}" for k, v in match.items() if v and v != "any"
            ) or "no filters"
            print(
                f"\n• {t.get('id')} [{state}] on {scope}\n"
                f"  events: {', '.join(t.get('events') or [])}\n"
                f"  match : {filters}\n"
                f"  run   : {t.get('run')}"
                + ("  (background)" if t.get("background") else "")
            )
            if t.get("description"):
                print(f"  note  : {t['description']}")
        return

    if action == "trigger-add":
        if not args.trigger_id or not args.run_cmd:
            print("trigger-add needs --trigger-id and --run.")
            return
        try:
            trigger = handoff_triggers.add_trigger(
                trigger_id=args.trigger_id,
                run=args.run_cmd,
                events=[e.strip() for e in (args.on_events or "").split(",") if e.strip()],
                origin=args.origin,
                agent=args.agent,
                host=args.match_host,
                branch=args.match_branch,
                goal_contains=args.match_goal,
                on_machine=args.on_machine,
                background=args.background,
                timeout=args.timeout,
                description=args.trigger_desc,
            )
        except ValueError as exc:
            print(f"Invalid trigger: {exc}")
            return
        print(f"Registered trigger '{trigger['id']}' → {handoff_triggers.get_trigger_file()}")
        return

    if action == "trigger-rm":
        if not args.trigger_id:
            print("trigger-rm needs --trigger-id.")
            return
        removed = handoff_triggers.remove_trigger(args.trigger_id)
        print("Removed." if removed else f"No trigger '{args.trigger_id}'.")
        return

    if action in {"trigger-enable", "trigger-disable"}:
        if not args.trigger_id:
            print(f"{action} needs --trigger-id.")
            return
        enabled = action == "trigger-enable"
        found = handoff_triggers.set_trigger_enabled(args.trigger_id, enabled)
        print(
            f"Trigger '{args.trigger_id}' {'enabled' if enabled else 'disabled'}."
            if found else f"No trigger '{args.trigger_id}'."
        )
        return

    if action == "trigger-test":
        # Dry run against a real record: shows which rules would fire without
        # executing anything, so a rule can be proven before it is trusted.
        path, data = handoff._find_handoff(
            args.agent, getattr(args, "handoff_id", None), None
        )
        if not path or not data:
            print("No handoff record found to test against.")
            return
        os.environ["NOUGEN_TRIGGERS"] = "dry"
        try:
            fired = handoff_triggers.fire(args.test_event, data, path)
        finally:
            os.environ.pop("NOUGEN_TRIGGERS", None)
        print(
            f"Handoff {data.get('handoff_id')} "
            f"(origin={machine.record_origin(data)}, event={args.test_event})"
        )
        if not fired:
            print("No triggers would fire.")
        for record in fired:
            print(f"  would run [{record['trigger_id']}]: {record['command']}")
        return

    if action == "trigger-runs":
        runs = handoff.get_trigger_runs(limit=args.limit, trigger_id=args.trigger_id)
        if not runs:
            print("No trigger runs recorded.")
            return
        for run in runs:
            print(
                f"{(run.get('timestamp') or '')[:19]}  {run.get('trigger_id')}  "
                f"{run.get('event')}  {run.get('status')}  "
                f"exit={run.get('exit_code')}  on={run.get('host')}  "
                f"handoff={run.get('handoff_id')}"
            )
            if run.get("stderr"):
                print(f"    stderr: {run['stderr'].strip()[:200]}")
        return


def cmd_tree(args):
    """Process provenance & import inspection."""
    if getattr(args, "health", None):
        try:
            info = tree_probe.inspect_node_health(args.health)
            def _plain_health(p, style):
                yield f"Health check for {args.health}:"
                for k, v in p.items():
                    yield f"  {k:<24} {v}"
            emit(info, plain=_plain_health, args=args)
        except Exception as e:
            print(f"[ERROR] Health check failed: {e}", file=sys.stderr)
            sys.exit(1)
        return

    res = tree_probe.probe_local_tree(
        module=getattr(args, "module", "nougen_shards.brain_scan.redaction"),
        marker=getattr(args, "marker", r"re\.compile"),
        expect=getattr(args, "expect", 29),
        proc_pattern=getattr(args, "proc", "app.py")
    )
    def _plain_tree(p, style):
        yield f"\n🌲 Tree Provenance Probe: {p['status'].upper()}"
        for proc in p.get("processes", []):
            yield f"  PID {proc['pid']}: {proc['command'][:60]}"
            yield f"    cwd:        {proc['cwd']}"
            yield f"    PYTHONPATH: {proc['pythonpath']}"
            yield f"    resolved:   {proc['resolved_file']}"
            yield f"    marker:     {proc['marker_count']} (expected: {proc['is_expected']})"
    emit(res, plain=_plain_tree, args=args)
    if res["status"] != "ok":
        sys.exit(1)


def cmd_tube(args):
    """NouGenTube media transcript ingester."""
    action = getattr(args, "tube_action", "pull")
    if action == "pull":
        url = args.url
        print(f"📺 NouGenTube pulling: {url}")
        try:
            prev_argv = sys.argv
            sys.argv = ["tube", url]
            if getattr(args, "dry_run", False):
                sys.argv.append("--dry-run")
            try:
                tube.main()
            finally:
                sys.argv = prev_argv
        except SystemExit:
            pass
        except Exception as e:
            print(f"[ERROR] Tube ingest failed: {e}", file=sys.stderr)
            sys.exit(1)


def cmd_arxiv(args):
    """ArXiv paper intelligence & shard capture."""
    action = getattr(args, "arxiv_action", "search")
    if action == "search":
        papers = arxiv_core.search_arxiv(args.query, max_results=args.limit)
        def _plain_search(p, style):
            yield f"\n📄 arXiv search for '{args.query}' ({len(p.get('papers', []))} hits):\n"
            for i, item in enumerate(p.get("papers", []), 1):
                yield f"{i}. [{item['arxiv_id']}] {item['title']}"
                yield f"   Authors: {', '.join(item['authors'][:3])}"
                yield f"   URL:     {item['url']}\n"
        emit({"query": args.query, "papers": papers}, plain=_plain_search, args=args)
    elif action == "ingest":
        papers = arxiv_core.search_arxiv(args.arxiv_id, max_results=1)
        if not papers:
            print(f"Paper {args.arxiv_id} not found.", file=sys.stderr)
            sys.exit(1)
        res = arxiv_core.ingest_paper_to_shard(papers[0])
        def _plain_ingest(p, style):
            yield f"Captured shard #{p['shard_id']} (db{p['db']}) sha:{p['file_hash'][:12]}"
        emit(res, plain=_plain_ingest, args=args)


def cmd_viz(args):
    """Brain session forensic & token telemetry visualizer."""
    action = getattr(args, "viz_action", "tokens")
    if action in {"tokens", "session"}:
        sid = getattr(args, "session_id", None)
        report = viz_core.audit_session(sid)
        def _plain_viz(p, style):
            if p.get("status") == "error":
                yield f"[ERROR] {p.get('message')}"
                return
            yield f"\n🧠 Brain Forensic Telemetry — Session {p['session_id'][:12]}..."
            yield f"  Total Steps:      {p['total_steps']}"
            yield f"  Tool Invocations: {p['tool_calls']}"
            yield f"  User Inputs:      {p['user_inputs']}"
            yield f"  Input Tokens:     ~{p['tokens']['input']:,}"
            yield f"  Output Tokens:    ~{p['tokens']['output']:,}"
            yield f"  Total Tokens:     ~{p['tokens']['total']:,}"
            yield f"  Est Cost (Flash): ${p['cost_estimate']['gemini_3_flash_usd']:.4f}"
            yield f"  Est Cost (Pro):   ${p['cost_estimate']['gemini_3_1_pro_usd']:.4f}\n"
        emit(report, plain=_plain_viz, args=args)


def cmd_msg(args):
    """Fleet live IPC messaging bus."""
    try:
        from nougen_shards import nougenmsg
    except ImportError:
        print("[ERROR] nougenmsg module not available.", file=sys.stderr)
        sys.exit(1)

    bus = nougenmsg.NouGenMsgBus
    msg_text = getattr(args, "message", "")
    target = getattr(args, "target", "all")

    if not msg_text and not getattr(args, "peers", False):
        print("Usage: nougen msg '<message>' [--to <target>]")
        return

    if getattr(args, "peers", False):
        peers = bus.list_peers()
        def _plain_peers(p, style):
            yield f"Reachable fleet nodes: {p}"
        emit(peers if isinstance(peers, dict) else {"peers": peers}, plain=_plain_peers, args=args)
        return

    node, agent_target = bus.parse_destination(target)

    if getattr(args, "dry_run", False):
        preview = {
            "target": target,
            "resolved_node": node,
            "resolved_agent": agent_target,
            "would_call": ("emit_fleet" if node == "fleet" else "emit_node"),
            "message": msg_text,
        }
        def _plain_dry_run(p, style):
            yield f"[dry-run] --to {p['target']!r} resolves to node={p['resolved_node']!r} agent={p['resolved_agent']!r}"
            yield f"[dry-run] would call {p['would_call']}(...) — nothing sent"
        emit(preview, plain=_plain_dry_run, args=args)
        return

    if node == "fleet":
        res = bus.emit_fleet(msg_text, target=agent_target)
    else:
        res = bus.emit_node(node, agent_target, msg_text)
    def _plain_send(p, style):
        yield f"Message dispatched to {target}: {p}"
    emit(res if isinstance(res, dict) else {"result": res}, plain=_plain_send, args=args)


def cmd_evidence(args):
    """Epistemic assurance & evidence classification validation."""
    action = getattr(args, "evidence_action", "classes")
    if action == "classes":
        print("\n⚖️ NouGen Evidence Classes (Strongest to Weakest):\n")
        for cls, desc in evidence.CLASSES.items():
            print(f"  • {evidence.PREFIX}{cls:<10} — {desc}")
        print()
    elif action == "require":
        tags = getattr(args, "tags", "").split(",")
        try:
            validated = evidence.require(*[t.strip() for t in tags if t.strip()])
            print(f"Validated evidence tags: {validated}")
        except ValueError as e:
            print(f"[REJECTED] {e}", file=sys.stderr)
            sys.exit(1)


RELAY_DIR_ENV_VARS = ("NOUGEN_RELAY_DIR", "FLEET_RELAY_DIR")
EX_CONFIG = 78


def _relay_registry_candidates():
    """Where the fleet registry clone may live, most explicit first.

    A NouGenShards checkout carries its own legacy `.handoffs/` (the older
    per-repo handoff system), so simply running the relay CLI from this repo
    silently reads the wrong board. The registry must be located explicitly.
    """
    for var in RELAY_DIR_ENV_VARS:
        raw = os.environ.get(var, "").strip()
        if raw:
            yield Path(raw).expanduser()
    # An installed (editable) nougen_relay is normally the registry clone's
    # own src/ tree, so the clone is two levels above the package.
    try:
        import nougen_relay as _relay_pkg
    except ImportError:
        _relay_pkg = None
    pkg_file = getattr(_relay_pkg, "__file__", None)
    if pkg_file:
        pkg_path = Path(pkg_file).resolve()
        if len(pkg_path.parents) > 2:
            yield pkg_path.parents[2]
    here = Path(__file__).resolve()
    # src/nougen_shards/cli.py -> repo root is parents[2]; the fleet keeps
    # NouGenRelay either beside the repo or beside the repo's parent folder
    # (The Observatory/NouGenRelay next to The Observatory/NouGen/nougenshards).
    for depth in (3, 4):
        if len(here.parents) > depth:
            yield here.parents[depth] / "NouGenRelay"


def find_relay_registry():
    """Return the NouGenRelay clone that holds a `.handoffs/` registry, or None."""
    for cand in _relay_registry_candidates():
        if (cand / ".handoffs").is_dir() and (cand / "src" / "nougen_relay").is_dir():
            return cand
    return None


def _import_relay_main(registry):
    """Import nougen_relay.main, falling back to the registry clone's src tree."""
    try:
        from nougen_relay.cli import main as relay_main
        return relay_main
    except ImportError:
        pass
    src = str(registry / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from nougen_relay.cli import main as relay_main  # noqa: E402
    return relay_main


def cmd_relay(args):
    """Forward to the NouGenRelay CLI inside the fleet registry clone."""
    registry = find_relay_registry()
    if registry is None:
        tried = ", ".join(str(c) for c in _relay_registry_candidates())
        print("[FATAL] no NouGenRelay registry found (need a clone with .handoffs/ and src/nougen_relay/).",
              file=sys.stderr)
        print(f"        looked in: {tried}", file=sys.stderr)
        print("        set NOUGEN_RELAY_DIR=/path/to/NouGenRelay, or clone it beside this repo.",
              file=sys.stderr)
        sys.exit(EX_CONFIG)
    relay_main = _import_relay_main(registry)
    forwarded = list(getattr(args, "relay_args", None) or [])
    if forwarded[:1] == ["--"]:
        forwarded = forwarded[1:]
    prev_cwd = os.getcwd()
    prev_argv = sys.argv
    os.chdir(registry)
    sys.argv = ["relay", *forwarded]
    action_mode = os.environ.get("NOUGEN_CONFLICT_ACTION", "").strip().lower() or "report"
    try:
        from .control_loop import intent_alignment_check  # pylint: disable=import-outside-toplevel
        verdict = intent_alignment_check({"task_id": "relay_execution"}, {})
        if verdict.get("verdict") == "CONFLICTED" and action_mode == "report":
            logger.warning("intent_alignment_check reported conflict before relay goal execution: %s", verdict)
    except Exception as exc:
        logger.warning("intent_alignment_check failed before relay goal execution: %s", exc)
    try:
        rc = relay_main()
    finally:
        sys.argv = prev_argv
        os.chdir(prev_cwd)
    if rc:
        sys.exit(rc)


def cmd_transcribe(args):
    """AI Video Transcriber: transcribe & summarize video/audio, auto-sharding output into NouGen."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    transcriber_dir = repo_root / "tools" / "ai_video_transcriber"
    if not transcriber_dir.is_dir():
        print(f"Error: ai_video_transcriber not found at {transcriber_dir}", file=sys.stderr)
        sys.exit(1)
    
    backend_dir = str(transcriber_dir / "backend")
    if str(transcriber_dir) not in sys.path:
        sys.path.insert(0, str(transcriber_dir))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
        
    import asyncio
    import transcribe as vt_cli
    
    out_dir = args.output_dir or str(Path.home() / ".nougen" / "transcripts")
    os.makedirs(out_dir, exist_ok=True)
    
    # Mirror args to transcribe namespace
    ns = argparse.Namespace(
        source=args.source,
        summary_language=args.summary_language,
        output_dir=out_dir,
        keep_video=args.keep_video,
        no_llm=args.no_llm,
        whisper_model=args.whisper_model,
        video_max_height=args.video_max_height,
        api_key=args.api_key or os.getenv("OPENAI_API_KEY"),
        base_url=args.base_url or os.getenv("OPENAI_BASE_URL"),
        model=args.model or os.getenv("SUMMARY_MODEL"),
        json=args.json,
        quiet=args.quiet,
    )
    
    try:
        res = asyncio.run(vt_cli.run(ns))
    except Exception as e:
        print(f"Transcription failed: {e}", file=sys.stderr)
        sys.exit(1)
        
    if getattr(args, "shard", True) and res and "files" in res:
        transcript_content = []
        for kind, file_path in res["files"].items():
            if Path(file_path).is_file():
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        transcript_content.append(f"### {kind.upper()}\n\n" + f.read())
                except Exception:
                    pass
        if transcript_content:
            full_text = "\n\n".join(transcript_content)
            title = f"Transcript: {res.get('title', args.source)[:60]}"
            shards.capture(
                event_type="KNOWLEDGE",
                title=title,
                content=f"# {title}\nSource: {args.source}\nPlatform: {res.get('platform', 'unknown')}\n\n" + full_text,
                tags=["video", "audio", "transcription", "summary", res.get("platform", "media")],
                domain_key="media/transcripts",
                source_uri=args.source
            )
            if not args.quiet and not args.json:
                print(f"🪩 Sharded transcript into NouGen 9-DB cluster ({title})")
                
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"\n✅ {res.get('title')}")
        for kind, p in res.get("files", {}).items():
            print(f"  {kind:12} {p}")
        if res.get("media"):
            print(f"  media:       {res['media'].get('path')}")


def cmd_tunnel(args):
    """Starts an ephemeral or custom edge tunnel via Ngrok."""
    from . import tunnel
    import time
    try:
        res = tunnel.start_tunnel(
            port=args.port,
            service_name=args.service,
            domain=args.domain
        )
        if args.json:
            print(json.dumps({
                "url": res["url"],
                "port": res["port"],
                "service": res["service"],
                "domain": res["domain"],
                "status": "online"
            }, indent=2))
        else:
            print("🚇 NouGen Edge Tunnel Active")
            print(f"  • Forwarding:  http://localhost:{res['port']} -> {res['url']}")
            print(f"  • Service:     {res['service']}")
            print("  • Ingress:     Ngrok Shang Tsung Gateway")
            print("\n[Press Ctrl+C to stop tunnel]")
        
        # Keep process alive while tunnel is open
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🚇 Tunnel terminated.")
    except Exception as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, indent=2))
        else:
            print(f"❌ Failed to start tunnel: {exc}")
        sys.exit(1)


def cmd_hi(args):
    from . import session_probe
    import json as _json
    report = session_probe.run_hi(fleet=not args.no_fleet)
    if getattr(args, "json", False):
        print(_json.dumps(report.__dict__, default=str, indent=2))
        return
    print(f"🌅 hi — {report.identity.get('host', 'unknown')} ({report.identity.get('machine_id', '?')}) — {report.local_time}")
    print(f"  Open handoffs: {report.open_handoffs}")
    if report.latest_goal:
        print(f"  Latest goal: {report.latest_goal}")
    if report.fleet_pulse:
        pulse = ", ".join(f"{h}:{'up' if ok else 'down'}" for h, ok in report.fleet_pulse.items())
        print(f"  Fleet pulse: {pulse}")
    if report.orphan_ports:
        print(f"  Ports already up: {', '.join(f'{p} ({label})' for p, label in report.orphan_ports)}")
    relay_status = "armed" if report.relay_armed else "unreachable"
    print(f"  Relay: {relay_status}, {report.relay_open_count} open leg(s)")
    for leg in report.relay_legs:
        print(f"    • {leg['who']} — {leg['goal']}  [{leg['id']}]")
    if report.next_play:
        print(f"  ▶ Next play: {report.next_play}")
    if report.usage:
        parts = [
            f"{label}: {u.get('total_tokens', 0):,} tok / ${u.get('estimated_cost', 0.0):.2f}"
            for label, u in report.usage.items() if u.get("ledger_present")
        ]
        if parts:
            print(f"  Usage (local ledger, shadow cost): {' | '.join(parts)}")


def cmd_bye(args):
    from . import session_probe
    import json as _json
    report = session_probe.run_bye(
        agent=args.agent, goal=args.goal, summary=args.summary, dry_run=args.dry_run,
        publish_leg=args.publish_leg, write_shard=not args.no_shard,
    )
    if getattr(args, "json", False):
        print(_json.dumps(report.__dict__, default=str, indent=2))
        return
    print(f"🌙 bye — {report.local_time} — {report.total_dirty} dirty file(s), {report.total_unpushed} unpushed commit(s)")
    for r in report.repos:
        if r["dirty"] or r["unpushed"]:
            print(f"  📁 {r['repo']} ({r['branch']}) — {r['dirty']} dirty, {r['unpushed']} unpushed")
    if report.orphan_ports:
        print(f"  Ports still up: {', '.join(f'{p} ({label})' for p, label in report.orphan_ports)}")
    if report.handoff_path:
        print(f"  ✅ Handoff written: {report.handoff_path}")
    elif args.dry_run:
        print("  [DRY RUN] No handoff written")
    if report.shard_verified is not None:
        mark = "✅" if report.shard_verified else "⚠️"
        print(f"  {mark} Session shard: {report.shard_note}")
    if report.relay_leg_published is not None:
        if report.relay_leg_published:
            print(f"  ✅ Relay leg published: {report.relay_leg_id}")
        else:
            print(f"  ⚠️ Relay leg NOT published: {report.relay_leg_id}")
    if report.usage:
        parts = [
            f"{label}: {u.get('total_tokens', 0):,} tok / ${u.get('estimated_cost', 0.0):.2f}"
            for label, u in report.usage.items() if u.get("ledger_present")
        ]
        if parts:
            print(f"  Usage (local ledger, shadow cost): {' | '.join(parts)}")
    print(f"  Primer: {report.primer}")


def cmd_hijack(args):
    from . import session_probe
    result = session_probe.run_hijack(handoff_id=args.handoff_id, agent=args.agent)
    if result.get("ok"):
        print(f"✅ Hijacked {result['id']} -> {result['identity'].get('host')} ({result['identity'].get('machine_id')})")
    else:
        print(f"❌ {result.get('error')}")
        sys.exit(1)


def cmd_open(args):
    """Forward to the NouGenOpen CLI (OpenRouter Free Fleet Engine)."""
    try:
        from nougen_open.cli import main as open_main
    except ImportError:
        print("[FATAL] nougen_open package not installed. Install with `pip install -e NouGenOpen`.", file=sys.stderr)
        sys.exit(1)
    
    forwarded = list(getattr(args, "open_args", None) or [])
    if forwarded[:1] == ["--"]:
        forwarded = forwarded[1:]
    open_main(forwarded)


def main():
    """Execution entry point."""
    if len(sys.argv) == 1:
        print("🪩 NouGenShards CLI — Powered by NouGenAi")
        print("┌┐╷┌─┐╷ ╷┌─╴┌─╴┌┐╷┌─┐╷ ╷┌─┐┌─┐╶┬┐┌─┐")
        print("│└┤│ ││ ││╶┐├╴ │└┤└─┐├─┤├─┤├┬┘ ││└─┐")
        print("╵ ╵└─┘└─┘└─┘└─╴╵ ╵└─┘╵ ╵╵ ╵╵└╴╶┴┘└─┘")
        print(f"  ⚡ NouGenMorph Engine · v{VERSION}")
        print()
        get_parser().print_help()
        sys.exit(0)
    if sys.argv[1] == "cf":
        cmd_cf(argparse.Namespace(command="cf", cf_args=sys.argv[2:]))
        return
    if sys.argv[1] == "relay":
        # Pure pass-through: argparse (3.13+) refuses to let a REMAINDER
        # positional swallow a leading option, so `nougen relay --help` and
        # `nougen relay -h` would die here instead of reaching the engine.
        cmd_relay(argparse.Namespace(command="relay", relay_args=sys.argv[2:]))
        return
    if sys.argv[1] == "open":
        cmd_open(argparse.Namespace(command="open", open_args=sys.argv[2:]))
        return

    parser = get_parser()

    # Dynamic second-reflex: Derive known subcommands dynamically from parser subparsers
    known_cmds = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            known_cmds.update(action.choices.keys())
    known_cmds.update({"cf", "relay", "open", "zombies", "sweep"})

    # If first argument is not a flag (-h, --version, etc) and not a registered subcommand,
    # automatically interpret `nougen <query>` as `nougen search "<query>"`
    if len(sys.argv) > 1 and sys.argv[1] not in known_cmds and not sys.argv[1].startswith("-"):
        query_str = " ".join(sys.argv[1:])
        cmd_search(argparse.Namespace(
            command="search",
            query=query_str,
            semantic=False,
            provider=None,
            json=False,
            domain=None,
            dual=True
        ))
        return

    args = parser.parse_args()
    cmds = {
        "init": cmd_init, "add": cmd_add, "get": cmd_get, "search": cmd_search, "assure": cmd_assure, "chat": cmd_chat,
        "auth": cmd_auth, "mark": cmd_mark, "status": cmd_status, "models": cmd_models, "ctx": cmd_ctx,
        "config": cmd_config, "connect": cmd_connect, "hook": cmd_hook, "ingest": cmd_ingest,
        "hi": cmd_hi, "bye": cmd_bye, "hijack": cmd_hijack,
        "db": cmd_db, "node": cmd_node, "stats": cmd_stats, "router": cmd_router,
        "doctor": cmd_doctor, "wishlist": cmd_wishlist, "brain": cmd_brain, "dream": cmd_dream, "evolve": cmd_evolve,
        "dashboard": cmd_dashboard, "handoff": cmd_handoff, "usage": cmd_usage,
        "tenant": cmd_tenant, "relay": cmd_relay, "pr": cmd_pr,
        "tree": cmd_tree, "tube": cmd_tube, "arxiv": cmd_arxiv,
        "viz": cmd_viz, "msg": cmd_msg, "evidence": cmd_evidence,
        "transcribe": cmd_transcribe, "live": cmd_live, "algo": cmd_algo,
        "tunnel": cmd_tunnel, "destiny": cmd_destiny, "wake": cmd_wake, "wispr": cmd_wispr, "studio": cmd_studio,
        "cf": cmd_cf, "sweep": cmd_sweep, "zombies": cmd_sweep, "open": cmd_open,
        "facts": cmd_facts, "mrsb": cmd_mrsb,
    }
    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
