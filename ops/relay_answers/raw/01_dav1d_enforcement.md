<!-- route: hf-space-davewho-deepseek -->

```markdown
### (a) Deterministic Predicate Ladder
1. **PATH CONTAINMENT**: Compare claim scope against active work paths.
2. **SESSION ID**: Match session IDs for duplicate claims.
3. **GOAL**: Compare claim goals for logical equivalence.
4. **TIMESTAMP**: Check claim timestamps for staleness.
5. **EVIDENCE**: Verify presence of required evidence for critical claims.
6. **ERROR CODES**: Escalate repeated 4xx/5xx/52x errors.
7. **SHA/TESTS/TELEMETRY**: Reconcile contradictory assertions.
8. **DECISION TRAIL**: Ensure immutable audit trail.

### (b) Model Judgment Needed
- **Reconcile Contradictory Assertions**: Requires model judgment to interpret conflicting data against claims/SHAs/tests/telemetry/timestamps.

### (c) Claim Record Fields
- `session_id`
- `goal`
- `timestamp`
- `evidence`
- `error_codes`
- `SHA`
- `tests`
- `telemetry`
- `decision_trail`

### (d) Dedup Rule
Collapse claims with identical session ID, goal, and scope, retaining the earliest timestamp and latest SHA.

### (e) Smallest First Commit
```python
# src/nougen_shards/enforcement.py
def enforce_claim(claim):
    if claim['session_id'] == active_session and claim['goal'] == active_goal and claim['scope'] == active_scope:
        if claim['timestamp'] < active_timestamp:
            active_timestamp = claim['timestamp']
            active_SHA = claim['SHA']
        return False
    return True
```
```