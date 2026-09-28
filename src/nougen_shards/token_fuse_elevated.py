r'''
Token Fuse Elevated Mathematical Algorithm (Module: Coach Token Ceiling).
Elevates raw token counting into formal queuing dynamics, Lyapunov stability analysis,
and continuous leaky-bucket velocity estimation.

Mathematical Foundations:
1. Continuous Leaky-Bucket Dynamic:
   $B(t) = \max(0, B(t_0) e^{-\lambda (t - t_0)} + \sum_{k} \Delta T_k e^{-\lambda (t - t_k)})$
   where $\lambda > 0$ is the token dissipation rate (tokens/sec).

2. Exponential Moving Average (EMA) Burn Velocity & Acceleration:
   $v(t) = \alpha \frac{\Delta T}{\Delta t} + (1 - \alpha) v(t - \Delta t)$
   $a(t) = \frac{dv}{dt} \approx \frac{v(t) - v(t - \Delta t)}{\Delta t}$

3. Lyapunov Candidate Stability Function:
   $V(B) = \frac{1}{2} \left( \frac{B(t)}{B_{\max}} \right)^2$
   $\dot{V}(B) = \left( \frac{B(t)}{B_{\max}^2} \right) \left( \dot{B}_{in} - \lambda B(t) \right)$
   Asymptotic stability requires $\dot{V} < 0$ when $B(t) \to B_{\max}$.
   If $\dot{V} \ge 0$ as $B \ge \theta_{critical} B_{\max}$, runaway divergence is detected.

4. Multi-Task Capacity & Shanon Entropy of Token Allocation:
   $H(p) = -\sum_{i=1}^N p_i \ln p_i$, where $p_i = \frac{T_i}{\sum_j T_j}$
   Quantifies whether token burn is balanced across the swarm or monopolized by an out-of-control task.
'''

import math
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ElevatedTaskProfile:
    task_id: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_creation: int = 0
    invocations: int = 0
    active: bool = True
    created_at: float = field(default_factory=time.time)
    last_event_time: float = field(default_factory=time.time)
    instantaneous_velocity: float = 0.0  # tokens/sec

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read + self.cache_creation


class TokenFuseBreaker(Exception):
    """Raised when Lyapunov divergence, leaky bucket overflow, or hard limits trip."""
    pass


class TokenFuseElevated:
    """
    Mathematical Circuit Breaker and Token Dynamics Regulator.
    """
    def __init__(
        self,
        session_id: str = "default",
        max_session_tokens: int = 250_000,
        max_task_tokens: int = 50_000,
        max_tasks: int = 4,
        warn_pct: float = 0.80,
        leak_rate: float = 100.0,       # Lambda: tokens leaked per second
        ema_alpha: float = 0.35,        # Velocity smoothing factor
        lyapunov_threshold: float = 0.85 # Critical margin where runaway velocity triggers trip
    ):
        self.session_id = session_id
        self.max_session_tokens = max_session_tokens
        self.max_task_tokens = max_task_tokens
        self.max_tasks = max_tasks
        self.warn_pct = warn_pct
        self.leak_rate = leak_rate
        self.ema_alpha = ema_alpha
        self.lyapunov_threshold = lyapunov_threshold

        self.tasks: Dict[str, ElevatedTaskProfile] = {}
        self.tripped = False
        self.trip_reason = ""
        self._lock = threading.Lock()

        # Leaky bucket state
        self.bucket_level: float = 0.0
        self.last_leak_update: float = time.time()
        self.global_velocity: float = 0.0  # tokens/sec

    @property
    def cumulative_tokens(self) -> int:
        return sum(t.total_tokens for t in self.tasks.values())

    @property
    def active_tasks_count(self) -> int:
        return sum(1 for t in self.tasks.values() if t.active)

    def _decay_leaky_bucket(self, current_time: float):
        """Computes continuous dissipation of the leaky bucket."""
        dt = max(0.0, current_time - self.last_leak_update)
        if dt > 0.0:
            dissipated = self.leak_rate * dt
            self.bucket_level = max(0.0, self.bucket_level - dissipated)
            self.last_leak_update = current_time

    def compute_lyapunov_stability(self, current_burn_rate: float) -> Tuple[float, float, bool]:
        """
        Calculates Lyapunov function V(B) and its derivative V_dot.
        Returns: (V, V_dot, is_stable)
        """
        if self.max_session_tokens <= 0:
            return 0.0, 0.0, True

        normalized_level = self.bucket_level / self.max_session_tokens
        v_candidate = 0.5 * (normalized_level ** 2)

        # Rate of change of bucket: B_dot = burn_rate - leak_rate
        b_dot = current_burn_rate - self.leak_rate
        v_dot = (self.bucket_level / (self.max_session_tokens ** 2)) * b_dot

        # System is unstable if level is near critical threshold AND derivative is strongly positive
        is_unstable = (normalized_level >= self.lyapunov_threshold and v_dot > 0.05)
        return v_candidate, v_dot, not is_unstable

    def compute_allocation_entropy(self) -> float:
        """
        Computes Shannon entropy of token distribution across active tasks.
        H = - sum(p_i * ln(p_i)).
        Higher entropy = well-balanced swarm load.
        Zero entropy = 1 task monopolizing 100% of tokens.
        """
        active_tokens = [t.total_tokens for t in self.tasks.values() if t.active and t.total_tokens > 0]
        total_active = sum(active_tokens)
        if not active_tokens or total_active == 0:
            return 0.0

        entropy = 0.0
        for tokens in active_tokens:
            p = tokens / total_active
            entropy -= p * math.log(p)
        return entropy

    def request_task_lease(self, task_id: str, model: str = "unknown") -> bool:
        """Request lease with concurrency and budget gates."""
        with self._lock:
            now = time.time()
            self._decay_leaky_bucket(now)

            if self.tripped:
                raise TokenFuseBreaker(f"Circuit breaker active: {self.trip_reason}")

            if self.cumulative_tokens >= self.max_session_tokens:
                self.tripped = True
                self.trip_reason = f"Session budget {self.max_session_tokens} tokens exceeded"
                raise TokenFuseBreaker(self.trip_reason)

            if self.active_tasks_count >= self.max_tasks:
                raise TokenFuseBreaker(
                    f"Concurrent task ceiling reached ({self.active_tasks_count}/{self.max_tasks}). Prohibiting fan-out."
                )

            self.tasks[task_id] = ElevatedTaskProfile(
                task_id=task_id,
                model=model,
                created_at=now,
                last_event_time=now
            )
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
        """
        Records spend, updates leaky bucket & EMA velocity, evaluates Lyapunov stability,
        and halts execution if ceilings or runaway divergence conditions are met.
        """
        with self._lock:
            now = time.time()
            self._decay_leaky_bucket(now)

            if task_id not in self.tasks:
                self.tasks[task_id] = ElevatedTaskProfile(
                    task_id=task_id,
                    model=model or "unknown",
                    created_at=now,
                    last_event_time=now
                )

            task = self.tasks[task_id]
            delta_tokens = input_tokens + output_tokens + cache_read + cache_creation
            dt = max(1e-4, now - task.last_event_time)

            # Instantaneous and EMA velocity for task
            inst_task_velocity = delta_tokens / dt
            task.instantaneous_velocity = (
                self.ema_alpha * inst_task_velocity + (1.0 - self.ema_alpha) * task.instantaneous_velocity
            )

            # Update bucket level
            self.bucket_level += delta_tokens

            # Update global velocity
            self.global_velocity = (
                self.ema_alpha * inst_task_velocity + (1.0 - self.ema_alpha) * self.global_velocity
            )

            # Update task stats
            task.input_tokens += input_tokens
            task.output_tokens += output_tokens
            task.cache_read += cache_read
            task.cache_creation += cache_creation
            task.invocations += 1
            task.last_event_time = now
            if model:
                task.model = model

            cum_tokens = self.cumulative_tokens

            # 1. Hard Task Ceiling Check
            if task.total_tokens > self.max_task_tokens:
                task.active = False
                raise TokenFuseBreaker(
                    f"Task {task_id} exceeded hard limit ({task.total_tokens}/{self.max_task_tokens} tokens). Task halted."
                )

            # 2. Hard Session Ceiling Check
            if cum_tokens >= self.max_session_tokens:
                self.tripped = True
                self.trip_reason = f"Session hard limit exceeded ({cum_tokens}/{self.max_session_tokens} tokens)"
                for t in self.tasks.values():
                    t.active = False
                raise TokenFuseBreaker(self.trip_reason)

            # 3. Lyapunov Stability & Runaway Burn Detection
            v_val, v_dot, is_stable = self.compute_lyapunov_stability(self.global_velocity)
            if not is_stable:
                self.tripped = True
                self.trip_reason = (
                    f"Runaway Lyapunov divergence: V={v_val:.4f}, V_dot={v_dot:.4f} > 0 at "
                    f"{self.bucket_level / self.max_session_tokens * 100:.1f}% capacity. Tripping fuse."
                )
                for t in self.tasks.values():
                    t.active = False
                raise TokenFuseBreaker(self.trip_reason)

            warning_triggered = (cum_tokens >= self.max_session_tokens * self.warn_pct)
            entropy = self.compute_allocation_entropy()

            return {
                "task_tokens": task.total_tokens,
                "cumulative_tokens": cum_tokens,
                "bucket_level": round(self.bucket_level, 2),
                "global_velocity": round(self.global_velocity, 2),
                "lyapunov_v": round(v_val, 5),
                "lyapunov_v_dot": round(v_dot, 5),
                "allocation_entropy": round(entropy, 4),
                "warning_level": "HIGH" if warning_triggered else "NOMINAL",
                "fanout_allowed": not warning_triggered,
                "tripped": self.tripped
            }

    def close_task(self, task_id: str):
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].active = False

    def reset(self):
        with self._lock:
            self.tasks.clear()
            self.tripped = False
            self.trip_reason = ""
            self.bucket_level = 0.0
            self.last_leak_update = time.time()
            self.global_velocity = 0.0
