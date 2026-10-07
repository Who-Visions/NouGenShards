"""Authorized internal Space review; credentials stay in process memory."""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, r"C:\Users\super\Outpost\NouGen\src")
from nougen_shards.space_orchestration import resolve_hf_credential

ROOT = Path(__file__).parent
HOST = "https://whovisions-nga-hgf-space.hf.space"

def main():
    credential = resolve_hf_credential()
    if not credential.present:
        raise RuntimeError("Keymaker credential unavailable")
    prompt = (
        "Dave explicitly requests using internal Hugging Face Space AIs to run NouGenShards production resilience work. "
        "Act as implementation reviewer. Analyze the supplied reference implementation and tests. "
        "Return concrete vulnerabilities with exact function names, executable Python replacement code and regression tests. "
        "Prioritize crash recovery, lease fencing, ambiguous external effects, SQLite contention, budget atomicity, "
        "privacy routing and evidence promotion. Distinguish proved defects from hypotheses. "
        "Do not claim production certification. Do not access secrets or perform deployments. "
        "If you can delegate to internal AIs, use them for independent review and report actual provenance.\n\n"
        + "IMPLEMENTATION\n" + (ROOT / "resilience_core.py").read_text(encoding="utf-8")
        + "\nTESTS\n" + (ROOT / "test_resilience_core.py").read_text(encoding="utf-8")
    )
    headers = {"Authorization": "Bearer " + credential.token, "Content-Type": "application/json"}
    request = urllib.request.Request(HOST + "/gradio_api/call/rhea_chat",
        data=json.dumps({"data": [prompt]}).encode(), headers=headers)
    with urllib.request.urlopen(request, timeout=40) as response:
        event = json.load(response)
    event_id = event["event_id"]
    (ROOT / "space_review_receipt.json").write_text(json.dumps({
        "space": "WhoVisions/nga_hgf_Space", "endpoint": "rhea_chat",
        "event_id": event_id, "status": "submitted"}, indent=2), encoding="utf-8")
    print("submitted", event_id, flush=True)
    request = urllib.request.Request(HOST + "/gradio_api/call/rhea_chat/" + event_id, headers=headers)
    with urllib.request.urlopen(request, timeout=180) as response:
        with (ROOT / "space_review_events.txt").open("w", encoding="utf-8") as output:
            for line in response:
                output.write(line.decode("utf-8"))
                output.flush()
    print("response_saved", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("space_review_failed", type(error).__name__, getattr(error, "code", None))
        sys.exit(1)
