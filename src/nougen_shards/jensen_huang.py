"""Jensen Huang agent: fan work out to many parallel NVIDIA NIM lanes.

The agent is named for the NVIDIA CEO, per the operator's order. It wraps
:class:`nougen_shards.nvidia_nim.NvidiaNimClient` and runs a list of tasks
concurrently — up to 50 lanes by default — each lane calling the NIM chat
endpoint with the client's per-model fallthrough.

The NVIDIA key is never held here: every lane builds its own client, which
resolves ``NVIDIA_API_KEY`` from the Keymaker at runtime. On a machine with
no local secrets store the client reports the key missing and every task
records a clean per-task error instead of raising. One failing task never
kills the others, and the key value is never logged, printed, or persisted.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .nvidia_nim import VERIFIED_CHAT_MODELS, NvidiaNimClient

DEFAULT_LANES = 50
DEFAULT_MAX_TOKENS = 1024
_MISSING_KEY_MARKER = "NVIDIA_API_KEY missing"


def _resolve_lanes(lanes: Optional[int]) -> int:
    """Lanes from the caller, else ``NOUGEN_JENSEN_LANES``, else 50."""
    if lanes is not None:
        resolved = lanes
    else:
        try:
            resolved = int(os.getenv("NOUGEN_JENSEN_LANES", str(DEFAULT_LANES)))
        except ValueError:
            resolved = DEFAULT_LANES
    if resolved < 1:
        raise ValueError(f"lanes must be >= 1, got {resolved}")
    return resolved


def _task_messages(task: Dict[str, Any]) -> List[Dict[str, str]]:
    """Chat messages for one task dict: ``messages`` wins, else ``prompt``."""
    if task.get("messages"):
        return list(task["messages"])
    prompt = task.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        raise ValueError("task needs a non-empty 'prompt' or a 'messages' list")
    return [{"role": "user", "content": prompt}]


class JensenHuang:
    """Run prompts across NVIDIA NIM on many parallel lanes.

    Args:
        api_key: Passed to each lane's client; None resolves it from the
            Keymaker at runtime (``NVIDIA_API_KEY``).
        lanes: Default lane count for :meth:`fan_out`. None resolves
            ``NOUGEN_JENSEN_LANES`` with a fallback of 50.
        models: Model chain each lane tries; None reuses the client's
            verified chat models. A per-task ``"model"`` overrides this.
        max_tokens: Per-call token cap handed to ``NvidiaNimClient.chat``.
    """

    def __init__(self, api_key: Optional[str] = None, lanes: Optional[int] = None,
                 models: Optional[Sequence[str]] = None,
                 max_tokens: int = DEFAULT_MAX_TOKENS) -> None:
        self.api_key = api_key
        self.lanes = _resolve_lanes(lanes)
        self.models = tuple(models) if models else VERIFIED_CHAT_MODELS
        self.max_tokens = max_tokens

    def _new_client(self) -> NvidiaNimClient:
        """One client per task, so no mutable client state is shared across threads."""
        return NvidiaNimClient(api_key=self.api_key)

    def _run_one(self, task: Dict[str, Any], task_id: Any) -> Dict[str, Any]:
        """Run a single task on its own lane; never raises.

        Returns ``{id, model, content, status, error, latency_s}`` where
        ``status`` is ``"ok"`` or ``"error"``.
        """
        started = time.perf_counter()
        model = task.get("model") or "auto"
        try:
            messages = _task_messages(task)
        except (ValueError, AttributeError, TypeError) as exc:
            return {
                "id": task_id,
                "model": None,
                "content": "",
                "status": "error",
                "error": f"bad task: {exc}",
                "latency_s": round(time.perf_counter() - started, 3),
            }
        try:
            client = self._new_client()
            content = client.chat(model, messages, max_tokens=self.max_tokens,
                                  fallbacks=self.models)
        except Exception as exc:  # noqa: BLE001 - one lane must never kill the batch
            return {
                "id": task_id,
                "model": None,
                "content": "",
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "latency_s": round(time.perf_counter() - started, 3),
            }
        latency = round(time.perf_counter() - started, 3)
        if content.startswith("Error:"):
            return {
                "id": task_id,
                "model": client.last_model,
                "content": "",
                "status": "error",
                "error": content,
                "latency_s": latency,
            }
        return {
            "id": task_id,
            "model": client.last_model or model,
            "content": content,
            "status": "ok",
            "error": None,
            "latency_s": latency,
        }

    def fan_out(self, tasks: Iterable[Dict[str, Any]],
                lanes: Optional[int] = None) -> List[Dict[str, Any]]:
        """Run ``tasks`` concurrently and return one result per task, in order.

        Each task is ``{"id": ..., "prompt": ...}`` or
        ``{"id": ..., "messages": [...]}``; an optional ``"model"`` picks the
        first model to try. ``lanes`` overrides the agent's default lane
        count for this call. A missing key, a bad task, or a failing lane
        records a per-task error; nothing here raises for a single task.
        """
        import contextvars
        worker_count = _resolve_lanes(lanes if lanes is not None else self.lanes)
        task_list = list(tasks)
        indexed = [
            (task.get("id", index) if isinstance(task, dict) else index, task)
            for index, task in enumerate(task_list)
        ]
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = [
                pool.submit(contextvars.copy_context().run, self._run_one, task, task_id)
                for task_id, task in indexed
            ]
            return [future.result() for future in futures]

    @staticmethod
    def summarize(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate counts, per-model counts, latencies, and failed ids."""
        total = len(results)
        succeeded = sum(1 for r in results if r.get("status") == "ok")
        failed = total - succeeded
        per_model: Dict[str, int] = {}
        for result in results:
            if result.get("status") == "ok" and result.get("model"):
                per_model[result["model"]] = per_model.get(result["model"], 0) + 1
        latencies = [float(r.get("latency_s") or 0.0) for r in results]
        total_latency = round(sum(latencies), 3)
        return {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "per_model": per_model,
            "total_latency_s": total_latency,
            "mean_latency_s": round(total_latency / total, 3) if total else 0.0,
            "failed_ids": [r.get("id") for r in results if r.get("status") != "ok"],
        }

    def probe(self) -> Dict[str, Any]:
        """Which verified models answer for this account, via the NIM client.

        Returns ``{"key_missing": True}`` without touching the network when
        no key resolves, so a keyless box reports the gap instead of
        burning unauthenticated calls.
        """
        client = self._new_client()
        if not client.is_alive():
            return {"key_missing": True}
        return dict(client.probe(self.models))


def _read_tasks(path: str) -> List[Dict[str, Any]]:
    """Tasks from a JSONL file; a malformed line becomes an error task."""
    tasks: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                tasks.append({"id": f"line-{number}",
                              "_malformed": f"bad JSON on line {number}: {exc}"})
                continue
            if not isinstance(parsed, dict):
                tasks.append({"id": f"line-{number}",
                              "_malformed": f"line {number} is not a JSON object"})
                continue
            tasks.append(parsed)
    return tasks


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI: fan a JSONL task file out to NIM lanes, or probe the models.

    ``--tasks`` takes one ``{"id": ..., "prompt": ...}`` per line;
    ``--out`` writes ``{"results": [...], "summary": {...}}`` as JSON.
    ``--probe`` prints which models answer and needs no task file.
    """
    parser = argparse.ArgumentParser(
        prog="nougen_shards.jensen_huang",
        description="Fan tasks out to parallel NVIDIA NIM lanes (Jensen Huang agent).")
    parser.add_argument("--tasks", help="JSONL file, one {\"id\": ..., \"prompt\": ...} per line")
    parser.add_argument("--lanes", type=int, default=None,
                        help="parallel lanes (default 50, or NOUGEN_JENSEN_LANES)")
    parser.add_argument("--out", help="write {\"results\": [...], \"summary\": {...}} JSON here")
    parser.add_argument("--probe", action="store_true",
                        help="report which verified models answer, then exit")
    args = parser.parse_args(argv)

    agent = JensenHuang(lanes=args.lanes)
    if args.probe:
        probed = agent.probe()
        if probed.get("key_missing"):
            print("NVIDIA_API_KEY missing from the Keymaker — probe cannot run.")
            return 0
        for model, status in probed.items():
            print(f"{model}: {status}")
        return 0

    if not args.tasks:
        parser.error("--tasks is required unless --probe is given")
    tasks = _read_tasks(args.tasks)
    good = [task for task in tasks if "_malformed" not in task]
    good_results = agent.fan_out(good)
    results: List[Dict[str, Any]] = []
    good_iter = iter(good_results)
    for task in tasks:
        malformed = task.pop("_malformed", None)
        if malformed is not None:
            results.append({"id": task.get("id"), "model": None, "content": "",
                            "status": "error", "error": malformed, "latency_s": 0.0})
        else:
            results.append(next(good_iter))
    summary = JensenHuang.summarize(results)
    payload = {"results": results, "summary": summary}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    else:
        json.dump(payload, sys.stdout, indent=2)
        print()
    print(f"{summary['succeeded']}/{summary['total']} succeeded, "
          f"{summary['failed']} failed, mean {summary['mean_latency_s']}s/task")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
