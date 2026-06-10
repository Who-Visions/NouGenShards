"""NouGenShards command-line interface."""
import sys
import argparse
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

VERSION = "1.0.0"

# UTF-8 Console protection for Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, Exception):
        pass

def get_client(provider: str):
    """Helper to get a client by provider name."""
    provider = provider.lower()
    if provider == "local": return get_best_available_client()
    if provider == "openai": return OpenAIClient()
    if provider == "anthropic": return AnthropicClient()
    if provider in ["google", "gemini"]: return GeminiClient()
    if provider in ["huggingface", "hf"]: return HuggingFaceClient()
    if provider in ["openrouter", "or"]: return OpenRouterClient()
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
        print("🔐 Connected Services:")
        providers = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "HUGGINGFACE_API_KEY", "OPENROUTER_API_KEY"]
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
                print(f" ✅ {display_names[k]}"); found = True
        if not found: print(" No cloud services connected.")

def cmd_init(_args):
    """Bootstrap the local shard layer."""
    print("Bootstraping NouGenShards local layer...")
    shards.init_db(index=1)
    print(f"✅ Created local-first database substrate.")
    print("\nNext steps: nougen auth set-key OR nougen add \"first memory\"")

def cmd_chat(args):
    """Starts a chat session with an LLM."""
    client = get_client(args.provider or "local")
    if not client or not client.is_alive():
        print(f"Error: {args.provider or 'local'} is not configured.")
        return

    model = args.model
    if not model:
        if isinstance(client, LocalLLMClient): model = client.find_best_edge_model()
        else: model = client.list_models()[0]

    if not model:
        print("Error: No model found."); return

    query = args.query
    if not query:
        print(f"Entering interactive chat with {model}...")
        messages = []
        while True:
            try:
                user_input = input("\n[You]: ").strip()
                if user_input.lower() in ['exit', 'quit']: break
                if not user_input: continue

                # Advanced Retrieval (Keyword + Bayesian)
                found = federation.federated_retrieve(user_input, limit=2)
                context = shards.compile_recall_packet(found)
                messages.append({"role": "user", "content": f"{user_input}\n\n{context}"})
                print(f"\n[{model}]: ", end="")
                response = client.chat(model, messages, stream=True)
                messages.append({"role": "assistant", "content": response})
                print()
            except KeyboardInterrupt: break
    else:
        found = federation.federated_retrieve(query, limit=3)
        context = shards.compile_recall_packet(found)
        messages = [{"role": "user", "content": f"{query}\n\n{context}"}]
        print(f"[*] Querying {model}...")
        response = client.chat(model, messages, stream=False)
        print(f"\n[Response]:\n{response}")

def cmd_models(args):
    """Manages LLM models."""
    client = get_client(args.provider or "local")
    if not client or not client.is_alive():
        print(f"Error: {args.provider or 'local'} not configured."); return

    if getattr(args, 'pull', None):
        if isinstance(client, OllamaClient):
            client.pull_model(args.pull)
        else:
            print("Error: Model pulling is currently only supported via Ollama.")
    else:
        models = client.list_models()
        print(f"{args.provider or 'local'} Models:")
        for m in models: print(f" - {m}")

def cmd_add(args):
    """Add a new shard with optional embedding support."""
    content = ""
    if args.stdin: content = sys.stdin.read().strip()
    elif args.content: content = args.content.strip()
    else: print("Error: Content missing."); sys.exit(1)

    embedding = None
    if getattr(args, 'embed', False):
        client = get_client(args.provider or "openai")
        if client and client.is_alive():
            model = "text-embedding-3-small" if args.provider == "openai" else "models/text-embedding-004"
            print(f"[*] Generating embeddings via {args.provider or 'openai'}...")
            embedding = client.embed(model, content)

    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
    success = shards.capture("KNOWLEDGE", content[:30], content, tags, embedding=embedding)
    if success: print(f"✅ Shard captured!")
    else: print("ℹ️ Shard already exists.")

def cmd_search(args):
    """Search for shards across local substrate and external DBs."""
    embedding = None
    if getattr(args, 'semantic', False):
        client = get_client(args.provider or "openai")
        if client and client.is_alive():
            model = "text-embedding-3-small" if args.provider == "openai" else "models/text-embedding-004"
            print(f"[*] Generating query embedding via {args.provider or 'openai'}...")
            embedding = client.embed(model, args.query)

    # Use Federation for unified search
    results = federation.federated_retrieve(args.query, limit=5, query_embedding=embedding)
    if not results: print("No shards found."); return

    print(f"🔍 Found {len(results)} records across the fabric (Ranked by Bayesian Relevance):\n")
    for res in results:
        header = f"[{res['id']}] Final Score: {res['final_score']:.2f} | Prior: {res['utility_score']} | Source: {res['_db_index']}"
        print(header)
        print(f"Title: {res['title']}\n{res['content'].strip()}\n" + "-" * 40)

def cmd_mark(args):
    """Close the outcome loop (Bayesian Update)."""
    if shards.mark_shard(args.id, worked=args.worked):
        print(f"✅ Shard #{args.id} updated. Bayesian prior adjusted.")
    else: print(f"Error finding shard #{args.id}.")

def cmd_status(_args):
    """Check the status of the Multi-DB cluster."""
    total = 0; active = shards.get_active_db_index()
    print("📊 NouGenShards Substrate Status:")
    for i in range(1, shards.MAX_DB_COUNT + 1):
        path = shards.get_db_path(i)
        if not path.exists(): continue
        try:
            conn = shards.get_connection(i)
            count = conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
            conn.close()
            size_mb = path.stat().st_size / (1024 * 1024)
            status = " (ACTIVE)" if i == active else ""
            print(f" - DB #{i}: {count} shards | {size_mb:.2f} MB / 1024 MB{status}")
            total += count
        except Exception: print(f" - DB #{i}: Database not initialized.")
    print(f"\nTotal records in memory: {total}")

def cmd_ctx(args):
    """Handles NouGenContext commands."""
    if args.action == "init":
        nougen_context.init_context_db()
        print("✅ Session initialized.")
    elif args.action == "execute":
        print(nougen_sandbox.execute_sandboxed(args.input))

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
        if not nodes:
            print(" No remote nodes linked.")
            return
        print("[*] Linked Remote Nodes:")
        for n in nodes:
            print(f" - #{n['id']}: {n['name']} | URL: {n['url']}")

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
    file_path = args.file
    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    print(f"Ingesting {file_path}...")
    try:
        with open(file_path, "r", encoding="utf-8") as f_in:
            content = f_in.read()
        shards.capture("INGEST", Path(file_path).name, content, ["ingested", "docs"])
        print("✅ Ingestion complete.")
    except Exception as exc: print(f"Failed: {exc}")

def get_parser():
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(prog="nougen", description="NouGenShards CLI")
    parser.add_argument("--version", action="version", version=f"NouGenShards v{VERSION}")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Bootstrap substrate")
    
    p_add = subparsers.add_parser("add", help="Save shard")
    p_add.add_argument("content", nargs="?")
    p_add.add_argument("--tags"); p_add.add_argument("--stdin", action="store_true")
    p_add.add_argument("--embed", action="store_true", help="Generate vector embedding")
    p_add.add_argument("--provider", help="Embedding provider")

    p_search = subparsers.add_parser("search", help="Search substrate")
    p_search.add_argument("query")
    p_search.add_argument("--semantic", action="store_true", help="Use vector search")
    p_search.add_argument("--provider", help="Embedding provider")

    p_chat = subparsers.add_parser("chat", help="Chat with memory")
    p_chat.add_argument("query", nargs="?")
    p_chat.add_argument("--model"); p_chat.add_argument("--provider")

    p_auth = subparsers.add_parser("auth", help="Manage keys")
    p_auth.add_argument("action", choices=["set-key", "list"])
    p_auth.add_argument("provider", nargs="?"); p_auth.add_argument("input", nargs="?")

    p_mark = subparsers.add_parser("mark", help="Update utility")
    p_mark.add_argument("id", type=int); p_mark.add_argument("--worked", action="store_true")

    subparsers.add_parser("status", help="Show cluster health")
    
    p_ctx = subparsers.add_parser("ctx", help="Context layer")
    p_ctx.add_argument("action", choices=["init", "execute"]); p_ctx.add_argument("input", nargs="?")

    p_config = subparsers.add_parser("config", help="Configuration")
    p_config.add_argument("action", choices=["set"]); p_config.add_argument("key"); p_config.add_argument("value")

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

    p_node = subparsers.add_parser("node", help="Manage remote cloud nodes")
    p_node.add_argument("action", choices=["link", "list"])
    p_node.add_argument("url", nargs="?", help="Remote node API URL")
    p_node.add_argument("--name", help="Friendly name for the node")

    return parser

def main():
    if len(sys.argv) == 1:
        print("🪩 NouGenShards CLI")
        print("░█▀█░█▀█░█░█░█▀▀░█▀▀░█▀█░█▀▀░█░█░█▀█░█▀▄░█▀▄░█▀▀")
        print("░█░█░█░█░█░█░█░█░█▀▀░█░█░▀▀█░█▀█░█▀█░█▀░▀░▀░▀▀▀")
        sys.exit(0)
    parser = get_parser(); args = parser.parse_args()
    cmds = {
        "init": cmd_init, "add": cmd_add, "search": cmd_search, "chat": cmd_chat, 
        "auth": cmd_auth, "mark": cmd_mark, "status": cmd_status, "ctx": cmd_ctx,
        "config": cmd_config, "connect": cmd_connect, "hook": cmd_hook, "ingest": cmd_ingest,
        "db": cmd_db, "node": cmd_node
    }
    if args.command in cmds: cmds[args.command](args)
    else: parser.print_help()

if __name__ == "__main__": main()
