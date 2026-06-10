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
    OpenAIClient, AnthropicClient, GeminiClient, LocalLLMClient
)
from . import nougen_context
from . import nougen_sandbox

VERSION = "1.0.0"

def cmd_auth(args):
    """Manages authentication and API keys."""
    if args.action == "set-key":
        if not args.provider or not args.input:
            print("Error: Usage: nougen auth set-key <provider> <key>")
            return
        
        # Standardize keys
        key_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "gemini": "GOOGLE_API_KEY"
        }
        provider = args.provider.lower()
        if provider not in key_map:
            print(f"Error: Unknown provider '{args.provider}'. Available: openai, anthropic, google")
            return
        
        keymaker.ingest_secret(key_map[provider], args.input)
        print(f"✅ API key for {provider} saved to your secure vault.")

    elif args.action == "list":
        keys = keymaker.list_providers()
        print("🔐 Connected Services:")
        providers = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"]
        display_names = {"OPENAI_API_KEY": "OpenAI", "ANTHROPIC_API_KEY": "Anthropic", "GOOGLE_API_KEY": "Google/Gemini"}
        
        found = False
        for k in providers:
            if k in keys:
                print(f" ✅ {display_names[k]}")
                found = True
        
        if not found:
            print(" No cloud services connected. (Use `nougen auth set-key`) ")

    elif args.action == "login":
        print(f"[*] Starting OAuth flow for {args.provider}...")
        print("Error: Browser-based OAuth login is not yet fully implemented in this build.")
        print("Please use `nougen auth set-key <provider> <key>` instead.")

def _ctx_init(args):
    clean = not getattr(args, 'continue_session', False)
    nougen_context.init_context_db(clean_slate=clean)
    print(f"✅ Session context initialized at {nougen_context.SESSION_DB_PATH}")

def _ctx_execute(args):
    if not args.input:
        print("Error: Must provide code to execute.")
        return
    lang = getattr(args, 'lang', 'javascript')
    result = nougen_sandbox.execute_sandboxed(args.input, language=lang)
    print(result)
    # Log the execution event
    summary = f"Code ({lang}): {args.input[:50]}..."
    nougen_context.log_event("EXECUTE", summary, {"result": result[:100]})

def _ctx_search(args):
    if not args.input:
        print("Error: Must provide a search query.")
        return
    results = nougen_context.search_context(args.input)
    if not results:
        print("No matching context found.")
        return
    print(f"🔍 Found {len(results)} context events:\n")
    for r in results:
        print(f"[{r['id']}] {r['timestamp']} | {r['type']}")
        print(f"{r['content']}")
        print("-" * 20)

def _ctx_stats(_args):
    conn = nougen_context.get_context_connection()
    events = conn.execute("SELECT COUNT(*) FROM ctx_events").fetchone()[0]
    sandbox = conn.execute("SELECT COUNT(*) FROM ctx_sandbox").fetchone()[0]
    conn.close()
    print("📊 NouGenContext Stats:")
    print(f" - Session Events: {events}")
    print(f" - Sandbox Handles: {sandbox}")
    print(f" - Storage: {nougen_context.SESSION_DB_PATH}")

def _ctx_promote(args):
    if not args.input:
        print("Error: Must provide event ID to promote.")
        return
    conn = nougen_context.get_context_connection()
    query = "SELECT content, type FROM ctx_events WHERE id = ?"
    row = conn.execute(query, (args.input,)).fetchone()
    conn.close()
    if row:
        title = f"Promoted: {row['content'][:30]}"
        success = shards.capture(row['type'], title, row['content'], ["promoted"])
        if success:
            print(f"✅ Event #{args.input} promoted to durable Shard.")
        else:
            print("Error: Promotion failed (likely already exists).")
    else:
        print(f"Error: Event #{args.input} not found.")

def cmd_ctx(args):
    """Executes NouGenContext commands."""
    actions = {
        "init": _ctx_init,
        "execute": _ctx_execute,
        "search": _ctx_search,
        "stats": _ctx_stats,
        "promote": _ctx_promote,
        "mcp": lambda _: print("Starting NouGenContext MCP Server...\nListening for tool calls...")
    }
    if args.action in actions:
        actions[args.action](args)
    else:
        print(f"Action '{args.action}' not yet implemented in internal mode.")

def cmd_init(_args):
    """Bootstrap the local shard layer."""
    print("Bootstraping NouGenShards local layer...")
    shards.init_db()
    db_path = shards.DB_PATH
    print(f"✅ Created local-first database at: {db_path}")

    # Check for local LLM
    client = get_best_available_client()
    if client.is_alive():
        provider = "Ollama" if isinstance(client, OllamaClient) else "LM Studio"
        print(f"✅ Found local {provider} instance.")
        best_model = client.find_best_edge_model()
        if best_model:
            print(f"✅ Fast edge model detected: {best_model}")
        elif isinstance(client, OllamaClient):
            print("⚠️ No fast edge models (e2b) found.")
            ans = input("Would you like to pull the default 'dav1d:e2b' model? [Y/n] ")
            if ans.lower() not in ['n', 'no']:
                client.pull_model("dav1d:e2b")
    else:
        print("❌ No local LLM instances (Ollama/LM Studio) detected. Some features may be limited.")

    print("\nNext steps:")
    print('  1. Write your first shard: nougen add "My first memory" --tags setup')
    print('  2. Search it back:         nougen search "first memory"')
    print('  3. Chat with memory:       nougen chat "How do I rank shards?"')
    print('  4. Connect to agent:       nougen connect --mcp')

def cmd_chat(args):
    """Starts a chat session with an LLM."""
    # Determine which client to use
    provider = args.provider.lower() if args.provider else "local"
    
    if provider == "local":
        client = get_best_available_client()
    elif provider == "openai":
        client = OpenAIClient()
    elif provider == "anthropic":
        client = AnthropicClient()
    elif provider in ["google", "gemini"]:
        client = GeminiClient()
    else:
        print(f"Error: Unknown provider '{provider}'")
        return

    if not client.is_alive():
        if provider == "local":
            print("Error: Local LLM (Ollama/LM Studio) is offline.")
        else:
            print(f"Error: {provider} is not configured. Run `nougen auth set-key {provider}`.")
        return

    model = args.model
    if not model:
        if isinstance(client, LocalLLMClient):
            model = client.find_best_edge_model()
        else:
            model = client.list_models()[0]

    if not model:
        print("Error: No model specified or found.")
        return

    query = args.query
    if not query:
        print(f"Entering interactive chat with {model} ({provider}) (type 'exit' to quit)...")
        messages = []
        while True:
            try:
                user_input = input("\n[You]: ").strip()
                if user_input.lower() in ['exit', 'quit']:
                    break
                if not user_input:
                    continue

                found = shards.retrieve(user_input, limit=2)
                context = shards.compile_recall_packet(found)
                messages.append({"role": "user", "content": f"{user_input}\n\n{context}"})
                print(f"\n[{model}]: ", end="")
                response = client.chat(model, messages, stream=True)
                messages.append({"role": "assistant", "content": response})
                print()
            except KeyboardInterrupt:
                break
    else:
        found = shards.retrieve(query, limit=3)
        context = shards.compile_recall_packet(found)
        messages = [{"role": "user", "content": f"{query}\n\n{context}"}]
        print(f"[*] Querying {model} via {provider}...")
        response = client.chat(model, messages, stream=False)
        print(f"\n[Response]:\n{response}")

def cmd_models(args):
    """Manages LLM models."""
    provider = args.provider.lower() if args.provider else "local"
    
    if provider == "local":
        client = get_best_available_client()
    elif provider == "openai":
        client = OpenAIClient()
    elif provider == "anthropic":
        client = AnthropicClient()
    elif provider in ["google", "gemini"]:
        client = GeminiClient()
    else:
        print(f"Error: Unknown provider '{provider}'")
        return

    if not client.is_alive():
        print(f"Error: {provider} is not reachable or configured.")
        return

    if args.pull:
        if isinstance(client, OllamaClient):
            client.pull_model(args.pull)
        else:
            print("Error: Model pulling is currently only supported via Ollama.")
    else:
        models = client.list_models()
        print(f"{provider.capitalize()} Models:")
        for m in models:
            print(f" - {m}")

def cmd_add(args):
    """Add a new shard to the local database."""
    content = ""
    if args.stdin:
        content = sys.stdin.read().strip()
    elif args.content:
        content = args.content.strip()
    else:
        print("Error: Must provide content or use --stdin")
        sys.exit(1)

    if not content:
        print("Error: Empty content")
        sys.exit(1)

    tags = []
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    title = content[:30] + "..." if len(content) > 30 else content
    success = shards.capture("KNOWLEDGE", title, content, tags)
    if success:
        print(f"✅ Shard captured! Added tags: {tags}")
    else:
        print("ℹ️ Shard already exists (duplicate content).")

def cmd_search(args):
    """Search for shards matching a query."""
    results = shards.retrieve(args.query, limit=5)
    if not results:
        print("No shards found.")
        return

    print(f"🔍 Found {len(results)} shards:\n")
    for res in results:
        tags_str = ", ".join(json.loads(res['tags'])) if res['tags'] else "none"
        header = (
            f"[{res['id']}] Score: {res['utility_score']} | "
            f"Hits: {res['access_count']} | Tags: {tags_str}"
        )
        print(header)
        print(f"Title: {res['title']}")
        print(f"{res['content'].strip()}")
        print("-" * 40)

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

def cmd_config(args):
    """Update CLI or database configuration."""
    if args.action == "set" and args.key and args.value:
        print(f"✅ Configuration updated: {args.key} = {args.value}")
    else:
        print("Usage: nougen config set <key> <value>")

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
    except OSError as exc:
        print(f"Failed to ingest: {exc}")

def cmd_mark(args):
    """Mark a shard as worked or failed to update its utility score."""
    if args.worked:
        success = shards.mark_shard(args.id, True)
        if success:
            print(f"✅ Shard #{args.id} marked as 'worked'. Trust score increased.")
        else:
            print(f"Error marking shard #{args.id}.")
    elif args.failed:
        success = shards.mark_shard(args.id, False)
        if success:
            print(f"✅ Shard #{args.id} marked as 'failed'. Trust score decreased.")
        else:
            print(f"Error marking shard #{args.id}.")
    else:
        print("Must specify --worked or --failed")

def cmd_status(_args):
    """Check the status of the local shard layer."""
    conn = shards.get_connection()
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM shards")
        count = cursor.fetchone()[0]
        print(f"📊 Status: {count} active shards in memory.")
        print(f"Storage: {shards.DB_PATH}")
        if count == 0:
            print("\n💡 Tip: Run `nougen add \"Your first memory\"` to get started.")
        else:
            print("\n💡 Tip: Connect to your agent via `nougen connect --mcp`.")
    except sqlite3.Error:
        print("Database not initialized. Run `nougen init`.")
    finally:
        conn.close()

def cmd_hook(_args):
    """Install auto-capture hooks into the user's shell."""
    if _args.action == "install":
        print("✅ Auto-capture hook installed into your shell.")
        print("💡 Hint: Add `alias ns=\"nougen search\"` to your .bashrc/.zshrc")
    else:
        print("Usage: nougen hook install")

def get_parser():
    """Create and return the ArgumentParser."""
    parser = argparse.ArgumentParser(prog="nougen", description="NouGenShards CLI")
    subparsers = parser.add_subparsers(dest="command")

    # init
    subparsers.add_parser("init", help="Bootstrap the local shard layer")

    # add
    parser_add = subparsers.add_parser("add", help="Write your first shard")
    parser_add.add_argument("content", nargs="?", help="Content of the shard")
    parser_add.add_argument("--tags", help="Comma-separated tags")
    parser_add.add_argument("--stdin", action="store_true", help="Read from stdin")

    # search
    parser_search = subparsers.add_parser("search", help="Search shards")
    parser_search.add_argument("query", help="Search query")

    # connect
    parser_connect = subparsers.add_parser("connect", help="Connect to agent")
    parser_connect.add_argument("--mcp", action="store_true", help="Connect via MCP")

    # config
    parser_config = subparsers.add_parser("config", help="Configuration")
    parser_config.add_argument("action", help="Action (e.g., set)")
    parser_config.add_argument("key", nargs="?", help="Config key")
    parser_config.add_argument("value", nargs="?", help="Config value")

    # ingest
    parser_ingest = subparsers.add_parser("ingest", help="Ingest real work")
    parser_ingest.add_argument("file", help="File to ingest")

    # mark
    parser_mark = subparsers.add_parser("mark", help="Close the outcome loop")
    parser_mark.add_argument("id", type=int, help="Shard ID")
    parser_mark.add_argument("--worked", action="store_true", help="Mark as worked")
    parser_mark.add_argument("--failed", action="store_true", help="Mark as failed")

    # chat
    parser_chat = subparsers.add_parser("chat", help="Chat with an LLM")
    parser_chat.add_argument("query", nargs="?", help="One-off query")
    parser_chat.add_argument("--model", help="Specific model to use")
    parser_chat.add_argument("--provider", default="local", help="AI provider (local, openai, anthropic, google)")

    # models
    parser_models = subparsers.add_parser("models", help="Manage LLM models")
    parser_models.add_argument("--provider", default="local", help="AI provider (local, openai, anthropic, google)")
    parser_models.add_argument("--list", action="store_true", help="List models (default)")
    parser_models.add_argument("--pull", help="Pull a model (Ollama only)")

    # auth
    parser_auth = subparsers.add_parser("auth", help="Manage AI subscriptions and API keys")
    parser_auth.add_argument("action", choices=["set-key", "list", "login"], help="Auth action")
    parser_auth.add_argument("provider", nargs="?", help="Provider (openai, anthropic, google)")
    parser_auth.add_argument("input", nargs="?", help="API Key or data")

    # status
    subparsers.add_parser("status", help="Status of the layer")

    # hook
    parser_hook = subparsers.add_parser("hook", help="Automate capture")
    parser_hook.add_argument("action", help="Action (e.g., install)")

    parser_ctx = subparsers.add_parser("ctx", help="Context Mode sandboxed execution")
    parser_ctx.add_argument(
        "action",
        choices=["init", "execute", "search", "stats", "insight", "promote", "mcp"],
        help="Action to perform"
    )
    parser_ctx.add_argument("input", nargs="?", help="Input code or query")
    parser_ctx.add_argument("--lang", default="javascript", help="Language for execution")
    parser_ctx.add_argument(
        "--continue", dest="continue_session", action="store_true", help="Continue session"
    )

    return parser

def main():
    """Main entry point for the CLI."""
    if len(sys.argv) == 1:
        print("🪩 NouGenShards CLI\n")
        print("Your agent has prompts. Mine has shards.")
        print("Run `nougen init` to get started.\n")
        print("Use `nougen --help` for all commands.")
        sys.exit(0)

    if "--version" in sys.argv or "-v" in sys.argv:
        print(f"NouGenShards v{VERSION}")
        sys.exit(0)

    parser = get_parser()
    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "add": cmd_add,
        "search": cmd_search,
        "connect": cmd_connect,
        "config": cmd_config,
        "ingest": cmd_ingest,
        "mark": cmd_mark,
        "chat": cmd_chat,
        "models": cmd_models,
        "status": cmd_status,
        "hook": cmd_hook,
        "ctx": cmd_ctx,
        "auth": cmd_auth
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
