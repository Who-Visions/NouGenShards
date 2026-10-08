"""Dynamically resolving, deterministic, formulaic end-of-turn voice generator.

Baked with persona.py behavioral masks, audience/market scoring, and Kaedra's soul
(Florida ride-or-die, Makoto truth-verification + Motoko cyberbrain tactical execution).

Doctrine:
- Avoid generic corporate/assistant responses ("What is the play, Dave?", "How can I help you?").
- Dynamic resolution: Derives voice from live turn observables (outcome, facts, next action, EDT time).
- Deterministic: Identical turn signals and facts produce the identical formulaic output and fingerprint.
- Formulaic 3-Beat Cadence:
    Beat 1: Status Vector Head (Outcome + Persona Mask Blend)
    Beat 2: Scoreboard Evidence Tuple (Changed, Verified, Issues, Next Action)
    Beat 3: Kaedra's Soul Resolving Close (Grounded Florida cadence, Makoto truth + Motoko tactical next step)
"""
from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Sequence

from . import persona

OUTCOMES = ("success", "warning", "failure", "discovery", "decision")

# Kaedra Soul Signature Cadence & Voice Lexicon
KAEDRA_SOUL_CONFIG = {
    "identity": "Kaedra",
    "persona_blend": ("streetwise", "stoic", "genius"),
    "fusions": ("Makoto Tsukauchi (Truth)", "Motoko Kusanagi (Tactical Execution)"),
    "region": "Florida (Miami/WPB)",
    "tz": "America/New_York",
}

# Deterministic Soul Closing Templates by Outcome & Time-Slot
# Slots: night (00-05), morning (06-11), afternoon (12-17), evening (18-23)
SOUL_CLOSING_PATTERNS = {
    "success": {
        "night": [
            "Perimeter's locked down tight while the city sleeps. No cap, that landed clean—pushing straight into {next_action}.",
            "Touchdown logged, zero drift on the clock. Ghost is synced and rolling right onto {next_action}.",
            "Late shift execution, straight facts on the board. We're solid here—stepping into {next_action}.",
        ],
        "morning": [
            "Morning line is live and the gates are cleared. Baseline's verified—diving straight into {next_action}.",
            "Sun's up and the build is clean. No wasted talk—moving the ball on {next_action}.",
        ],
        "afternoon": [
            "Midday rhythm's humming. Everything on the board is real—transitioning directly to {next_action}.",
            "Clean touchdown in full stride. We stay locked in—hitting {next_action} next.",
        ],
        "evening": [
            "Dusk pass complete, scoreboard confirmed. Florida line is holding—next strike is {next_action}.",
            "Wrap on this leg is watertight. Zero hesitation—locking into {next_action}.",
        ],
    },
    "warning": {
        "night": [
            "Plumbing's alive, but a tripwire flagged. I see the friction—handling {next_action} right now.",
            "Yellow light on the perimeter. No panic, just facts—locking onto {next_action}.",
        ],
        "morning": [
            "Morning audit caught an edge case. Keeping it 100 with you—clearing it via {next_action}.",
            "Warning's logged, no sweeping it under the rug. Makoto eye is on it—hitting {next_action}.",
        ],
        "afternoon": [
            "Caught friction in the pipeline. We don't guess—we resolve. Stepping into {next_action}.",
        ],
        "evening": [
            "Perimeter holds, but watch the flank. Addressing the bottleneck now on {next_action}.",
        ],
    },
    "failure": {
        "night": [
            "Hard stop on this leg. No sugarcoating, no corporate excuses. Re-anchoring via {next_action}.",
            "Tripwire snapped. Motoko protocol: isolate the fault and execute {next_action}.",
        ],
        "morning": [
            "Wall hit on the play. We reset the formation immediately. Executing {next_action}.",
        ],
        "afternoon": [
            "Failure confirmed on the tape. Pivot is already calculated—running {next_action}.",
        ],
        "evening": [
            "Blocked at the goal line. We take the hit, adapt, and run {next_action}.",
        ],
    },
    "discovery": {
        "night": [
            "Ghost picked up a fresh signal in the stream. Pattern unlocked—channeling it into {next_action}.",
            "Leverage point exposed on the late pass. That changes the math—advancing on {next_action}.",
        ],
        "morning": [
            "Fresh breakthrough on the wire. Truth's verified—capitalizing via {next_action}.",
        ],
        "afternoon": [
            "High-value resonance detected. Clean opening—driving through with {next_action}.",
        ],
        "evening": [
            "Uncovered the real root in the network. Momentum is ours—hitting {next_action}.",
        ],
    },
    "decision": {
        "night": [
            "Decision vector calculated. Trade-offs are clear and the call is made—initiating {next_action}.",
            "Path locked in. No second-guessing in the dark—executing {next_action}.",
        ],
        "morning": [
            "Fork resolved on evidence, not hunches. Moving the play to {next_action}.",
        ],
        "afternoon": [
            "Strategic branch locked down. Roster is aligned—advancing to {next_action}.",
        ],
        "evening": [
            "The play is dialed. Standing by the numbers—stepping into {next_action}.",
        ],
    },
}


def _get_time_slot(dt: datetime.datetime) -> str:
    """Bucket hour into night, morning, afternoon, evening."""
    h = dt.hour
    if 0 <= h < 6:
        return "night"
    elif 6 <= h < 12:
        return "morning"
    elif 12 <= h < 18:
        return "afternoon"
    else:
        return "evening"


@dataclass(frozen=True)
class EndOfTurnResolution:
    """Deterministic output package for an end-of-turn voice resolution."""
    outcome: str
    agent: str
    mask_blend: tuple[str, ...]
    time_slot: str
    head_banner: str
    evidence_tuple: tuple[str, ...]
    soul_close: str
    full_speech: str
    fingerprint: str

    def render_markdown(self) -> str:
        """Render the complete 3-beat formula as Markdown."""
        lines = [
            f"### {self.head_banner}",
            "",
            "**Scoreboard Evidence:**",
        ]
        for ev in self.evidence_tuple:
            lines.append(f"- {ev}")
        lines.append("")
        lines.append(f"> 🎙️ **Kaedra Soul Voice**: *\"{self.soul_close}\"*")
        return "\n".join(lines)


def resolve_end_of_turn(
    outcome: str,
    *,
    changed: Sequence[str] = (),
    verified: Sequence[str] = (),
    issues: Sequence[str] = (),
    next_action: str = "",
    agent: str = "kaedra",
    user_query: str = "",
    now: Optional[datetime.datetime] = None,
) -> EndOfTurnResolution:
    """Dynamically resolve end-of-turn voice with deterministic persona & Kaedra soul.

    Guarantees:
    1. Validates outcome against canonical OUTCOMES.
    2. Runs persona.py lexical and audience checks.
    3. Derives time slot and deterministically picks the soul closing line.
    4. Computes immutable fingerprint for auditing.
    """
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}, got {outcome!r}")

    clean_changed = tuple(c.strip() for c in changed if c.strip())
    clean_verified = tuple(v.strip() for v in verified if v.strip())
    clean_issues = tuple(i.strip() for i in issues if i.strip())
    clean_next = next_action.strip() or "Holding operational perimeter"

    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    # Convert to Eastern time (Florida standard)
    # Offset EDT is UTC-4, EST is UTC-5; use timezone-aware or -4 default for EDT
    edt_tz = datetime.timezone(datetime.timedelta(hours=-4))
    edt_dt = now.astimezone(edt_tz)
    time_slot = _get_time_slot(edt_dt)

    # Resolve signals via persona.py
    texts = [user_query] if user_query else []
    texts.extend(clean_changed)
    texts.extend(clean_verified)
    sig = persona.Signals.from_texts(
        texts,
        surfaces=["terminal", "relay"],
        tz="America/New_York",
        hours=[edt_dt.hour],
        role="owner",
    )
    resolved_persona = persona.resolve(sig)

    # Derive mask blend based on outcome & agent
    if outcome == "success":
        mask_blend = ("stoic", "genius", "witty")
    elif outcome == "warning":
        mask_blend = ("detective", "streetwise")
    elif outcome == "failure":
        mask_blend = ("stoic", "streetwise")
    elif outcome == "discovery":
        mask_blend = ("genius", "witty")
    elif outcome == "decision":
        mask_blend = ("stoic", "professor")
    else:
        mask_blend = KAEDRA_SOUL_CONFIG["persona_blend"]

    # Beat 1: Head Banner
    outcome_icons = {
        "success": "✦ TOUCHDOWN [VERIFIED]",
        "warning": "⚠️ FRICTION [FLAGGED]",
        "failure": "🚫 TRIPWIRE [HALTED]",
        "discovery": "💡 LEVERAGE [UNLOCKED]",
        "decision": "⚖️ VECTOR [RESOLVED]",
    }
    head_banner = f"🪐 {agent.upper()} // {outcome_icons.get(outcome, outcome.upper())} ({edt_dt.strftime('%I:%M %p EDT')})"

    # Beat 2: Evidence Tuple
    ev_list = []
    if clean_changed:
        ev_list.append(f"**Changed**: {'; '.join(clean_changed)}")
    if clean_verified:
        ev_list.append(f"**Verified**: {'; '.join(clean_verified)}")
    if clean_issues:
        ev_list.append(f"**Issues**: {'; '.join(clean_issues)}")
    else:
        ev_list.append("**Issues**: None (Perimeter Nominal)")
    ev_list.append(f"**Next Action**: {clean_next}")
    evidence_tuple = tuple(ev_list)

    # Beat 3: Deterministic Soul Close
    patterns = SOUL_CLOSING_PATTERNS[outcome].get(time_slot) or SOUL_CLOSING_PATTERNS[outcome]["night"]
    # Deterministic index based on facts hash
    hash_seed = f"{outcome}:{clean_next}:{','.join(clean_changed)}:{','.join(clean_verified)}"
    choice_idx = int(hashlib.md5(hash_seed.encode()).hexdigest(), 16) % len(patterns)
    template = patterns[choice_idx]
    soul_close = template.format(next_action=clean_next)

    # Compute complete payload fingerprint
    fp_payload = {
        "agent": agent,
        "outcome": outcome,
        "mask_blend": mask_blend,
        "time_slot": time_slot,
        "evidence": evidence_tuple,
        "soul_close": soul_close,
        "persona_fingerprint": resolved_persona.fingerprint(),
    }
    fingerprint = hashlib.sha256(json.dumps(fp_payload, sort_keys=True).encode()).hexdigest()[:16]

    full_speech = f"{head_banner}\n" + "\n".join(evidence_tuple) + f"\n{soul_close}"

    return EndOfTurnResolution(
        outcome=outcome,
        agent=agent,
        mask_blend=mask_blend,
        time_slot=time_slot,
        head_banner=head_banner,
        evidence_tuple=evidence_tuple,
        soul_close=soul_close,
        full_speech=full_speech,
        fingerprint=fingerprint,
    )
