"""Hardcade Quota Alert Ladder & Provider Usage Telemetry Governor.

Implements the Hardcade quota ladder doctrine (Relay leg 20260906T224549Z, Shard 17922@db1):
Thresholds by percent USED:
  <60%: SILENT / GREEN (normal routing)
  60%:  HEADS UP (informational alert, normal routing)
  75%:  LOW AMMO (prefer cheaper/local routes)
  85%:  DANGER (restrict expensive reasoning, avoid starting long cloud jobs)
  90%:  RATION (discretionary cloud usage behaves as if only 1% remains)
  95%:  CONTINUE? (checkpoint state and prepare fallback)
  99%:  FINAL ROUND (closure-critical work only)
  100%: GAME OVER (bucket exhausted, TAG IN eligible fallback)

Events:
  RESET:       1UP (restores normal routing)
  BONUS:       EXTRA CONTINUE (temporary quota expansion)
  PAID OVERFLOW: INSERT COIN (only if owner explicitly enables it)

Requirements:
- Deduplicates alerts per provider/bucket.
- Reports provider, model, bucket_type, percent_used, reset_eta, active_work, recommended_route.
- Alters routing safely based on threshold level.
- Denominator provenance: metered, estimated, or unknown.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import enum
from typing import Dict, List, Optional, Tuple


class QuotaLevel(str, enum.Enum):
    GREEN = "GREEN"                 # <60%
    HEADS_UP = "HEADS_UP"           # 60%
    LOW_AMMO = "LOW_AMMO"           # 75%
    DANGER = "DANGER"               # 85%
    RATION = "RATION"               # 90%
    CONTINUE = "CONTINUE"           # 95%
    FINAL_ROUND = "FINAL_ROUND"     # 99%
    GAME_OVER = "GAME_OVER"         # 100%
    ONE_UP = "1UP"                  # Reset event
    EXTRA_CONTINUE = "EXTRA_CONTINUE"# Bonus event
    INSERT_COIN = "INSERT_COIN"     # Paid overflow


class DenominatorProvenance(str, enum.Enum):
    METERED = "metered"       # Exact API response or authoritative usage meter
    ESTIMATED = "estimated"   # Local heuristic or calculated inference
    UNKNOWN = "unknown"       # Missing or unverified


class RoutingDirective(str, enum.Enum):
    NORMAL = "NORMAL"                     # No restriction
    PREFER_LOCAL = "PREFER_LOCAL"         # Steer to Ollama / local Gemma
    RESTRICT_REASONING = "RESTRICT_REASONING" # Disallow deep reasoning/speculative branches
    RATION_CLOUD = "RATION_CLOUD"         # Severe cloud rationing
    CHECKPOINT_FALLBACK = "CHECKPOINT_FALLBACK" # Force checkpoint and stage fallback
    CLOSURE_ONLY = "CLOSURE_ONLY"         # Only work that immediately finalizes task
    TAG_IN_FALLBACK = "TAG_IN_FALLBACK"   # Hard-stop cloud bucket, fail over to fallback lane


@dataclass
class QuotaAlert:
    alert_id: str
    provider: str
    bucket: str
    percent_used: float
    level: QuotaLevel
    directive: RoutingDirective
    recommended_route: str
    provenance: DenominatorProvenance
    reset_eta: Optional[str] = None
    active_work: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged: bool = False


class QuotaGovernor:
    """Evaluates provider usage telemetry, deduplicates alerts, and determines routing directives."""

    def __init__(self, allow_paid_overflow: bool = False):
        self.allow_paid_overflow = allow_paid_overflow
        self._last_emitted_level: Dict[Tuple[str, str], QuotaLevel] = {}
        self._alert_history: List[QuotaAlert] = []

    def classify_percentage(self, percent_used: float) -> Tuple[QuotaLevel, RoutingDirective, str]:
        """Map percent used to QuotaLevel, RoutingDirective, and recommended route."""
        pct = max(0.0, float(percent_used))

        if pct >= 100.0:
            if self.allow_paid_overflow:
                return QuotaLevel.INSERT_COIN, RoutingDirective.NORMAL, "paid-overflow"
            return QuotaLevel.GAME_OVER, RoutingDirective.TAG_IN_FALLBACK, "ollama-local"
        elif pct >= 99.0:
            return QuotaLevel.FINAL_ROUND, RoutingDirective.CLOSURE_ONLY, "workers-ai"
        elif pct >= 95.0:
            return QuotaLevel.CONTINUE, RoutingDirective.CHECKPOINT_FALLBACK, "workers-ai"
        elif pct >= 90.0:
            return QuotaLevel.RATION, RoutingDirective.RATION_CLOUD, "openrouter-free"
        elif pct >= 85.0:
            return QuotaLevel.DANGER, RoutingDirective.RESTRICT_REASONING, "openrouter-free"
        elif pct >= 75.0:
            return QuotaLevel.LOW_AMMO, RoutingDirective.PREFER_LOCAL, "ollama-local"
        elif pct >= 60.0:
            return QuotaLevel.HEADS_UP, RoutingDirective.NORMAL, "standard-cloud"
        else:
            return QuotaLevel.GREEN, RoutingDirective.NORMAL, "standard-cloud"

    def evaluate_usage(
        self,
        provider: str,
        bucket: str,
        used: float,
        limit: Optional[float],
        provenance: DenominatorProvenance = DenominatorProvenance.METERED,
        reset_eta: Optional[str] = None,
        active_work: Optional[str] = None
    ) -> Optional[QuotaAlert]:
        """Evaluate current telemetry, returning a QuotaAlert if a threshold transition occurred."""
        key = (provider, bucket)

        if limit is None or limit <= 0:
            # Missing or invalid limit: honest UNKNOWN status
            pct = 0.0
            prov = DenominatorProvenance.UNKNOWN
            level = QuotaLevel.GREEN
            directive = RoutingDirective.NORMAL
            route = "standard-cloud"
        else:
            pct = (used / limit) * 100.0
            prov = provenance
            level, directive, route = self.classify_percentage(pct)

        last_level = self._last_emitted_level.get(key)

        # Check for 1UP Reset condition
        if last_level in (QuotaLevel.DANGER, QuotaLevel.RATION, QuotaLevel.CONTINUE, QuotaLevel.FINAL_ROUND, QuotaLevel.GAME_OVER) and level == QuotaLevel.GREEN:
            alert = QuotaAlert(
                alert_id=f"alert-{provider}-{bucket}-{int(datetime.now(timezone.utc).timestamp())}",
                provider=provider,
                bucket=bucket,
                percent_used=pct,
                level=QuotaLevel.ONE_UP,
                directive=RoutingDirective.NORMAL,
                recommended_route="standard-cloud",
                provenance=prov,
                reset_eta=reset_eta,
                active_work=active_work
            )
            self._last_emitted_level[key] = QuotaLevel.GREEN
            self._alert_history.append(alert)
            return alert

        # Deduplication: emit only on level changes or critical non-green thresholds
        if level != last_level and level != QuotaLevel.GREEN:
            alert = QuotaAlert(
                alert_id=f"alert-{provider}-{bucket}-{int(datetime.now(timezone.utc).timestamp())}",
                provider=provider,
                bucket=bucket,
                percent_used=pct,
                level=level,
                directive=directive,
                recommended_route=route,
                provenance=prov,
                reset_eta=reset_eta,
                active_work=active_work
            )
            self._last_emitted_level[key] = level
            self._alert_history.append(alert)
            return alert

        if level == QuotaLevel.GREEN:
            self._last_emitted_level[key] = QuotaLevel.GREEN

        return None

    def get_effective_directive(self, provider: str, bucket: str) -> RoutingDirective:
        """Get the active routing directive for a provider bucket."""
        level = self._last_emitted_level.get((provider, bucket), QuotaLevel.GREEN)
        if level == QuotaLevel.GAME_OVER:
            return RoutingDirective.TAG_IN_FALLBACK
        elif level == QuotaLevel.FINAL_ROUND:
            return RoutingDirective.CLOSURE_ONLY
        elif level == QuotaLevel.CONTINUE:
            return RoutingDirective.CHECKPOINT_FALLBACK
        elif level == QuotaLevel.RATION:
            return RoutingDirective.RATION_CLOUD
        elif level == QuotaLevel.DANGER:
            return RoutingDirective.RESTRICT_REASONING
        elif level == QuotaLevel.LOW_AMMO:
            return RoutingDirective.PREFER_LOCAL
        return RoutingDirective.NORMAL
