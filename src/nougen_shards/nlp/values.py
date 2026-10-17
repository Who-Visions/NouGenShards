"""
NouGenMorph NLP Engine — Module 2: Values Hierarchy & 5-Driver Matrix.

Provenance:
- Source: Christopher Howard, Breakthrough to Success (CD 4: The Internal Compass & Workbook)
- War-Gamed & Drafted By: Free Fleet Lane (`ollama-cloud-aiwithdav3`) + Local `gemma4:e2b-qat`
- Reviewed By: Antigravity Coach (UDCT Architecture Solver)
"""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple


DRIVER_CATALOG: Dict[str, Dict[str, Any]] = {
    "freedom": {
        "persona": "Frank",
        "need": "Freedom",
        "reward": "Options / Adventure / Autonomy",
        "stressor": "Restriction / Micromanagement",
        "keywords": ("freedom", "autonomy", "adventure", "options", "choice", "independence", "flexibility", "explore", "fast", "unbounded"),
    },
    "security": {
        "persona": "Sally",
        "need": "Security",
        "reward": "Assurance / Plans / Stability",
        "stressor": "Chaos / Uncertainty",
        "keywords": ("security", "safety", "stability", "plan", "assurance", "certainty", "reliable", "deterministic", "backup", "hardening", "trust"),
    },
    "belonging": {
        "persona": "Bob",
        "need": "Belonging",
        "reward": "Inclusion / Team / Connection",
        "stressor": "Rejection / Isolation",
        "keywords": ("belonging", "team", "family", "connection", "community", "love", "mesh", "fleet", "harmony", "collaboration", "relationship"),
    },
    "competency": {
        "persona": "Cecil",
        "need": "Competency",
        "reward": "Validation / Value / Mastery",
        "stressor": "Disrespect / Incompetence",
        "keywords": ("competency", "mastery", "excellence", "achievement", "success", "wealth", "revenue", "roi", "skill", "intelligence", "growth", "results"),
    },
    "self_expression": {
        "persona": "Dwayne",
        "need": "Self-Expression",
        "reward": "Uniqueness / Craft / Identity",
        "stressor": "Average / Mediocrity",
        "keywords": ("expression", "creativity", "uniqueness", "originality", "art", "vision", "design", "style", "innovation", "distinction", "voice"),
    },
}

AWAY_FROM_PATTERNS = re.compile(
    r"\b(not|never|avoid|prevent|escape|fear|pain|loss|debt|failure|stress|chaos|rejection|poverty|crash|bug|outage)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValueEntry:
    """Single elicited value with polarity, driver mapping, and ordinal rank."""

    name: str
    rank: int
    polarity: str  # "TOWARDS" or "AWAY_FROM"
    driver_key: str
    persona: str
    weight: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "rank": self.rank,
            "polarity": self.polarity,
            "driver_key": self.driver_key,
            "persona": self.persona,
            "weight": round(self.weight, 4),
        }


@dataclass(frozen=True)
class ValueConflictResolution:
    """Deterministic resolution between two competing values."""

    primary: ValueEntry
    secondary: ValueEntry
    conflict_type: str
    integration_frame: str
    aligned: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary": self.primary.to_dict(),
            "secondary": self.secondary.to_dict(),
            "conflict_type": self.conflict_type,
            "integration_frame": self.integration_frame,
            "aligned": self.aligned,
        }


class ValuesMatrix:
    """
    Christopher Howard CD 4 Values Elicitation, Ranking, and 5-Driver Alignment Engine.
    """

    def classify_polarity(self, statement: str) -> str:
        """Classify whether a value expression is motivated TOWARDS pleasure/goals or AWAY_FROM pain."""
        text = (statement or "").strip()
        if not text:
            return "TOWARDS"
        if AWAY_FROM_PATTERNS.search(text):
            return "AWAY_FROM"
        return "TOWARDS"

    def map_driver(self, value_text: str) -> Tuple[str, str]:
        """Map any value string to one of the 5 canonical NLP drivers (Frank, Sally, Bob, Cecil, Dwayne)."""
        lowered = (value_text or "").lower()
        best_key = "competency"
        best_hits = 0
        for d_key, meta in DRIVER_CATALOG.items():
            hits = sum(1 for kw in meta["keywords"] if kw in lowered)
            if hits > best_hits:
                best_hits = hits
                best_key = d_key
        return best_key, DRIVER_CATALOG[best_key]["persona"]

    def build_hierarchy(
        self,
        raw_values: Sequence[str],
        pairwise_wins: Optional[Dict[str, int]] = None,
    ) -> List[ValueEntry]:
        """
        Build an ordinal numbered hierarchy (1..N) from elicited values.
        Uses explicit pairwise comparison wins when provided (CD 4: 'How to Number Your Values'),
        breaking ties deterministically by original elicitation order.
        """
        cleaned: List[str] = []
        seen = set()
        for v in raw_values:
            s = (v or "").strip()
            if s and s.lower() not in seen:
                cleaned.append(s)
                seen.add(s.lower())

        if not cleaned:
            return []

        wins = pairwise_wins or {}
        indexed = list(enumerate(cleaned))
        # Sort by pairwise wins descending, then original index ascending
        indexed.sort(key=lambda item: (-wins.get(item[1], len(cleaned) - item[0]), item[0]))

        total = len(indexed)
        hierarchy: List[ValueEntry] = []
        for rank_idx, (_, val_str) in enumerate(indexed, start=1):
            polarity = self.classify_polarity(val_str)
            driver_key, persona = self.map_driver(val_str)
            weight = (total - rank_idx + 1) / float(total)
            hierarchy.append(
                ValueEntry(
                    name=val_str,
                    rank=rank_idx,
                    polarity=polarity,
                    driver_key=driver_key,
                    persona=persona,
                    weight=weight,
                )
            )
        return hierarchy

    def reframe_away_from(self, value_entry: ValueEntry) -> ValueEntry:
        """Transform an AWAY_FROM value into a TOWARDS value while preserving its rank and driver."""
        if value_entry.polarity == "TOWARDS":
            return value_entry
        cleaned = AWAY_FROM_PATTERNS.sub("", value_entry.name).strip(" -_,.;:")
        driver_meta = DRIVER_CATALOG.get(value_entry.driver_key, DRIVER_CATALOG["competency"])
        positive_name = f"{driver_meta['need']} ({cleaned})" if cleaned else driver_meta["need"]
        return ValueEntry(
            name=positive_name,
            rank=value_entry.rank,
            polarity="TOWARDS",
            driver_key=value_entry.driver_key,
            persona=value_entry.persona,
            weight=value_entry.weight,
        )

    def resolve_conflict(self, val_a: ValueEntry, val_b: ValueEntry) -> ValueConflictResolution:
        """
        Resolve a conflict between two values using ordinal rank precedence and driver synthesis.
        """
        primary, secondary = (val_a, val_b) if val_a.rank <= val_b.rank else (val_b, val_a)

        pair_drivers = {primary.driver_key, secondary.driver_key}
        if pair_drivers == {"freedom", "security"}:
            conflict_type = "AUTONOMY_VS_CERTAINTY"
        elif primary.polarity != secondary.polarity:
            conflict_type = "POLARITY_SPLIT_TOWARDS_VS_AWAY"
        elif primary.driver_key == secondary.driver_key:
            conflict_type = "INTRA_DRIVER_REDUNDANCY"
        else:
            conflict_type = "ORDINAL_PRECEDENCE_ALIGNMENT"

        frame = (
            f"Honor #{primary.rank} '{primary.name}' ({primary.persona}/{primary.driver_key}) as the governing constraint, "
            f"and fulfill #{secondary.rank} '{secondary.name}' ({secondary.persona}/{secondary.driver_key}) as its supporting vehicle."
        )
        return ValueConflictResolution(
            primary=primary,
            secondary=secondary,
            conflict_type=conflict_type,
            integration_frame=frame,
            aligned=True,
        )
