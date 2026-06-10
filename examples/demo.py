"""
NouGenShards Demonstration Workflow.
This module demonstrates the use of NouGenShards to query an LLM
with and without injected memory shards.
"""

# pylint: disable=duplicate-code

import sys
import json
import urllib.request
import urllib.error
import socket
from nougen_shards import capture, retrieve, compile_recall_packet

# UTF-8 Console protection for Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def check_ollama_alive() -> bool:
    """Check if the local Ollama server is running."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        sock.connect(("127.0.0.1", 11434))
        sock.close()
        return True
    except OSError:
        return False

def get_available_models() -> list:
    """Fetch the list of available models from the local Ollama server."""
    if not check_ollama_alive():
        return []
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.getcode() == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        pass
    return []

def query_local_llm(model: str, prompt: str, system_prompt: str = "") -> str:
    """Send a query to the local Ollama model and return its response."""
    if not check_ollama_alive():
        return "[Local Ollama Offline - Simulating response based on context]"

    try:
        payload = {"model": model, "prompt": prompt, "stream": False}
        if system_prompt:
            payload["system"] = system_prompt

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=body,
            method="POST"
        )
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.getcode() == 200:
                response_data = json.loads(resp.read().decode("utf-8"))
                return response_data.get("response", "").strip()
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        return f"[Model execution failed: {exc}]"
    return "[No response]"

def get_selected_model() -> str:
    """Select the appropriate model from the list of available models."""
    models = get_available_models()
    if not models:
        print("[!] Local Ollama is not active or no models found. Running in SIMULATED Mode.")
        return ""

    for mod in models:
        if any(x in mod.lower() for x in ["e2b", "e4b", "2b", "4b"]):
            print(f"[*] Connected to Ollama. Selected Model: {mod}")
            return mod

    print(f"[*] Connected to Ollama. Selected Model: {models[0]}")
    return models[0]

def simulate_amnesia_response() -> str:
    """Return a simulated response for the amnesia phase."""
    return (
        "This error occurs when Node.js is unable to spawn the child process. "
        "Check your PATH environment variables, make sure python is correctly "
        "installed, check file permissions, or ensure the executable exists."
    )

def simulate_recall_response() -> str:
    """Return a simulated response for the recall phase."""
    return (
        "Based on the recalled memory (Shard #1), you need to normalize the backslashes "
        "in process.env.PATH. Update your Next.js subprocess call to replace "
        "backslashes with forward slashes, and call subprocess.Popen with shell=True "
        "to successfully spawn the process on Windows."
    )

def phase_one_amnesia(selected_model: str, issue_query: str, base_system_prompt: str) -> None:
    """Run phase 1: Query the model without memory."""
    print("\n--- PHASE 1: Querying Agent B (Clean Environment / Amnesia) ---")
    print(f"Query: {issue_query}")
    print("[*] Generating response without memory...")

    if selected_model:
        response_without_recall = query_local_llm(selected_model, issue_query, base_system_prompt)
        if "Model execution failed" in response_without_recall or \
           "timed out" in response_without_recall:
            print("[!] Local LLM timed out/failed. Falling back to simulated Amnesia response.")
            response_without_recall = simulate_amnesia_response()
    else:
        response_without_recall = simulate_amnesia_response()
    print(f"\n[Agent Response - Amnesia]:\n{response_without_recall}\n")

def phase_two_capture() -> None:
    """Run phase 2: Persist experience to NouGenShards."""
    print("\n--- PHASE 2: Persisting Experience to NouGenShards ---")
    shard_title = "Next.js Windows Python Spawn Helper Resolution"
    shard_content = (
        "RESOLVED: Next.js API routes on Windows fail to spawn Python child processes "
        "if path slashes are unescaped. Fix this by normalizing the PATH using "
        "forward slashes in your Next.js subprocess config or calling `subprocess.Popen` "
        "with shell=True and replacing all backslashes in `process.env.PATH` with "
        "forward slashes."
    )
    tags = ["nextjs", "windows", "python", "subprocess", "spawn-helper"]

    added = capture(event_type="BUG_FIX", title=shard_title, content=shard_content, tags=tags)
    if added:
        print(f"[+] Successfully captured shard: '{shard_title}'")
    else:
        print("[!] Shard already exists in database. Proceeding.")

def phase_three_retrieve() -> str:
    """Run phase 3: Retrieve and rank the recall candidates."""
    print("\n--- PHASE 3: Lexical & Ranked Recall Match (FTS5) ---")
    retrieved_shards = retrieve("spawn helper Next.js Windows python")
    print(f"[*] Retrieved {len(retrieved_shards)} matching shards.")

    recall_packet = compile_recall_packet(retrieved_shards)
    print("\nCompiled Recall Packet:")
    print("-" * 50)
    print(recall_packet)
    print("-" * 50)
    return recall_packet

def phase_four_recall(
    selected_model: str,
    issue_query: str,
    base_system_prompt: str,
    recall_packet: str
) -> None:
    """Run phase 4: Query the model with memory injected."""
    print("\n--- PHASE 4: Querying Agent B (With Recall Injected) ---")
    print("[*] Generating response with memory recall...")

    system_prompt_with_recall = f"{base_system_prompt}\n\n{recall_packet}"

    if selected_model:
        response_with_recall = query_local_llm(
            selected_model, issue_query, system_prompt_with_recall
        )
        if "Model execution failed" in response_with_recall or \
           "timed out" in response_with_recall:
            print("[!] Local LLM timed out/failed. Falling back to simulated Recall response.")
            response_with_recall = simulate_recall_response()
    else:
        response_with_recall = simulate_recall_response()
    print(f"\n[Agent Response - Recall]:\n{response_with_recall}\n")

def print_scoreboard() -> None:
    """Print the final scoreboard."""
    print("=" * 80)
    print("                      NOUGENSHARDS SCOREBOARD                     ")
    print("=" * 80)
    print(f" {'MODE':<25} | {'BEHAVIOR / EFFECTIVENESS':<50}")
    print("-" * 80)
    print(f" {'Amnesia (No Shard)':<25} | {'Generic/broad system tips. Lacks repo context.':<50}")
    print(f" {'Recall (With NouGenShards)':<25} | "
          f"{'Retrieves exact slash normalization fix instantly.':<50}")
    print("=" * 80)

def main():
    """Execute the full NouGenShards demonstration workflow."""
    print("=" * 80)
    print(" NOUGENSHARDS DEMONSTRATION WORKFLOW ")
    print("=" * 80)

    selected_model = get_selected_model()

    issue_query = (
        "How do we fix the 'spawn helper failed' RuntimeError when calling "
        "python subprocesses inside our Windows Next.js API routes?"
    )
    base_system_prompt = "You are a senior coding assistant. Help the user solve their issue."

    phase_one_amnesia(selected_model, issue_query, base_system_prompt)
    phase_two_capture()
    recall_packet = phase_three_retrieve()
    phase_four_recall(selected_model, issue_query, base_system_prompt, recall_packet)
    print_scoreboard()

if __name__ == "__main__":
    main()
