"""Hardcade Evidence Verifier & Combo Breaker Evaluator.

Implements the Hardcade evidence rules (Hops 2, 3, 4 from docs/hardcade-lexicon.md):
1. Evidence tuple mandatory: (claim, probe, node, observed).
2. Self-attestation forbidden: probe must not be the call that produced the result.
3. Observer-stamped node rule: `node` must be stamped by observer, never subject.
4. Credential de-duplication: observations sharing a credential count as ONE observation.
5. Two independent probes required for PERFECT.
6. Success-shaped failures MUST trigger COMBO BREAKER, never PERFECT.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class EvidenceTuple:
    claim: str
    probe: str
    node: str
    observed: Dict[str, Any]
    credential: Optional[str] = None
    observer: Optional[str] = None
    subject: Optional[str] = None


@dataclass
class EvaluationResult:
    verdict: str  # "PERFECT", "COMBO BREAKER", "GODLIKE", "DENIED", "INCOMPLETE"
    announcer_call: str
    hit_count: int
    breaker_hit_index: Optional[int] = None
    reasons: List[str] = field(default_factory=list)
    effective_observations: int = 0


def evaluate_hardcade_evidence(
    claim: str,
    evidence_list: List[EvidenceTuple],
    subject: Optional[str] = None,
    observer: Optional[str] = None
) -> EvaluationResult:
    """Evaluate a sequence of evidence tuples against the Hardcade Lexicon doctrine."""
    if not evidence_list:
        return EvaluationResult(
            verdict="INCOMPLETE",
            announcer_call="DENIED",
            hit_count=0,
            reasons=["No evidence tuples provided"]
        )

    distinct_credentials: Set[str] = set()
    distinct_observer_nodes: Set[str] = set()
    reasons: List[str] = []

    for idx, ev in enumerate(evidence_list, start=1):
        # Rule 1: Evidence tuple fields mandatory
        if not ev.claim or not ev.probe or not ev.node or ev.observed is None:
            return EvaluationResult(
                verdict="COMBO BREAKER",
                announcer_call="COMBO BREAKER",
                hit_count=idx,
                breaker_hit_index=idx,
                reasons=[f"Hit {idx}: Invalid evidence tuple. All 4 fields (claim, probe, node, observed) mandatory."]
            )

        # Rule 2 & 3: node is stamped by an OBSERVER, never by the subject.
        #
        # Identity verification is opt-IN, deliberately. The earlier form fell
        # back to trusting any node string that was not the literal
        # "self-reported", which made verification opt-OUT: a tuple was treated
        # as an independent observer unless it confessed otherwise. Two tuples
        # carrying ordinary hostnames and no observer at all - which is exactly
        # what NouGenMsg produces when a lane self-stamps NouGenMsg-<node> -
        # then scored 2 independent observations and reached GODLIKE, having
        # been stamped by nobody. A hostname is a claim about identity, not
        # evidence of it; the whole point of hop 4 is that the subject does not
        # get to assert who it is.
        #
        # So: corroborating identity requires an observer PRESENT and DISTINCT
        # from the subject. Everything else - absent observer, observer equal to
        # the subject, or the literal "self-reported" - is self-reported and can
        # never corroborate.
        # An explicit node="self-reported" is an admission and always wins, even
        # if an observer field is populated: a tuple that declares its identity
        # unverified must never be upgraded by metadata around it.
        subject_of = ev.subject or subject
        if ev.node != "self-reported" and ev.observer and ev.observer != subject_of:
            node_effective = ev.observer
            distinct_observer_nodes.add(node_effective)
        else:
            node_effective = "self-reported"

        # Rule 4: Credential deduplication
        if ev.credential:
            distinct_credentials.add(ev.credential)

        # Inspect observed payload for known success-shaped failure signatures
        obs = ev.observed
        # Check: empty body with status 200 (either in same tuple or across status + body probe pairs)
        if obs.get("body_length") == 0 and (obs.get("status_code") == 200 or any(e.observed.get("status_code") == 200 for e in evidence_list)):
            return EvaluationResult(
                verdict="COMBO BREAKER",
                announcer_call="COMBO BREAKER",
                hit_count=idx,
                breaker_hit_index=idx,
                reasons=[f"Hit {idx}: HTTP 200 with empty body (0 bytes) detected."]
            )

        # Check: degraded / timeout despite green status
        if obs.get("lanes_timed_out") or (obs.get("complete") is False and "elapsed_s" in obs):
            return EvaluationResult(
                verdict="COMBO BREAKER",
                announcer_call="COMBO BREAKER",
                hit_count=idx,
                breaker_hit_index=idx,
                reasons=[f"Hit {idx}: Underlying lane timed out or incomplete while claim asserted green."]
            )

        # Check: silent tool removal (zero tools)
        if obs.get("tools_count") == 0 and obs.get("expected_min", 0) > 0:
            return EvaluationResult(
                verdict="COMBO BREAKER",
                announcer_call="COMBO BREAKER",
                hit_count=idx,
                breaker_hit_index=idx,
                reasons=[f"Hit {idx}: Tools count is 0 (expected minimum {obs['expected_min']})."]
            )

        # Check: write committed into quarantined / unreadable db
        if obs.get("state") == "quarantined" or obs.get("readable") is False:
            return EvaluationResult(
                verdict="COMBO BREAKER",
                announcer_call="COMBO BREAKER",
                hit_count=idx,
                breaker_hit_index=idx,
                reasons=[f"Hit {idx}: Operation committed into a quarantined or unreadable database."]
            )

        # Check: stale claim vs live dead endpoint
        if obs.get("alive") is False or obs.get("connection_refused") is True:
            return EvaluationResult(
                verdict="COMBO BREAKER",
                announcer_call="COMBO BREAKER",
                hit_count=idx,
                breaker_hit_index=idx,
                reasons=[f"Hit {idx}: Live endpoint is down / connection refused."]
            )

        # Check: zero tools executed with high hallucinations
        if obs.get("tools_executed") == 0 and obs.get("hallucinated_answers", 0) > 0:
            return EvaluationResult(
                verdict="COMBO BREAKER",
                announcer_call="COMBO BREAKER",
                hit_count=idx,
                breaker_hit_index=idx,
                reasons=[f"Hit {idx}: Zero tools executed with {obs['hallucinated_answers']} hallucinations."]
            )

    # Corroboration verification.
    #
    # Hop 4 rule 1 (identity): a self-reported tuple can NEVER count toward
    # corroboration, no matter how many nodes the evidence names. Counting
    # distinct credentials alone let a self-reported tuple pair with one
    # verified tuple and reach 2 effective observations -- PERFECT on evidence
    # where only ONE party's identity was ever established. Independence is
    # bounded by the number of tuples whose identity was stamped by an OBSERVER,
    # and then de-duplicated by credential (hop 4 rule 2). Neither bound alone
    # is sufficient: credentials catch one actor wearing two hostnames, verified
    # identity catches one hostname vouching for itself.
    corroborating = len(distinct_observer_nodes)
    if distinct_credentials:
        corroborating = min(corroborating, len(distinct_credentials))
    effective_obs_count = corroborating
    
    # Check if all observations shared a single credential
    if len(evidence_list) > 1 and len(distinct_credentials) == 1:
        reasons.append("Observations share a single credential; counts as ONE observation.")
        effective_obs_count = 1

    # Check self-reported limitation. Report it whenever ANY tuple's identity was
    # self-reported, not only when every tuple was: a mixed set is exactly the
    # case that silently reached PERFECT before, and the caller needs to see why
    # its observation count is lower than the number of tuples it supplied.
    self_reported_count = sum(
        1 for ev in evidence_list
        if ev.node == "self-reported"
        or not (ev.observer and ev.observer != (ev.subject or subject))
    )
    if not distinct_observer_nodes or distinct_observer_nodes == {"self-reported"}:
        reasons.append("Identity is self-reported only; cannot provide independent corroboration.")
        effective_obs_count = min(effective_obs_count, 1)
    elif self_reported_count:
        reasons.append(
            f"{self_reported_count} of {len(evidence_list)} tuples are self-reported; "
            "they do not count toward corroboration."
        )

    if effective_obs_count >= 2 and len(evidence_list) >= 2:
        if len(distinct_observer_nodes) >= 2:
            return EvaluationResult(
                verdict="GODLIKE",
                announcer_call="GODLIKE",
                hit_count=len(evidence_list),
                effective_observations=effective_obs_count,
                reasons=["Fleet-wide green verified from 2+ independent nodes with distinct credentials."]
            )
        return EvaluationResult(
            verdict="PERFECT",
            announcer_call="PERFECT",
            hit_count=len(evidence_list),
            effective_observations=effective_obs_count,
            reasons=["End-to-end green verified from two independent probe premises."]
        )

    return EvaluationResult(
        verdict="INCOMPLETE",
        announcer_call="HEADSHOT" if len(evidence_list) == 1 else "DENIED",
        hit_count=len(evidence_list),
        effective_observations=effective_obs_count,
        reasons=reasons or ["Insufficient independent corroboration for PERFECT/GODLIKE."]
    )
