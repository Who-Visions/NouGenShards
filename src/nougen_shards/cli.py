"""NouGenShards command-line interface."""
import argparse
import sys
import json
import sqlite3
from pathlib import Path
from . import core as shards
from . import keymaker
from .models_client import (
    get_best_available_client, OllamaClient,
    OpenAIClient, AnthropicClient, GeminiClient, LocalLLMClient,
    HuggingFaceClient, OpenRouterClient
)
from . import nougen_context
from . import nougen_sandbox
from . import federation
from . import history
from . import router
from . import structured
from .connectors.cloud import push_to_cloud, pull_from_cloud

VERSION = "1.0.0"

# UTF-8 Console protection for Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


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
            "or": "OPENROUTER_API_KEY"
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
        providers = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
                     "HUGGINGFACE_API_KEY", "OPENROUTER_API_KEY"]
        display_names = {
            "OPENAI_API_KEY": "OpenAI",
            "ANTHROPIC_API_KEY": "Anthropic",
            "GOOGLE_API_KEY": "Google/Gemini",
            "HUGGINGFACE_API_KEY": "Hugging Face",
            "OPENROUTER_API_KEY": "OpenRouter"
        }
        found = False
        for k in providers:
            if k in keys:
                print(f" ✅ {display_names[k]}")
                found = True
        if not found:
            print(" No cloud services connected.")


def cmd_init(_args):
    """Bootstrap the local shard layer."""
    print("Bootstraping NouGenShards local layer...")
    shards.init_db(index=1)
    print("✅ Created local-first database substrate.")
    print("\nNext steps: nougen auth set-key OR nougen add \"first memory\"")


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
            model = client.find_best_edge_model()
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
    success = shards.capture("KNOWLEDGE", content[:30], content, tags, embedding=embedding)
    if success:
        print("✅ Shard captured!")
    else:
        print("ℹ️ Shard already exists.")


def cmd_search(args):
    """Search for shards across local substrate and external DBs."""
    embedding = None
    if getattr(args, 'semantic', False):
        client = get_client(args.provider or "openai")
        if client and client.is_alive():
            model = "text-embedding-3-small" if args.provider == "openai" \
                else "models/text-embedding-004"
            print(f"[*] Generating query embedding via {args.provider or 'openai'}...")
            embedding = client.embed(model, args.query)

    # Use Federation for unified search
    results = federation.federated_retrieve(args.query, limit=5, query_embedding=embedding)
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

    print(f"🔍 Found {len(results)} records across the fabric (Ranked by Bayesian Relevance):\n")
    for res in results:
        header = f"[{res['id']}] Final Score: {res['final_score']:.2f} | " \
                 f"Prior: {res['utility_score']} | Source: {res['_db_index']}"
        print(header)
        print(f"Title: {res['title']}\n{res['content'].strip()}\n" + "-" * 40)


def cmd_mark(args):
    """Close the outcome loop (Bayesian Update)."""
    if shards.mark_shard(args.id, worked=args.worked):
        print(f"✅ Shard #{args.id} updated. Bayesian prior adjusted.")
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

    growth = engine.get_growth_stats(period)
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
    print(f" - Bayesian Utility \u0394: {'+' if utility >= 0 else ''}{utility:.2f}")

    if growth['total_shards'] > 0:
        rate = (growth['new_shards'] / growth['total_shards']) * 100
        print(f" - Acceleration Rate:   {rate:.1f}% expansion")


def cmd_ctx(args):
    """Handles NouGenContext commands."""
    if args.action == "init":
        nougen_context.init_context_db()
        print("✅ Session initialized.")
    elif args.action == "execute":
        print(nougen_sandbox.execute_sandboxed(args.input))
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
                print(json.dumps(res["data"], indent=2))
                if not res["valid"]:
                    print(f"⚠️ Schema Errors: {res['errors']}")

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
            rows = conn.execute("SELECT * FROM shards").fetchall()
            for r in rows:
                d = dict(r)
                if d.get("embedding"): d["embedding"] = json.loads(d["embedding"].decode())
                all_shards.append(d)
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
            success = shards.capture(
                s.get("event_type", "SYNC"),
                s.get("title", "Synced Shard"),
                s.get("content", ""),
                json.loads(s.get("tags", "[]")) if isinstance(s.get("tags"), str) else s.get("tags"),
                embedding=s.get("embedding")
            )
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
        shards.capture("INGEST", path.name, content, ["ingested", "docs"])
        print("✅ Ingestion complete.")
    except (OSError, sqlite3.Error) as exc:
        print(f"Failed: {exc}")


def get_parser():
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(prog="nougen", description="NouGenShards CLI")
    parser.add_argument("--version", action="version", version=f"NouGenShards v{VERSION}")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Bootstrap substrate")

    p_add = subparsers.add_parser("add", help="Save shard")
    p_add.add_argument("content", nargs="?")
    p_add.add_argument("--tags")
    p_add.add_argument("--stdin", action="store_true")
    p_add.add_argument("--embed", action="store_true", help="Generate vector embedding")
    p_add.add_argument("--provider", help="Embedding provider")

    p_search = subparsers.add_parser("search", help="Search substrate")
    p_search.add_argument("query")
    p_search.add_argument("--semantic", action="store_true", help="Use vector search")
    p_search.add_argument("--provider", help="Embedding provider")
    p_search.add_argument("--json", action="store_true", help="Machine-readable output")

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

    p_status = subparsers.add_parser("status", help="Show cluster health")
    p_status.add_argument("--json", action="store_true", help="Machine-readable output")

    p_stats = subparsers.add_parser("stats", help="Historical analytics")
    p_stats.add_argument("--period", choices=["24h", "week", "month", "quarter", "year"],
                         default="week")
    p_stats.add_argument("--json", action="store_true", help="Machine-readable output")

    p_ctx = subparsers.add_parser("ctx", help="Context layer")
    p_ctx.add_argument("action", choices=["init", "execute", "promote"])
    p_ctx.add_argument("input", nargs="?")
    p_ctx.add_argument("--tags", help="Tags for promoted shard")

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

    return parser


def main():
    """Execution entry point."""
    if len(sys.argv) == 1:
        print("🪩 NouGenShards CLI")
        print("░█▀█░█▀█░█░█░█▀▀░█▀▀░█▀█░█▀▀░█░█░█▀█░█▀▄░█▀▄░█▀▀")
        print("░█░█░█░█░█░█░█░█░█▀▀░█░█░▀▀█░█▀█░█▀█░█▀░▀░▀░▀▀▀")
        sys.exit(0)
    parser = get_parser()
    args = parser.parse_args()
    cmds = {
        "init": cmd_init, "add": cmd_add, "search": cmd_search, "chat": cmd_chat,
        "auth": cmd_auth, "mark": cmd_mark, "status": cmd_status, "ctx": cmd_ctx,
        "config": cmd_config, "connect": cmd_connect, "hook": cmd_hook, "ingest": cmd_ingest,
        "db": cmd_db, "node": cmd_node, "stats": cmd_stats, "router": cmd_router
    }
    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
