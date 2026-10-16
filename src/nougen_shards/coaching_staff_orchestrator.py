# src/nougen_shards/coaching_staff_orchestrator.py
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class CoordinatorSeat(str, Enum):
    HEAD_COACH_ARGON = "antigravity:argon"         # Systems Topology & Master DAG
    DEFENSIVE_COORD_OPUS = "claude:opus"           # Formal Verification, Concurrency & Security Invariants
    SPECIAL_TEAMS_FABLE = "claude:fable"           # Schema Alignment, Protocol Bridges & Shard Compression
    OFFENSIVE_COORD_ASTRA = "chatgpt:astra"        # Deep Algorithmic Search & Symbolic Math Proofs
    TEMPO_COORD_SOL = "chatgpt:sol"                # Fast Tool Choreography & Live Fault Recovery


class SwarmPlayer(str, Enum):
    QB_KAEDRA = "phoebus:ollama:kaedracode"
    SAFETY_IRIS = "local:ollama:gemma4:e2b-qat"
    ANCHOR_DAV1D = "blade:ollama:dav1d:e2b"
    EDGE_QWEN = "cloudflare:qwen3-30b-a3b-fp8"
    FREE_ROUTER = "openrouter:free-router"


@dataclass(frozen=True)
class TaskSignal:
    goal: str
    domain_tags: List[str]
    structural_divergence_jsd: float
    cyclomatic_complexity: int
    concurrency_depth: int
    schema_surface_count: int
    algorithmic_depth: float
    latency_budget_ms: int
    local_fumble_streak: int


@dataclass(frozen=True)
class CoordinatorDirective:
    seat: CoordinatorSeat
    lineage_hash: str
    target_files: List[str]
    formal_invariants: List[str]
    ast_signature_map: Dict[str, List[str]]
    assigned_swarm_lanes: Dict[str, SwarmPlayer]
    verification_commands: List[str]
    confidence_weight: float


class EVIGatekeeper:
    """
    Expected Value of Information (EVI) Gatekeeper.
    Enforces the 99.99% free-lane law across the entire 5-model frontier booth.
    Computes which specific Coordinator Seat yields maximum entropy reduction per token.
    """

    def __init__(self, hard_cap_ratio: float = 0.0001):
        self.hard_cap_ratio = hard_cap_ratio
        self.free_swarm_tokens: int = 1_000_000  # Seed baseline for rolling window
        self.booth_tokens_by_seat: Dict[CoordinatorSeat, int] = {
            seat: 0 for seat in CoordinatorSeat
        }

    @property
    def total_booth_tokens(self) -> int:
        return sum(self.booth_tokens_by_seat.values())

    @property
    def current_free_ratio(self) -> float:
        total = self.free_swarm_tokens + self.total_booth_tokens
        return self.free_swarm_tokens / max(1, total)

    def record_usage(self, lane: str, tokens: int) -> None:
        matched_seat = next((s for s in CoordinatorSeat if s.value == lane), None)
        if matched_seat is not None:
            self.booth_tokens_by_seat[matched_seat] += tokens
        else:
            self.free_swarm_tokens += tokens

    def select_coordinator(self, signal: TaskSignal) -> Tuple[Optional[CoordinatorSeat], str]:
        """
        Returns None if the 99.99% local swarm should handle the play without waking the booth.
        Otherwise selects the exact specialized coordinator whose inductive bias fits the fault.
        """
        if signal.local_fumble_streak < 2 and signal.structural_divergence_jsd < 0.72:
            return None, "SWARM_AUTONOMOUS_EXECUTION"

        # Score each seat on orthogonal capability axes
        scores: Dict[CoordinatorSeat, float] = {
            CoordinatorSeat.HEAD_COACH_ARGON: (
                0.45 * signal.structural_divergence_jsd
                + 0.35 * min(1.0, len(signal.domain_tags) / 5.0)
                + 0.20 * (1.0 if "architecture" in signal.domain_tags else 0.0)
            ),
            CoordinatorSeat.DEFENSIVE_COORD_OPUS: (
                0.50 * min(1.0, signal.concurrency_depth / 4.0)
                + 0.30 * min(1.0, signal.cyclomatic_complexity / 40.0)
                + 0.20 * (1.0 if "security" in signal.domain_tags or "race" in signal.domain_tags else 0.0)
            ),
            CoordinatorSeat.SPECIAL_TEAMS_FABLE: (
                0.55 * min(1.0, signal.schema_surface_count / 6.0)
                + 0.45 * (1.0 if "protocol" in signal.domain_tags or "interface" in signal.domain_tags else 0.0)
            ),
            CoordinatorSeat.OFFENSIVE_COORD_ASTRA: (
                0.65 * signal.algorithmic_depth
                + 0.35 * (1.0 if "math" in signal.domain_tags or "optimization" in signal.domain_tags else 0.0)
            ),
            CoordinatorSeat.TEMPO_COORD_SOL: (
                0.60 * (1.0 if signal.latency_budget_ms <= 2500 else 0.1)
                + 0.40 * (1.0 if "relay" in signal.domain_tags or "hotfix" in signal.domain_tags else 0.0)
            ),
        }

        best_seat = max(scores, key=lambda s: scores[s])
        best_score = scores[best_seat]

        # Enforce strict 99.99% ratio unless local swarm is in confirmed deadlock
        if self.current_free_ratio < (1.0 - self.hard_cap_ratio) and signal.local_fumble_streak < 3:
            return None, f"BOOTH_CAP_GUARD (free_ratio={self.current_free_ratio:.6f})"

        if best_score < 0.55 and signal.local_fumble_streak < 3:
            return None, "BELOW_EVI_ACTIVATION_THRESHOLD"

        return best_seat, f"SUMMONED_{best_seat.name} (evi_score={best_score:.3f})"


class CrossBoothShadowCache:
    """
    SQLite FTS5 Cross-Booth Shadow Cache.
    Indexes every CoordinatorDirective by its normalized AST problem signature so
    isomorphic structural problems reuse frontier Hoare contracts at zero token cost.
    """

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS booth_directives (
                    signature_hash TEXT PRIMARY KEY,
                    seat TEXT NOT NULL,
                    lineage_hash TEXT NOT NULL,
                    normalized_ast_signature TEXT NOT NULL,
                    directive_json TEXT NOT NULL,
                    created_utc REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS booth_directives_fts USING fts5(
                    signature_hash UNINDEXED,
                    seat,
                    normalized_ast_signature,
                    formal_invariants_text
                )
                """
            )

    @staticmethod
    def compute_ast_signature_hash(ast_signature_map: Dict[str, List[str]]) -> Tuple[str, str]:
        normalized = json.dumps(
            {fn: list(args) for fn, args in sorted(ast_signature_map.items())},
            sort_keys=True,
            separators=(",", ":"),
        )
        sig_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
        return sig_hash, normalized

    def store(self, directive: CoordinatorDirective) -> str:
        sig_hash, normalized = self.compute_ast_signature_hash(directive.ast_signature_map)
        payload = {
            "seat": directive.seat.value,
            "lineage_hash": directive.lineage_hash,
            "target_files": directive.target_files,
            "formal_invariants": directive.formal_invariants,
            "ast_signature_map": directive.ast_signature_map,
            "assigned_swarm_lanes": {k: v.value for k, v in directive.assigned_swarm_lanes.items()},
            "verification_commands": directive.verification_commands,
            "confidence_weight": directive.confidence_weight,
        }
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO booth_directives
                (signature_hash, seat, lineage_hash, normalized_ast_signature, directive_json, created_utc)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    sig_hash,
                    directive.seat.value,
                    directive.lineage_hash,
                    normalized,
                    json.dumps(payload, sort_keys=True),
                    time.time(),
                ),
            )
            self._conn.execute(
                "DELETE FROM booth_directives_fts WHERE signature_hash = ?",
                (sig_hash,),
            )
            self._conn.execute(
                """
                INSERT INTO booth_directives_fts
                (signature_hash, seat, normalized_ast_signature, formal_invariants_text)
                VALUES (?, ?, ?, ?)
                """,
                (
                    sig_hash,
                    directive.seat.value,
                    normalized,
                    " ".join(directive.formal_invariants),
                ),
            )
        return sig_hash

    def lookup_isomorphic(
        self,
        ast_signature_map: Dict[str, List[str]],
        rebind_files: Optional[List[str]] = None,
    ) -> Optional[CoordinatorDirective]:
        sig_hash, _ = self.compute_ast_signature_hash(ast_signature_map)
        row = self._conn.execute(
            "SELECT directive_json FROM booth_directives WHERE signature_hash = ?",
            (sig_hash,),
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row["directive_json"])
        target_files = rebind_files if rebind_files is not None else data["target_files"]
        saved_lanes = [SwarmPlayer(v) for v in data["assigned_swarm_lanes"].values()]
        default_lane = saved_lanes[0] if saved_lanes else SwarmPlayer.QB_KAEDRA
        rebound_lanes = {
            f: SwarmPlayer(data["assigned_swarm_lanes"].get(f, default_lane.value))
            for f in target_files
        }
        return CoordinatorDirective(
            seat=CoordinatorSeat(data["seat"]),
            lineage_hash=data["lineage_hash"],
            target_files=target_files,
            formal_invariants=data["formal_invariants"],
            ast_signature_map=data["ast_signature_map"],
            assigned_swarm_lanes=rebound_lanes,
            verification_commands=data["verification_commands"],
            confidence_weight=float(data["confidence_weight"]),
        )


class CoachingStaffBooth:
    """
    Coordinates Argon, Claude Opus, Claude Fable, ChatGPT Astra, and ChatGPT Sol.
    Supports Single-Coordinator Play Calling, Dual-Coordinator Algebraic Synthesis,
    and Cross-Booth Shadow Cache lookup for zero-drift execution by the local/free swarm.
    """

    def __init__(
        self,
        gatekeeper: EVIGatekeeper,
        frontier_call_fn: Callable[[CoordinatorSeat, str, str], Tuple[str, int]],
        swarm_call_fn: Callable[[SwarmPlayer, str], Tuple[str, int]],
        sandbox_run_fn: Callable[[str], Tuple[int, str]],
        shadow_cache: Optional[CrossBoothShadowCache] = None,
    ):
        self.gatekeeper = gatekeeper
        self._call_frontier = frontier_call_fn
        self._call_swarm = swarm_call_fn
        self._run_sandbox = sandbox_run_fn
        self.shadow_cache = shadow_cache or CrossBoothShadowCache()

    def build_seat_system_prompt(self, seat: CoordinatorSeat) -> str:
        base_schema = (
            "Respond ONLY with valid JSON containing keys: "
            "'target_files' (list of str), 'formal_invariants' (list of str), "
            "'ast_signature_map' (dict mapping function_name -> list of arg names), "
            "'assigned_swarm_lanes' (dict mapping target_file -> swarm lane id), "
            "'verification_commands' (list of shell commands), 'confidence_weight' (float 0..1)."
        )
        role_directives = {
            CoordinatorSeat.HEAD_COACH_ARGON: (
                "You are Argon, Head Coach on Antigravity. Optimize global DAG topology, "
                "cross-node state lineage, and zero-bloqueo decoupling."
            ),
            CoordinatorSeat.DEFENSIVE_COORD_OPUS: (
                "You are Opus, Defensive Coordinator. Enforce strict memory safety, idempotency, "
                "deadlock elimination, and exhaustive edge-case postconditions."
            ),
            CoordinatorSeat.SPECIAL_TEAMS_FABLE: (
                "You are Fable, Special Teams Coordinator. Enforce clean API contracts, "
                "minimalist schema boundaries, and high-density telemetry serialization."
            ),
            CoordinatorSeat.OFFENSIVE_COORD_ASTRA: (
                "You are Astra, Offensive Coordinator. Synthesize optimal algorithmic complexity, "
                "tight asymptotic bounds, and exact symbolic verification assertions."
            ),
            CoordinatorSeat.TEMPO_COORD_SOL: (
                "You are Sol, Tempo Coordinator. Minimize execution hops, isolate fast-path "
                "circuit breakers, and produce immediate single-pass recovery commands."
            ),
        }
        return f"{role_directives[seat]} {base_schema}"

    def summon_coordinator(
        self, seat: CoordinatorSeat, compressed_state_json: str
    ) -> CoordinatorDirective:
        lineage_hash = hashlib.sha256(compressed_state_json.encode("utf-8")).hexdigest()[:16]
        sys_prompt = self.build_seat_system_prompt(seat)
        raw_out, tokens = self._call_frontier(seat, sys_prompt, compressed_state_json)
        self.gatekeeper.record_usage(seat.value, tokens)

        parsed = json.loads(raw_out)
        lane_map = {
            f: SwarmPlayer(lane_val)
            for f, lane_val in parsed.get("assigned_swarm_lanes", {}).items()
        }
        directive = CoordinatorDirective(
            seat=seat,
            lineage_hash=lineage_hash,
            target_files=parsed.get("target_files", []),
            formal_invariants=parsed.get("formal_invariants", []),
            ast_signature_map=parsed.get("ast_signature_map", {}),
            assigned_swarm_lanes=lane_map,
            verification_commands=parsed.get("verification_commands", []),
            confidence_weight=float(parsed.get("confidence_weight", 0.85)),
        )
        self.shadow_cache.store(directive)
        return directive

    def synthesize_dual_coordinator_directive(
        self,
        primary_seat: CoordinatorSeat,
        secondary_seat: CoordinatorSeat,
        compressed_state_json: str,
    ) -> CoordinatorDirective:
        """
        Used only on highest-stakes franchise forks (e.g. Argon + Opus or Astra + Opus).
        Merges their formal invariants and AST contracts algebraically without prose debate.
        """
        d1 = self.summon_coordinator(primary_seat, compressed_state_json)
        d2 = self.summon_coordinator(secondary_seat, compressed_state_json)

        merged_files = list(dict.fromkeys(d1.target_files + d2.target_files))
        merged_invariants = list(dict.fromkeys(d1.formal_invariants + d2.formal_invariants))
        merged_verifications = list(dict.fromkeys(d1.verification_commands + d2.verification_commands))

        # Primary seat wins AST signature ties unless secondary seat has strictly higher confidence
        merged_ast = dict(d2.ast_signature_map)
        if d1.confidence_weight >= d2.confidence_weight:
            merged_ast.update(d1.ast_signature_map)

        merged_lanes = dict(d2.assigned_swarm_lanes)
        merged_lanes.update(d1.assigned_swarm_lanes)

        merged_directive = CoordinatorDirective(
            seat=primary_seat,
            lineage_hash=d1.lineage_hash,
            target_files=merged_files,
            formal_invariants=merged_invariants,
            ast_signature_map=merged_ast,
            assigned_swarm_lanes=merged_lanes,
            verification_commands=merged_verifications,
            confidence_weight=round((d1.confidence_weight + d2.confidence_weight) / 2.0, 4),
        )
        self.shadow_cache.store(merged_directive)
        return merged_directive

    def run_field_execution(self, directive: CoordinatorDirective, context_slice: str) -> Dict[str, Any]:
        """Hands the compiled coordinator directive down to the 99.99% free swarm."""
        execution_log: List[Dict[str, Any]] = []

        for target_file in directive.target_files:
            player = directive.assigned_swarm_lanes.get(target_file, SwarmPlayer.QB_KAEDRA)
            worker_prompt = json.dumps({
                "target_file": target_file,
                "required_ast_signatures": directive.ast_signature_map,
                "invariants": directive.formal_invariants,
                "context": context_slice[:4000],
            })
            code_patch, tokens = self._call_swarm(player, worker_prompt)
            self.gatekeeper.record_usage(player.value, tokens)
            execution_log.append({
                "file": target_file,
                "player": player.value,
                "tokens": tokens,
                "patch_bytes": len(code_patch),
            })

        for cmd in directive.verification_commands:
            code, out = self._run_sandbox(cmd)
            if code != 0:
                return {
                    "status": "VERIFICATION_REJECTED",
                    "coordinator": directive.seat.value,
                    "failed_cmd": cmd,
                    "stderr_tail": out[-600:],
                    "free_ratio": round(self.gatekeeper.current_free_ratio, 6),
                }

        return {
            "status": "CHAMPIONSHIP_DRIVE_COMPLETE",
            "coordinator": directive.seat.value,
            "lineage": directive.lineage_hash,
            "files_updated": directive.target_files,
            "free_ratio": round(self.gatekeeper.current_free_ratio, 6),
            "execution_log": execution_log,
        }
