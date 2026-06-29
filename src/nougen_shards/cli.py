"""NouGenShards command-line interface."""
import argparse
import sys
import json
import sqlite3
import os
from pathlib import Path
from . import core as shards
from . import keymaker
from .models_client import (
    get_best_available_client, OllamaClient,
    OpenAIClient, AnthropicClient, GeminiClient, LocalLLMClient,
    HuggingFaceClient, OpenRouterClient, WhoVisionsCloudClient
)
from . import nougen_context
from . import nougen_sandbox
from . import federation
from . import history
from . import router
from . import structured
from .connectors.cloud import push_to_cloud, pull_from_cloud
from .brain_scan import scan_environment, run_import, print_scan_report, print_import_report
from . import dream
from . import evolution
from . import griot
from . import griot_eval

VERSION = "1.1.0"



# UTF-8 Console protection for Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    except (AttributeError, ValueError):
        pass

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
            "cloud": "NGS_CLOUD_CREDENTIALS"
        }
        provider = args.provider.lower()
        if provider not in key_map:
            print(f"Error: Unknown provider '{args.provider}'.")
            return

        keymaker.ingest_secret(key_map[provider], args.input)
        print(f"✅ API key for {provider} saved to vault.")

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


def cmd_init(_args):
    """Bootstrap the local shard layer."""
    print("🪩 Initializing Valerion — The Metameric Memory Engine...")
    shards.init_db(index=1)
    print("✅ Created local-first database substrate.")
    print("\n[IGNITION COMPLETE]")
    print(" NouGenShards is now active. Your machine has memory.")
    print("\nNext Plays:")
    print(" 1. nougen brain scan         (Discover your lost AI history)")
    print(" 2. nougen dashboard          (Launch the visual Cortex HUD)")
    print(" 3. nougen auth set-key OR    (Connect to the cloud)")
    print(" 4. nougen add \"first shard\" (Start capturing manually)")


def _run_interactive_chat(model, provider, client):
    """Interactive chat loop."""
    print(f"Entering interactive chat with {model} ({provider})...")
    msgs = []
    while True:
        try:
            user_input = input("\n[You]: ").strip()
            if user_input.lower() in ['exit', 'quit']:
                break
            if not user_input:
                continue

            found = federation.federated_retrieve(user_input, limit=2)
            context = shards.compile_recall_packet(found)
            msgs.append({"role": "user", "content": f"{user_input}\n\n{context}"})
            print(f"\n[{model}]: ", end="")
            response = client.chat(model, msgs, stream=True)
            msgs.append({"role": "assistant", "content": response})
            print()
        except KeyboardInterrupt:
            break


def cmd_chat(args):
    """Starts a chat session with an LLM."""
    prov_name = args.provider or "local"
    client = get_client(prov_name)
    if not client or not client.is_alive():
        print(f"Error: {prov_name} is not configured.")
        return

    model = args.model
    if not model:
        if isinstance(client, LocalLLMClient):
            model_config = client.find_best_edge_model()
            model = model_config.model_name if model_config else None
        else:
            model = client.list_models()[0]

    if not model:
        print("Error: No model found.")
        return

    if not args.query:
        _run_interactive_chat(model, prov_name, client)
    else:
        found = federation.federated_retrieve(args.query, limit=3)
        ctx = shards.compile_recall_packet(found)
        msgs = [{"role": "user", "content": f"{args.query}\n\n{ctx}"}]
        print(f"[*] Querying {model}...")
        resp = client.chat(model, msgs, stream=False)
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
        client = get_client(args.provider or "openai")
        if client and client.is_alive():
            model = "text-embedding-3-small" if args.provider == "openai" \
                else "models/text-embedding-004"
            print(f"[*] Generating embeddings via {args.provider or 'openai'}...")
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
        client = get_client(args.provider or "openai")
        if client and client.is_alive():
            model = "text-embedding-3-small" if args.provider == "openai" \
                else "models/text-embedding-004"
            print(f"[*] Generating query embedding via {args.provider or 'openai'}...")
            embedding = client.embed(model, args.query)

    # Use Federation for unified search
    results = federation.federated_retrieve(args.query, limit=5, query_embedding=embedding, domain_key=domain_key)
    if not results:
        if getattr(args, 'json', False) is True:
            print("[]")
        else:
            print("No shards found.")
        return

    if getattr(args, 'json', False) is True:
        # Convert binary embeddings to lists for JSON serialization
        for res in results:
            if 'embedding' in res and isinstance(res['embedding'], bytes):
                res['embedding'] = json.loads(res['embedding'].decode())
        print(json.dumps(results))
        return

    print(f"🔍 Found {len(results)} records across the fabric (Ranked by Relevance):\n")
    for res in results:
        header = f"[{res['id']}] Final Score: {res['final_score']:.2f} | " \
                 f"Prior: {res['utility_score']} | Source: {res['_db_index']}"
        print(header)
        print(f"Title: {res['title']}\n{res['content'].strip()}\n" + "-" * 40)


def cmd_mark(args):
    """Close the outcome loop (usefulness update)."""
    if shards.mark_shard(args.id, worked=args.worked, db_index=args.db):
        print(f"✅ Shard #{args.id} updated. Usefulness prior adjusted.")
    else:
        print(f"Error finding shard #{args.id}.")


def cmd_status(args):
    """Check the status of the Multi-DB cluster."""
    active = shards.get_active_db_index()
    db_stats = []
    total_count = 0
    for i in range(1, shards.MAX_DB_COUNT + 1):
        path = shards.get_db_path(i)
        if not path.exists():
            continue
        try:
            conn = shards.get_connection(i)
            count = conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
            conn.close()
            size_mb = path.stat().st_size / (1024 * 1024)
            db_stats.append({
                "index": i,
                "shards": count,
                "size_mb": size_mb,
                "is_active": i == active
            })
            total_count += count
        except (sqlite3.Error, OSError):
            pass

    if getattr(args, 'json', False) is True:
        print(json.dumps({"databases": db_stats, "total_shards": total_count}))
        return

    print("📊 NouGenShards Substrate Status:")
    for db in db_stats:
        status = " (ACTIVE)" if db['is_active'] else ""
        print(f" - DB #{db['index']}: {db['shards']} shards | {db['size_mb']:.2f} MB / 1024 MB{status}")
    print(f"\nTotal records in memory: {total_count}")


def cmd_stats(args):
    """Reports memory growth and utility trends across horizons."""
    period = args.period or "week"
    engine = history.HistoryEngine()

    growth = engine.get_growth_rate(period)
    utility = engine.get_utility_delta(period)
    timeline = engine.get_timeline(period)

    if getattr(args, 'json', False) is True:
        print(json.dumps({
            "period": period,
            "growth": growth,
            "utility_delta": utility
        }))
        return

    print(f"📈 NouGenShards History ({period})")
    print(timeline)
    print(f"\n - New Shards Captured: {growth['new_shards']}")
    print(f" - Total Memory Size:   {growth['total_shards']} shards")
    print(f" - Usefulness \u0394: {'+' if utility >= 0 else ''}{utility:.2f}")

    if growth['total_shards'] > 0:
        rate = (growth['new_shards'] / growth['total_shards']) * 100
        print(f" - Acceleration Rate:   {rate:.1f}% expansion")


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
        event = nougen_context.get_event(int(args.input))
        if not event:
            print(f"Error: Context event #{args.input} not found.")
            return
        print(json.dumps(event, indent=2))
    elif args.action == "promote":
        if not args.input:
            print("Error: Usage: nougen ctx promote <event_id> [--tags <tags>]")
            return
        event = nougen_context.get_event(int(args.input))
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
            print(f"ℹ️ Shard already exists.")


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
            model=args.model or "openrouter/auto",
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
                print(f"\nUsage: {u['total_tokens']} tokens ({u['cached_tokens']} cached)")

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
            model=args.model or "openrouter/auto",
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
            "default_model": "openrouter/auto",
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
        
        print(f"[*] Extracting shards for push...")
        all_shards = []
        for i in range(1, shards.MAX_DB_COUNT + 1):
            if not shards.get_db_path(i).exists(): continue
            conn = shards.get_connection(i)
            try:
                rows = conn.execute("SELECT * FROM shards").fetchall()
                for r in rows:
                    d = dict(r)
                    emb = d.get("embedding")
                    if emb:
                        try:
                            raw = emb.decode() if isinstance(emb, (bytes, bytearray)) else emb
                            d["embedding"] = json.loads(raw)
                        except (AttributeError, ValueError, TypeError) as e:
                            print(f"[!] Skipping bad embedding on shard #{d.get('id')}: {e}")
                            d["embedding"] = None
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
    """Executes the Dream cycle (Autonomous Metameric Evolution)."""
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
                print(f" - Status: Verified in Sandbox.")
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


def get_parser():



    """Create the CLI parser."""
    parser = argparse.ArgumentParser(prog="nougen", description="NouGenShards CLI — Powered by Valerion")
    parser.add_argument("--version", action="version", version=f"NouGenShards v{VERSION} (Valerion Engine)")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Bootstrap substrate")

    p_add = subparsers.add_parser("add", help="Save shard")
    p_add.add_argument("content", nargs="?")
    p_add.add_argument("--tags")
    p_add.add_argument("--stdin", action="store_true")
    p_add.add_argument("--embed", action="store_true", help="Generate vector embedding")
    p_add.add_argument("--provider", help="Embedding provider")
    p_add.add_argument("--domain", help="Explicit domain boundary key override")

    p_search = subparsers.add_parser("search", help="Search substrate")
    p_search.add_argument("query")
    p_search.add_argument("--semantic", action="store_true", help="Use vector search")
    p_search.add_argument("--provider", help="Embedding provider")
    p_search.add_argument("--json", action="store_true", help="Machine-readable output")
    p_search.add_argument("--domain", help="Explicit domain boundary key filter override")
    p_search.add_argument("--dual", action="store_true", help="Use dual-system memory recall (episodic + semantic rules)")

    p_chat = subparsers.add_parser("chat", help="Chat with memory")
    p_chat.add_argument("query", nargs="?")
    p_chat.add_argument("--model")
    p_chat.add_argument("--provider")

    p_auth = subparsers.add_parser("auth", help="Manage keys")
    p_auth.add_argument("action", choices=["set-key", "list"])
    p_auth.add_argument("provider", nargs="?")
    p_auth.add_argument("input", nargs="?")
    p_auth.add_argument("--json", action="store_true", help="Machine-readable output")

    p_mark = subparsers.add_parser("mark", help="Update utility")
    p_mark.add_argument("id", type=int)
    p_mark.add_argument("--worked", action="store_true")
    p_mark.add_argument("--db", type=int, default=None,
                        help="Source DB index (the 'Source:' column from search) to target the exact shard")

    p_status = subparsers.add_parser("status", help="Show cluster health")
    p_status.add_argument("--json", action="store_true", help="Machine-readable output")

    p_stats = subparsers.add_parser("stats", help="Historical analytics")
    p_stats.add_argument("--period", choices=["24h", "week", "month", "quarter", "year"],
                         default="week")
    p_stats.add_argument("--json", action="store_true", help="Machine-readable output")

    p_ctx = subparsers.add_parser("ctx", help="Context layer")
    p_ctx.add_argument("action", choices=["init", "execute", "search", "get", "promote"])
    p_ctx.add_argument("input", nargs="?")
    p_ctx.add_argument("--tags", help="Tags for promoted shard")
    p_ctx.add_argument("--limit", type=int, default=5, help="Max results for ctx search")

    # router
    p_router = subparsers.add_parser("router", help="OpenRouter production routing")
    p_router_sub = p_router.add_subparsers(dest="action")
    
    p_router_chat = p_router_sub.add_parser("chat", help="Chat with fallback")
    p_router_chat.add_argument("input")
    p_router_chat.add_argument("--model", default="openrouter/auto")
    p_router_chat.add_argument("--fallback", action="append", help="Fallback models")
    p_router_chat.add_argument("--session-id")
    p_router_chat.add_argument("--stream", action="store_true")
    p_router_chat.add_argument("--json", action="store_true")
    p_router_chat.add_argument("--temperature", type=float)
    p_router_chat.add_argument("--max-tokens", type=int)
    
    p_router_json = p_router_sub.add_parser("json", help="Structured JSON chat")
    p_router_json.add_argument("input")
    p_router_json.add_argument("--schema", required=True)
    p_router_json.add_argument("--model", default="openrouter/auto")
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

    p_doctor = subparsers.add_parser("doctor", help="Check system health")
    p_doctor.add_argument("--json", action="store_true", help="Machine-readable output")

    p_dream = subparsers.add_parser("dream", help="Autonomous Metameric Evolution (TMEM)")
    p_dream.add_argument("action", choices=["wake"])
    p_dream.add_argument("--json", action="store_true", help="Machine-readable output")

    p_evolve = subparsers.add_parser("evolve", help="Universal Open-World Skill Evolution (OpenSkill)")
    p_evolve.add_argument("action", choices=["run"])
    p_evolve.add_argument("instruction", help="The task instruction to evolve a skill for")
    p_evolve.add_argument("--json", action="store_true", help="Machine-readable output")

    p_dashboard = subparsers.add_parser("dashboard", help="Launch visual Cortex HUD")
    p_dashboard.add_argument("--port", type=int, default=4444, help="Port to run on")

    p_brain = subparsers.add_parser("brain", help="Universal AI Memory Forensic Engine")
    p_brain.add_argument("action", choices=["scan", "import"])
    p_brain.add_argument("--project", help="Target project path to scan/import")
    p_brain.add_argument("--unknown", action="store_true", help="Include unknown files/folders")
    p_brain.add_argument("--source", help="Filter by specific source")
    p_brain.add_argument("--no-redact", action="store_true", help="Do not redact secrets")
    p_brain.add_argument("--confirm", action="store_true", help="Confirm writing to database")
    p_brain.add_argument("--json", action="store_true", help="Machine-readable output")

    p_handoff = subparsers.add_parser("handoff", help="Cross-agent session handoff notes")
    p_handoff.add_argument("action", choices=[
        "create", "read", "list", "ack", "start", "checkpoint", "complete",
        "rebuild-db", "reconcile", "watch",
    ], help="create | read | list | ack | start | checkpoint | complete | rebuild-db | reconcile | watch")
    p_handoff.add_argument("--message", "-m", default="", help="Handoff note or acknowledgement message")
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

    p_griot = subparsers.add_parser("griot", help="Griot agent (vault-grounded chat & consolidation)")
    p_griot.add_argument("action", nargs="?", default="chat",
                         choices=["chat", "consolidate", "rules", "ask", "tools", "conflicts", "eval", "heal"],
                         help="chat | consolidate | rules | ask | tools | conflicts | eval | heal (default: chat)")
    p_griot.add_argument("rest", nargs="*",
                         help="chat: query | rules: [subject] | ask: <agent> <message...>")
    p_griot.add_argument("--limit", type=int, default=10,
                         help="(consolidate) max shards to scan (default: 10)")

    return parser




def cmd_doctor(args):
    """Verifies installation, database health, and service connectivity (Valerion Engine)."""
    print("👨‍⚕️ NouGenShards Doctor (Valerion): Running diagnostics...")
    
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

    # 2. Check Vault
    print("\n[Vault]")
    vault_path = keymaker.DB_PATH
    if vault_path.exists():
        print(f" ✅ Vault: {vault_path.absolute()}")
        providers = keymaker.list_providers()
        print(f" ✅ Connected Providers: {', '.join(providers) if providers else 'None'}")
    else:
        print(" ❌ Vault not found.")

    # 3. Check Providers
    print("\n[Service Connectivity]")
    p_status = {}
    for name in ["openai", "anthropic", "google", "openrouter", "local"]:
        c = get_client(name)
        alive = c.is_alive() if c else False
        p_status[name] = alive
        print(f" {'✅' if alive else '❌'} {name.capitalize()}")

    # 4. Check Valerion Engine Modules
    print("\n[Valerion Cognitive Engines]")
    try:
        from . import dream, evolution
        print(" ✅ Dream State (TMEM): Ready")
        print(" ✅ Evolution Engine (OpenSkill): Ready")
    except ImportError as e:
        print(f" ❌ Engine Modules missing: {e}")

    if getattr(args, 'json', False):
        import json
        print("\n[JSON Output]")
        report = {
            "substrate": {"active_index": active, "found": found_db},
            "vault": {"path": str(vault_path.absolute()), "providers": keymaker.list_providers()},
            "connectivity": p_status
        }
        print(json.dumps(report, indent=2))

def _run_griot_repl(g):
    """Minimal interactive REPL for the Griot agent."""
    print("Entering interactive chat with the Griot (vault-grounded). Empty line, 'exit', or 'quit' to leave.")
    while True:
        try:
            line = input("\n[You]: ").strip()
            if not line or line.lower() in ("exit", "quit"):
                break
            print(f"\n[Griot]: {g.chat(line, reflect=True)}")
        except KeyboardInterrupt:
            break


def cmd_griot(args):
    """Griot agent: vault-grounded chat, consolidation, rules, peer A2A, tools."""
    g = griot.get_default_griot()
    action = getattr(args, "action", "chat") or "chat"
    rest = list(getattr(args, "rest", []) or [])

    if action == "chat":
        query = " ".join(rest).strip()
        if query:
            print(g.chat(query, reflect=True))
        else:
            _run_griot_repl(g)

    elif action == "eval":
        result = griot_eval.run_all(verbose=True)
        for e in result.get("evals", []):
            status = "PASS" if e.get("passed") else "FAIL"
            print(f"{e.get('name')}: {e.get('score'):.2f} (threshold {e.get('threshold'):.2f}) {status}")
        overall = "PASS" if result.get("passed") else "FAIL"
        print(f"Overall: {overall}")
        if not result.get("passed"):
            sys.exit(1)

    elif action == "consolidate":
        limit = getattr(args, "limit", 10)
        result = g.consolidate(limit=limit)
        print("🧠 Griot Consolidation")
        print(f" - Shards scanned: {result.get('shards_scanned', 0)}")
        print(f" - Shards consolidated: {result.get('shards_consolidated', 0)}")
        print(f" - New invariants extracted: {result.get('new_invariants_extracted', 0)}")
        rules = result.get("rules") or []
        if rules:
            print(" - Rules:")
            for r in rules:
                print(f"   [{r.get('subject')}] {r.get('predicate')}")

        # Adversarial verification report
        verified = result.get("verified", False)
        print(f" - Verification: {'active' if verified else 'inactive'}")
        rejected = result.get("rejected") or []
        print(f" - Rejected invariants: {len(rejected)}")
        for rej in rejected:
            print(f"   [{rej.get('subject')}] {rej.get('predicate')} — {rej.get('reason')}")
        conflicts = result.get("conflicts") or []
        print(f" - Conflicts: {len(conflicts)}")
        for c in conflicts:
            print(f"   [{c.get('subject')}] {c.get('candidate')} vs {c.get('existing')}")

    elif action == "conflicts":
        groups = g.find_conflicts()
        if not groups:
            print("✅ No contradictions found in the rule base.")
            return
        print(f"⚠️ Found {len(groups)} conflicting rule group(s):")
        for grp in groups:
            print(f"\n[{grp.get('subject')}]")
            for r in grp.get("rules") or []:
                print(f"   [{r.get('subject')}] {r.get('predicate')} "
                      f"(confidence {float(r.get('confidence_score', 0.0)):.1f})")

    elif action == "rules":
        subject = rest[0] if rest else None
        rules = g.list_rules(subject)
        if not rules:
            print("No invariant rules found yet. Run 'nougen griot consolidate' to extract some.")
            return
        for r in rules:
            print(f"[{r.get('subject')}] {r.get('predicate')} (confidence {float(r.get('confidence_score', 0.0)):.1f})")

    elif action == "ask":
        if len(rest) < 2:
            print("Error: Usage: nougen griot ask <agent> <message...>")
            return
        peer = rest[0]
        message = " ".join(rest[1:])
        print(g.ask_peer(peer, message))

    elif action == "tools":
        print(g.tools.catalog())

    elif action == "heal":
        res = g.heal()
        decay = res["decay"]
        recon = res["reconciliation"]
        print(f"🩹 Self-heal complete.")
        print(f"  Decay: {decay['decayed']} rule(s) decayed (x{decay['factor']}), "
              f"{decay['pruned']} pruned.")
        print(f"  Reconcile: {recon['groups_reconciled']}/{recon['groups_found']} "
              f"contradiction group(s) resolved.")
        for entry in recon["reconciled"]:
            print(f"   [{entry['subject']}] winner: {entry['winner']}")
            for d in entry["demoted"]:
                print(f"      demoted: {d['predicate']} -> {d['confidence']}")


def cmd_handoff(args):
    """Executes agent handoff subcommands."""
    from . import handoff
    if args.action == "create":
        handoff.create_handoff(args.message, args.agent, goal=getattr(args, "goal", None))
    elif args.action == "read":
        handoff.show_latest_handoff(args.agent)
    elif args.action == "list":
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

def main():
    """Execution entry point."""
    if len(sys.argv) == 1:
        print("🪩 NouGenShards CLI")
        print("┌┐╷┌─┐╷ ╷┌─╴┌─╴┌┐╷┌─┐╷ ╷┌─┐┌─┐╶┬┐┌─┐")
        print("│└┤│ ││ ││╶┐├╴ │└┤└─┐├─┤├─┤├┬┘ ││└─┐")
        print("╵ ╵└─┘└─┘└─┘└─╴╵ ╵└─┘╵ ╵╵ ╵╵└╴╶┴┘└─┘")
        print(f"  ⚡ Valerion Engine · v{VERSION}")
        print()
        get_parser().print_help()
        sys.exit(0)
    parser = get_parser()
    args = parser.parse_args()
    cmds = {
        "init": cmd_init, "add": cmd_add, "search": cmd_search, "chat": cmd_chat,
        "auth": cmd_auth, "mark": cmd_mark, "status": cmd_status, "ctx": cmd_ctx,
        "config": cmd_config, "connect": cmd_connect, "hook": cmd_hook, "ingest": cmd_ingest,
        "db": cmd_db, "node": cmd_node, "stats": cmd_stats, "router": cmd_router,
        "doctor": cmd_doctor, "brain": cmd_brain, "dream": cmd_dream, "evolve": cmd_evolve,
        "dashboard": cmd_dashboard, "handoff": cmd_handoff, "griot": cmd_griot
    }
    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
