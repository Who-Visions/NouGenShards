"""
Token Fuse & Task Circuit Breaker (Module: Coach Token Ceiling).
Implements machine-enforced token budgets, task lease allocation, real-time burn velocity,
and automatic circuit breaking to prevent runaway multi-million token consumption during
Ultra-Code / agentic test executions (Relay Directive 20260913T165628Z).
"""

import os
import json
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict

# Default hard token limits (Env configurable)
DEFAULT_MAX_SESSION_TOKENS = int(os.environ.get("NOUGEN_MAX_SESSION_TOKENS", "250000"))
DEFAULT_MAX_TASK_TOKENS = int(os.environ.get("NOUGEN_MAX_TASK_TOKENS", "50000"))
DEFAULT_MAX_CONCURRENT_TASKS = int(os.environ.get("NOUGEN_MAX_CONCURRENT_TASKS", "4"))
DEFAULT_WARN_THRESHOLD_PCT = float(os.environ.get("NOUGEN_BUDGET_WARN_PCT", "0.80"))

STATE_DIR = Path.home() / ".nougen" / "state"
FUSE_STORE = STATE_DIR / "token_fuse_ledger.json"


@dataclass
class TaskUsage:
    task_id: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_creation: int = 0
    invocations: int = 0
    active: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read + self.cache_creation


class TokenFuseBreaker(Exception):
    """Raised when a hard token or task ceiling is tripped."""
    pass


class TokenFuse:
    _instance = None
    _lock = threading.Lock()

    def __init__(
        self,
        session_id: str = "default",
        max_session_tokens: int = DEFAULT_MAX_SESSION_TOKENS,
        max_task_tokens: int = DEFAULT_MAX_TASK_TOKENS,
        max_tasks: int = DEFAULT_MAX_CONCURRENT_TASKS,
        warn_pct: float = DEFAULT_WARN_THRESHOLD_PCT
    ):
        self.session_id = session_id
        self.max_session_tokens = max_session_tokens
        self.max_task_tokens = max_task_tokens
        self.max_tasks = max_tasks
        self.warn_pct = warn_pct
        self.tasks: Dict[str, TaskUsage] = {}
        self.tripped = False
        self.trip_reason = ""
        self._load_ledger()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _load_ledger(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if FUSE_STORE.exists():
            try:
                with open(FUSE_STORE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for tid, tdata in data.get("tasks", {}).items():
                        self.tasks[tid] = TaskUsage(**tdata)
            except Exception:
                pass

    def _save_ledger(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(FUSE_STORE, "w", encoding="utf-8") as f:
                json.dump({
                    "session_id": self.session_id,
                    "max_session_tokens": self.max_session_tokens,
                    "cumulative_tokens": self.cumulative_tokens,
                    "tripped": self.tripped,
                    "trip_reason": self.trip_reason,
                    "tasks": {k: asdict(v) for k, v in self.tasks.items()}
                }, f, indent=2)
        except Exception:
            pass

    @property
    def cumulative_tokens(self) -> int:
        return sum(t.total_tokens for t in self.tasks.values())

    @property
    def active_tasks_count(self) -> int:
        return sum(1 for t in self.tasks.values() if t.active)

    def request_task_lease(self, task_id: str, model: str = "unknown") -> bool:
        """Request a lease to spawn a background child or execute an Ultra-Code task."""
        with self._lock:
            if self.tripped:
                raise TokenFuseBreaker(f"Circuit breaker active: {self.trip_reason}")

            # Check session token headroom
            if self.cumulative_tokens >= self.max_session_tokens:
                self.tripped = True
                self.trip_reason = f"Session budget {self.max_session_tokens} tokens exceeded"
                self._save_ledger()
                raise TokenFuseBreaker(self.trip_reason)

            # Check concurrent task ceiling
            if self.active_tasks_count >= self.max_tasks:
                raise TokenFuseBreaker(
                    f"Concurrent task ceiling reached ({self.active_tasks_count}/{self.max_tasks}). Prohibiting fan-out."
                )

            self.tasks[task_id] = TaskUsage(task_id=task_id, model=model)
            self._save_ledger()
            return True

    def record_usage(
        self,
        task_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read: int = 0,
        cache_creation: int = 0,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Record granular token spend and evaluate real-time circuit breakers."""
        with self._lock:
            if task_id not in self.tasks:
                self.tasks[task_id] = TaskUsage(task_id=task_id, model=model or "unknown")

            t = self.tasks[task_id]
            t.input_tokens += input_tokens
            t.output_tokens += output_tokens
            t.cache_read += cache_read
            t.cache_creation += cache_creation
            t.invocations += 1
            t.updated_at = time.time()
            if model:
                t.model = model

            cum_tokens = self.cumulative_tokens

            # Evaluate Warning Threshold
            warning_triggered = (cum_tokens >= self.max_session_tokens * self.warn_pct)

            # Evaluate Per-Task Hard Limit
            if t.total_tokens > self.max_task_tokens:
                t.active = False
                self._save_ledger()
                raise TokenFuseBreaker(
                    f"Task {task_id} exceeded hard limit ({t.total_tokens}/{self.max_task_tokens} tokens). Task halted."
                )

            # Evaluate Session Hard Limit
            if cum_tokens >= self.max_session_tokens:
                self.tripped = True
                self.trip_reason = f"Session hard limit exceeded ({cum_tokens}/{self.max_session_tokens} tokens)"
                for task in self.tasks.values():
                    task.active = False
                self._save_ledger()
                raise TokenFuseBreaker(self.trip_reason)

            self._save_ledger()
            return {
                "task_tokens": t.total_tokens,
                "cumulative_tokens": cum_tokens,
                "warning_level": "HIGH" if warning_triggered else "NOMINAL",
                "fanout_allowed": not warning_triggered,
                "tripped": self.tripped
            }

    def close_task(self, task_id: str):
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].active = False
                self._save_ledger()

    def reset(self):
        with self._lock:
            self.tasks.clear()
            self.tripped = False
            self.trip_reason = ""
            self._save_ledger()
