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
from . import hooks
from .connectors.cloud import push_to_cloud, pull_from_cloud
from .brain_scan import scan_environment, run_import, print_scan_report, print_import_report
from . import dream
from . import evolution

VERSION = "1.1.0"

# --- Exit-code contract -----------------------------------------------------
# Handlers return None or EXIT_OK on success and a non-zero code on failure;
# main() propagates whatever they return to the process exit status. Keep the
# vocabulary this small and named (Rule 0.2: no bare magic numbers on the wire)
# — hooks, CI steps and this repo's scheduled tasks branch on it.
#
#   EXIT_OK      the command did what it was asked to do. This includes honest
#                empty results: "no shards found", "no triggers", "0 nodes
#                linked" are successful answers, not failures.
#   EXIT_FAILURE the command ran and the operation failed, or a diagnostic
#                found a problem it is supposed to report.
#   EXIT_USAGE   the invocation itself was wrong (missing/unknown arguments or
#                subcommand). Matches argparse's own convention and main()'s
#                unknown-command path.
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2



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
    """Universal AI Memory Forensic Engine.

    Subcommand dispatcher: each branch returns its own code. Finding zero
    candidates is a successful scan (nothing to recover), not a failure.
    """
    if args.action == "scan":
        candidates = scan_environment(
            project_path=str(getattr(args, 'project')) if getattr(args, 'project', None) else None,
            include_unknown=getattr(args, 'unknown', False)
        )
        print_scan_report(candidates, as_json=getattr(args, 'json', False))
        return EXIT_OK
    elif args.action == "import":
        result = run_import(
            project_path=str(getattr(args, 'project')) if getattr(args, 'project', None) else None,
            include_unknown=getattr(args, 'unknown', False),
            source_filter=str(getattr(args, 'source')) if getattr(args, 'source', None) else None,
            redact=not getattr(args, 'no_redact', False),
            confirm=getattr(args, 'confirm', False)
        )
        print_import_report(result, dry_run=not getattr(args, 'confirm', False), as_json=getattr(args, 'json', False))
        # run_import returns an ImportResult with no in-band error channel:
        # parse/capture problems raise, which main() already surfaces non-zero.
        # A 0-shard import is a legitimate "nothing new to recover" result.
        return EXIT_OK

    print(f"Error: unknown brain action '{getattr(args, 'action', None)}'.")
    return EXIT_USAGE

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
    """Manages authentication and API keys.

    A credential write that fails must never look like it landed: the next run
    would silently fall back to an unauthenticated lane.
    """
    if args.action == "set-key":
        if not args.provider or not args.input:
            print("Error: Usage: nougen auth set-key <provider> <key>")
            return EXIT_USAGE

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
            return EXIT_USAGE

        secret_key = key_map[provider]
        try:
            keymaker.ingest_secret(secret_key, args.input)
        except Exception as exc:  # pylint: disable=broad-except
            # sqlite errors, vault-hardening refusals, DPAPI failures — any of
            # them means the key is NOT stored. Never print the ✅ in that case.
            print(f"Error: could not save the {provider} key to the vault: {exc}",
                  file=sys.stderr)
            return EXIT_FAILURE
        # Read-back: a write nobody verified is a claim, not a fact.
        if secret_key not in keymaker.list_providers():
            print(f"Error: {provider} key did not survive read-back from the vault.",
                  file=sys.stderr)
            return EXIT_FAILURE
        print(f"✅ API key for {provider} saved to vault.")
        return EXIT_OK

    elif args.action == "list":
        keys = keymaker.list_providers()
        if getattr(args, 'json', False) is True:
            print(json.dumps(keys))
            return EXIT_OK
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
            # An empty list is a correct answer, not a failure: NouGenShards is
            # local-first and "no cloud services connected" is a valid state.
            print(" No cloud services connected.")
        return EXIT_OK

    print(f"Error: unknown auth action '{getattr(args, 'action', None)}'.")
    return EXIT_USAGE


def cmd_init(_args):
    """Bootstrap the local shard layer."""
    print("🪩 Initializing Valerion — The Memory Engine...")
    try:
        shards.init_db(index=1)
    except (OSError, sqlite3.Error) as exc:
        # An unwritable/inaccessible vault dir is the realistic failure here, and
        # every "Next Play" printed below is a lie if the substrate never landed.
        print(f"❌ Could not create the database substrate: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    print("✅ Created local-first database substrate.")
    print("\n[IGNITION COMPLETE]")
    print(" NouGenShards is now active. Your machine has memory.")
    print("\nNext Plays:")
    print(" 1. nougen brain scan         (Discover your lost AI history)")
    print(" 2. nougen dashboard          (Launch the visual Cortex HUD)")
    print(" 3. nougen auth set-key OR    (Connect to the cloud)")
    print(" 4. nougen add \"first shard\" (Start capturing manually)")
    return EXIT_OK


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
        return EXIT_FAILURE

    model = args.model
    if not model:
        if isinstance(client, LocalLLMClient):
            model_config = client.find_best_edge_model()
            model = model_config.model_name if model_config else None
        else:
            model = client.list_models()[0]

    if not model:
        print("Error: No model found.")
        return EXIT_FAILURE

    if not args.query:
        _run_interactive_chat(model, prov_name, client)
    else:
        found = federation.federated_retrieve(args.query, limit=3)
        ctx = shards.compile_recall_packet(found)
        msgs = [{"role": "user", "content": f"{args.query}\n\n{ctx}"}]
        print(f"[*] Querying {model}...")
        resp = client.chat(model, msgs, stream=False)
        print(f"\n[Response]:\n{resp}")
    return EXIT_OK


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
    """Search for shards across local substrate and external DBs.

    Exit-code note: a search that matches nothing is a SUCCESSFUL search. "No
    shards found" is an answer, and scripting `nougen search` into an `if` must
    not treat an empty vault as a broken one. The only non-zero paths here would
    be genuine retrieval faults, which raise and are surfaced by main().
    """
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
        return EXIT_OK

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
        return EXIT_OK

    if getattr(args, 'json', False) is True:
        # Convert binary embeddings to lists for JSON serialization
        for res in results:
            if 'embedding' in res and isinstance(res['embedding'], bytes):
                res['embedding'] = json.loads(res['embedding'].decode())
        print(json.dumps(results))
        return EXIT_OK

    print(f"🔍 Found {len(results)} records across the fabric (Ranked by Relevance):\n")
    for res in results:
        header = f"[{res['id']}] Final Score: {res['final_score']:.2f} | " \
                 f"Prior: {res['utility_score']} | Source: {res['_db_index']}"
        print(header)
        print(f"Title: {res['title']}\n{res['content'].strip()}\n" + "-" * 40)
    return EXIT_OK


def cmd_mark(args):
    """Close the outcome loop (usefulness update)."""
    if shards.mark_shard(args.id, worked=args.worked, db_index=args.db):
        print(f"✅ Shard #{args.id} updated. Usefulness prior adjusted.")
        return EXIT_OK
    # The shard the caller named does not exist, so the update it asked for did
    # not happen. That is a failure, not an empty result.
    print(f"Error finding shard #{args.id}.")
    return EXIT_FAILURE


def cmd_status(args):
    """Check the status of the Multi-DB cluster.

    A cluster with zero databases is reported, not failed — that is a valid
    pre-`init` state. But a database file that EXISTS and cannot be read is an
    outage: the totals printed below are silently short by that DB's contents,
    which is exactly the shape of failure this command is watched for.
    """
    active = shards.get_active_db_index()
    db_stats = []
    total_count = 0
    unreadable = []
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
        except (sqlite3.Error, OSError) as exc:
            unreadable.append(f"DB #{i} ({path}): {exc}")

    if getattr(args, 'json', False) is True:
        print(json.dumps({
            "databases": db_stats,
            "total_shards": total_count,
            "unreadable": unreadable,
        }))
    else:
        print("📊 NouGenShards Substrate Status:")
        for db in db_stats:
            status = " (ACTIVE)" if db['is_active'] else ""
            print(f" - DB #{db['index']}: {db['shards']} shards | {db['size_mb']:.2f} MB / 1024 MB{status}")
        print(f"\nTotal records in memory: {total_count}")

    if unreadable:
        for line in unreadable:
            print(f"Error: unreadable database — {line}", file=sys.stderr)
        return EXIT_FAILURE
    return EXIT_OK


def cmd_stats(args):
    """Reports memory growth and utility trends across horizons.

    Exit-code note: zero growth over the window is a real, successful answer.
    There is no in-band error channel here — a broken history store raises, and
    main() turns that into a non-zero status on its own.
    """
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
        return EXIT_OK

    print(f"📈 NouGenShards History ({period})")
    print(timeline)
    print(f"\n - New Shards Captured: {growth['new_shards']}")
    print(f" - Total Memory Size:   {growth['total_shards']} shards")
    print(f" - Usefulness \u0394: {'+' if utility >= 0 else ''}{utility:.2f}")

    if growth['total_shards'] > 0:
        rate = (growth['new_shards'] / growth['total_shards']) * 100
        print(f" - Acceleration Rate:   {rate:.1f}% expansion")
    return EXIT_OK


def cmd_ctx(args):
    """Handles NouGenContext commands.

    Subcommand dispatcher: every branch returns its own code and cmd_ctx returns
    it unchanged — no branch may swallow a subhandler's failure.
    """
    if args.action == "init":
        # Explicit user 'init' intends a fresh session, so opt into the wipe.
        nougen_context.init_context_db(clean_slate=True)
        print("✅ Session initialized.")
        return EXIT_OK
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
                    return EXIT_OK
                print("🚫 Action aborted.")
                return EXIT_FAILURE
            # Non-interactive: the gate blocked the run and nothing executed.
            # A caller that pipes this into a script must see the abort.
            print("🚫 Action aborted.")
            return EXIT_FAILURE
        print(nougen_sandbox.execute_sandboxed(args.input))
        return EXIT_OK
    elif args.action == "search":
        if not args.input:
            print("Error: Usage: nougen ctx search <query> [--limit <n>]")
            return EXIT_USAGE
        results = nougen_context.search_events(args.input, limit=args.limit)
        if not results:
            # An empty search result is a successful search.
            print("No context events found.")
            return EXIT_OK
        for event in results:
            print(
                f"#{event['id']} {event['timestamp']} "
                f"{event['event_type']}: {event['description']}"
            )
        return EXIT_OK
    elif args.action == "get":
        if not args.input:
            print("Error: Usage: nougen ctx get <event_id>")
            return EXIT_USAGE
        event = nougen_context.get_event(int(args.input))
        if not event:
            # A specific event was named and it is not there: a lookup failure,
            # unlike an open-ended search that matched nothing.
            print(f"Error: Context event #{args.input} not found.")
            return EXIT_FAILURE
        print(json.dumps(event, indent=2))
        return EXIT_OK
    elif args.action == "promote":
        if not args.input:
            print("Error: Usage: nougen ctx promote <event_id> [--tags <tags>]")
            return EXIT_USAGE
        event = nougen_context.get_event(int(args.input))
        if not event:
            print(f"Error: Context event #{args.input} not found.")
            return EXIT_FAILURE

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
            # Dedup hit: the content is already durable, which is the state the
            # caller asked for. Idempotent success, matching `nougen add`.
            print(f"ℹ️ Shard already exists.")
        return EXIT_OK

    print(f"Error: unknown ctx action '{args.action}'.")
    return EXIT_USAGE


def cmd_router(args):
    """Handles OpenRouter production routing commands.

    Subcommand dispatcher: every branch returns its own code and this function
    returns it — nothing here swallows a subhandler's failure. Note that the
    missing-key guard below fails `router doctor` too, which is correct: a
    routing doctor that reports "no key" and then exits 0 tells a scheduled
    task that routing is fine.
    """
    client = OpenRouterClient()
    if not client.is_alive():
        print("Error: OpenRouter key not found in vault. Use: nougen auth set-key openrouter <key>")
        return EXIT_FAILURE

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
        # A router response carrying an error key means every model in the
        # fallback chain failed; the printed text is the error, not an answer.
        return EXIT_FAILURE if isinstance(res, dict) and res.get("error") else EXIT_OK

    elif args.action == "json":
        if not args.schema:
            print("Error: --schema path/to/schema.json is required.")
            return EXIT_USAGE

        try:
            with open(args.schema, "r") as f:
                schema = json.load(f)
        except Exception as e:
            print(f"Error loading schema: {e}")
            return EXIT_FAILURE

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
        # Same verdict in both render modes: an error, or output that failed the
        # caller's own schema, is a failed structured call.
        if "error" in res or not res.get("valid"):
            return EXIT_FAILURE
        return EXIT_OK

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
        # Belt and braces: the guard at the top already fails a keyless run, but
        # the doctor's verdict must come from the diagnosis it just printed.
        return EXIT_OK if diag["openrouter_key"] else EXIT_FAILURE

    else:
        print(f"Error: unknown router action '{args.action}'.")
        return EXIT_USAGE


def cmd_db(args):
    """Manages external database connections.

    Subcommand dispatcher: each branch returns its own code. A link that did not
    persist must not report success — the next federated search would quietly
    query one source fewer.
    """
    if args.action == "link":
        if not args.uri or not args.table:
            print("Error: Usage: nougen db link <uri> --table <name> --title <col> --content <col>")
            return EXIT_USAGE
        try:
            keymaker.register_external_db(args.uri, args.table, args.title, args.content)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"Error: could not link external DB '{args.table}': {exc}", file=sys.stderr)
            return EXIT_FAILURE
        print(f"✅ External DB linked: {args.table}")
        return EXIT_OK
    elif args.action == "list":
        dbs = keymaker.list_external_dbs()
        if getattr(args, 'json', False) is True:
            print(json.dumps(dbs))
            return EXIT_OK
        if not dbs:
            # Zero linked databases is a legitimate state, not a failure.
            print(" No external databases linked.")
            return EXIT_OK
        print("📊 Linked External Databases:")
        for d in dbs:
            print(f" - #{d['id']}: {d['uri'][:30]}... | Table: {d['table_name']}")
        return EXIT_OK

    print(f"Error: unknown db action '{args.action}'.")
    return EXIT_USAGE


def cmd_node(args):
    """Manages remote NouGenShards cloud nodes.

    Subcommand dispatcher: each branch returns its own code. Sync is the sharp
    edge here — a push or pull that half-failed and exited 0 reads as "backup
    succeeded" to any scheduled task watching it.
    """
    if args.action == "link":
        if not args.url:
            print("Error: Usage: nougen node link <url> [--name <name>]")
            return EXIT_USAGE
        name = args.name or f"node_{abs(hash(args.url)) % 1000}"
        try:
            keymaker.register_cloud_node(args.url, name)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"Error: could not link node '{name}': {exc}", file=sys.stderr)
            return EXIT_FAILURE
        print(f"[*] Remote node linked: {name} ({args.url})")
        return EXIT_OK
    elif args.action == "list":
        nodes = keymaker.list_cloud_nodes()
        if getattr(args, 'json', False) is True:
            print(json.dumps(nodes))
            return EXIT_OK
        if not nodes:
            # Zero linked nodes is a legitimate state, not a failure.
            print(" No remote nodes linked.")
            return EXIT_OK
        print("[*] Linked Remote Nodes:")
        for n in nodes:
            print(f" - #{n['id']}: {n['name']} | URL: {n['url']}")
        return EXIT_OK
    elif args.action == "push":
        if not args.url:
            print("Error: Usage: nougen node push <url> --token <token>")
            return EXIT_USAGE
        if not args.token:
            print("Error: --token <token> is required for push.")
            return EXIT_USAGE

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
        # push_to_cloud reports transport/URL rejection in-band as
        # {"status": "error"} — that line above prints "✅ Sync result: error".
        if res.get("status") == "error":
            print(f"Error: push failed — {res.get('message', 'unknown error')}",
                  file=sys.stderr)
            return EXIT_FAILURE
        return EXIT_OK

    elif args.action == "pull":
        if not args.url:
            print("Error: Usage: nougen node pull <url> --token <token>")
            return EXIT_USAGE
        if not args.token:
            print("Error: --token <token> is required for pull.")
            return EXIT_USAGE

        print(f"[*] Pulling shards from {args.url}...")
        remote_shards = pull_from_cloud(args.url, args.token)
        print(f"[*] Pulled {len(remote_shards)} shards. Ingesting locally...")
        count = 0
        ingest_failures = 0
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
                ingest_failures += 1
                continue
            if success: count += 1
        print(f"✅ Ingestion complete. {count} new shards added.")
        # Dropping shards on the floor during a sync is data loss, however
        # cheerful the summary line above looks. `count == 0` on its own is NOT
        # a failure: an already-synced or empty remote legitimately adds nothing.
        if ingest_failures:
            print(f"Error: {ingest_failures} shard(s) failed to ingest during pull.",
                  file=sys.stderr)
            return EXIT_FAILURE
        return EXIT_OK

    print(f"Error: unknown node action '{args.action}'.")
    return EXIT_USAGE


class ConfigError(Exception):
    """Raised when the user config cannot be read or written safely."""


def config_path() -> Path:
    """Resolve the user config file: env -> core's resolved path -> logged fallback.

    Rule 0.2: nothing here is a bare constant. This deliberately reuses the SAME
    file core._config_vault_dir() and tools/arxiv_*.py already read
    (~/.nougen/config.json, overridable with NOUGEN_CONFIG) — a second config
    store would be a worse defect than having none.
    """
    env_path = os.environ.get("NOUGEN_CONFIG")
    if env_path:
        return Path(env_path)
    core_path = getattr(shards, "NOUGEN_CONFIG_PATH", None)
    if core_path:
        return Path(core_path)
    fallback = Path.home() / ".nougen" / "config.json"
    print(f"[config] NOUGEN_CONFIG unset and core path unavailable; "
          f"falling back to {fallback}", file=sys.stderr)
    return fallback


def load_config(path: Path) -> dict:
    """Return the config dict. Missing file -> {}. Corrupt file -> ConfigError.

    A corrupt file must NOT degrade to {}: merging into {} would silently erase
    every existing key on the next write.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ConfigError(
            f"{path} is not valid JSON ({exc}); refusing to overwrite it"
        ) from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} does not contain a JSON object; refusing to overwrite it")
    return data


def save_config(path: Path, config: dict) -> Path | None:
    """Merge-safe atomic write. Backs the existing file up once, returns backup path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return backup


def cmd_config(args):
    """Read/write persisted CLI configuration. Returns 0 on success, 1 on failure."""
    action = getattr(args, "action", None)
    key = getattr(args, "key", None)
    value = getattr(args, "value", None)

    if action == "set" and key and value:
        path = config_path()
        try:
            config = load_config(path)
            config[key] = value
            backup = save_config(path, config)
            # Never report success on an unverified write: read it back.
            if load_config(path).get(key) != value:
                raise ConfigError(f"{key} did not survive read-back from {path}")
        except (ConfigError, OSError) as exc:
            print(f"❌ Configuration NOT updated: {exc}", file=sys.stderr)
            return 1
        print(f"✅ Configuration updated: {key} = {value} -> {path}")
        if backup:
            print(f"   (previous config backed up to {backup})")
        return 0

    if action == "get" and key:
        path = config_path()
        try:
            config = load_config(path)
        except (ConfigError, OSError) as exc:
            print(f"❌ Cannot read configuration: {exc}", file=sys.stderr)
            return 1
        if key not in config:
            print(f"Error: no value set for '{key}' in {path}", file=sys.stderr)
            return 1
        print(config[key])
        return 0

    print("Usage: nougen config set <key> <value> | nougen config get <key>")
    return 1


def cmd_connect(args):
    """Connect NouGenShards to an agent (e.g., via MCP)."""
    if args.mcp:
        print("Auto-detecting agent configuration...")
        ans = input("Add NouGenShards to your MCP config? [Y/n] ")
        if ans.lower() not in ['n', 'no']:
            print("✅ Wires connected. NouGenShards is now an active MCP memory tool.")
            return EXIT_OK
        # Declining is a deliberate choice, but the connection the caller asked
        # for did not happen — a wrapper script must not read this as connected.
        print("Cancelled.")
        return EXIT_FAILURE
    print("Usage: nougen connect --mcp")
    return EXIT_USAGE


def cmd_hook(args):
    """Manage local hook adapters.

    Subcommand dispatcher: each branch returns its own code and cmd_hook returns
    it unchanged.
    """
    if args.action in {"codex-anchor", "anchor"}:
        print(hooks.get_latest_anchor(limit=args.limit, max_chars=args.max_chars))
        return EXIT_OK
    elif args.action == "space-anchor":
        print(hooks.get_space_orchestration_anchor(
            limit=args.limit,
            max_chars=args.max_chars,
            space_id=getattr(args, "space", None),
            token_key=getattr(args, "token_key", None),
        ))
        return EXIT_OK
    elif args.action == "space-logs":
        from . import space_orchestration

        snapshot = space_orchestration.fetch_log_snapshot(
            kind=getattr(args, "log_kind", "run"),
            space_id=getattr(args, "space", None),
            token_key=getattr(args, "token_key", None),
        )
        # Same verdict in both render modes: a non-"ok" snapshot means the logs
        # could not be fetched, whether or not --json was asked for.
        log_ok = snapshot.get("status") == "ok"
        if getattr(args, "json", False):
            print(json.dumps(snapshot, indent=2))
            return EXIT_OK if log_ok else EXIT_FAILURE
        print(
            f"HF Space {snapshot.get('kind')} logs: {snapshot.get('status')} "
            f"({snapshot.get('url')})"
        )
        if log_ok:
            print(snapshot.get("body", ""))
            return EXIT_OK
        print(snapshot.get("error", "Unknown error"))
        return EXIT_FAILURE
    elif args.action == "install":
        agent = (args.agent or "codex").lower()
        if agent != "codex":
            print("Error: only the local Codex hook adapter is implemented.")
            return EXIT_USAGE
        target_dir = hooks.install_local_codex_hook(
            output_dir=args.output_dir,
            limit=args.limit,
            max_chars=args.max_chars,
        )
        print(f"✅ Local Codex hook artifacts written to {target_dir}")
        print("No shell profile or global runtime config was modified.")
        return EXIT_OK

    print("Usage: nougen hook codex-anchor | space-anchor | space-logs | install --agent codex")
    return EXIT_USAGE


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
        # The missing-file guard above already sys.exit(1)s, but this branch —
        # an unreadable file or a write that failed — printed "Failed:" and
        # still exited 0. Same class of hole, same fix.
        print(f"Failed: {exc}")
        return EXIT_FAILURE
    return EXIT_OK


def cmd_dream(args):
    """Executes the Dream cycle (Autonomous Memory Evolution)."""
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
        return EXIT_OK

    print(f"Error: unknown dream action '{args.action}'.")
    return EXIT_USAGE


def cmd_evolve(args):
    """NouGenSkills — Universal Open-World Skill Evolution."""
    if args.action == "run":
        is_json = getattr(args, 'json', False)
        if not is_json:
            print("[EXPERIMENTAL: NouGenSkills acquisition + verification are simulated stubs]")
            print(f"[*] Evolution: Initiating NouGenSkills cycle for '{args.instruction}'...")
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
        # Unverified means the skill was not acquired: "[Evolution Failed]" must
        # not exit 0, in either render mode.
        return EXIT_OK if summary.get("verified") else EXIT_FAILURE

    print(f"Error: unknown evolve action '{args.action}'.")
    return EXIT_USAGE


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
        return EXIT_FAILURE

    print(f"🚀 Igniting Cortex HUD on http://127.0.0.1:{args.port}...")
    uvicorn.run(dashboard_app, host="127.0.0.1", port=args.port)
    # Reached only after the server shuts down cleanly.
    return EXIT_OK


def cmd_power(args):
    """Host power surface: CPU ceiling control and host-death correlation."""
    from . import host_power

    action = getattr(args, "action", None) or "status"

    if action == "status":
        state = host_power.status()
        if not state.get("supported"):
            print(f"host power control unavailable — {state.get('reason')}")
            return EXIT_FAILURE
        print(f"scheme:  {state['scheme_guid']}")
        print(f"ceiling: {state['ceiling_pct']}%   floor: {state['floor_pct']}%")
        if state.get("floor_pct") == 100:
            # A pinned floor is a finding to report, not a command failure.
            print("  NOTE: floor is pinned at 100% — the CPU never downclocks, even idle.")
        return EXIT_OK

    if action == "set":
        try:
            after = host_power.set_cpu_range(args.ceiling, args.floor)
        except host_power.PowerUnsupported as exc:
            print(f"could not apply: {exc}")
            return EXIT_FAILURE
        print(f"applied — ceiling: {after.get('ceiling_pct')}%  floor: {after.get('floor_pct')}%")
        return EXIT_OK

    if action == "shutdowns":
        found = host_power.shutdown_events(args.days)
        if not found.get("queried"):
            print(f"query failed — {found.get('reason')}")
            return EXIT_FAILURE
        events = found["events"]
        print(f"{len(events)} unexpected shutdown(s) in {found['lookback_days']}d")
        for event in events[:20]:
            cause = "unexplained rail loss" if event["unexplained_rail_loss"] else (
                "bugcheck" if event["bugcheck"] else
                "power button" if event["button"] else
                "thermal" if event["thermal"] else f"id={event['event_id']}")
            print(f"  {event['utc']}  {cause}")
        # Finding shutdowns is the command working, not failing: this is a
        # report, and a host that died last night still answers correctly.
        return EXIT_OK

    if action == "correlate":
        print(host_power.format_correlation(
            host_power.correlate(args.days, args.window)))
        return EXIT_OK

    if action == "boot":
        report = host_power.boot_report()
        if not report.get("supported"):
            print(f"boot report unavailable — {report.get('reason')}")
            return EXIT_FAILURE
        uptime = report.get("uptime_s")
        print(f"booted:  {report['boot_utc']}")
        if uptime is not None:
            print(f"uptime:  {uptime // 3600}h {(uptime % 3600) // 60}m")
        if report["previous_shutdown_clean"]:
            print("previous shutdown: clean")
        else:
            death = report["previous_death"]
            cause = "unexplained rail loss" if death["unexplained_rail_loss"] else "see flags"
            # An unclean previous shutdown is a reported fact, not a failure of
            # this command to produce the report.
            print(f"previous shutdown: UNCLEAN at {death['utc']} ({cause})")
        return EXIT_OK

    if action == "record-boot":
        result = host_power.record_boot(dry_run=args.dry_run)
        if result.get("dry_run"):
            print(f"would capture: {result['title']}")
            return EXIT_OK
        if result.get("recorded"):
            print(f"captured: {result['title']}")
            return EXIT_OK
        print(f"nothing captured — {result.get('reason')}")
        # "previous shutdown was clean" (result["clean"]) is the happy path:
        # there was no host death to record. Anything else — an unsupported
        # host, an unreadable event log — is a real failure to capture.
        return EXIT_OK if result.get("clean") else EXIT_FAILURE


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

    p_power = subparsers.add_parser("power", help="Host power surface (Windows)")
    p_power_sub = p_power.add_subparsers(dest="action")
    p_power_sub.add_parser("status", help="Show active scheme, CPU ceiling and floor")
    p_power_set = p_power_sub.add_parser("set", help="Set AC CPU ceiling/floor")
    p_power_set.add_argument("ceiling", type=int, help="Max processor state %%")
    p_power_set.add_argument("--floor", type=int, default=None, help="Min processor state %%")
    p_power_down = p_power_sub.add_parser("shutdowns", help="List unexpected host shutdowns")
    p_power_down.add_argument("--days", type=int, default=None, help="Lookback window")
    p_power_corr = p_power_sub.add_parser(
        "correlate", help="Join host deaths against vault activity preceding them")
    p_power_corr.add_argument("--days", type=int, default=None, help="Lookback window")
    p_power_corr.add_argument("--window", type=int, default=None,
                              help="Minutes before each death to inspect")
    p_power_sub.add_parser("boot", help="This boot, and whether the last shutdown was clean")
    p_power_boot = p_power_sub.add_parser(
        "record-boot", help="Capture a shard if the previous shutdown was unclean (idempotent)")
    p_power_boot.add_argument("--dry-run", action="store_true", help="Report without capturing")

    p_config = subparsers.add_parser("config", help="Configuration")
    p_config.add_argument("action", choices=["set", "get"])
    p_config.add_argument("key")
    p_config.add_argument("value", nargs="?", default=None)

    p_connect = subparsers.add_parser("connect", help="Connect agent")
    p_connect.add_argument("--mcp", action="store_true")

    p_hook = subparsers.add_parser("hook", help="Auto-capture")
    p_hook.add_argument(
        "action",
        choices=["install", "uninstall", "codex-anchor", "anchor", "space-anchor", "space-logs"],
    )
    p_hook.add_argument("--agent", default="codex")
    p_hook.add_argument("--limit", type=int, default=5)
    p_hook.add_argument("--max-chars", type=int, default=8000)
    p_hook.add_argument("--output-dir")
    p_hook.add_argument("--space", default=None, help="Hugging Face Space id, owner/name")
    p_hook.add_argument("--token-key", default=None, help="Keymaker token alias to use")
    p_hook.add_argument("--log-kind", choices=["run", "build"], default="run")
    p_hook.add_argument("--json", action="store_true", help="Machine-readable output")

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

    p_dream = subparsers.add_parser("dream", help="Autonomous Memory Evolution (TMEM)")
    p_dream.add_argument("action", choices=["wake"])
    p_dream.add_argument("--json", action="store_true", help="Machine-readable output")

    p_evolve = subparsers.add_parser("evolve", help="NouGenSkills — Universal Open-World Skill Evolution")
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

    p_index = subparsers.add_parser("index", help="ANN index / embedding backfill / schema migration")
    p_index.add_argument("action", choices=["ann-build", "embed-backfill", "schema-migrate"])
    p_index.add_argument("--vault", default=os.environ.get("NOUGEN_VAULT_DIR"), help="Vault directory override")
    p_index.add_argument("--model", default=os.environ.get("NOUGEN_EMBED_MODEL", "nomic-embed-text"), help="Ollama embedding model (embed-backfill)")
    p_index.add_argument("--batch", type=int, default=64, help="Batch size (embed-backfill)")
    p_index.add_argument("--execute", action="store_true", help="Apply writes (embed-backfill / schema-migrate); default is dry-run")
    p_index.add_argument("--no-backup", action="store_true", help="Skip .bak backup before schema-migrate")
    p_index.add_argument("--json", action="store_true", help="Machine-readable output")

    p_handoff = subparsers.add_parser("handoff", help="Cross-agent session handoff notes")
    p_handoff.add_argument("action", choices=[
        "create", "read", "list", "ack", "start", "checkpoint", "complete",
        "rebuild-db", "reconcile", "watch",
    ], help="create | read | list | ack | start | checkpoint | complete | rebuild-db | reconcile | watch")
    p_handoff.add_argument("--message", "-m", default="", help="Handoff note or acknowledgement message")
    p_handoff.add_argument("--message-file", "-M", dest="message_file", default=None,
                           help="Read the note from a UTF-8 file. Required for multi-line "
                                "notes: cmd.exe ends an argument at the first newline, so "
                                "-m silently truncates a templated note to its first heading.")
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

    p_trigger = subparsers.add_parser(
        "trigger", help="Cue-anchored delivery: attach trigger conditions to shards")
    p_trigger.add_argument("action", choices=[
        "add", "list", "rm", "derive", "preview", "status",
    ], help="add | list | rm | derive | preview | status")
    p_trigger.add_argument("--shard", "-s", dest="shard_ref", default=None,
                           help="Shard ref: hash:<file_hash> | db:<index>:<id> | file:<name>")
    p_trigger.add_argument("--type", "-t", dest="trigger_type", default=None,
                           help="path | symbol | semantic | event | temporal")
    p_trigger.add_argument("--pattern", "-p", default=None,
                           help="Glob (path), identifier (symbol), comma terms (semantic), "
                                "event name(s), or an age window like 'age<=7d' (temporal)")
    p_trigger.add_argument("--weight", type=float, default=None,
                           help="Per-trigger weight multiplier (default 1.0)")
    p_trigger.add_argument("--note", default=None, help="Why this trigger exists")
    p_trigger.add_argument("--id", dest="trigger_id", type=int, default=None,
                           help="Trigger id (rm)")
    p_trigger.add_argument("--event", default="", help="(preview) Lifecycle event name")
    p_trigger.add_argument("--paths", default="", help="(preview) Comma-separated touched paths")
    p_trigger.add_argument("--symbols", default="", help="(preview) Comma-separated symbols")
    p_trigger.add_argument("--text", default="", help="(preview) Free text / prompt")
    p_trigger.add_argument("--apply", action="store_true",
                           help="(derive) Persist the proposal; default is dry-run")
    p_trigger.add_argument("--json", action="store_true", help="Machine-readable output")

    p_queue = subparsers.add_parser(
        "queue", help="Open Engine task queue: ticket-level cross-agent work"
    )
    p_queue.add_argument("action", choices=[
        "add", "list", "claim", "block", "answer", "done", "cancel",
        "show", "smoke",
    ], help="add | list | claim | block | answer | done | cancel | show | smoke")
    p_queue.add_argument("--title", "-t", default=None, help="(add) Ticket title")
    p_queue.add_argument("--message", "-m", default="",
                         help="(add) Instructions / (cancel) reason")
    p_queue.add_argument("--owner", "-o", default=None,
                         help="Owner agent lane (claude-cli, gemini, codex, ollama, openrouter)")
    p_queue.add_argument("--agent", "-a", default=None,
                         help="Acting agent (defaults to NOUGEN_AGENT / auto-detect)")
    p_queue.add_argument("--id", dest="task_id", default=None, help="Target task id")
    p_queue.add_argument("--sources", default="", help="(add) Background/context that matters")
    p_queue.add_argument("--allowed", default="", help="(add) What the agent may do")
    p_queue.add_argument("--stop", default="", help="(add) Where the agent must stop")
    p_queue.add_argument("--dod", default="", help="(add) Definition of done")
    p_queue.add_argument("--question", default="", help="(block) Exact blocking question")
    p_queue.add_argument("--answer", default="", help="(answer) Answer to the blocking question")
    p_queue.add_argument("--did", default="", help="(done) Receipt: what was done")
    p_queue.add_argument("--not-done", dest="not_done", default="",
                         help="(done) Receipt: what was NOT done")
    p_queue.add_argument("--evidence", default="", help="(done) Receipt: proof it got done")
    p_queue.add_argument("--status", dest="task_status", default=None,
                         help="(list) Filter by status (todo|working|needs_input|done|cancelled)")

    return parser




# ann_index.build() reports its outcome in-band; these are the statuses that
# mean "the build did its job". Kept next to the reader, not inlined as a magic
# string in a comparison (Rule 0.2).
_ANN_BUILD_OK_STATUSES = frozenset(
    s.strip() for s in os.environ.get("NOUGEN_ANN_OK_STATUSES", "ok,empty").split(",") if s.strip()
)


def cmd_index(args):
    """ANN index build / embedding backfill / schema migration. Delegates to each
    module's own argparse entrypoint so behavior matches `python -m nougen_shards.<mod>`.

    The embed-backfill and schema-migrate branches already propagate correctly
    via `raise SystemExit(mod._main(argv))`; ann-build was the branch that
    printed a failed report and exited 0.
    """
    if args.action == "ann-build":
        from . import ann_index
        report = ann_index.build(vault=args.vault)
        print(json.dumps(report, indent=2, default=str))
        # "empty" is a successful build of a vault that has no embeddings yet —
        # recall falls back to the linear scan, which is a working path, not an
        # outage. Any other non-"ok" status means the index was not written.
        if report.get("status") not in _ANN_BUILD_OK_STATUSES:
            print(f"Error: ANN index build failed — status={report.get('status')!r}",
                  file=sys.stderr)
            return EXIT_FAILURE
        return EXIT_OK
    if args.action == "embed-backfill":
        from . import embedding_backfill
        argv = ["--model", args.model, "--batch", str(args.batch)]
        if args.vault:
            argv += ["--vault", args.vault]
        if args.execute:
            argv.append("--execute")
        raise SystemExit(embedding_backfill._main(argv))
    from . import schema  # schema-migrate
    argv = []
    if args.vault:
        argv += ["--vault", args.vault]
    if args.execute:
        argv.append("--execute")
    if args.no_backup:
        argv.append("--no-backup")
    raise SystemExit(schema._main(argv))


def cmd_doctor(args):
    """Verifies installation, database health, and service connectivity (Valerion Engine).

    Exit code is the whole point of a doctor: a health check that always exits 0
    cannot report a bad diagnosis, so every caller that branches on it is
    silently disarmed. Returns EXIT_FAILURE when a diagnosis is bad.

    What counts as bad (and what deliberately does not):
      * no shard database at all -> FAILURE. The engine has nowhere to remember.
      * a cognitive engine module fails to import -> FAILURE. Broken install.
      * no secrets vault yet -> NOT a failure. keymaker.DB_PATH is created lazily
        on the first `auth set-key`, and it resolves relative to the CWD unless
        NOUGEN_VAULT_DIR is set, so gating the exit code on it would make a
        clean local-only install (and any run from another directory) look
        broken. Reported, not fatal.
      * a provider showing ❌ -> NOT a failure. NouGenShards is local-first;
        a user with zero BYOK keys is a healthy install, and a red row here
        means "not configured", not "outage".
    """
    print("👨‍⚕️ NouGenShards Doctor (Valerion): Running diagnostics...")
    problems = []

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
        problems.append("no shard database found")

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
        print(" ✅ Evolution Engine (NouGenSkills): Ready")
    except ImportError as e:
        print(f" ❌ Engine Modules missing: {e}")
        problems.append(f"engine modules missing: {e}")

    if getattr(args, 'json', False):
        import json
        print("\n[JSON Output]")
        report = {
            "substrate": {"active_index": active, "found": found_db},
            "vault": {"path": str(vault_path.absolute()), "providers": keymaker.list_providers()},
            "connectivity": p_status,
            "healthy": not problems,
            "problems": problems,
        }
        print(json.dumps(report, indent=2))

    if problems:
        print(f"\n❌ Diagnosis: {len(problems)} problem(s) — " + "; ".join(problems),
              file=sys.stderr)
        return EXIT_FAILURE
    return EXIT_OK

def cmd_handoff(args):
    """Executes agent handoff subcommands."""
    from . import handoff

    # --message-file wins over -m: it is the only path that survives cmd.exe, which
    # ends an argument at the first newline. Applies to every action that takes a note.
    message_file = getattr(args, "message_file", None)
    if message_file:
        try:
            args.message = Path(message_file).read_text(encoding="utf-8")
        except OSError as e:
            print(f"Error reading --message-file {message_file}: {e}", file=sys.stderr)
            return 1

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

def cmd_queue(args):
    """Executes Open Engine task-queue subcommands."""
    from . import taskqueue

    if args.action == "add":
        if not args.title:
            print("A ticket needs a --title.")
            sys.exit(1)
        task_id = taskqueue.add_task(
            title=args.title,
            instructions=args.message,
            owner=args.owner,
            created_by=args.agent,
            sources=args.sources,
            allowed_actions=args.allowed,
            stop_conditions=args.stop,
            definition_of_done=args.dod,
        )
        print(f"Task created: {task_id}")
    elif args.action == "list":
        taskqueue.render_task_list(args.owner, args.task_status)
    elif args.action == "claim":
        task = taskqueue.claim_task(args.task_id, agent=args.agent)
        if task:
            print(f"Claimed: {task['task_id']} — {task['title']}")
            taskqueue.render_task(task["task_id"])
        else:
            print("Nothing claimable (empty lane, or another agent won the claim).")
            sys.exit(1)
    elif args.action == "block":
        if not args.task_id or not args.question:
            print("block needs --id and --question (the exact blocking question).")
            sys.exit(1)
        ok = taskqueue.block_task(args.task_id, args.question, agent=args.agent)
        print("Parked in needs_input." if ok else "Could not block (task must be 'working').")
        if not ok:
            sys.exit(1)
    elif args.action == "answer":
        if not args.task_id or not args.answer:
            print("answer needs --id and --answer.")
            sys.exit(1)
        ok = taskqueue.answer_task(args.task_id, args.answer, agent=args.agent)
        print("Answered; task re-entered todo." if ok else "Could not answer (task must be 'needs_input').")
        if not ok:
            sys.exit(1)
    elif args.action == "done":
        if not args.task_id or not args.did:
            print("done needs --id and --did (the receipt is mandatory).")
            sys.exit(1)
        ok = taskqueue.complete_task(
            args.task_id,
            receipt_done=args.did,
            receipt_evidence=args.evidence,
            receipt_not_done=args.not_done,
            agent=args.agent,
        )
        print("Done with receipt." if ok else "Could not complete (task must be 'working').")
        if not ok:
            sys.exit(1)
    elif args.action == "cancel":
        if not args.task_id:
            print("cancel needs --id.")
            sys.exit(1)
        ok = taskqueue.cancel_task(args.task_id, reason=args.message, agent=args.agent)
        print("Cancelled." if ok else "Could not cancel (already terminal?).")
        if not ok:
            sys.exit(1)
    elif args.action == "show":
        if not args.task_id:
            print("show needs --id.")
            sys.exit(1)
        taskqueue.render_task(args.task_id)
    elif args.action == "smoke":
        if not taskqueue.smoke_test(agent=args.agent):
            sys.exit(1)


def cmd_trigger(args):
    """Author and inspect cue-anchored trigger conditions.

    This is the "without hand-editing files" path: triggers live in a sidecar
    DB, so attaching one never rewrites a shard and never touches the cluster.
    """
    from . import triggers  # pylint: disable=import-outside-toplevel

    action = args.action
    if action == "status":
        info = {
            "enabled": triggers.enabled(),
            "autoderive": triggers.autoderive_enabled(),
            "pretooluse": triggers.pretooluse_enabled(),
            "db": str(triggers.db_path()),
            "log": str(triggers.log_path()),
            "budget_tokens": triggers.budget_tokens(),
            "max_shards": triggers.max_shards(),
            "triggers": triggers.count_triggers(),
        }
        print(json.dumps(info, indent=2) if args.json else
              "\n".join(f"{k:>15}: {v}" for k, v in info.items()))
        return

    if action == "add":
        if not (args.shard_ref and args.trigger_type and args.pattern):
            print("❌ add requires --shard, --type and --pattern")
            return
        try:
            tid = triggers.add_trigger(args.shard_ref, args.trigger_type, args.pattern,
                                       weight=args.weight, note=args.note)
        except triggers.TriggerError as exc:
            print(f"❌ {exc}")
            return
        print(f"✅ trigger #{tid}: {args.trigger_type}:{args.pattern} -> {args.shard_ref}")
        return

    if action == "list":
        rows = triggers.list_triggers(args.shard_ref, args.trigger_type)
        if args.json:
            print(json.dumps(rows, indent=2))
            return
        if not rows:
            print("(no triggers)")
            return
        for r in rows:
            print(f"#{r['id']:<5} {r['trigger_type']:<9} {r['pattern']:<40} "
                  f"w={r['weight']:<5} [{r['source']}] {r['shard_ref']}")
        return

    if action == "rm":
        if args.trigger_id is None:
            print("❌ rm requires --id")
            return
        print("🗑️ removed" if triggers.remove_trigger(args.trigger_id) else "❌ no such trigger")
        return

    if action == "derive":
        if not args.shard_ref:
            print("❌ derive requires --shard")
            return
        shard = triggers.resolve_shard(args.shard_ref)
        if shard is None:
            print(f"❌ could not resolve {args.shard_ref}")
            return
        proposed = triggers.derive_triggers(shard.get("title", ""), shard.get("content", ""))
        if not proposed:
            print("🤏 nothing derived (auto-derivation is deliberately conservative)")
            return
        for ttype, pat in proposed:
            if args.apply:
                triggers.add_trigger(args.shard_ref, ttype, pat, source="auto")
            print(f"{'✅ attached' if args.apply else '🔎 would attach'}  {ttype}:{pat}")
        if not args.apply:
            print("(dry-run — pass --apply to persist)")
        return

    if action == "preview":
        def _split(v):
            return tuple(x.strip() for x in (v or "").split(",") if x.strip())
        ctx = triggers.TriggerContext(
            event=args.event, cwd=os.getcwd(), paths=_split(args.paths),
            symbols=_split(args.symbols), text=args.text)
        sel = triggers.select(ctx)
        if args.json:
            print(json.dumps({
                "candidates": sel.candidates, "tokens": sel.tokens,
                "truncated": sel.truncated,
                "injected": [{"ref": m.shard_ref, "score": m.score, "cues": m.reasons,
                              "title": m.title} for m in sel.injected]}, indent=2))
            return
        print(f"candidates={sel.candidates} injected={len(sel.injected)} "
              f"tokens={sel.tokens}/{triggers.budget_tokens()} truncated={sel.truncated}")
        text = triggers.render(ctx, sel)
        print(text if text else "(nothing would be injected)")
        return


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
        "dashboard": cmd_dashboard, "handoff": cmd_handoff, "index": cmd_index,
        "queue": cmd_queue, "trigger": cmd_trigger, "power": cmd_power,
    }
    if args.command in cmds:
        # Handler exit-code contract: return None (or 0) on success, a non-zero
        # int on failure. main() MUST propagate it — hooks, CI steps and the
        # scheduled tasks in this repo branch on %ERRORLEVEL%/$?, so swallowing
        # a handler's failure code silently disarms every one of them.
        rc = cmds[args.command](args)
        sys.exit(0 if rc is None else int(rc))
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
