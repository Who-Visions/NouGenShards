import concurrent.futures
import json
import urllib.request
from pathlib import Path
from nougen_shards.space_orchestration import resolve_hf_credential
ROOT = Path(__file__).parent
TASKS = {
    "journal": "Implement a Python SQLite external-effect journal with PREPARED/DISPATCHED/COMMITTED states. Stable idempotency key and payload hash; owner and monotonic fencing epoch. A crash after dispatch must require trusted reconciliation, never blind replay. Give a compact implementation and two regression tests. Explain remaining external adapter guarantees.",
    "budget": "Implement a compact Python SQLite shared budget ledger for concurrent AI workers. Reserve atomically under BEGIN IMMEDIATE; idempotent reservation IDs with payload binding; reject NaN, infinity and negative costs; immutable run limits. Give executable code and concurrency regression test. Discuss exact units and contention.",
    "evidence": "Implement a compact Python evidence promotion gate for NouGenShards. Bind candidate/source/environment hashes and trusted verifier identity, count independent provenance groups rather than model votes, reject critical refutations irrespective of ordering, reject nonfinite metrics and resource regression. Return executable code and tests; bounded tests must never imply formal equivalence."
}
def main():
    c = resolve_hf_credential()
    if not c.present:
        raise RuntimeError("Keymaker credential unavailable")
    def run(item):
        name, prompt = item
        body = {"model": "Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf",
            "messages": [{"role": "system", "content": "You are a production resilience implementation engineer. Give concise concrete Python code. Do not claim tests were executed. /no_think"},
                         {"role": "user", "content": prompt}],
            "max_tokens": 900, "temperature": 0.2, "stream": False}
        req = urllib.request.Request("https://whovisions-qwen-aggressive-chat.hf.space/v1/chat/completions",
            data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + c.token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=1200) as response:
                result = json.load(response)
            (ROOT / ("qwen_" + name + ".json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(name, "response_saved", flush=True)
        except Exception as error:
            (ROOT / ("qwen_" + name + ".json")).write_text(json.dumps({"error_type": type(error).__name__, "http_status": getattr(error, "code", None)}), encoding="utf-8")
            print(name, "failed", type(error).__name__, getattr(error, "code", None), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(run, TASKS.items()))
if __name__ == "__main__":
    main()
