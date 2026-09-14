"""
NouGen Token Hypervisor v1.0 (Codename: Coach Governor).
Canonical runtime implementation of the Token Hypervisor YAML specification (Relay Directive 20260913T170403Z).

Prime Directive:
"Models may request resources. Models never authorize their own resources."
"Provider availability never implies NouGen authorization."
"A provider quota or session limit must never become NouGen's first effective circuit breaker."
"Prompting encourages efficiency. The NouGen Governor enforces it."
"""

import os
import json
import time
import threading
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field, asdict

STATE_DIR = Path.home() / ".nougen" / "state"
GOVERNOR_STORE = STATE_DIR / "governor_state.json"
GOVERNOR_TELEMETRY = STATE_DIR / "governor_telemetry.json"


class ExecutionMode(str, Enum):
    COACH = "coach"
    ULTRA_CODE = "ultra_code"


class CircuitBreakerLevel(str, Enum):
    NORMAL = "normal"           # 0..59%: continue
    WATCH = "watch"             # 60..79%: increase telemetry, reject speculative exploration
    THROTTLE = "throttle"       # 80..89%: reduce reasoning, compact context, reduce parallelism
    CONTAINMENT = "containment" # 90..94%: prohibit new children, finish active critical path only
    CHECKPOINT = "checkpoint"   # 95..99%: stop new tool calls, generate checkpoint, prepare termination
    KILL = "kill"               # >=100%: cancel children/tools, revoke leases, terminate session


class GovernorException(Exception):
    """Base exception raised by Governor when safety policies or limits are breached."""
    pass


class BudgetExhaustedException(GovernorException):
    pass


class FanoutViolationException(GovernorException):
    pass


class LoopDetectedException(GovernorException):
    pass


@dataclass
class ModeConfig:
    mode: ExecutionMode
    soft_tokens: int
    hard_tokens: int
    max_turns: int
    max_children: int
    max_parallel_tools: int
    target_output_tokens: int


MODE_SPECS: Dict[ExecutionMode, ModeConfig] = {
    ExecutionMode.COACH: ModeConfig(
        mode=ExecutionMode.COACH,
        soft_tokens=5000,
        hard_tokens=10000,
        max_turns=3,
        max_children=0,
        max_parallel_tools=2,
        target_output_tokens=500
    ),
    ExecutionMode.ULTRA_CODE: ModeConfig(
        mode=ExecutionMode.ULTRA_CODE,
        soft_tokens=250000,
        hard_tokens=400000,
        max_turns=30,
        max_children=4,
        max_parallel_tools=6,
        target_output_tokens=4000
    )
}


@dataclass
class LeaseReservation:
    lease_id: str
    session_id: str
    task_id: str
    agent_id: str
    model: str
    provider: str
    tokens_reserved: int
    created_at: float = field(default_factory=time.time)
    active: bool = True


@dataclass
class TokenAccounting:
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    cache_create_tokens: int = 0
    tool_context_tokens: int = 0

    @property
    def total_billable_tokens(self) -> int:
        return (
            self.input_tokens +
            self.output_tokens +
            self.reasoning_tokens +
            self.cache_read_tokens +
            self.cache_create_tokens +
            self.tool_context_tokens
        )


class TokenHypervisor:
    _instance = None
    _lock = threading.Lock()

    def __init__(self, mode: ExecutionMode = ExecutionMode.ULTRA_CODE, session_id: str = "default"):
        self.session_id = session_id
        self.mode = mode
        self.config = MODE_SPECS.get(mode, MODE_SPECS[ExecutionMode.ULTRA_CODE])
        self.accounting = TokenAccounting()
        self.leases: Dict[str, LeaseReservation] = {}
        self.active_children: Dict[str, str] = {} # child_id -> parent_id
        self.recent_tool_calls: List[Tuple[float, str, str]] = [] # ts, tool_name, arg_hash
        self.is_killed = False
        self.kill_reason = ""
        self.checkpoint_state: Dict[str, Any] = {}
        self._load_state()

    @classmethod
    def get_instance(cls, mode: Optional[ExecutionMode] = None, session_id: str = "default"):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(mode=mode or ExecutionMode.ULTRA_CODE, session_id=session_id)
            elif mode and cls._instance.mode != mode:
                cls._instance.set_mode(mode)
            return cls._instance

    def set_mode(self, mode: ExecutionMode):
        with self._lock:
            self.mode = mode
            self.config = MODE_SPECS.get(mode, MODE_SPECS[ExecutionMode.ULTRA_CODE])
            self._save_state()

    def _load_state(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if GOVERNOR_STORE.exists():
            try:
                with open(GOVERNOR_STORE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.is_killed = data.get("is_killed", False)
                    self.kill_reason = data.get("kill_reason", "")
            except Exception:
                pass

    def _save_state(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(GOVERNOR_STORE, "w", encoding="utf-8") as f:
                json.dump({
                    "session_id": self.session_id,
                    "mode": self.mode.value,
                    "total_tokens": self.accounting.total_billable_tokens,
                    "circuit_level": self.get_circuit_breaker_level().value,
                    "is_killed": self.is_killed,
                    "kill_reason": self.kill_reason,
                    "active_children_count": len(self.active_children),
                    "active_leases": len([l for l in self.leases.values() if l.active])
                }, f, indent=2)
        except Exception:
            pass

    def get_circuit_breaker_level(self) -> CircuitBreakerLevel:
        """Evaluate real-time percentage against hard budget."""
        if self.is_killed:
            return CircuitBreakerLevel.KILL

        used = self.accounting.total_billable_tokens
        hard = self.config.hard_tokens
        pct = (used / hard) * 100.0 if hard > 0 else 100.0

        if pct < 60.0:
            return CircuitBreakerLevel.NORMAL
        elif 60.0 <= pct < 80.0:
            return CircuitBreakerLevel.WATCH
        elif 80.0 <= pct < 90.0:
            return CircuitBreakerLevel.THROTTLE
        elif 90.0 <= pct < 95.0:
            return CircuitBreakerLevel.CONTAINMENT
        elif 95.0 <= pct < 100.0:
            return CircuitBreakerLevel.CHECKPOINT
        else:
            return CircuitBreakerLevel.KILL

    def request_budget_lease(
        self,
        task_id: str,
        agent_id: str,
        model: str,
        provider: str,
        tokens_requested: int
    ) -> LeaseReservation:
        """
        Reserve tokens before model or expensive tool execution.
        Strategy: reserve_before_execution (no overcommit allowed).
        """
        with self._lock:
            if self.is_killed:
                raise GovernorException(f"Governor Emergency Stop is active: {self.kill_reason}")

            current_level = self.get_circuit_breaker_level()
            if current_level in [CircuitBreakerLevel.CHECKPOINT, CircuitBreakerLevel.KILL]:
                raise BudgetExhaustedException(
                    f"Governor at {current_level.value.upper()} level ({self.accounting.total_billable_tokens}/{self.config.hard_tokens} tokens). Lease denied."
                )

            current_used = self.accounting.total_billable_tokens
            reserved_total = sum(l.tokens_reserved for l in self.leases.values() if l.active)
            remaining_headroom = self.config.hard_tokens - (current_used + reserved_total)

            if tokens_requested > remaining_headroom:
                # Shrink or deny
                if remaining_headroom <= 0:
                    raise BudgetExhaustedException(
                        f"Zero token headroom remaining ({remaining_headroom} tokens). Lease denied."
                    )
                tokens_granted = remaining_headroom
            else:
                tokens_granted = tokens_requested

            lease_id = f"lease_{task_id}_{int(time.time()*1000)}"
            lease = LeaseReservation(
                lease_id=lease_id,
                session_id=self.session_id,
                task_id=task_id,
                agent_id=agent_id,
                model=model,
                provider=provider,
                tokens_reserved=tokens_granted
            )
            self.leases[lease_id] = lease
            self._save_state()
            return lease

    def record_usage(
        self,
        lease_id: Optional[str],
        input_tokens: int = 0,
        output_tokens: int = 0,
        reasoning_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_create_tokens: int = 0,
        tool_context_tokens: int = 0
    ) -> Dict[str, Any]:
        """Record actual token consumption and release reservation."""
        with self._lock:
            if lease_id and lease_id in self.leases:
                self.leases[lease_id].active = False

            self.accounting.input_tokens += input_tokens
            self.accounting.output_tokens += output_tokens
            self.accounting.reasoning_tokens += reasoning_tokens
            self.accounting.cache_read_tokens += cache_read_tokens
            self.accounting.cache_create_tokens += cache_create_tokens
            self.accounting.tool_context_tokens += tool_context_tokens

            level = self.get_circuit_breaker_level()
            if level == CircuitBreakerLevel.KILL and not self.is_killed:
                self.is_killed = True
                self.kill_reason = f"Hard token budget of {self.config.hard_tokens} reached ({self.accounting.total_billable_tokens} used)"
                self._create_checkpoint()

            self._save_state()
            return {
                "total_tokens": self.accounting.total_billable_tokens,
                "circuit_level": level.value,
                "remaining_budget": max(0, self.config.hard_tokens - self.accounting.total_billable_tokens),
                "is_killed": self.is_killed
            }

    def request_child_agent_spawn(self, parent_id: str, child_id: str, purpose: str) -> bool:
        """Enforce child agent fan-out bounds and lease requirements."""
        with self._lock:
            if self.is_killed:
                raise FanoutViolationException("Governor killed. Cannot spawn child agents.")

            level = self.get_circuit_breaker_level()
            if level in [CircuitBreakerLevel.CONTAINMENT, CircuitBreakerLevel.CHECKPOINT, CircuitBreakerLevel.KILL]:
                raise FanoutViolationException(
                    f"Fan-out prohibited at circuit breaker level {level.value.upper()}."
                )

            if len(self.active_children) >= self.config.max_children:
                raise FanoutViolationException(
                    f"Child agent ceiling reached ({len(self.active_children)}/{self.config.max_children}). Prohibiting fan-out."
                )

            # Prevent recursive child spawning
            if parent_id in self.active_children:
                raise FanoutViolationException("Recursive child agent spawning is strictly prohibited.")

            self.active_children[child_id] = parent_id
            self._save_state()
            return True

    def record_tool_call(self, tool_name: str, arguments: Dict[str, Any]):
        """Loop detection: detect identical repeated tool calls."""
        with self._lock:
            now = time.time()
            arg_str = json.dumps(arguments, sort_keys=True)
            self.recent_tool_calls.append((now, tool_name, arg_str))
            # Keep last 20
            self.recent_tool_calls = self.recent_tool_calls[-20:]

            # Count duplicates in recent window
            matches = sum(1 for _, tname, args in self.recent_tool_calls[-5:] if tname == tool_name and args == arg_str)
            if matches >= 5:
                raise LoopDetectedException(
                    f"Runaway loop detected: Tool '{tool_name}' invoked 5 times with identical arguments. Circuit broken."
                )

    def emergency_stop(self, reason: str = "User /nougen kill"):
        """Emergency halt: revoke all leases, terminate children, save checkpoint."""
        with self._lock:
            self.is_killed = True
            self.kill_reason = reason
            for l in self.leases.values():
                l.active = False
            self.active_children.clear()
            self._create_checkpoint()
            self._save_state()

    def _create_checkpoint(self):
        """Persist compact recovery checkpoint."""
        self.checkpoint_state = {
            "timestamp": time.time(),
            "session_id": self.session_id,
            "mode": self.mode.value,
            "tokens_used": self.accounting.total_billable_tokens,
            "kill_reason": self.kill_reason,
            "accounting": asdict(self.accounting)
        }
        with open(STATE_DIR / "governor_checkpoint.json", "w", encoding="utf-8") as f:
            json.dump(self.checkpoint_state, f, indent=2)

    def reset(self):
        """Explicit administrative reset."""
        with self._lock:
            self.accounting = TokenAccounting()
            self.leases.clear()
            self.active_children.clear()
            self.recent_tool_calls.clear()
            self.is_killed = False
            self.kill_reason = ""
            self._save_state()
