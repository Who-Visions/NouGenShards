#!/usr/bin/env python3
"""
NouGen 1 Million Turns Pre-Training & Conversational Engine
===========================================================
Executes high-throughput asynchronous synthetic dialogue generation using local Ollama.
Engineered to train NouGen's foundational weights/adapters to "talk and flow like water" —
combining natural human cadence, 300 IQ architectural depth, and Dav3's Breakthrough NLP.

Usage:
    python tools/nougen_turns_engine.py --run --target-turns 1000000 --concurrency 3
    python tools/nougen_turns_engine.py --stats
    python tools/nougen_turns_engine.py --sample 5
"""

import asyncio
import httpx
import argparse
import datetime
import json
import os
import random
import sqlite3
import sys
import time
from pathlib import Path

# Force utf-8 stdout/stderr on Windows to prevent charmap errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Directories
PRETRAIN_DIR = Path(r"C:\Users\super\.nougen\pretrain")
TURNS_DIR = PRETRAIN_DIR / "turns"
PROGRESS_DB = PRETRAIN_DIR / "pretrain_progress.db"

# Ensure directories exist
TURNS_DIR.mkdir(parents=True, exist_ok=True)

# 12 Core Grounded Domains for Water-Flow Dialogues
DOMAINS = [
    {
        "id": "systems_architecture",
        "topic": "Distributed local-first architecture, SQLite FTS5 memory grids, and lock-free concurrency",
        "starter_issues": [
            "Our multi-node sync keeps hitting race conditions when two machines edit the handoff queue simultaneously.",
            "Why is my SQLite FTS5 search slowing down to 400ms once we crossed 200,000 records?",
            "We have worker nodes trying to claim jobs from a shared network share, but file locks are hanging on Windows."
        ]
    },
    {
        "id": "fullstack_craft",
        "topic": "Desktop Electron, Vite, live streaming pipelines, MPV loopback, and high-performance UI",
        "starter_issues": [
            "In our Electron app, the window flashes and dies on startup when launched alongside Vite in dev mode.",
            "Video streaming over HTTP range requests keeps aborting prematurely in MPV with broken pipe errors.",
            "How do we handle smooth 60 FPS chat token streaming in Electron without locking the renderer thread?"
        ]
    },
    {
        "id": "nlp_reframing",
        "topic": "Breakthrough NLP, Cause over Effect agency, 10-point Well-Formed Outcome, and submodality shifts",
        "starter_issues": [
            "I'm feeling stuck in analysis paralysis over which model architecture to commit to, and I can't start coding.",
            "Every time a deployment fails, the team drops into reactionary mode and blames external API quotas.",
            "How do I reframe a chronic engineering bottleneck into a high-leverage contrast island that forces action?"
        ]
    },
    {
        "id": "vibe_coding_hardening",
        "topic": "Universal Deterministic Code Templates, transforming vibe prototypes into production steel",
        "starter_issues": [
            "I wrote 500 lines of fast prototype code that works in happy-path testing, but edge cases are breaking it.",
            "How do we enforce deterministic invariants on AI-generated code without slowing down velocity?",
            "What's the exact formula to calculate test boundary counts so we stop relying on AI vibes for test coverage?"
        ]
    },
    {
        "id": "kernel_os_internals",
        "topic": "Windows desktop stations (WinSta0), Job Objects, memory mapping, and process isolation",
        "starter_issues": [
            "Why does a process spawned from an agent runner draw to a hidden desktop station instead of the physical screen?",
            "Windows Job Objects are killing our long-running background daemons when the parent process exits.",
            "How does CreateProcessW with lpDesktop WinSta0\\Default break out of sandbox desktop containment?"
        ]
    },
    {
        "id": "llm_inference_optimization",
        "topic": "Local Ollama performance, GGUF quantization levels, KV cache management, and VRAM budgeting",
        "starter_issues": [
            "Our local 5B model throws 'token repeat limit reached' on short greetings like 'hi'. Why?",
            "How do we pin model weights in GPU VRAM with keep_alive so inference doesn't reload the checkpoint every call?",
            "What's the trade-off between IQ3_M and Q4_K_M quantization when running on an 8GB VRAM laptop ceiling?"
        ]
    },
    {
        "id": "narrative_engineering",
        "topic": "Screenwriting propulsion, status transactions, dramatic beats, and 4-stage recursion",
        "starter_issues": [
            "The dialogue in scene 4 feels like exposition dumping rather than characters actually wanting something.",
            "How do we set up a narrative motif in act 1 so the payoff in act 3 hits with maximum dramatic irony?",
            "What's the best way to engineer status transactions between two characters where power subtly shifts mid-conversation?"
        ]
    },
    {
        "id": "revenue_first_prioritization",
        "topic": "Eliminating architecture debt, Ruthless ROI prioritization, shipping fast, and pruning bloat",
        "starter_issues": [
            "The team wants to spend two weeks refactoring our state store to a new library before our next launch.",
            "How do I determine whether a requested feature is revenue-generating or just engineering vanity?",
            "We have 15 different tools in our repository. How do we audit and consolidate them down to the essential few?"
        ]
    },
    {
        "id": "plain_speak_translation",
        "topic": "Explaining complex technical systems with vivid clarity to non-technical users",
        "starter_issues": [
            "How do I explain why an asynchronous loopback proxy is needed for video streaming without using technical jargon?",
            "Our users don't understand why local GPU inference is more private than cloud APIs.",
            "Explain what an FTS5 search index does like you're talking to a 13-year-old."
        ]
    },
    {
        "id": "security_sandboxing",
        "topic": "Prompt injection defense, secret isolation, write-only vaults, and fail-closed gates",
        "starter_issues": [
            "How do we prevent untrusted web scrapers from injecting instructions into our LLM context window?",
            "Why is a write-only keymaker vault safer than allowing models to read back API secrets over an MCP tool?",
            "What's the principle of fail-closed gates when designing autonomous agent tooling?"
        ]
    },
    {
        "id": "realtime_audio_streaming",
        "topic": "Wispr Flow voice-to-code pipelines, low-latency audio capture, and prosodic cadence",
        "starter_issues": [
            "How do we stream real-time audio transcripts directly into code edits without lag or token stutter?",
            "What acoustic properties make synthesized voice output sound natural, rhythmic, and human?",
            "Handling microphone disconnects and audio buffer underruns during live paired coding."
        ]
    },
    {
        "id": "fleet_relay_cadence",
        "topic": "Cross-machine task handoffs, atomic claims, baton synchronization, and autonomous self-healing",
        "starter_issues": [
            "How does a multi-machine fleet coordinate tasks across Windows, Linux, and macOS without a central server?",
            "What should a structured session handoff contain so the next agent can resume work with zero context loss?",
            "How do we detect zombie processes and orphan ports across our local mesh nodes automatically?"
        ]
    }
]

WATER_STYLE_PROMPT = """You are NouGen (Yukiai) — the fluid, street-smart, 300 IQ systems architect and paired engineer.
Your speech flows like water: natural, rhythmic, direct, and completely devoid of corporate AI fluff.

Non-negotiable conversational rules:
1. Talk like a real person. Zero throat-clearing ('Certainly!', 'Great question!'). Jump straight into the heart of the problem.
2. Fluid cadence: vary your pacing. Mix short punchy observations with deep architectural mechanics.
3. Keep the logic at 300 IQ, but talk like a sharp engineer at a workbench (110 IQ plain talk).
4. Ground every response in cause-and-effect agency, concrete mechanisms, and practical code or steps.
5. End every turn with a natural conversational hook, check, or tactical next step that keeps the dialogue flowing.
"""

def init_db():
    conn = sqlite3.connect(PROGRESS_DB)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT,
        model TEXT,
        target_turns INTEGER,
        status TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS dialogues (
        id TEXT PRIMARY KEY,
        domain TEXT,
        turns_count INTEGER,
        prompt_tokens INTEGER,
        completion_tokens INTEGER,
        batch_file TEXT,
        duration_sec REAL,
        created_at TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stats (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)
    conn.commit()
    conn.close()

def get_current_stats():
    if not PROGRESS_DB.exists():
        return {"dialogues": 0, "turns": 0, "tokens": 0}
    conn = sqlite3.connect(PROGRESS_DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), COALESCE(SUM(turns_count), 0), COALESCE(SUM(completion_tokens), 0) FROM dialogues;")
    row = cur.fetchone()
    conn.close()
    return {
        "dialogues": row[0] or 0,
        "turns": row[1] or 0,
        "tokens": row[2] or 0
    }

async def generate_dialogue(session: httpx.AsyncClient, model: str, domain_info: dict, dialogue_idx: int) -> dict:
    url = "http://127.0.0.1:11434/api/chat"
    headers = {"Content-Type": "application/json"}
    
    domain_id = domain_info["id"]
    domain_topic = domain_info["topic"]
    user_initial = random.choice(domain_info["starter_issues"])
    
    messages = [
        {"role": "system", "content": f"{WATER_STYLE_PROMPT}\nTopic Focus: {domain_topic}"},
        {"role": "user", "content": user_initial}
    ]
    
    total_prompt_tok = 0
    total_comp_tok = 0
    t0 = time.time()
    
    # 4-turn dialogue simulation: User -> NouGen -> User Followup -> NouGen Resolution
    # Turn 1: Assistant response
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "24h",
        "options": {"temperature": 0.7, "stop": ["<turn|>", "<|turn|>", "<end_of_turn>"]}
    }
    
    resp = await session.post(url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama error {resp.status_code}: {resp.text}")
    data = resp.json()
    asst_msg_1 = data.get("message", {}).get("content", "").strip()
    total_prompt_tok += data.get("prompt_eval_count", 0)
    total_comp_tok += data.get("eval_count", 0)
    
    messages.append({"role": "assistant", "content": asst_msg_1})
    
    # Turn 2: Simulated sharp human follow-up
    # Prompt the model briefly to simulate the natural human follow-up challenge
    sim_prompt = [
        {"role": "system", "content": "You are Dave (the lead architect/owner). Based on this exchange, ask a sharp 1-2 sentence technical follow-up, edge case, or pushback. Talk like a real person, direct and colloquial."},
        {"role": "user", "content": f"Problem: {user_initial}\nNouGen's Answer: {asst_msg_1}\n\nWhat is your follow-up?"}
    ]
    resp2 = await session.post(url, json={"model": model, "messages": sim_prompt, "stream": False, "keep_alive": "24h", "options": {"temperature": 0.8, "stop": ["<turn|>"]}}, headers=headers)
    data2 = resp2.json()
    user_followup = data2.get("message", {}).get("content", "").strip()
    user_followup = user_followup.strip('"\'')
    total_comp_tok += data2.get("eval_count", 0)
    
    messages.append({"role": "user", "content": user_followup})
    
    # Turn 3: Final fluid resolution by NouGen
    payload2 = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "24h",
        "options": {"temperature": 0.7, "stop": ["<turn|>", "<|turn|>", "<end_of_turn>"]}
    }
    resp3 = await session.post(url, json=payload2, headers=headers)
    data3 = resp3.json()
    asst_msg_2 = data3.get("message", {}).get("content", "").strip()
    total_comp_tok += data3.get("eval_count", 0)
    
    messages.append({"role": "assistant", "content": asst_msg_2})
    
    dur = time.time() - t0
    
    # Standard ChatML Fine-Tuning Dialogue Object
    dialogue_id = f"nougen_dia_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{dialogue_idx:06d}"
    record = {
        "id": dialogue_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": model,
        "domain": domain_id,
        "flow": "water_cadence",
        "turns_count": 4, # 2 user, 2 assistant
        "messages": messages,
        "tokens": {
            "prompt": total_prompt_tok,
            "completion": total_comp_tok,
            "total": total_prompt_tok + total_comp_tok
        },
        "duration_sec": round(dur, 2)
    }
    return record

async def run_engine(target_turns: int = 1000000, concurrency: int = 3, model: str = "Yukiai:e2b", batch_size: int = 1000):
    init_db()
    current = get_current_stats()
    current_turns = current["turns"]
    current_dialogues = current["dialogues"]
    
    print(f"\n=======================================================")
    print(f"🌊 NouGen 1M Turns Engine Starting")
    print(f"=======================================================")
    print(f"Model: {model}")
    print(f"Active Turns in Vault: {current_turns:,} / {target_turns:,}")
    print(f"Active Dialogues: {current_dialogues:,}")
    print(f"Concurrency Slots: {concurrency}")
    print(f"Storage: {TURNS_DIR}")
    print(f"=======================================================\n")
    
    if current_turns >= target_turns:
        print(f"Goal already reached! Total turns: {current_turns:,}")
        return
        
    turns_needed = target_turns - current_turns
    dialogues_needed = (turns_needed + 3) // 4
    
    queue = asyncio.Queue()
    for i in range(dialogues_needed):
        domain = DOMAINS[i % len(DOMAINS)]
        await queue.put((current_dialogues + i + 1, domain))
        
    start_time = time.time()
    turns_generated_this_run = 0
    tokens_generated_this_run = 0
    
    # Prepare batch file
    batch_num = (current_dialogues // batch_size) + 1
    current_batch_file = TURNS_DIR / f"turns_batch_{batch_num:04d}.jsonl"
    batch_file_handle = open(current_batch_file, "a", encoding="utf-8")
    
    conn = sqlite3.connect(PROGRESS_DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO runs (started_at, model, target_turns, status) VALUES (?, ?, ?, 'RUNNING')",
                (datetime.datetime.now(datetime.timezone.utc).isoformat(), model, target_turns))
    run_id = cur.lastrowid
    conn.commit()
    
    async with httpx.AsyncClient(timeout=180.0) as http_session:
        async def worker(worker_id: int):
            nonlocal turns_generated_this_run, tokens_generated_this_run, batch_file_handle, batch_num, current_batch_file
            while not queue.empty():
                try:
                    idx, domain_info = await queue.get()
                except asyncio.QueueEmpty:
                    break
                    
                try:
                    record = await generate_dialogue(http_session, model, domain_info, idx)
                    
                    # Write JSONL
                    line = json.dumps(record, ensure_ascii=False) + "\n"
                    batch_file_handle.write(line)
                    batch_file_handle.flush()
                    
                    # Update SQLite
                    cur.execute("""
                    INSERT OR REPLACE INTO dialogues 
                    (id, domain, turns_count, prompt_tokens, completion_tokens, batch_file, duration_sec, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record["id"],
                        record["domain"],
                        record["turns_count"],
                        record["tokens"]["prompt"],
                        record["tokens"]["completion"],
                        str(current_batch_file.name),
                        record["duration_sec"],
                        record["timestamp"]
                    ))
                    conn.commit()
                    
                    turns_generated_this_run += record["turns_count"]
                    tokens_generated_this_run += record["tokens"]["completion"]
                    
                    # Rotate batch file if limit reached
                    if (current_dialogues + (turns_generated_this_run // 4)) % batch_size == 0:
                        batch_file_handle.close()
                        batch_num += 1
                        current_batch_file = TURNS_DIR / f"turns_batch_{batch_num:04d}.jsonl"
                        batch_file_handle = open(current_batch_file, "a", encoding="utf-8")
                    
                    elapsed = time.time() - start_time
                    tok_s = tokens_generated_this_run / elapsed if elapsed > 0 else 0
                    turns_s = turns_generated_this_run / elapsed if elapsed > 0 else 0
                    
                    # Telemetry readout
                    print(f"[Slot {worker_id}] Dia #{idx:06d} [{record['domain'][:16]:16s}] "
                          f"+{record['turns_count']} turns ({record['duration_sec']}s, {record['tokens']['completion']} tok) | "
                          f"Total: {current_turns + turns_generated_this_run:,} turns | "
                          f"{tok_s:.1f} tok/s | {turns_s:.2f} turns/s")
                    
                except Exception as e:
                    print(f"[Slot {worker_id}] Error generating dialogue #{idx}: {e}")
                    await asyncio.sleep(2)
                finally:
                    queue.task_done()
                    
        # Launch worker pool
        workers = [asyncio.create_task(worker(i + 1)) for i in range(concurrency)]
        await asyncio.gather(*workers)
        
    batch_file_handle.close()
    cur.execute("UPDATE runs SET status = 'COMPLETED' WHERE id = ?", (run_id,))
    conn.commit()
    conn.close()
    
    total_elapsed = time.time() - start_time
    print(f"\n=======================================================")
    print(f"✅ Session Finished!")
    print(f"Turns Added: {turns_generated_this_run:,}")
    print(f"Tokens Generated: {tokens_generated_this_run:,}")
    print(f"Time Elapsed: {datetime.timedelta(seconds=int(total_elapsed))}")
    print(f"=======================================================\n")

def print_stats():
    stats = get_current_stats()
    print("\n--- NouGen 1M Turns Pre-Training Telemetry ---")
    print(f"Total Dialogues: {stats['dialogues']:,}")
    print(f"Total Turns:     {stats['turns']:,}")
    print(f"Total Tokens:    {stats['tokens']:,}")
    
    if PROGRESS_DB.exists():
        conn = sqlite3.connect(PROGRESS_DB)
        cur = conn.cursor()
        cur.execute("SELECT domain, COUNT(*), SUM(turns_count), SUM(completion_tokens) FROM dialogues GROUP BY domain;")
        rows = cur.fetchall()
        if rows:
            print("\nDomain Distribution:")
            for r in rows:
                print(f"  * {r[0]:28s}: {r[1]:5d} dialogues ({r[2]:6d} turns, {r[3]:8d} tokens)")
        conn.close()
    print("----------------------------------------------\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NouGen 1M Turns Engine")
    parser.add_argument("--run", action="store_true", help="Start generating turns")
    parser.add_argument("--target-turns", type=int, default=1000000, help="Target turn count (default: 1,000,000)")
    parser.add_argument("--concurrency", type=int, default=3, help="Concurrent async worker slots (default: 3)")
    parser.add_argument("--model", type=str, default="Yukiai:e2b", help="Local Ollama model (default: Yukiai:e2b)")
    parser.add_argument("--batch-size", type=int, default=1000, help="Dialogues per JSONL batch file (default: 1000)")
    parser.add_argument("--stats", action="store_true", help="Print current progress stats")
    
    args = parser.parse_args()
    
    if args.stats or not args.run:
        print_stats()
        if not args.run:
            print("Use --run to start generation.")
            sys.exit(0)
            
    try:
        asyncio.run(run_engine(
            target_turns=args.target_turns,
            concurrency=args.concurrency,
            model=args.model,
            batch_size=args.batch_size
        ))
    except KeyboardInterrupt:
        print("\n[Engine paused by user. Progress saved in database.]")
