"""NouGen Human Translation Layer: technical to human-first response translation.

Preserves exact underlying facts, uncertainty, and machine state while translating
machine-centric jargon into concrete, picture-ready mental models.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple


@dataclass(frozen=True)
class TranslationResult:
    human_response: str
    technical_layer: Optional[str] = None
    preserved_facts: List[str] = None
    uncertainty_markers: List[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "human_response": self.human_response,
            "technical_layer": self.technical_layer,
            "preserved_facts": self.preserved_facts or [],
            "uncertainty_markers": self.uncertainty_markers or [],
        }


# High-frequency infrastructure and machine jargon translation patterns
JARGON_PATTERNS = [
    (
        r"(?i)\bfederated multi[- ]vault ingress with context[- ]aware routing\b",
        "three machines sharing one memory highway instead of each machine trying to be the highway",
    ),
    (
        r"(?i)\bdenial-of-service via thread starvation in event loop\b",
        "the door was locked because too many workers were stuck inside waiting on slow tasks",
    ),
    (
        r"(?i)\bHTTP 502 Bad Gateway\b",
        "the front door answered, but the service sitting behind it was unreachable or restarting",
    ),
    (
        r"(?i)\bHTTP 401 Unauthorized\b",
        "credential check failed: key missing, invalid, or mismatched",
    ),
    (
        r"(?i)\bHTTP 503 Service Unavailable\b",
        "service is intentionally refusing traffic (deny-by-default or unconfigured credentials)",
    ),
    (
        r"(?i)\bFTS5 full-text index synchronization\b",
        "refreshing the fast search index so new shards can be looked up immediately",
    ),
    (
        r"(?i)\breceiver-side non-interactive subprocess lifecycle termination\b",
        "process died when the background connection closed because it wasn't detached or run as a service",
    ),
]


def detect_uncertainty(text: str) -> List[str]:
    """Extract and preserve explicit uncertainty or unknown states."""
    markers = []
    patterns = [
        (r"(?i)\b(unknown|cannot determine|unreachable|partial coverage|timed out)\b", "uncertainty_state"),
        (r"(?i)\b(timeout after \d+[\.\d]*s?)\b", "deadline_timeout"),
        (r"(?i)\b(\d+ of \d+ (?:vaults|nodes|databases) (?:mounted|online|answering))\b", "partial_coverage"),
    ]
    for pat, label in patterns:
        for match in re.finditer(pat, text):
            markers.append(f"{label}:{match.group(0)}")
    return sorted(list(set(markers)))


def translate_to_human(
    raw_response: str,
    mode: str = "human_first",
    audience: str = "dave",
    preserve_technical: bool = True
) -> TranslationResult:
    """Translate raw machine/technical text into human-first explanations.
    
    Modes:
      - human_first: Conversational mental model first, with optional technical appendix.
      - dual_layer: Structured Human View + Technical Telemetry block.
      - technical_first: Raw technical readout with a concise plain-English TL;DR.
      - concise: Shortest 1-2 sentence human-readable takeaway.
    """
    cleaned = raw_response.strip()
    human_text = cleaned
    
    for pat, rep in JARGON_PATTERNS:
        human_text = re.sub(pat, rep, human_text)
        
    uncertainties = detect_uncertainty(cleaned)
    
    # Extract preserved technical terms (error codes, machine names, counts, latency)
    preserved = []
    codes = re.findall(r"\b(?:HTTP )?[1-5]\d{2}\b|\b(?:blade|phoebus|whoart|hyperion|apollo)\b|\b\d+\.?\d*ms|\b\d+\.?\d*s\b", cleaned, re.I)
    if codes:
        preserved.extend(list(set(codes)))

    if mode == "concise":
        lines = human_text.splitlines()
        first_line = lines[0] if lines else human_text
        return TranslationResult(
            human_response=first_line,
            technical_layer=cleaned if preserve_technical else None,
            preserved_facts=preserved,
            uncertainty_markers=uncertainties,
        )

    if mode == "dual_layer":
        return TranslationResult(
            human_response=human_text,
            technical_layer=cleaned,
            preserved_facts=preserved,
            uncertainty_markers=uncertainties,
        )

    # Default: human_first
    return TranslationResult(
        human_response=human_text,
        technical_layer=cleaned if (preserve_technical and human_text != cleaned) else None,
        preserved_facts=preserved,
        uncertainty_markers=uncertainties,
    )
